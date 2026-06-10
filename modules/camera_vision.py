"""
camera_vision.py — Живий зір JARVIS (камера + MediaPipe Hands).

Окремий daemon-тред читає USB-камеру, проганяє кадр через MediaPipe Hands,
тримає ОСТАННІЙ результат (скільки рук, landmarks, простий жест) у полях.
Решта системи НЕ блокується — просто опитує get_state() / get_gesture().

УВАГА: це НЕ vision_module.py (той — Google Cloud Vision по скриншотах).
Тут — жива камера в реальному часі.

Залежності:
    pip install opencv-python mediapipe

Прев'ю: зараз OpenCV-вікно (debug). Пізніше кадр піде стрімом у HUD.
"""

import threading
import time

import cv2
import mediapipe as mp


# ── Конфіг ─────────────────────────────────────────────────────────────
CAMERA_INDEX = 0          # зовнішня USB-камера (0 — вбудована; підбери числом)
FRAME_W = 640
FRAME_H = 480
MAX_HANDS = 1             # поки одна рука; розширимо пізніше
DRAW_PREVIEW = True       # OpenCV-вікно з landmarks (debug). Пізніше → HUD


class CameraVision:
    def __init__(self, camera_index: int = CAMERA_INDEX, draw_preview: bool = DRAW_PREVIEW):
        self._cam_index = camera_index
        self._draw      = draw_preview

        self._running = False
        self._thread  = None

        # ── Останній стан (опитується ззовні) ──
        self._lock        = threading.Lock()
        self._hands_count = 0          # скільки рук видно
        self._gesture     = "none"     # поточний жест (рядок)
        self._fingers     = 0          # к-сть піднятих пальців
        self._last_seen   = 0.0        # коли востаннє бачили руку (timestamp)

        # MediaPipe
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._hands    = None          # створюється в треді (важко серіалізується)

    # ------------------------------------------------------------------ #
    #  Запуск / зупинка
    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            print("[CAMERA] Вже запущено")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="CameraVision")
        self._thread.start()
        print(f"[CAMERA] Запущено (камера index={self._cam_index})")

    def stop(self):
        self._running = False
        print("[CAMERA] Зупинка...")

    # ------------------------------------------------------------------ #
    #  Публічний інтерфейс — опитування стану
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict:
        """Знімок останнього стану зору (потокобезпечно)."""
        with self._lock:
            return {
                "hands": self._hands_count,
                "gesture": self._gesture,
                "fingers": self._fingers,
                "fresh": (time.time() - self._last_seen) < 1.0,  # рука свіжа (<1с)
            }

    def get_gesture(self) -> str:
        """Швидкий доступ до поточного жесту."""
        with self._lock:
            return self._gesture

    # ------------------------------------------------------------------ #
    #  Основний цикл (у власному треді)
    # ------------------------------------------------------------------ #

    def _loop(self):
        # CAP_DSHOW — швидкий і стабільний бекенд для USB-камер на Windows
        cap = cv2.VideoCapture(self._cam_index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

        if not cap.isOpened():
            print(f"[CAMERA] ПОМИЛКА: камеру index={self._cam_index} не відкрито. "
                  f"Спробуй інший CAMERA_INDEX (0/1/2).")
            self._running = False
            return

        # MediaPipe Hands створюємо тут, у треді
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_HANDS,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

        print("[CAMERA] Потік кадрів пішов")
        while self._running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            # Дзеркалимо (зручніше для користувача) + RGB для MediaPipe
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self._hands.process(rgb)

            hands_count = 0
            gesture = "none"
            fingers = 0

            if result.multi_hand_landmarks:
                hands_count = len(result.multi_hand_landmarks)
                hand = result.multi_hand_landmarks[0]
                handedness = "Right"
                if result.multi_handedness:
                    handedness = result.multi_handedness[0].classification[0].label

                fingers = self._count_fingers(hand, handedness)
                gesture = self._classify_gesture(fingers, hand)

                if self._draw:
                    self._mp_draw.draw_landmarks(
                        frame, hand, self._mp_hands.HAND_CONNECTIONS
                    )

            # Оновлюємо стан
            with self._lock:
                self._hands_count = hands_count
                self._gesture     = gesture
                self._fingers     = fingers
                if hands_count > 0:
                    self._last_seen = time.time()

            # Прев'ю-вікно (debug)
            if self._draw:
                cv2.putText(frame, f"{gesture} | fingers: {fingers}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 255, 200), 2)
                cv2.imshow("JARVIS Vision", frame)
                # 'q' у вікні — закрити прев'ю (сам зір продовжує)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self._draw = False
                    cv2.destroyWindow("JARVIS Vision")

        cap.release()
        if self._draw:
            cv2.destroyAllWindows()
        print("[CAMERA] Зупинено")

    # ------------------------------------------------------------------ #
    #  Розпізнавання пальців і жестів
    # ------------------------------------------------------------------ #

    def _count_fingers(self, hand, handedness: str) -> int:
        """Рахує підняті пальці за landmarks.
        Великий палець — по X (залежить від лівої/правої руки),
        решта — по Y (кінчик вище суглоба = піднятий)."""
        lm = hand.landmark
        up = 0

        # Кінчики пальців: великий=4, вказ=8, серед=12, безім=16, мізин=20
        # Суглоби (PIP) для 4 пальців: 6, 10, 14, 18
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        for tip, pip in zip(tips, pips):
            if lm[tip].y < lm[pip].y:   # кінчик вище суглоба
                up += 1

        # Великий палець — по горизонталі (X), напрям залежить від руки
        if handedness == "Right":
            if lm[4].x < lm[3].x:
                up += 1
        else:  # Left
            if lm[4].x > lm[3].x:
                up += 1

        return up

    def _classify_gesture(self, fingers: int, hand) -> str:
        """Простий класифікатор жесту за кількістю пальців.
        Розширимо пізніше (peace, thumbs up/down тощо)."""
        lm = hand.landmark
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        # Які саме пальці підняті (без великого)
        up_flags = [lm[t].y < lm[p].y for t, p in zip(tips, pips)]
        index_up, middle_up, ring_up, pinky_up = up_flags

        if fingers == 0:
            return "fist"
        if fingers == 5:
            return "open_palm"
        if index_up and middle_up and not ring_up and not pinky_up:
            return "peace"
        if fingers == 1 and index_up:
            return "point"
        return f"hand_{fingers}"


# ── Швидкий локальний тест: python camera_vision.py ────────────────────
if __name__ == "__main__":
    cv = CameraVision()
    cv.start()
    try:
        while True:
            time.sleep(1)
            print(cv.get_state())
    except KeyboardInterrupt:
        cv.stop()
        time.sleep(1)
