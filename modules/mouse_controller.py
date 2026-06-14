"""
mouse_controller.py — Керування курсором рукою (Етап 4).

Окремий режим: вмикається жестом point (або ззовні), вимикається fist.
Поки активний — веде системний курсор за кінчиком вказівного (landmark 8),
pinch = лівий клік, утримання pinch + рух = drag.

Згладжування ОБОВ'ЯЗКОВЕ — без нього курсор на вебці дрижить.
Активна зона звужена (центральні ~70% кадру) → не треба тягтись у кути.

Залежність: pyautogui (вже встановлено).
camera_vision лишається чистим — лише віддає index_xy через get_state.
"""

import threading
import time

import pyautogui


# ── Конфіг ─────────────────────────────────────────────────────────────
POLL_SEC      = 0.02      # ~50 опитувань/с (курсор має бути плавним)
SMOOTH_N      = 5         # усереднення позиції по N кадрах (більше = плавніше/повільніше)
ACTIVE_MARGIN = 0.15      # звужуємо активну зону: 15% з кожного краю кадру ігноруємо
# Робоча зона ЛІВОЇ руки (вона веде курсор). Ліва рука фізично не дотягується
# до правого краю кадру, тому її зона зміщена вліво — мапимо на ВЕСЬ екран.
# Підкрути під себе: [x_min, x_max, y_min, y_max] у частках кадру.
CURSOR_ZONE = [0.05, 0.55, 0.10, 0.65]
PINCH_HOLD_FOR_DRAG = 0.25  # скільки тримати pinch, щоб почався drag (сек)
LERP = 0.35               # інтерполяція: курсор доїжджає до цілі (0..1; менше=плавніше)

pyautogui.FAILSAFE = False  # курсор у кут не має кидати помилку
pyautogui.PAUSE = 0         # без штучних пауз між діями


class MouseController:
    def __init__(self, camera_vision, hud_callback=None, speak_callback=None):
        self._cam   = camera_vision
        self._hud   = hud_callback
        self._speak = speak_callback

        self._running = False     # тред живий
        self._active  = False     # режим курсора увімкнений
        self._thread  = None

        self._screen_w, self._screen_h = pyautogui.size()

        # Згладжування — буфер останніх позицій
        self._buf_x = []
        self._buf_y = []

        # Стан pinch (для кліку/drag)
        self._pinch_down = False     # чи зараз pinch
        self._pinch_start = 0.0      # коли почався pinch
        self._dragging = False

        # Поточна екранна позиція курсора (для плавної інтерполяції)
        self._cur_x = self._screen_w / 2
        self._cur_y = self._screen_h / 2

        # Дебаунс кліків правої руки (щоб один жест = один клік)
        self._last_click_gesture = "none"
        self._last_click_time = 0.0

    # ------------------------------------------------------------------ #

    def start(self):
        """Запускає тред (режим ще НЕ активний — чекає activate())."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="MouseController")
        self._thread.start()
        print("[MOUSE] Тред запущено (режим вимкнено)")

    def stop(self):
        self._running = False

    def activate(self):
        """Увімкнути режим курсора (2 руки: ліва веде, права клікає)."""
        if self._active:
            return
        self._active = True
        self._buf_x.clear()
        self._buf_y.clear()
        self._last_click_gesture = "none"
        # вмикаємо 2 руки в камері (вимкнемо при виході)
        try:
            self._cam.set_max_hands(2)
        except Exception:
            pass
        print("[MOUSE] Курсор-режим УВІМКНЕНО (2 руки)")
        self._log("Mouse control ON", kind="warning")
        if self._speak:
            try:
                self._speak("Mouse control on, Sir.")
            except Exception:
                pass

    def deactivate(self):
        """Вимкнути режим курсора, повернути камеру на 1 руку."""
        if not self._active:
            return
        self._active = False
        if self._dragging:
            try:
                pyautogui.mouseUp()
            except Exception:
                pass
            self._dragging = False
        self._pinch_down = False
        try:
            self._cam.set_max_hands(1)   # назад на 1 руку (економія CPU)
        except Exception:
            pass
        print("[MOUSE] Курсор-режим ВИМКНЕНО")
        self._log("Mouse control OFF", kind="info")
        if self._speak:
            try:
                self._speak("Mouse control off, Sir.")
            except Exception:
                pass

    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            time.sleep(POLL_SEC)
            if not self._active:
                continue
            try:
                self._tick()
            except Exception as e:
                print(f"[MOUSE] tick error: {e}")

    def _tick(self):
        state = self._cam.get_state()
        if not state.get("fresh"):
            return
        hands = self._cam.get_hands()
        if not hands:
            return

        # Розділяємо руки за фізичною стороною
        left = next((h for h in hands if h["handedness"] == "Left"), None)
        right = next((h for h in hands if h["handedness"] == "Right"), None)

        # ── ЛІВА веде курсор (жест point) ──
        if left and left["gesture"] == "point" and left.get("index_xy"):
            sx, sy = self._map_to_screen(left["index_xy"][0], left["index_xy"][1])
            if sx is not None:
                self._buf_x.append(sx)
                self._buf_y.append(sy)
                if len(self._buf_x) > SMOOTH_N:
                    self._buf_x.pop(0)
                    self._buf_y.pop(0)
                target_x = sum(self._buf_x) / len(self._buf_x)
                target_y = sum(self._buf_y) / len(self._buf_y)
                self._cur_x += (target_x - self._cur_x) * LERP
                self._cur_y += (target_y - self._cur_y) * LERP
                try:
                    pyautogui.moveTo(int(self._cur_x), int(self._cur_y), _pause=False)
                except Exception:
                    pass

        # ── ПРАВА робить кліки за жестом ──
        # point = клік, rock = подвійний клік, call_me = права кнопка
        right_g = right["gesture"] if right else "none"
        self._handle_right_click(right_g)

    def _handle_right_click(self, gesture: str):
        now = time.time()
        # дебаунс: один жест = один клік, повтор лише після зміни жесту або паузи
        if gesture == self._last_click_gesture:
            return
        click_map = {
            "peace": "left",     # ✌️ → клік
            "rock": "double",    # 🤘 → подвійний клік
            "four": "right",     # 4 пальці → права кнопка
            # point — дефолтний нейтральний жест правої (нічого не робить)
        }
        if gesture in click_map:
            kind = click_map[gesture]
            try:
                if kind == "left":
                    pyautogui.click(_pause=False)
                    print("[MOUSE] click")
                elif kind == "double":
                    pyautogui.doubleClick(_pause=False)
                    print("[MOUSE] double click")
                elif kind == "right":
                    pyautogui.rightClick(_pause=False)
                    print("[MOUSE] right click")
            except Exception as e:
                print(f"[MOUSE] click error: {e}")
            self._last_click_time = now
        # запам'ятовуємо поточний жест правої (скидається коли рука змінює жест)
        self._last_click_gesture = gesture

    def _map_to_screen(self, nx: float, ny: float):
        """Позиція лівої руки (0..1 у кадрі) → пікселі екрана.
        Мапимо РОБОЧУ зону лівої руки (CURSOR_ZONE) на весь екран,
        бо ліва рука не дотягується до правого краю кадру."""
        x_min, x_max, y_min, y_max = CURSOR_ZONE
        cx = (nx - x_min) / (x_max - x_min)
        cy = (ny - y_min) / (y_max - y_min)
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))
        return cx * self._screen_w, cy * self._screen_h

    def _handle_pinch(self, is_pinch: bool):
        now = time.time()
        if is_pinch and not self._pinch_down:
            # pinch почався
            self._pinch_down = True
            self._pinch_start = now
        elif is_pinch and self._pinch_down:
            # pinch тримається — після порогу починаємо drag
            if not self._dragging and (now - self._pinch_start) >= PINCH_HOLD_FOR_DRAG:
                try:
                    pyautogui.mouseDown(_pause=False)
                except Exception:
                    pass
                self._dragging = True
                print("[MOUSE] drag start")
        elif not is_pinch and self._pinch_down:
            # pinch відпущено
            self._pinch_down = False
            if self._dragging:
                try:
                    pyautogui.mouseUp(_pause=False)
                except Exception:
                    pass
                self._dragging = False
                print("[MOUSE] drag end")
            else:
                # короткий pinch = клік
                try:
                    pyautogui.click(_pause=False)
                except Exception:
                    pass
                print("[MOUSE] click")

    # ------------------------------------------------------------------ #

    def _log(self, text: str, kind: str = "info"):
        if self._hud:
            try:
                self._hud(text, kind=kind)
            except Exception:
                pass