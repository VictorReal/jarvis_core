import platform
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

class MusicModule:
    def __init__(self):
        scope = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=os.getenv("SPOTIPY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
            scope=scope,
            open_browser=False 
        ))

    def _ensure_spotify_is_running(self):
    #"""Перевіряє чи запущено Spotify — тільки на Windows."""
        if platform.system() != "Windows":
            return True  # на Linux/Mac не перевіряємо — Spotify запускається інакше
        
        try:
            output = subprocess.check_output('tasklist', shell=True).decode('cp1251')
            if "Spotify.exe" not in output:
                print("[DEBUG] Spotify не виявлено. Спроба автозапуску...")
                spotify_path = os.path.expandvars(r"%AppData%\Spotify\Spotify.exe")
                if os.path.exists(spotify_path):
                    os.startfile(spotify_path)
                    print("[DEBUG] Очікування ініціалізації пристрою (5 сек)...")
                    time.sleep(5)
                    return True
                else:
                    print("[DEBUG] Помилка: Шлях до Spotify не знайдено.")
                    return False
        except Exception as e:
            print(f"[DEBUG] Помилка перевірки процесу: {e}")
        return True

    # --- НОВИЙ МЕТОД: КЕРУВАННЯ ГУЧНІСТЮ ---
    def set_volume(self, volume_percent):
        """Змінює гучність, якщо є активний пристрій, ігноруючи помилки 404"""
        try:
            devices = self.sp.devices()
            if not devices['devices']:
                return False # Немає пристроїв — нічого не робимо, мовчки
            
            # Шукаємо активний пристрій для зміни гучності
            active_list = [d for d in devices['devices'] if d['is_active']]
            device_id = active_list[0]['id'] if active_list else devices['devices'][0]['id']
            
            self.sp.volume(volume_percent, device_id=device_id)
            return True
        except Exception:
            # Якщо Spotify API все одно "брикається" (404), просто ігноруємо
            return False

    def play(self, search_query=None):
        try:
            self._ensure_spotify_is_running()
            devices = self.sp.devices()

            if not devices['devices']:
                return "ERROR|No active Spotify device found."

            active_list = [d for d in devices['devices'] if d['is_active']]
            device_id = active_list[0]['id'] if active_list else devices['devices'][0]['id']

            if search_query:
                blacklist = ["karaoke", "cover", "tribute", "made popular", "originally"]

                # Крок 1: пряме комбіноване search — трек + артист разом
                direct = self.sp.search(q=search_query, limit=10, type='track')
                direct_tracks = [
                    t for t in direct['tracks']['items']
                    if not any(b in t['name'].lower() for b in blacklist)
                    and not any(b in t['artists'][0]['name'].lower() for b in blacklist)
                ]
                if direct_tracks:
                    best = max(direct_tracks, key=lambda t: t.get('popularity', 0))
                    self.sp.start_playback(device_id=device_id, uris=[best['uri']])
                    return f"PLAYING|{best['artists'][0]['name']} - {best['name']}"

                # Крок 2: якщо прямий пошук не дав результату — шукаємо тільки артиста
                words = search_query.split()
                for n in range(len(words), 0, -1):
                    artist_query = " ".join(words[:n])
                    artist_results = self.sp.search(
                        q="artist:" + artist_query,
                        limit=5,
                        type='artist'
                    )
                    items = artist_results['artists']['items']
                    if items:
                        best_artist = max(items, key=lambda a: a.get('popularity', 0))
                        self.sp.start_playback(device_id=device_id, context_uri=best_artist['uri'])
                        return f"PLAYING|{best_artist['name']}'s top tracks"

                return f"ERROR|Sir, I couldn't find '{search_query}'"

            self.sp.start_playback(device_id=device_id)
            return "RESUMING|Music"

        except Exception as e:
            if "404" in str(e):
                return "ERROR|No active playback session. Open Spotify on your device."
            return f"ERROR|Audio System Error: {str(e)}"

    def stop(self):
        try:
            self.sp.pause_playback()
            return "As you wish, Sir. Silence restored."
        except Exception:
            return "The audio streams are already silent, Sir."

    def _active_device_id(self):
        """Повертає id активного (або першого доступного) пристрою, або None."""
        try:
            devices = self.sp.devices().get("devices", [])
            if not devices:
                return None
            active = [d for d in devices if d.get("is_active")]
            return (active[0] if active else devices[0])["id"]
        except Exception:
            return None

    def pause(self):
        """Пауза (для HUD-кнопки)."""
        try:
            did = self._active_device_id()
            self.sp.pause_playback(device_id=did)
            return "PAUSED|Silence restored"
        except Exception:
            return "The audio streams are already silent, Sir."

    def resume(self):
        """Відновити відтворення на активному пристрої."""
        did = self._active_device_id()
        if not did:
            return "ERROR|No active Spotify device. Open Spotify and play something first."
        try:
            self.sp.start_playback(device_id=did)
            return "RESUMING|Music"
        except Exception as e:
            es = str(e)
            if "403" in es or "Restriction" in es:
                return ("ERROR|Nothing to resume. Spotify needs an active track first "
                        "(press play once in the app), Sir.")
            if "404" in es:
                return "ERROR|No active playback session."
            return f"ERROR|{e}"

    def is_playing(self) -> bool:
        """Чи грає зараз музика."""
        try:
            pb = self.sp.current_playback()
            return bool(pb and pb.get("is_playing"))
        except Exception:
            return False

    def toggle(self):
        """Перемикає play/pause залежно від поточного стану."""
        if self.is_playing():
            return self.pause()
        return self.resume()

    def next_track(self):
        """Наступний трек."""
        try:
            did = self._active_device_id()
            self.sp.next_track(device_id=did)
            return "NEXT|Skipped to next track"
        except Exception as e:
            return f"ERROR|{e}"

    def previous_track(self):
        """Попередній трек."""
        try:
            did = self._active_device_id()
            self.sp.previous_track(device_id=did)
            return "PREV|Back to previous track"
        except Exception as e:
            return f"ERROR|{e}"