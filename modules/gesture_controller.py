"""
gesture_controller.py — Жести → дії JARVIS.

Опитує CameraVision у власному треді й виконує дію в момент,
коли жест ВПЕВНЕНО з'явився (а не поки тримається).

Захист від хаосу:
  • STABLE_FRAMES — жест має протриматись N опитувань поспіль (відсіює мигання)
  • cooldown      — між діями пауза (одна рука = одна дія, не потік)
  • тригер по зміні — дія раз на появу жесту, повтор лише після 'none' або іншого жесту

Вивід тихий: рядок у HUD activity-лог (kind="info"). Без голосу.

camera_vision лишається чистим (тільки бачить) — дії живуть тут.
"""

import threading
import time


# ── Конфіг ─────────────────────────────────────────────────────────────
POLL_SEC      = 0.1     # як часто опитуємо стан зору
STABLE_FRAMES = 4       # скільки опитувань поспіль жест має бути стабільним
COOLDOWN_SEC  = 1.5     # мін. пауза між діями

# Маппінг жест → (назва дії, метод music_module). point поки резерв.
# Розширимо пізніше (гучність, попередній трек тощо).


class GestureController:
    def __init__(self, camera_vision, music_module, hud_callback=None):
        """
        camera_vision  — CameraVision (має get_state())
        music_module   — MusicModule (toggle/stop/next_track)
        hud_callback   — log_activity(text, kind), опційно
        """
        self._cam   = camera_vision
        self._music = music_module
        self._hud   = hud_callback

        self._running = False
        self._thread  = None

        # Стан розпізнавання
        self._candidate   = "none"   # жест-кандидат, що набирає стабільність
        self._stable_cnt  = 0        # скільки опитувань кандидат тримається
        self._last_action_gesture = "none"  # останній жест, що ВИКОНАВ дію
        self._last_action_time    = 0.0

        # Жести, які запускають дії (інші ігноруємо)
        self._actions = {
            "open_palm": ("Pause/Play", self._music.toggle),
            "fist":      ("Stop",       self._music.stop),
            "peace":     ("Next track", self._music.next_track),
            "hand_2":    ("Next track", self._music.next_track),  # MediaPipe часто читає 2 пальці як hand_2
            # "point":   зарезервовано
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
        # Якщо руки нема / стан застарів — скидаємо все, дозволяємо повтор жесту
        if not state.get("fresh") or state.get("hands", 0) == 0:
            self._candidate = "none"
            self._stable_cnt = 0
            self._last_action_gesture = "none"  # рука зникла → той самий жест можна повторити
            return

        gesture = state.get("gesture", "none")

        # Набираємо стабільність кандидата
        if gesture == self._candidate:
            self._stable_cnt += 1
        else:
            self._candidate = gesture
            self._stable_cnt = 1

        # Жест ще не стабільний — чекаємо
        if self._stable_cnt < STABLE_FRAMES:
            return

        # Жест не з тих, що мають дію
        if gesture not in self._actions:
            return

        # Той самий жест уже спрацював і рука не зникала — не повторюємо
        if gesture == self._last_action_gesture:
            return

        # Cooldown між діями
        now = time.time()
        if now - self._last_action_time < COOLDOWN_SEC:
            return

        # ── Виконуємо дію ──
        label, fn = self._actions[gesture]
        try:
            result = fn()
        except Exception as e:
            result = f"ERROR|{e}"

        self._last_action_gesture = gesture
        self._last_action_time = now

        print(f"[GESTURE] {gesture} → {label} ({result})")
        if self._hud:
            try:
                self._hud(f"Gesture: {label}", kind="info")
            except Exception as e:
                print(f"[GESTURE] HUD error: {e}")


# ── Локальний тест разом із камерою: python gesture_controller.py ──────
if __name__ == "__main__":
    from camera_vision import CameraVision
    from music_module import MusicModule

    cam = CameraVision()
    cam.start()
    music = MusicModule()

    gc = GestureController(cam, music, hud_callback=lambda t, kind: print(f"[HUD] {t}"))
    gc.start()

    print("Показуй жести: open_palm=пауза/плей, fist=стоп, peace=наступний. Ctrl+C — вихід.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        gc.stop()
        cam.stop()
        time.sleep(1)