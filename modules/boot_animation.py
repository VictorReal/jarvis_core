"""
boot_animation.py — анімований "Boot Sequence" старт для JARVIS HUD.

Підключення (мінімальний дотик до hud_module.py):
    1) У run_hud / при створенні app:
         from modules.boot_animation import register_boot
         register_boot(app)
    2) У HTML_TEMPLATE перед </body> додати ОДИН рядок:
         <script src="/boot.js"></script>

Анімація:
  • чорний overlay поверх HUD, друкується лог завантаження (мікс гарних + реальних рядків)
  • прогрес-бар, фінальний спалах, плавне зникнення
  • ПРОПУСК: клік будь-де / Esc / Enter / пробіл → миттєво показати HUD
  • якщо нічого не натиснуто — сам зникає (~4.5 c)

Overlay створюється повністю з JS (document.createElement), тож HUD-розмітку
міняти не треба — лише підключити boot.js.
"""

from flask import Response

# Рядки логу завантаження. ok=True → праворуч зелене "OK".
# Мікс "фільмових" і реальних статусів модулів JARVIS.
BOOT_LINES = [
    ("INITIALIZING J.A.R.V.I.S. CORE", True),
    ("Verifying system integrity", True),
    ("Loading kernel modules", True),
    ("Establishing neural interface", True),
    ("Mounting long-term memory", True),
    ("Indexing daily logs", True),
    ("Spinning up LangChain agent", True),
    ("Connecting Groq LLM endpoint", True),
    ("Google OAuth2 handshake", True),
    ("Calendar sync", True),
    ("Gmail agent online", True),
    ("Health analytics engine", True),
    ("Loading Samsung Health data", True),
    ("Money manager", True),
    ("50/30/20 budget model", True),
    ("Mood engine", True),
    ("Cross-correlation matrix", True),
    ("Weather monitor", True),
    ("Geolocation triangulation", True),
    ("Spotify poller", True),
    ("Telegram uplink", True),
    ("TTS voice synthesis", True),
    ("Reminder scheduler", True),
    ("HUD socket bridge", True),
    ("Known individuals registry", True),
    ("Running diagnostics", True),
    ("Calibrating sensors", True),
    ("All systems nominal", True),
]

_BOOT_JS = """
(function () {
  // не показувати двічі за сесію вкладки
  if (window.__jarvisBooted) return;
  window.__jarvisBooted = true;

  var LINES = __BOOT_LINES__;
  var LINE_DELAY = 85;      // мс між рядками (більше рядків — менший крок, та сама тривалість)
  var AUTO_HIDE_AFTER = 700; // мс після останнього рядка до зникнення
  var START_DELAY = 500;     // пауза перед першим рядком

  // ---- стилі ----
  var css = document.createElement('style');
  css.textContent = `
    #jarvis-boot {
      position: fixed; inset: 0; z-index: 9999;
      background: radial-gradient(ellipse at center, #02101f 0%, #000 75%);
      color: #00d4ff; font-family: 'Share Tech Mono', monospace;
      cursor: pointer; overflow: hidden;
      transition: opacity 0.5s ease;
      width:100vw; 
      max-width:100%;
      box-sizing:border-box
    }
    #jarvis-boot .jb-scan {
      position: absolute; inset: 0; pointer-events: none;
      background: repeating-linear-gradient(0deg, transparent, transparent 2px,
                  rgba(0,212,255,0.04) 2px, rgba(0,212,255,0.04) 4px);
    }
    /* центрований контейнер СТАЛОГО розміру — нічого не "їде" */
    #jarvis-boot .jb-wrap {
      position: absolute; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      display: flex; flex-direction: column; align-items: center;
      width: min(560px, 86vw);
    }
    #jarvis-boot .jb-logo {
      font-family: 'Orbitron', sans-serif; font-size: 42px; font-weight: 900;
      letter-spacing: 14px; color: #00d4ff;
      text-shadow: 0 0 24px #00d4ff, 0 0 48px #00d4ff55;
      margin-bottom: 26px; opacity: 0; transform: scale(0.9);
      animation: jb-logo-in 0.8s ease forwards;
      text-align: center;
    }
    @keyframes jb-logo-in { to { opacity: 1; transform: scale(1); } }
    /* лог-вікно ФІКСОВАНОЇ висоти; нові рядки знизу, старі підіймаються і зникають
       вгорі під fade-маскою — ефект "текст іде вверх за логотипом" */
    #jarvis-boot .jb-log {
      width: 100%; height: 240px; font-size: 13px; line-height: 1.8;
      overflow: hidden; position: relative;
      -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 38px, #000 100%);
      mask-image: linear-gradient(to bottom, transparent 0, #000 38px, #000 100%);
    }
    #jarvis-boot .jb-log-inner {
      position: absolute; bottom: 0; left: 0; right: 0;
      display: flex; flex-direction: column;
    }
    #jarvis-boot .jb-row { display: flex; justify-content: space-between;
      opacity: 0; animation: jb-row-in 0.25s ease forwards; }
    @keyframes jb-row-in { from { opacity: 0; transform: translateY(6px); }
                           to { opacity: 1; transform: translateY(0); } }
    #jarvis-boot .jb-row .jb-ok { color: #00ff88; }
    #jarvis-boot .jb-row .jb-dots { color: #00d4ff44; flex: 1;
      margin: 0 8px; overflow: hidden; white-space: nowrap; }
    #jarvis-boot .jb-bar {
      width: 100%; height: 3px; margin-top: 22px;
      background: #00d4ff22; border-radius: 2px; overflow: hidden;
    }
    #jarvis-boot .jb-bar-fill {
      height: 100%; width: 0%;
      background: linear-gradient(90deg, #00d4ff, #00ff88);
      box-shadow: 0 0 10px #00d4ff; transition: width 0.15s ease;
    }
    #jarvis-boot .jb-skip {
      position: absolute; bottom: 26px; left: 0; right: 0; text-align: center;
      font-size: 10px; letter-spacing: 3px;
      color: #00d4ff55; text-transform: uppercase;
      animation: jb-skip-pulse 1.6s infinite;
    }
    @keyframes jb-skip-pulse { 0%,100%{opacity:0.4;} 50%{opacity:0.9;} }
    #jarvis-boot.jb-flash { animation: jb-flash 0.4s ease; }
    @keyframes jb-flash { 50% { background: #00d4ff33; } }
    /* ---- МОБІЛЬНА версія ---- */
    @media (max-width: 768px) {
      #jarvis-boot .jb-wrap { width: 90vw; }
      #jarvis-boot .jb-logo { font-size: 26px; letter-spacing: 7px; margin-bottom: 18px; }
      #jarvis-boot .jb-log { height: 200px; font-size: 11px; line-height: 1.7; }
      #jarvis-boot .jb-row .jb-dots { margin: 0 5px; }
      #jarvis-boot .jb-skip { font-size: 9px; letter-spacing: 2px; bottom: 18px; }
    }
  `;
  document.head.appendChild(css);

  // ---- DOM ----
  var ov = document.createElement('div');
  ov.id = 'jarvis-boot';
  ov.innerHTML =
    '<div class="jb-scan"></div>' +
    '<div class="jb-wrap">' +
      '<div class="jb-logo">J.A.R.V.I.S.</div>' +
      '<div class="jb-log"><div class="jb-log-inner" id="jb-log"></div></div>' +
      '<div class="jb-bar"><div class="jb-bar-fill" id="jb-bar"></div></div>' +
    '</div>' +
    '<div class="jb-skip">click or press any key to skip</div>';
  document.body.appendChild(ov);

  var logEl = ov.querySelector('#jb-log');
  var barEl = ov.querySelector('#jb-bar');
  var done = false;
  var timers = [];

  function dots(n) { var s=''; for (var i=0;i<n;i++) s+='.'; return s; }

  function addRow(item, idx) {
    var row = document.createElement('div');
    row.className = 'jb-row';
    var label = item[0], ok = item[1];
    row.innerHTML = '<span>&gt; ' + label + '</span>' +
                    '<span class="jb-dots">' + dots(30) + '</span>' +
                    (ok ? '<span class="jb-ok">OK</span>' : '<span style="color:#ff9500">..</span>');
    logEl.appendChild(row);
    // нові рядки додаються знизу (flex bottom:0), старі підіймаються під fade-маску
    barEl.style.width = Math.round(((idx + 1) / LINES.length) * 100) + '%';
  }

  function finish() {
    if (done) return;
    done = true;
    timers.forEach(clearTimeout);
    ov.classList.add('jb-flash');
    setTimeout(function () {
      ov.style.opacity = '0';
      setTimeout(function () { if (ov.parentNode) ov.parentNode.removeChild(ov); }, 500);
    }, 180);
    window.removeEventListener('keydown', onKey);
  }

  function onKey(e) { finish(); }

  // друкуємо рядки по черзі
  LINES.forEach(function (item, i) {
    timers.push(setTimeout(function () { addRow(item, i); }, START_DELAY + i * LINE_DELAY));
  });
  // авто-зникнення після останнього
  timers.push(setTimeout(finish, START_DELAY + LINES.length * LINE_DELAY + AUTO_HIDE_AFTER));

  // пропуск
  ov.addEventListener('click', finish);
  window.addEventListener('keydown', onKey);
})();
"""


def build_boot_js() -> str:
    """Формує boot.js з підставленими рядками логу."""
    import json
    lines_js = json.dumps(BOOT_LINES, ensure_ascii=False)
    return _BOOT_JS.replace("__BOOT_LINES__", lines_js)


def register_boot(app):
    """Реєструє роут /boot.js. Викликати один раз з hud_module/main."""
    @app.route("/boot.js")
    def _boot_js():
        return Response(build_boot_js(), mimetype="application/javascript")
    print("[BOOT] /boot.js зареєстровано")