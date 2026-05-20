import threading
import time
import psutil
from datetime import datetime
from flask import Flask, render_template_string
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

hud_state = {
    "status": "STANDBY",
    "status_color": "#00d4ff",
    "current_song": "No music playing",
    "is_playing": False,
    "volume": 0,
    "track_progress": 0,
    "track_duration": 0,
    "weather": "Loading...",
    "time": "",
    "date": "",
    "messages": [],
    "people": [],
    "cpu": 0,
    "ram": 0,
    "mode": "HOME",
    "model": "llama-3.3-70b",
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>JARVIS HUD</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: #000;
    color: #00d4ff;
    font-family: 'Share Tech Mono', monospace;
    height: 100vh;
    overflow: hidden;
    background-image: radial-gradient(ellipse at center, #001a2e 0%, #000 70%);
  }

  .scanline {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: repeating-linear-gradient(
      0deg, transparent, transparent 2px,
      rgba(0,212,255,0.03) 2px, rgba(0,212,255,0.03) 4px
    );
    pointer-events: none;
    z-index: 100;
  }

  .grid {
    display: grid;
    grid-template-columns: 280px 1fr 280px;
    grid-template-rows: 80px 1fr 180px;
    height: 100vh;
    gap: 1px;
    padding: 8px;
  }

  /* HEADER */
  .header {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #00d4ff33;
    padding: 0 20px;
  }

  .logo {
    font-family: 'Orbitron', sans-serif;
    font-size: 28px;
    font-weight: 900;
    letter-spacing: 8px;
    color: #00d4ff;
    text-shadow: 0 0 20px #00d4ff, 0 0 40px #00d4ff55;
  }

  .status-pill {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 20px;
    border: 1px solid;
    border-radius: 30px;
    font-family: 'Orbitron', sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 3px;
    transition: all 0.3s;
  }

  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    animation: pulse 1.5s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }

  .datetime { text-align: right; font-family: 'Orbitron', sans-serif; }
  .time-display { font-size: 24px; font-weight: 700; color: #00d4ff; }
  .date-display { font-size: 11px; color: #00d4ff88; letter-spacing: 2px; }

  /* PANELS */
  .panel {
    border: 1px solid #00d4ff22;
    background: rgba(0, 20, 40, 0.6);
    padding: 16px;
    position: relative;
    overflow: hidden;
  }

  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 40px; height: 40px;
    border-top: 2px solid #00d4ff;
    border-left: 2px solid #00d4ff;
  }

  .panel::after {
    content: '';
    position: absolute;
    bottom: 0; right: 0;
    width: 40px; height: 40px;
    border-bottom: 2px solid #00d4ff;
    border-right: 2px solid #00d4ff;
  }

  .panel-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 10px;
    letter-spacing: 4px;
    color: #00d4ff88;
    margin-bottom: 12px;
    text-transform: uppercase;
  }

  /* LEFT PANEL */
  .left-panel { grid-row: 2; }

  .sys-item { margin-bottom: 14px; }

  .sys-label {
    font-size: 10px;
    color: #00d4ff66;
    letter-spacing: 2px;
    margin-bottom: 4px;
  }

  .sys-bar {
    height: 4px;
    background: #00d4ff11;
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 2px;
  }

  .sys-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #00d4ff, #0088ff);
    border-radius: 2px;
    transition: width 1s ease;
    box-shadow: 0 0 8px #00d4ff;
  }

  .sys-value {
    font-size: 18px;
    font-weight: 700;
    color: #00d4ff;
    font-family: 'Orbitron', sans-serif;
  }

  .music-info {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #00d4ff22;
  }

  .song-name {
    font-size: 13px;
    color: #fff;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  #play-icon {
    font-size: 11px;
    flex-shrink: 0;
    transition: opacity 0.3s;
  }

  .volume-bar {
    height: 3px;
    background: #00d4ff11;
    border-radius: 2px;
    margin-top: 6px;
    overflow: hidden;
  }

  .volume-fill {
    height: 100%;
    background: #00d4ff;
    border-radius: 2px;
    transition: width 0.5s;
    box-shadow: 0 0 6px #00d4ff;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #00ff88, #00d4ff);
    border-radius: 2px;
    transition: width 0.5s;
    box-shadow: 0 0 6px #00ff8888;
  }

  .track-times {
    display: flex;
    justify-content: space-between;
    margin-top: 3px;
  }

  .track-time {
    font-size: 9px;
    color: #00d4ff66;
    letter-spacing: 1px;
  }

  /* CENTER */
  .center-panel {
    grid-row: 2;
    display: flex;
    flex-direction: column;
  }

  .messages-container {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-right: 4px;
  }

  .messages-container::-webkit-scrollbar { width: 3px; }
  .messages-container::-webkit-scrollbar-track { background: transparent; }
  .messages-container::-webkit-scrollbar-thumb { background: #00d4ff44; }

  .message {
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 13px;
    line-height: 1.5;
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .message.user {
    background: rgba(0, 212, 255, 0.08);
    border-left: 2px solid #00d4ff;
    color: #fff;
    align-self: flex-start;
    max-width: 80%;
  }

  .message.user::before {
    content: 'SIR › ';
    color: #00d4ff;
    font-size: 10px;
    letter-spacing: 2px;
  }

  .message.jarvis {
    background: rgba(0, 212, 255, 0.08);
    border-left: 2px solid #00d4ff;
    color: #fff;
    align-self: flex-end;
    max-width: 85%;
  }

  .message.jarvis::before {
    content: 'JARVIS › ';
    color: #00d4ff;
    font-size: 10px;
    letter-spacing: 2px;
  }

  /* RIGHT */
  .right-panel { grid-row: 2; }

  .weather-block { margin-bottom: 20px; }

  .weather-text {
    font-size: 12px;
    color: #00ff88;
    line-height: 1.6;
  }

  .person-card {
    padding: 8px 0;
    border-bottom: 1px solid #00d4ff11;
  }

  .person-name {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    color: #00d4ff;
    letter-spacing: 2px;
  }

  .person-role {
    font-size: 10px;
    color: #00d4ff66;
    margin: 2px 0;
  }

  .person-facts {
    font-size: 10px;
    color: #ffffff55;
  }

  /* BOTTOM */
  .bottom {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px solid #00d4ff33;
    padding: 0 40px;
  }

  .mode-indicator {
    font-family: 'Orbitron', sans-serif;
    font-size: 12px;
    letter-spacing: 4px;
    color: #00d4ff;
    text-shadow: 0 0 10px #00d4ff55;
  }

  .model-indicator {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    color: #00d4ff66;
  }

  .arc-reactor {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    border: 2px solid #00d4ff44;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 20px #00d4ff55, inset 0 0 20px #00d4ff22;
    animation: reactor-pulse 2s infinite;
  }

  @keyframes reactor-pulse {
    0%, 100% { box-shadow: 0 0 20px #00d4ff55, inset 0 0 20px #00d4ff22; }
    50% { box-shadow: 0 0 40px #00d4ffaa, inset 0 0 30px #00d4ff44; }
  }

  .arc-inner {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: radial-gradient(circle, #00d4ff, #0044aa);
    box-shadow: 0 0 15px #00d4ff;
  }
</style>
</head>
<body>
<div class="scanline"></div>
<div class="grid">

  <!-- HEADER -->
  <div class="header">
    <div class="logo">J.A.R.V.I.S</div>
    <div class="status-pill" id="status-pill">
      <div class="status-dot" id="status-dot"></div>
      <span id="status-text">STANDBY</span>
    </div>
    <div class="datetime">
      <div class="time-display" id="time">00:00</div>
      <div class="date-display" id="date">--</div>
    </div>
  </div>

  <!-- LEFT -->
  <div class="panel left-panel">
    <div class="panel-title">◈ System Status</div>
    <div class="sys-item">
      <div class="sys-label">CPU LOAD</div>
      <div class="sys-bar"><div class="sys-bar-fill" id="cpu-bar" style="width:0%"></div></div>
      <div class="sys-value"><span id="cpu-val">0</span>%</div>
    </div>
    <div class="sys-item">
      <div class="sys-label">MEMORY</div>
      <div class="sys-bar"><div class="sys-bar-fill" id="ram-bar" style="width:0%"></div></div>
      <div class="sys-value"><span id="ram-val">0</span>%</div>
    </div>

    <div class="music-info">
      <div class="panel-title">◈ Audio Stream</div>
      <div class="song-name">
        <span id="play-icon" style="opacity:0.3">—</span>
        <span id="song-name">No music playing</span>
      </div>

      <div class="sys-label" style="margin-top:10px">VOLUME</div>
      <div class="volume-bar">
        <div class="volume-fill" id="vol-bar" style="width:0%"></div>
      </div>

      <div class="sys-label" style="margin-top:10px">TRACK PROGRESS</div>
      <div class="volume-bar">
        <div class="progress-fill" id="progress-bar" style="width:0%"></div>
      </div>
      <div class="track-times">
        <span class="track-time" id="progress-time">0:00</span>
        <span class="track-time" id="duration-time">0:00</span>
      </div>
    </div>
  </div>

  <!-- CENTER -->
  <div class="panel center-panel">
    <div class="panel-title">◈ Communication Log</div>
    <div class="messages-container" id="messages"></div>
  </div>

  <!-- RIGHT -->
  <div class="panel right-panel">
    <div class="panel-title">◈ Environment</div>
    <div class="weather-block">
      <div class="weather-text" id="weather">Loading weather...</div>
    </div>
    <div class="panel-title">◈ Known Individuals</div>
    <div id="people-list"></div>
  </div>

  <!-- BOTTOM -->
  <div class="bottom">
    <div class="mode-indicator">MODE: <span id="mode">HOME</span></div>
    <div class="arc-reactor"><div class="arc-inner"></div></div>
    <div class="model-indicator">AI: <span id="model-name">llama-3.3-70b</span></div>
  </div>

</div>
<script>
const socket = io();

// ── Track progress interpolation ──────────────────────────────────────────
let trackProgress  = 0;
let trackDuration  = 0;
let trackUpdatedAt = 0;
let trackPlaying   = false;

function fmtTime(ms) {
  const s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

function renderProgress() {
  if (!trackDuration) return;
  const elapsed = trackPlaying ? (Date.now() - trackUpdatedAt) : 0;
  const current = Math.min(trackProgress + elapsed, trackDuration);
  const pct = (current / trackDuration) * 100;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-time').textContent = fmtTime(current);
  document.getElementById('duration-time').textContent = fmtTime(trackDuration);
}
setInterval(renderProgress, 500);

// ── Clock ─────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById('time').textContent =
    now.toLocaleTimeString('uk-UA', {hour:'2-digit', minute:'2-digit'});
  document.getElementById('date').textContent =
    now.toLocaleDateString('en-US', {weekday:'long', day:'numeric', month:'long', year:'numeric'}).toUpperCase();
}
setInterval(updateClock, 1000);
updateClock();

// ── Status colors ─────────────────────────────────────────────────────────
const STATUS_COLORS = {
  'STANDBY':   '#00d4ff',
  'LISTENING': '#00ff88',
  'THINKING':  '#ffaa00',
  'SPEAKING':  '#ff6600',
};

function setStatus(status) {
  const color = STATUS_COLORS[status] || '#00d4ff';
  const pill  = document.getElementById('status-pill');
  const dot   = document.getElementById('status-dot');
  pill.style.borderColor = color;
  pill.style.color       = color;
  dot.style.background   = color;
  document.getElementById('status-text').textContent = status;
  dot.style.animation  = status === 'THINKING' ? 'pulse 0.4s infinite' : 'pulse 1.5s infinite';
  pill.style.boxShadow = status === 'THINKING' ? '0 0 15px #ffaa0055' : 'none';
}

// ── Play/pause icon ───────────────────────────────────────────────────────
function updatePlayIcon(isPlaying, songName) {
  const icon = document.getElementById('play-icon');
  const noMusic = !songName || songName === 'No music playing';
  if (noMusic) {
    icon.textContent = '—';
    icon.style.opacity = '0.3';
  } else if (isPlaying) {
    icon.textContent = '▶';
    icon.style.opacity = '1';
    icon.style.color = '#00ff88';
  } else {
    icon.textContent = '⏸';
    icon.style.opacity = '0.5';
    icon.style.color = '#00d4ff';
  }
}

// ── Socket events ─────────────────────────────────────────────────────────
socket.on('state_update', (data) => {

  if (data.status !== undefined)
    setStatus(data.status);

  if (data.cpu !== undefined) {
    document.getElementById('cpu-val').textContent = data.cpu;
    document.getElementById('cpu-bar').style.width = data.cpu + '%';
  }
  if (data.ram !== undefined) {
    document.getElementById('ram-val').textContent = data.ram;
    document.getElementById('ram-bar').style.width = data.ram + '%';
  }

  // Музика — спершу оновлюємо текст, потім іконку
  const songEl = document.getElementById('song-name');
  if (data.current_song !== undefined) {
    songEl.textContent = data.current_song;
    // Якщо нема музики — скидаємо прогрес одразу
    if (data.current_song === 'No music playing') {
      trackProgress = 0; trackDuration = 0; trackPlaying = false;
      document.getElementById('progress-bar').style.width = '0%';
      document.getElementById('progress-time').textContent = '0:00';
      document.getElementById('duration-time').textContent = '0:00';
    }
  }

  if (data.is_playing !== undefined) {
    trackPlaying = data.is_playing;
    updatePlayIcon(data.is_playing, songEl.textContent);
  }

  if (data.volume !== undefined)
    document.getElementById('vol-bar').style.width = data.volume + '%';

  // Прогрес трека
  if (data.track_progress !== undefined) {
    trackProgress  = data.track_progress;
    trackDuration  = data.track_duration || trackDuration;
    trackUpdatedAt = Date.now();
    trackPlaying   = data.is_playing !== undefined ? data.is_playing : trackPlaying;
    renderProgress();
  }

  // Погода
  if (data.weather) {
    var wParts = data.weather.split("|");
    var wEl = document.getElementById('weather');
    if (wParts.length >= 3) {
      wEl.innerHTML =
        '<span style="font-family:Orbitron,sans-serif;font-size:13px;letter-spacing:2px;color:#00d4ff">' + wParts[0] + '</span><br>' +
        '<span>' + wParts[1] + '</span><br>' +
        '<span style="color:#00d4ff88">' + wParts[2] + '</span>';
    } else {
      wEl.textContent = data.weather;
    }
  }

  // Режим
  if (data.mode) {
    document.getElementById('mode').textContent = data.mode;
    const modeEl = document.querySelector('.mode-indicator');
    modeEl.style.color      = data.mode === 'IRON MAN' ? '#ff4400' : '#00d4ff';
    modeEl.style.textShadow = data.mode === 'IRON MAN' ? '0 0 10px #ff440055' : '0 0 10px #00d4ff55';
  }

  if (data.model)
    document.getElementById('model-name').textContent = data.model;

  // Люди
  if (data.people) {
    document.getElementById('people-list').innerHTML = data.people.map(p => `
      <div class="person-card">
        <div class="person-name">${p.name.toUpperCase()}</div>
        <div class="person-role">${p.relationship || 'unknown'}</div>
        <div class="person-facts">${(p.facts || []).slice(0,2).join(' · ') || '—'}</div>
      </div>
    `).join('');
  }

  // Нове повідомлення
  if (data.new_message) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message ' + data.new_message.role;
    div.textContent = data.new_message.text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    while (container.children.length > 50)
      container.removeChild(container.firstChild);
  }
});
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


def update_hud(key: str, value):
    """Оновлює одне поле HUD і надсилає всім клієнтам."""
    hud_state[key] = value
    socketio.emit('state_update', {key: value})


def add_message(role: str, text: str):
    """Додає повідомлення в лог розмови."""
    socketio.emit('state_update', {'new_message': {'role': role, 'text': text}})


def _system_monitor():
    """Фоновий потік — оновлює CPU/RAM кожні 3 секунди."""
    while True:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        socketio.emit('state_update', {'cpu': cpu, 'ram': ram})
        time.sleep(3)


def run_hud():
    """Запускає Flask сервер і відкриває браузер."""
    import webbrowser
    threading.Thread(target=_system_monitor, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False, log_output=False)