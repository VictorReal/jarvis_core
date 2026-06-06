"""
rag_module.py — семантичний пошук по щоденних логах JARVIS (RAG).

Принцип:
  • Логи logs/YYYY-MM-DD.md → розбиваються на обміни (### час + SIR + JARVIS)
  • Кожен обмін → embedding (sentence-transformers, multilingual)
  • Вектори → ChromaDB (локальна, persist у data/rag_db)
  • Запит → embedding → top-k схожих обмінів → контекст для LLM

LAZY: модель і БД вантажаться лише при першому запиті (не при старті JARVIS),
щоб не вішати систему на 16GB RAM.

Залежності: pip install sentence-transformers chromadb
"""

import os
import re
import logging
import threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

LOGS_DIR = Path("logs")
DB_DIR = Path("data/rag_db")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION = "jarvis_logs"
TOP_K = 5


class RAGModule:
    def __init__(self):
        self._model = None          # lazy
        self._client = None         # lazy
        self._collection = None     # lazy
        self._ready = False
        self._loading = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Lazy-ініціалізація (модель + БД вантажаться при першому запиті)
    # ------------------------------------------------------------------ #

    def _ensure_loaded(self) -> bool:
        """Вантажить модель і БД при першому виклику. True якщо готово."""
        if self._ready:
            return True
        with self._lock:
            if self._ready:
                return True
            if self._loading:
                return False
            self._loading = True
        try:
            logger.info("[RAG] Завантаження моделі embeddings (перший запит)...")
            from sentence_transformers import SentenceTransformer
            import chromadb

            self._model = SentenceTransformer(MODEL_NAME)
            DB_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(DB_DIR))
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            logger.info("[RAG] Модель і БД готові")
            return True
        except ImportError:
            logger.error("[RAG] Встановіть: pip install sentence-transformers chromadb")
            return False
        except Exception as e:
            logger.error(f"[RAG] Помилка ініціалізації: {e}")
            return False
        finally:
            self._loading = False

    # ------------------------------------------------------------------ #
    #  Парсинг логів → обміни
    # ------------------------------------------------------------------ #

    def _parse_log_file(self, path: Path) -> list[dict]:
        """Розбиває один лог-файл на обміни. Кожен: {id, text, date, time}."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return []

        date_str = path.stem  # YYYY-MM-DD
        exchanges = []
        # розбиваємо за маркером "### HH:MM:SS"
        blocks = re.split(r"\n###\s+", content)
        for block in blocks:
            block = block.strip()
            if not block or block.startswith("# JARVIS Log"):
                continue
            # перший рядок — час
            lines = block.split("\n", 1)
            time_str = lines[0].strip() if lines else ""
            body = lines[1] if len(lines) > 1 else block
            # витягуємо SIR / JARVIS
            sir = re.search(r"\*\*SIR:\*\*\s*(.+?)(?=\n\*\*|\Z)", body, re.DOTALL)
            jarvis = re.search(r"\*\*JARVIS:\*\*\s*(.+?)(?=\n\*\*|\Z)", body, re.DOTALL)
            sir_t = sir.group(1).strip() if sir else ""
            jarvis_t = jarvis.group(1).strip() if jarvis else ""
            if not sir_t and not jarvis_t:
                continue
            text = f"SIR: {sir_t}\nJARVIS: {jarvis_t}".strip()
            exchanges.append({
                "id": f"{date_str}_{time_str}",
                "text": text,
                "date": date_str,
                "time": time_str,
            })
        return exchanges

    def _all_exchanges(self) -> list[dict]:
        """Усі обміни з усіх лог-файлів."""
        if not LOGS_DIR.exists():
            return []
        out = []
        for path in sorted(LOGS_DIR.glob("*.md")):
            out.extend(self._parse_log_file(path))
        return out

    # ------------------------------------------------------------------ #
    #  Індексація
    # ------------------------------------------------------------------ #

    def reindex(self) -> str:
        """Перебудовує індекс з усіх логів. Повертає статус-рядок."""
        if not self._ensure_loaded():
            return "RAG offline (install sentence-transformers + chromadb)"

        exchanges = self._all_exchanges()
        if not exchanges:
            return "No logs to index, Sir."

        # які id вже в БД — додаємо лише нові (інкрементально)
        try:
            existing = set(self._collection.get(include=[])["ids"])
        except Exception:
            existing = set()

        new = [e for e in exchanges if e["id"] not in existing]
        if not new:
            return f"Index up to date ({len(exchanges)} exchanges), Sir."

        texts = [e["text"] for e in new]
        embeddings = self._model.encode(texts, show_progress_bar=False).tolist()
        self._collection.add(
            ids=[e["id"] for e in new],
            embeddings=embeddings,
            documents=texts,
            metadatas=[{"date": e["date"], "time": e["time"]} for e in new],
        )
        logger.info(f"[RAG] Проіндексовано {len(new)} нових обмінів")
        return f"Indexed {len(new)} new exchanges ({len(exchanges)} total), Sir."

    # ------------------------------------------------------------------ #
    #  Пошук
    # ------------------------------------------------------------------ #

    def search(self, query: str, k: int = TOP_K) -> list[dict]:
        """Семантичний пошук. Повертає [{text, date, time, score}]."""
        if not self._ensure_loaded():
            return []
        # автоіндексація при першому пошуку (якщо порожньо)
        try:
            count = self._collection.count()
        except Exception:
            count = 0
        if count == 0:
            self.reindex()

        try:
            q_emb = self._model.encode([query]).tolist()
            res = self._collection.query(query_embeddings=q_emb, n_results=k)
            out = []
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0]
            for doc, meta, dist in zip(docs, metas, dists):
                out.append({
                    "text": doc,
                    "date": meta.get("date", ""),
                    "time": meta.get("time", ""),
                    "score": round(1 - dist, 3),  # cosine dist → similarity
                })
            return out
        except Exception as e:
            logger.error(f"[RAG] search error: {e}")
            return []

    def search_as_context(self, query: str, k: int = TOP_K) -> str:
        """Форматує знайдене як контекст для LLM."""
        results = self.search(query, k)
        if not results:
            return ""
        lines = ["Relevant past conversations from your logs:"]
        for r in results:
            lines.append(f"[{r['date']} {r['time']}] {r['text']}")
        return "\n\n".join(lines)


# ── Lazy singleton ──────────────────────────────────────────────────────────
_rag_instance = None

def get_rag() -> "RAGModule":
    """Повертає єдиний екземпляр RAG (lazy). Модель вантажиться при першому search."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGModule()
    return _rag_instance