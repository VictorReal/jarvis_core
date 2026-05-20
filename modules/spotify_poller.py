"""
spotify_poller.py — Фоновий Spotify polling для JARVIS HUD
Оновлює: поточний трек, гучність, стан паузи — кожні 2 сек
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)


class SpotifyPoller:
    def __init__(self, music_module, poll_interval: int = 2):
        self._sp = music_module.sp
        self._interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None

        self._last_track = None
        self._last_volume = None
        self._last_is_playing = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SpotifyPoller")
        self._thread.start()
        logger.info("[POLLER] Spotify polling запущено")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval + 1)
        logger.info("[POLLER] Spotify polling зупинено")

    def _loop(self):
        while self._running:
            try:
                self._poll()
            except Exception as e:
                logger.debug(f"[POLLER] Помилка запиту: {e}")
            time.sleep(self._interval)

    def _poll(self):
        current = self._sp.current_playback()

        if not current or not current.get("item"):
            if self._last_track is not None or self._last_is_playing:
                self._last_track = None
                self._last_is_playing = False
                self._last_volume = None
                # Скидаємо все одним emit — включно з прогресом
                try:
                    from modules.hud_module import socketio
                    socketio.emit('state_update', {
                        'current_song': 'No music playing',
                        'is_playing': False,
                        'volume': 0,
                        'track_progress': 0,
                        'track_duration': 0,
                    })
                except Exception:
                    pass
            return

        item = current["item"]
        artist = item["artists"][0]["name"] if item.get("artists") else "Unknown"
        track = item["name"]
        full_name = f"{artist} - {track}"
        volume = current.get("device", {}).get("volume_percent", 0)
        is_playing = current.get("is_playing", False)

        if full_name != self._last_track:
            self._last_track = full_name
            self._update_hud("current_song", full_name)
            logger.debug(f"[POLLER] Трек: {full_name}")

        if volume != self._last_volume:
            self._last_volume = volume
            self._update_hud("volume", volume)

        if is_playing != self._last_is_playing:
            self._last_is_playing = is_playing
            self._update_hud("is_playing", is_playing)

        # Прогрес — надсилаємо завжди (змінюється кожну секунду)
        progress_ms = current.get("progress_ms") or 0
        duration_ms = item.get("duration_ms") or 0
        self._update_hud_progress(progress_ms, duration_ms, is_playing)

    def _update_hud_progress(self, progress_ms: int, duration_ms: int, is_playing: bool):
        """Надсилає прогрес і тривалість одним emit'ом."""
        try:
            from modules.hud_module import socketio, hud_state
            socketio.emit('state_update', {
                'track_progress': progress_ms,
                'track_duration': duration_ms,
                'is_playing': is_playing,
            })
        except Exception:
            pass

    def _update_hud(self, key: str, value):
        try:
            from modules.hud_module import update_hud
            update_hud(key, value)
        except Exception:
            pass