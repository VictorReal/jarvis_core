"""
ticker_module.py — дані для бігучої стрічки JARVIS.

Джерела (кешуються на сервері, стрічка крутить кеш — анімація не робить запитів):
  • Курси валют USD/UAH, EUR/UAH — bank.gov.ua (НБУ), БЕЗ ключа
  • Біткойн BTC/USD — CoinGecko, БЕЗ ключа
  • Акції (NVDA, MSFT, AAPL, GOOGL, TSLA, AMZN) — Finnhub, потрібен FINNHUB_KEY (free)
  • Новини (топ) — NewsAPI, потрібен NEWSAPI_KEY (free)

Інтервали оновлення (щоб вкластись у безкоштовні ліміти):
  • валюти: 60 хв   • крипта: 10 хв   • акції: раз на день   • новини: 60 хв
"""

import os
import time
import logging
import threading
import requests

logger = logging.getLogger(__name__)

STOCKS = ["NVDA", "MSFT", "AAPL", "GOOGL", "TSLA", "AMZN"]

# інтервали (секунди)
INTERVAL_FX = 3600
INTERVAL_CRYPTO = 600
INTERVAL_STOCKS = 86400
INTERVAL_NEWS = 3600

# Українські RSS-джерела (без ключа)
UA_RSS = [
    "https://www.pravda.com.ua/rss/",
    "https://suspilne.media/rss/all.rss",
    "https://nv.ua/ukr/rss/all.xml",
]
UA_NEWS_LIMIT = 8        # скільки UA-заголовків брати сумарно


class TickerModule:
    def __init__(self):
        self._news_key = os.getenv("NEWSAPI_KEY")
        self._finnhub_key = os.getenv("FINNHUB_KEY")
        self._cache = {
            "fx": [],        # [{symbol, value}]
            "crypto": [],    # [{symbol, value, change}]
            "stocks": [],    # [{symbol, value, change}]
            "news": [],      # [str]
        }
        self._last = {"fx": 0, "crypto": 0, "stocks": 0, "news": 0}
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="Ticker").start()
        logger.info("[TICKER] Запущено")

    def stop(self):
        self._running = False

    def _loop(self):
        # перше оновлення одразу
        while self._running:
            now = time.time()
            try:
                if now - self._last["fx"] >= INTERVAL_FX:
                    self._update_fx(); self._last["fx"] = now
                if now - self._last["crypto"] >= INTERVAL_CRYPTO:
                    self._update_crypto(); self._last["crypto"] = now
                if now - self._last["stocks"] >= INTERVAL_STOCKS:
                    self._update_stocks(); self._last["stocks"] = now
                if now - self._last["news"] >= INTERVAL_NEWS:
                    self._update_news(); self._last["news"] = now
                self._emit()
            except Exception as e:
                logger.warning(f"[TICKER] loop error: {e}")
            time.sleep(60)

    # ------------------------------------------------------------------ #
    #  Джерела
    # ------------------------------------------------------------------ #

    def _update_fx(self):
        """Курси НБУ (без ключа)."""
        try:
            r = requests.get(
                "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json",
                timeout=10
            )
            data = r.json()
            wanted = {"USD": "USD/UAH", "EUR": "EUR/UAH"}
            out = []
            for item in data:
                cc = item.get("cc")
                if cc in wanted:
                    out.append({"symbol": wanted[cc], "value": f"{item.get('rate'):.2f}"})
            if out:
                with self._lock:
                    self._cache["fx"] = out
                logger.info(f"[TICKER] FX оновлено: {out}")
        except Exception as e:
            logger.info(f"[TICKER] FX error: {e}")

    def _update_crypto(self):
        """BTC через CoinGecko (без ключа)."""
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "usd",
                        "include_24hr_change": "true"},
                timeout=10
            )
            d = r.json().get("bitcoin", {})
            price = d.get("usd")
            change = d.get("usd_24h_change", 0)
            if price:
                with self._lock:
                    self._cache["crypto"] = [{
                        "symbol": "BTC",
                        "value": f"${price:,.0f}",
                        "change": round(change, 1),
                    }]
        except Exception as e:
            logger.info(f"[TICKER] crypto error: {e}")

    def _update_stocks(self):
        """Акції через Finnhub (потрібен ключ)."""
        if not self._finnhub_key:
            return
        out = []
        for sym in STOCKS:
            try:
                r = requests.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": sym, "token": self._finnhub_key},
                    timeout=10
                )
                q = r.json()
                price = q.get("c")        # current
                pct = q.get("dp")         # percent change
                if price:
                    out.append({
                        "symbol": sym,
                        "value": f"${price:,.2f}",
                        "change": round(pct, 1) if pct is not None else 0,
                    })
                time.sleep(0.3)           # не спамити
            except Exception as e:
                logger.info(f"[TICKER] stock {sym} error: {e}")
        if out:
            with self._lock:
                self._cache["stocks"] = out
            logger.info(f"[TICKER] Акції оновлено ({len(out)})")

    def _update_news(self):
        """UA RSS (перші) + світові NewsAPI."""
        ua = self._fetch_ua_rss()
        world = self._fetch_world_news()
        heads = ua + world           # українські першими
        if heads:
            with self._lock:
                self._cache["news"] = heads
            logger.info(f"[TICKER] Новини оновлено: {len(ua)} UA + {len(world)} світ")

    def _fetch_ua_rss(self) -> list:
        """Українські новини через RSS (без ключа). Потрібен feedparser."""
        try:
            import feedparser
        except ImportError:
            logger.info("[TICKER] feedparser не встановлено — UA новини пропущено")
            return []
        out = []
        per_source = max(2, UA_NEWS_LIMIT // len(UA_RSS))
        for url in UA_RSS:
            try:
                feed = feedparser.parse(url)
                src_name = (feed.feed.get("title") or "").split("|")[0].strip()
                for entry in feed.entries[:per_source]:
                    title = (entry.get("title") or "").strip()
                    if title:
                        out.append(f"{title} — {src_name}" if src_name else title)
            except Exception as e:
                logger.info(f"[TICKER] UA RSS error ({url}): {e}")
        return out[:UA_NEWS_LIMIT]

    def _fetch_world_news(self) -> list:
        """Світові новини через NewsAPI (потрібен ключ)."""
        if not self._news_key:
            return []
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"language": "en", "pageSize": 10, "apiKey": self._news_key},
                timeout=10
            )
            arts = r.json().get("articles", [])
            heads = []
            for a in arts:
                title = (a.get("title") or "").strip()
                src = (a.get("source", {}) or {}).get("name", "")
                if not title:
                    continue
                if src and src.lower() not in title.lower():
                    heads.append(f"{title} — {src}")
                else:
                    heads.append(title)
            return heads
        except Exception as e:
            logger.info(f"[TICKER] world news error: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Віддача
    # ------------------------------------------------------------------ #

    def get_data(self) -> dict:
        with self._lock:
            return {
                "finance": self._cache["fx"] + self._cache["crypto"] + self._cache["stocks"],
                "news": list(self._cache["news"]),
            }

    def _emit(self):
        try:
            from modules.hud_module import update_ticker
            update_ticker(self.get_data())
        except Exception as e:
            logger.debug(f"[TICKER] emit error: {e}")