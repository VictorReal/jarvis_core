"""
doctor_module.py — Doctor JARVIS Lvl1 (advisory самодіагностика).

Принцип (Lvl1 = тільки порада, БЕЗ автозмін коду):
  • Ловить помилки з двох джерел:
      1. КРАШІ — необроблені винятки (sys.excepthook + threading.excepthook).
         → запис у logs/errors.log + миттєва коротка нотифікація (без LLM).
      2. ТИХІ помилки — усі logger.error(...) по коду (logging.Handler).
         → лише запис у logs/errors.log (без нотифікації, щоб не спамити).
  • На команду "продіагностуй / що зламалось" → diagnose():
      бере ОСТАННІЙ запис з errors.log, дістає файл+рядок з traceback,
      підтягує ±15 рядків коду (з фільтром секретів і заборонених шляхів),
      + хвіст денного логу → LLM → коротка порада.

Безпека: код у LLM віддається тільки з .py; шляхи з .gitignore (env, data,
json, csv, md, logs, token/credentials) НЕ читаються; рядки, схожі на
секрети, вирізаються.
"""

import os
import re
import sys
import logging
import traceback
import threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

ERRORS_LOG = Path("logs/errors.log")
GITIGNORE = Path(".gitignore")
CODE_CONTEXT_LINES = 15          # ±рядків коду навколо місця помилки
LOG_TAIL_CHARS = 1500            # скільки хвоста денного логу додати в контекст

# Дефолтні заборони (якщо .gitignore нема/порожній) — щоб код-читач
# ніколи не чіпав секрети/дані навіть без gitignore.
_DEFAULT_DENY = {".env", "data/", "logs/", "token.json", "credentials.json",
                 "api_usage.json", ".cache"}
_DENY_EXT = {".json", ".csv", ".md", ".mp3", ".env"}

# Рядки, схожі на секрети — вирізаємо перед відправкою коду в LLM.
_SECRET_RE = re.compile(
    r'(?i)(key|token|secret|password|passwd|api[_-]?key|access[_-]?key|'
    r'bearer|authorization)\s*[=:]\s*["\']?[\w\-./+]{8,}'
)


class DoctorModule:
    def __init__(self, llm=None, notify_cb=None, hud_cb=None):
        """
        llm        — LLM для діагнозу (self.llm з агента), ставиться пізніше set_llm
        notify_cb  — функція нотифікації (Telegram), напр. telegram.notify_owner
        hud_cb     — функція в HUD Activity, напр. hud_module.log_activity
        """
        self._llm = llm
        self._notify = notify_cb
        self._hud = hud_cb
        self._deny = self._load_gitignore_denies()

    def set_llm(self, llm):
        self._llm = llm

    # ------------------------------------------------------------------ #
    #  Заборонені шляхи (з .gitignore)
    # ------------------------------------------------------------------ #

    def _load_gitignore_denies(self) -> set:
        """Читає .gitignore → набір патернів, код з яких НЕ віддаємо в LLM."""
        denies = set(_DEFAULT_DENY)
        try:
            if GITIGNORE.exists():
                for line in GITIGNORE.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip().lstrip("\ufeff")  # прибрати BOM
                    if line and not line.startswith("#"):
                        denies.add(line)
        except Exception as e:
            logger.debug(f"[DOCTOR] gitignore read error: {e}")
        return denies

    def _is_path_blocked(self, path: str) -> bool:
        """True якщо шлях підпадає під заборону (секрети/дані)."""
        p = path.replace("\\", "/").lower()
        # розширення
        if Path(p).suffix in _DENY_EXT:
            return True
        # патерни з gitignore
        for pat in self._deny:
            pat = pat.replace("\\", "/").lower().rstrip("/")
            if not pat:
                continue
            # каталог (data/ → блокуємо все всередині) або файл
            if pat in p or p.endswith(pat):
                return True
        return False

    # ------------------------------------------------------------------ #
    #  Хуки на помилки (краші + тихі)
    # ------------------------------------------------------------------ #

    def install_hooks(self):
        """Ставить глобальні хуки. Викликати раз при старті JARVIS."""
        ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)

        # 1) Необроблені винятки головного потоку → КРАШ
        _prev_hook = sys.excepthook

        def _excepthook(exc_type, exc_value, exc_tb):
            self._record_crash(exc_type, exc_value, exc_tb)
            _prev_hook(exc_type, exc_value, exc_tb)  # лишаємо стандартний вивід

        sys.excepthook = _excepthook

        # 2) Необроблені винятки у тредах (Python 3.8+)
        def _thread_hook(args):
            self._record_crash(args.exc_type, args.exc_value, args.exc_traceback,
                               thread=getattr(args, "thread", None))

        try:
            threading.excepthook = _thread_hook
        except Exception:
            pass

        # 3) Тихі помилки — усе, що йде через logger.error(...)
        self._attach_logging_handler()

        logger.info("[DOCTOR] Хуки встановлено (краші + тихі помилки)")

    def _attach_logging_handler(self):
        """Handler рівня ERROR — ловить усі logger.error по коду в errors.log."""
        doctor = self

        class _DoctorHandler(logging.Handler):
            def emit(self, record):
                try:
                    if record.levelno < logging.ERROR:
                        return
                    msg = record.getMessage()
                    tb = ""
                    if record.exc_info:
                        tb = "".join(traceback.format_exception(*record.exc_info))
                    doctor._append_log(
                        kind="SILENT",
                        header=f"{record.name}: {msg}",
                        body=tb,
                    )
                except Exception:
                    pass  # хендлер ніколи не має крашити сам

        h = _DoctorHandler()
        h.setLevel(logging.ERROR)
        logging.getLogger().addHandler(h)  # root logger

    # ------------------------------------------------------------------ #
    #  Запис помилок
    # ------------------------------------------------------------------ #

    def _record_crash(self, exc_type, exc_value, exc_tb, thread=None):
        """Краш: пишемо повний traceback + миттєва коротка нотифікація."""
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        module = self._guess_module(exc_tb)
        where = f" in {module}" if module else ""
        self._append_log(kind="CRASH", header=f"{exc_type.__name__}: {exc_value}",
                         body=tb_text)

        # Миттєва коротка нотифікація (БЕЗ LLM)
        short = f"Sir, a fault occurred{where}. Say 'diagnose' for analysis."
        self._send_notify(short)
        self._send_hud(f"Fault{where}: {exc_type.__name__}")

    def _append_log(self, kind: str, header: str, body: str):
        """Дописує запис у errors.log."""
        try:
            ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(ERRORS_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n===== [{kind}] {ts} =====\n{header}\n{body}\n")
        except Exception as e:
            logger.debug(f"[DOCTOR] append_log error: {e}")

    def _guess_module(self, exc_tb) -> str:
        """Назва файлу останнього кадру стека (де реально впало)."""
        try:
            frames = traceback.extract_tb(exc_tb)
            if frames:
                return Path(frames[-1].filename).name
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------ #
    #  Діагноз на команду
    # ------------------------------------------------------------------ #

    def _read_last_error(self) -> str:
        """Останній блок з errors.log (між роздільниками =====)."""
        try:
            if not ERRORS_LOG.exists():
                return ""
            text = ERRORS_LOG.read_text(encoding="utf-8", errors="ignore")
            blocks = re.split(r"\n=====\s", text)
            for b in reversed(blocks):
                if b.strip():
                    return "===== " + b.strip()
            return ""
        except Exception as e:
            logger.debug(f"[DOCTOR] read_last_error: {e}")
            return ""

    def _extract_frame(self, tb_text: str):
        """З traceback дістає (шлях, рядок) останнього кадру 'File "...", line N'."""
        matches = re.findall(r'File "([^"]+)", line (\d+)', tb_text)
        if not matches:
            return None, None
        path, lineno = matches[-1]
        return path, int(lineno)

    def _read_code_safely(self, path: str, lineno: int) -> str:
        """±CODE_CONTEXT_LINES навколо рядка. Блокує заборонені шляхи,
        вирізає рядки-секрети. Повертає текст або причину відмови."""
        # читаємо лише .py і лише з нашого проєкту, не з .venv/бібліотек
        norm = path.replace("\\", "/")
        if "/.venv/" in norm or "/site-packages/" in norm or "lib/python" in norm.lower():
            return "(code from external library — skipped)"
        if not norm.endswith(".py"):
            return "(non-python or unknown file — code skipped)"
        if self._is_path_blocked(norm):
            return "(file is gitignored/sensitive — code not shared)"
        try:
            p = Path(path)
            if not p.exists():
                return "(source file not found)"
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            start = max(0, lineno - 1 - CODE_CONTEXT_LINES)
            end = min(len(lines), lineno + CODE_CONTEXT_LINES)
            snippet = []
            for i in range(start, end):
                raw = lines[i]
                # вирізаємо рядки, схожі на секрети
                if _SECRET_RE.search(raw):
                    raw = re.sub(r'(["\']?[\w\-./+]{8,}["\']?)\s*$', '<REDACTED>', raw)
                marker = ">>" if (i + 1) == lineno else "  "
                snippet.append(f"{marker} {i+1}: {raw}")
            return "\n".join(snippet)
        except Exception as e:
            return f"(could not read code: {e})"

    def _tail_day_log(self) -> str:
        """Хвіст сьогоднішнього денного логу — для контексту, що робив юзер."""
        try:
            path = Path("logs") / f"{datetime.now().strftime('%Y-%m-%d')}.md"
            if not path.exists():
                return ""
            text = path.read_text(encoding="utf-8", errors="ignore")
            return text[-LOG_TAIL_CHARS:]
        except Exception:
            return ""

    def diagnose(self) -> str:
        """Головний метод: аналізує останній краш/помилку → порада від LLM."""
        err = self._read_last_error()
        if not err:
            return "Sir, no faults are recorded. All systems nominal."

        path, lineno = self._extract_frame(err)
        code_ctx = ""
        if path and lineno:
            code_ctx = self._read_code_safely(path, lineno)

        if self._llm is None:
            # без LLM — хоча б повідомимо суть
            first = err.splitlines()[:4]
            return "Sir, fault recorded: " + " ".join(first)

        day_log = self._tail_day_log()
        prompt = (
            "You are JARVIS running a self-diagnostic. Below is the most recent error "
            "from the system, the relevant code around the failure, and recent activity. "
            "Explain in 2-3 short spoken sentences: what likely went wrong and what to try. "
            "Be specific and practical. Do NOT output code blocks — this will be spoken aloud. "
            "Address the user as 'Sir'.\n\n"
            f"=== ERROR ===\n{err[:2000]}\n\n"
            f"=== CODE AROUND FAILURE ===\n{code_ctx[:1500]}\n\n"
            f"=== RECENT ACTIVITY ===\n{day_log[:800]}\n"
        )
        try:
            from langchain_core.messages import HumanMessage
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            advice = (resp.content or "").strip().replace("*", "").replace("#", "")
            if not advice:
                advice = "Sir, I analysed the fault but couldn't form a clear conclusion."
            # дублюємо у HUD + Telegram
            self._send_hud("Diagnosis ready")
            self._send_notify("[JARVIS Doctor] " + advice)
            return advice
        except Exception as e:
            logger.error(f"[DOCTOR] diagnose LLM error: {e}")
            return "Sir, my diagnostic subsystem itself failed to respond."

    # ------------------------------------------------------------------ #
    #  Вивід
    # ------------------------------------------------------------------ #

    def _send_notify(self, text: str):
        if self._notify:
            try:
                self._notify(text)
            except Exception as e:
                logger.debug(f"[DOCTOR] notify error: {e}")

    def _send_hud(self, text: str):
        if self._hud:
            try:
                self._hud(text, kind="warning")
            except Exception as e:
                logger.debug(f"[DOCTOR] hud error: {e}")


# ── Singleton ────────────────────────────────────────────────────────────────
_doctor = None

def get_doctor(llm=None, notify_cb=None, hud_cb=None) -> "DoctorModule":
    global _doctor
    if _doctor is None:
        _doctor = DoctorModule(llm=llm, notify_cb=notify_cb, hud_cb=hud_cb)
    else:
        if llm is not None:
            _doctor.set_llm(llm)
        if notify_cb is not None:
            _doctor._notify = notify_cb
        if hud_cb is not None:
            _doctor._hud = hud_cb
    return _doctor
