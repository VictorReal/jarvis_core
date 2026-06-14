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
PROCESS_EVERY = 2         # MediaPipe обробляє кожен N-й кадр (throttle CPU).
                          # 1 = кожен кадр, 2 = через кадр (~вдвічі менше навантаження)
DETECTION_CONF = 0.7      # поріг впевненості детекції (вище = менше хибних, напр. голова)
TRACKING_CONF = 0.6
STABLE_FRAMES = 3         # жест зараховується лише після N однакових обробок поспіль
                          # (прибирає мигання й випадкові хибні спрацювання)


class CameraVision:
    def __init__(self, camera_index: int = CAMERA_INDEX, draw_preview: bool = DRAW_PREVIEW):
        self._cam_index = camera_index
        self._draw      = draw_preview

        self._running = False
        self._thread  = None

        # ── Останній стан (опитується ззовні) ──
        self._lock        = threading.Lock()
        self._hands_count = 0          # скільки рук видно
        self._gesture     = "none"     # поточний жест (рядок) — стабілізований
        self._fingers     = 0          # к-сть піднятих пальців
        self._last_seen   = 0.0        # коли востаннє бачили руку (timestamp)

        # Згладжування жесту: сирий кандидат набирає стабільність
        self._raw_gesture = "none"
        self._stable_cnt  = 0

        # Позиція кінчика вказівного (landmark 8), нормалізована 0..1 — для курсора
        self._index_xy = None

        # Список обох рук (для 2-рукого курсора): [{handedness, gesture, index_xy}]
        self._hands_list = []
        # Скільки рук обробляти зараз (1 або 2). Перемикається set_max_hands().
        self._max_hands = MAX_HANDS
        self._reinit_hands = False   # прапор: треба перестворити MediaPipe

        # Останній кадр у JPEG (для стріму в HUD)
        self._jpeg_lock = threading.Lock()
        self._last_jpeg = None

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
                "index_xy": self._index_xy,  # позиція вказівного для курсора
                "fresh": (time.time() - self._last_seen) < 1.0,  # рука свіжа (<1с)
            }

    def get_gesture(self) -> str:
        """Швидкий доступ до поточного жесту."""
        with self._lock:
            return self._gesture

    def get_jpeg(self):
        """Останній кадр у JPEG (bytes) для HUD-стріму, або None."""
        with self._jpeg_lock:
            return self._last_jpeg

    def get_hands(self) -> list:
        """Список рук: [{handedness:'Left'/'Right', gesture, index_xy}].
        handedness вже сконвертовано під дзеркалений кадр (= фізична рука)."""
        with self._lock:
            return list(self._hands_list)

    def set_max_hands(self, n: int):
        """Перемкнути к-сть рук (1 або 2). MediaPipe перестворюється у треді.
        2 руки = вдвічі більше CPU — вмикати лише на час курсор-режиму."""
        n = 2 if n >= 2 else 1
        if n != self._max_hands:
            self._max_hands = n
            self._reinit_hands = True
            print(f"[CAMERA] Перемикаю на {n} руку(и)")

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
        def _make_hands(n):
            # для 2 рук трохи нижчий поріг — інакше другу руку погано ловить
            det_conf = 0.55 if n >= 2 else DETECTION_CONF
            return self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=n,
                min_detection_confidence=det_conf,
                min_tracking_confidence=TRACKING_CONF,
            )
        self._hands = _make_hands(self._max_hands)

        print("[CAMERA] Потік кадрів пішов")
        frame_idx = 0
        last_landmarks = None   # останні landmarks для малювання на пропущених кадрах
        while self._running:
            # Перестворення MediaPipe при зміні к-сті рук (1↔2)
            if self._reinit_hands:
                try:
                    self._hands.close()
                except Exception:
                    pass
                self._hands = _make_hands(self._max_hands)
                self._reinit_hands = False
                print(f"[CAMERA] MediaPipe перестворено ({self._max_hands} руки)")
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            # Дзеркалимо (зручніше для користувача)
            frame = cv2.flip(frame, 1)

            frame_idx += 1
            process_now = (frame_idx % PROCESS_EVERY == 0)

            if process_now:
                # ── Важка обробка: лише кожен PROCESS_EVERY-й кадр ──
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self._hands.process(rgb)

                hands_count = 0
                gesture = "none"
                fingers = 0
                last_landmarks = None
                index_xy = None
                hands_list = []

                if result.multi_hand_landmarks:
                    for i, hand in enumerate(result.multi_hand_landmarks):
                        if not self._looks_like_hand(hand):
                            continue
                        # handedness від MediaPipe + конверсія під дзеркалений кадр:
                        # cv2.flip інвертує, тому MediaPipe 'Left' = фізична Right.
                        mp_label = "Right"
                        if result.multi_handedness and i < len(result.multi_handedness):
                            mp_label = result.multi_handedness[i].classification[0].label
                        phys = mp_label  # без конверсії — MediaPipe на flip-кадрі вже дає вірно

                        f = self._count_fingers(hand, mp_label)
                        g = self._classify_gesture(f, hand)
                        idx = hand.landmark[8]
                        hands_list.append({
                            "handedness": phys,
                            "gesture": g,
                            "index_xy": (idx.x, idx.y),
                            "fingers": f,
                        })
                        if i == 0:
                            last_landmarks = hand

                    if hands_list:
                        hands_count = len(hands_list)
                        # primary рука (для старого get_state / жестів-команд) — перша
                        gesture = hands_list[0]["gesture"]
                        fingers = hands_list[0]["fingers"]
                        index_xy = hands_list[0]["index_xy"]
                        raw = gesture
                    else:
                        raw = "none"
                else:
                    raw = "none"

                # ── Згладжування: жест зараховуємо лише після STABLE_FRAMES однакових ──
                if raw == self._raw_gesture:
                    self._stable_cnt += 1
                else:
                    self._raw_gesture = raw
                    self._stable_cnt = 1

                stable_gesture = self._gesture  # за замовчуванням тримаємо попередній
                if self._stable_cnt >= STABLE_FRAMES:
                    stable_gesture = raw

                # Оновлюємо стан тільки на оброблених кадрах
                with self._lock:
                    self._hands_count = hands_count
                    self._gesture     = stable_gesture
                    self._fingers     = fingers
                    self._index_xy    = index_xy
                    self._hands_list  = hands_list
                    if hands_count > 0:
                        self._last_seen = time.time()
                gesture = stable_gesture
            else:
                # ── Пропущений кадр: жест тримаємо, лише читаємо для прев'ю ──
                with self._lock:
                    gesture = self._gesture
                    fingers = self._fingers

            # Малюємо landmarks (останні відомі) — і на оброблених, і на пропущених
            if self._draw and last_landmarks is not None:
                self._mp_draw.draw_landmarks(
                    frame, last_landmarks, self._mp_hands.HAND_CONNECTIONS
                )

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

            # Кодуємо кадр у JPEG для HUD-стріму (з підписом жесту)
            try:
                annotated = frame.copy()
                cv2.putText(annotated, f"{gesture}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 200), 2)
                ok_enc, buf = cv2.imencode(".jpg", annotated,
                                           [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok_enc:
                    with self._jpeg_lock:
                        self._last_jpeg = buf.tobytes()
            except Exception:
                pass

        cap.release()
        if self._draw:
            cv2.destroyAllWindows()
        print("[CAMERA] Зупинено")

    # ------------------------------------------------------------------ #
    #  Розпізнавання пальців і жестів
    # ------------------------------------------------------------------ #

    def _looks_like_hand(self, hand) -> bool:
        """Груба валідація: чи landmarks справді схожі на руку, а не хибна
        детекція (голова/обличчя в кадрі). Перевіряємо, що точки достатньо
        розкидані й кисть має правдоподібні пропорції.
        Прибирає баг 'голова → fist'."""
        lm = hand.landmark
        xs = [p.x for p in lm]
        ys = [p.y for p in lm]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)

        # 1) занадто дрібний об'єкт (точки збилися в купу) — не рука
        if span_x < 0.05 and span_y < 0.05:
            return False

        # 2) рука завжди має помітну "довжину" від зап'ястка до кінчиків.
        # Відстань зап'ясток(0) → середній кінчик(12) має бути відчутною.
        wrist = lm[0]
        mid_tip = lm[12]
        dist = ((wrist.x - mid_tip.x) ** 2 + (wrist.y - mid_tip.y) ** 2) ** 0.5
        if dist < 0.10:
            return False

        # 3) аспект: майже точне коло точок (як обличчя) — підозріло.
        # У руки розкид по одній осі зазвичай більший за іншу.
        if span_x > 0 and span_y > 0:
            ratio = max(span_x, span_y) / min(span_x, span_y)
            # надто "квадратний"/круглий кластер — найчастіше хибна детекція
            # (рука рідко ідеально квадратна; послаблений поріг, щоб не різати реальні руки)
            if ratio < 1.05 and dist < 0.15:
                return False

        # 4) у справжньої руки кінчики 5 пальців — на ПОМІТНО різній відстані
        # від зап'ястка. Хибна детекція голови дає рівномірний кластер.
        wr = lm[0]
        tip_ids = [4, 8, 12, 16, 20]
        dists = [((lm[t].x - wr.x) ** 2 + (lm[t].y - wr.y) ** 2) ** 0.5 for t in tip_ids]
        if (max(dists) - min(dists)) < 0.04:
            return False

        return True

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

    def _thumb_up(self, hand) -> bool:
        """Справжній thumbs_up: великий ВІДСТАВЛЕНИЙ від кулака і спрямований вгору.
        Ключове — кінчик великого далеко від кісточок 4 пальців (не притиснутий),
        інакше боковий кулак хибно читається як thumbs_up."""
        lm = hand.landmark
        tip, mcp, wrist = lm[4], lm[2], lm[0]
        # 1) кінчик вище основи великого і вище зап'ястка
        clearly_up = (tip.y < mcp.y - 0.04) and (tip.y < wrist.y - 0.08)
        # 2) великий ВІДСТАВЛЕНИЙ: кінчик(4) далеко від кісточок пальців (5,9,13,17)
        knuckles = [lm[5], lm[9], lm[13], lm[17]]
        min_d = min(((tip.x - k.x) ** 2 + (tip.y - k.y) ** 2) ** 0.5 for k in knuckles)
        apart = min_d > 0.12
        return clearly_up and apart

    def _thumb_down(self, hand) -> bool:
        """Справжній thumbs_down: великий відставлений і спрямований вниз."""
        lm = hand.landmark
        tip, mcp, wrist = lm[4], lm[2], lm[0]
        clearly_down = (tip.y > mcp.y + 0.04) and (tip.y > wrist.y + 0.08)
        knuckles = [lm[5], lm[9], lm[13], lm[17]]
        min_d = min(((tip.x - k.x) ** 2 + (tip.y - k.y) ** 2) ** 0.5 for k in knuckles)
        apart = min_d > 0.12
        return clearly_down and apart

    def _thumb_out(self, hand) -> bool:
        """Великий палець відставлений убік (розкритий, не притиснутий до долоні).
        Для call_me 🤙 — великий стирчить, мізинець піднятий."""
        lm = hand.landmark
        tip, mcp = lm[4], lm[2]
        # кінчик великого помітно вбік від його основи
        return abs(tip.x - mcp.x) > 0.06

    def _is_pinch(self, hand) -> bool:
        """Щипок/кільце: кінчики великого (4) і вказівного (8) близько,
        АЛЕ вказівний при цьому ВИТЯГНУТИЙ (а не втиснутий у долоню, як у кулаку).
        Без цього кулак (усі пальці зібрані) хибно читається як pinch."""
        lm = hand.landmark
        # 1) кінчики великого і вказівного близько
        d = ((lm[4].x - lm[8].x) ** 2 + (lm[4].y - lm[8].y) ** 2) ** 0.5
        if d >= 0.06:
            return False
        # 2) вказівний витягнутий: кінчик(8) далеко від п'ясткового суглоба(5).
        # У кулаку палець зігнутий → ця відстань мала.
        ext = ((lm[8].x - lm[5].x) ** 2 + (lm[8].y - lm[5].y) ** 2) ** 0.5
        return ext > 0.12

    def _classify_gesture(self, fingers: int, hand) -> str:
        """Класифікатор статичних жестів за landmarks.
        Жести: fist, open_palm, peace, point, thumbs_up, thumbs_down,
        ok, rock, three, four, pinch."""
        lm = hand.landmark
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        up_flags = [lm[t].y < lm[p].y for t, p in zip(tips, pips)]
        index_up, middle_up, ring_up, pinky_up = up_flags
        n4 = sum(up_flags)   # скільки з 4 пальців (без великого) піднято

        # ── OK 👌: кільце великий+вказівний, інші пальці переважно підняті ──
        # (досить 2 з 3, бо на реальному ok пальці часто не повністю випрямлені)
        others_up = sum([middle_up, ring_up, pinky_up])
        if self._is_pinch(hand) and others_up >= 2:
            return "ok"

        # ── pinch 🤏: щипок, інші пальці зігнуті (аналоговий, для гучності) ──
        if self._is_pinch(hand) and others_up == 0:
            return "pinch"

        # ── call_me 🤙: великий + мізинець, решта зігнуті ──
        if pinky_up and not index_up and not middle_up and not ring_up and self._thumb_out(hand):
            return "call_me"

        # ── rock 🤘: вказівний + мізинець, середній і безіменний зігнуті ──
        if index_up and pinky_up and not middle_up and not ring_up:
            return "rock"

        # ── thumbs_up/down 👍👎: лише великий, 4 пальці зігнуті ──
        if n4 == 0:
            if self._thumb_up(hand):
                return "thumbs_up"
            if self._thumb_down(hand):
                return "thumbs_down"
            return "fist"   # 0 пальців і великий не вгору/вниз → кулак

        # ── peace ✌️: вказівний + середній ──
        if index_up and middle_up and not ring_up and not pinky_up:
            return "peace"

        # ── point ☝️: лише вказівний ──
        if index_up and not middle_up and not ring_up and not pinky_up:
            return "point"

        # ── three / four / open_palm за кількістю ──
        if n4 == 3:
            return "three"
        if n4 == 4 and not self._thumb_up(hand):
            return "four"
        if fingers == 5:
            return "open_palm"

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