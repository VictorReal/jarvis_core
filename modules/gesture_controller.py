"""
gesture_controller.py — Жести → дії JARVIS.

Опитує CameraVision у власному треді й виконує дію в момент,
коли жест ВПЕВНЕНО з'явився (а не поки тримається).

Режими:
  • normal — жести працюють штатно
  • sleep  — вхід кулаком (fist): музика стоп, ігнор УСІХ жестів крім peace.
             peace → пробудження (wake scene) + вихід у normal.
  • focus  — вхід/вихід жестом ok: ігнор УСІХ жестів крім ok.
             Щоб працювати за ноутом і не ловити випадкові рухи як команди.
             Музику НЕ чіпає. Голосове підтвердження "focus mode on/off".

Захист від хаосу:
  • STABLE_FRAMES — жест має протриматись N опитувань поспіль (відсіює мигання)
  • cooldown      — між діями пауза (одна рука = одна дія, не потік)
  • тригер по зміні — дія раз на появу жесту, повтор лише після 'none'/іншого жесту

Вивід тихий: HUD activity-лог. Голос — лише де доречно (режими, пробудження).
camera_vision лишається чистим (тільки бачить) — дії живуть тут.
"""

import threading
import time
from datetime import datetime
from pathlib import Path


# ── Конфіг ─────────────────────────────────────────────────────────────
POLL_SEC      = 0.1     # як часто опитуємо стан зору
STABLE_FRAMES = 4       # скільки опитувань поспіль жест має бути стабільним
COOLDOWN_SEC  = 1.5     # мін. пауза між діями
SNAPSHOT_DIR  = Path("logs/snapshots")


class GestureController:
    def __init__(self, camera_vision, music_module, hud_callback=None,
                 speak_callback=None, wake_callback=None, sleep_callback=None,
                 mouse_controller=None, media_callback=None):
        """
        camera_vision  — CameraVision (get_state / get_jpeg)
        music_module   — MusicModule (toggle/stop/next_track)
        hud_callback   — log_activity(text, kind), опційно
        speak_callback — safe_speak(text), опційно (підтвердження режимів)
        wake_callback  — функція пробудження зі sleep (wake scene), опційно
        sleep_callback — справжній sleep_mode JARVIS (затемнення/гучність/STANDBY)
        """
        self._cam   = camera_vision
        self._music = music_module
        self._hud   = hud_callback
        self._speak = speak_callback
        self._wake  = wake_callback
        self._sleep = sleep_callback
        self._mouse = mouse_controller
        self._media = media_callback   # маршрутизація медіа у фронт (YouTube/Spotify)

        # Стан pinch-гучності (аналоговий жест)
        self._vol_pinch_active = False
        self._vol_start_y = None    # висота руки на старті pinch
        self._vol_start_val = None  # гучність на старті pinch

        self._running = False
        self._thread  = None

        # Стан розпізнавання
        self._candidate   = "none"
        self._stable_cnt  = 0
        self._last_action_gesture = "none"
        self._last_action_time    = 0.0

        # Режим: "normal" | "sleep" | "focus" | "mouse"
        # Старт у FOCUS: жести вимкнені за замовчуванням, щоб випадкові рухи
        # не спрацьовували. Свідоме увімкнення/вимкнення — жестом ok.
        self._mode = "focus"

        # Дії в НОРМАЛЬНОМУ режимі (fist/ok/peace — окремо, бо особлива логіка)
        self._actions = {
            "open_palm": ("Pause/Play", lambda: self._media_action("toggle", self._music.toggle)),
            "hand_2":    ("Next track", self._music.next_track),
            "four":      ("Previous track", self._music.previous_track),
        }

    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            print("[GESTURE] Вже запущено")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="GestureController")
        self._thread.start()
        print("[GESTURE] Запущено")

    def stop(self):
        self._running = False
        print("[GESTURE] Зупинено")

    # ── Синхронізація стану з рештою JARVIS ──────────────────────────
    # Викликати, коли sleep/wake стався НЕ через жест (текст, голос, HUD),
    # щоб режим контролера не розсинхронізувався.

    def notify_woke(self):
        """Зовнішнє пробудження (текст 'wake up', daddy's home тощо)."""
        if self._mode == "sleep":
            self._mode = "normal"
            self._last_action_gesture = "none"
            print("[GESTURE] Режим скинуто в normal (зовнішнє пробудження)")

    def notify_slept(self):
        """Зовнішнє засинання (текст 'good night' тощо)."""
        self._mode = "sleep"
        self._last_action_gesture = "none"
        print("[GESTURE] Режим встановлено sleep (зовнішня команда)")

    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            time.sleep(POLL_SEC)
            try:
                self._tick()
            except Exception as e:
                print(f"[GESTURE] tick error: {e}")

    def _tick(self):
        state = self._cam.get_state()
        if not state.get("fresh") or state.get("hands", 0) == 0:
            self._candidate = "none"
            self._stable_cnt = 0
            self._last_action_gesture = "none"
            self._end_volume_pinch()   # рука зникла — завершуємо pinch-гучність
            return

        gesture = state.get("gesture", "none")

        # ── pinch-гучність (аналогово, лише в normal) ──
        # Тримаєш pinch + рух вгору=гучніше / вниз=тихіше. Обробляємо
        # безперервно ДО дискретної логіки й виходимо, поки тримається pinch.
        if self._mode == "normal":
            if gesture == "pinch":
                self._handle_volume_pinch(state)
                return
            else:
                self._end_volume_pinch()

        # Стабільність кандидата
        if gesture == self._candidate:
            self._stable_cnt += 1
        else:
            self._candidate = gesture
            self._stable_cnt = 1
        if self._stable_cnt < STABLE_FRAMES:
            return

        # Той самий жест уже спрацював і рука не зникала
        if gesture == self._last_action_gesture:
            return

        # Cooldown
        now = time.time()
        if now - self._last_action_time < COOLDOWN_SEC:
            return

        # ── Маршрутизація за режимом ──
        if self._mode == "sleep":
            handled = self._handle_sleep(gesture)
        elif self._mode == "focus":
            handled = self._handle_focus(gesture)
        elif self._mode == "mouse":
            handled = self._handle_mouse(gesture)
        else:
            handled = self._handle_normal(gesture)

        if handled:
            self._last_action_gesture = gesture
            self._last_action_time = now

    # ------------------------------------------------------------------ #
    #  Режим NORMAL
    # ------------------------------------------------------------------ #

    def _handle_mouse(self, gesture: str) -> bool:
        # У курсор-режимі реагуємо лише на fist (вихід).
        # Рух/клік курсора робить сам MouseController у своєму треді.
        if gesture == "fist":
            self._mode = "normal"
            if self._mouse:
                self._mouse.deactivate()
            return True
        return False

    def _media_action(self, action: str, music_fallback):
        """Медіа-дія: якщо є media_callback — шлемо у фронт (там вирішується
        YouTube чи Spotify). Інакше — прямий виклик music_module."""
        if self._media:
            try:
                self._media(action)
                return
            except Exception as e:
                print(f"[GESTURE] media_callback error: {e}")
        # fallback — прямо в музику
        try:
            music_fallback()
        except Exception as e:
            print(f"[GESTURE] music error: {e}")

    def _handle_volume_pinch(self, state):
        """Аналогова гучність: тримаєш pinch, рух руки вгору=гучніше/вниз=тихіше.
        Стартова точка фіксується на початку pinch; далі гучність = старт + зсув."""
        xy = state.get("index_xy")
        if not xy:
            return
        y = xy[1]   # 0 (верх кадру) .. 1 (низ)

        if not self._vol_pinch_active:
            # старт pinch — фіксуємо точку відліку й поточну гучність
            self._vol_pinch_active = True
            self._vol_start_y = y
            cur = None
            try:
                cur = self._music._current_volume()
            except Exception:
                pass
            self._vol_start_val = cur if cur is not None else 50
            self._log("Volume control (pinch)", kind="info")
            return

        # зсув по вертикалі: вгору (y менше) = гучніше. Коеф. 150 → повний хід руки ~міняє на 100%.
        delta = (self._vol_start_y - y) * 200
        new_vol = int(max(0, min(100, self._vol_start_val + delta)))
        # throttle: не частіше ніж раз на 0.3с і лише при зміні (бережемо Spotify API)
        now = time.time()
        last_t = getattr(self, "_vol_last_t", 0)
        last_v = getattr(self, "_vol_last_v", None)
        if now - last_t < 0.3 or new_vol == last_v:
            return
        self._vol_last_t = now
        self._vol_last_v = new_vol
        try:
            self._music.set_volume(new_vol)
        except Exception as e:
            print(f"[GESTURE] volume error: {e}")

    def _end_volume_pinch(self):
        """Завершення pinch-гучності (відпустив щипок або рука зникла)."""
        if self._vol_pinch_active:
            self._vol_pinch_active = False
            self._vol_start_y = None
            self._vol_start_val = None
            print("[GESTURE] pinch-гучність зафіксовано")

    def _handle_normal(self, gesture: str) -> bool:
        if gesture == "fist":
            self._enter_sleep()
            return True
        if gesture == "ok":
            self._enter_focus()
            return True
        if gesture == "point" and self._mouse is not None:
            self._mode = "mouse"
            self._mouse.activate()
            return True
        if gesture == "peace":
            try:
                self._music.next_track()
            except Exception as e:
                print(f"[GESTURE] music error: {e}")
            print("[GESTURE] peace → Next track")
            self._log("Gesture: Next track")
            return True
        if gesture in self._actions:
            label, fn = self._actions[gesture]
            try:
                result = fn()
            except Exception as e:
                result = f"ERROR|{e}"
            print(f"[GESTURE] {gesture} → {label} ({result})")
            self._log(f"Gesture: {label}")
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Режим SLEEP
    # ------------------------------------------------------------------ #

    def _enter_sleep(self):
        self._mode = "sleep"
        print("[GESTURE] → SLEEP MODE (вихід: peace)")
        self._log("Sleep mode (show peace to wake)", kind="warning")
        # Викликаємо СПРАВЖНІЙ sleep_mode JARVIS (затемнення HUD, гучність,
        # STANDBY, ранковий reminder, Telegram). Не дублюємо логіку тут.
        if self._sleep:
            try:
                self._sleep()
            except Exception as e:
                print(f"[GESTURE] sleep error: {e}")
        else:
            # fallback, якщо callback не передано
            try:
                self._music.stop()
            except Exception:
                pass

    def _handle_sleep(self, gesture: str) -> bool:
        if gesture == "peace":
            self._snapshot()                       # знімок "хто будить"
            self._mode = "normal"
            print("[GESTURE] → WAKE (peace)")
            self._log("Awake", kind="info")
            if self._wake:
                try:
                    self._wake()
                except Exception as e:
                    print(f"[GESTURE] wake error: {e}")
            elif self._speak:
                try:
                    self._speak("Welcome back, Sir.")
                except Exception:
                    pass
            return True
        return False   # решта жестів у sleep ігноруються

    # ------------------------------------------------------------------ #
    #  Режим FOCUS
    # ------------------------------------------------------------------ #

    def _enter_focus(self):
        # жести ВИМКНЕНІ
        self._mode = "focus"
        print("[GESTURE] → жести вимкнені")
        self._log("Gestures off", kind="info")
        if self._speak:
            try:
                self._speak("Gestures off, Sir.")
            except Exception:
                pass

    def _handle_focus(self, gesture: str) -> bool:
        if gesture == "ok":
            # жести УВІМКНЕНІ
            self._mode = "normal"
            print("[GESTURE] → жести увімкнені")
            self._log("Gestures on", kind="warning")
            if self._speak:
                try:
                    self._speak("Gestures on, Sir.")
                except Exception:
                    pass
            return True
        return False   # решта жестів у focus ігноруються

    # ------------------------------------------------------------------ #
    #  Знімок камери (заготовка під face recognition)
    # ------------------------------------------------------------------ #

    def _snapshot(self):
        """Зберігає поточний кадр у logs/snapshots/. Без оцінювання."""
        try:
            jpeg = self._cam.get_jpeg()
            if not jpeg:
                return
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            fname = SNAPSHOT_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
            with open(fname, "wb") as f:
                f.write(jpeg)
            print(f"[GESTURE] Знімок збережено: {fname}")
        except Exception as e:
            print(f"[GESTURE] snapshot error: {e}")

    # ------------------------------------------------------------------ #

    def _log(self, text: str, kind: str = "info"):
        if self._hud:
            try:
                self._hud(text, kind=kind)
            except Exception as e:
                print(f"[GESTURE] HUD error: {e}")


# ── Локальний тест: python gesture_controller.py ──────
if __name__ == "__main__":
    from camera_vision import CameraVision
    from music_module import MusicModule

    cam = CameraVision()
    cam.start()
    music = MusicModule()

    gc = GestureController(cam, music,
                           hud_callback=lambda t, kind="info": print(f"[HUD] {t}"),
                           speak_callback=lambda t: print(f"[SPEAK] {t}"))
    gc.start()

    print("Жести: open_palm=пауза, peace=наступний+знімок, fist=sleep, ok=focus. Ctrl+C — вихід.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        gc.stop()
        cam.stop()
        time.sleep(1)