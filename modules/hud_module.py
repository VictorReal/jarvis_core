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
    "next_event": None,
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>JARVIS HUD</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --hud-accent: #00d4ff;
    --hud-accent2: #00ff88;
    --hud-accent-dim: #00d4ff88;
    --hud-accent-faint: #00d4ff22;
    --hud-accent-trace: #00d4ff11;
    --hud-glow: #00d4ff55;
    --hud-bg: #003355;
    --reactor-color1: #00d4ff;
    --reactor-color2: #0044aa;
  }

  body.ultron-mode {
    --hud-accent: #ff2200;
    --hud-accent2: #ff6600;
    --hud-accent-dim: #ff220088;
    --hud-accent-faint: #ff220022;
    --hud-accent-trace: #ff220011;
    --hud-glow: #ff220055;
    --hud-bg: #1a0000;
    --reactor-color1: #ff2200;
    --reactor-color2: #660000;
  }

  body {
    background: #000;
    color: var(--hud-accent);
    font-family: 'Share Tech Mono', monospace;
    height: 100vh;
    overflow: hidden;
    background-image: radial-gradient(ellipse at center, var(--hud-bg) 0%, #000 70%);
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
    grid-template-rows: 80px 1fr 80px;
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
    border-bottom: 1px solid var(--hud-accent-faint);
    padding: 0 20px;
    position: sticky;
    top: 0;
    z-index: 50;
    background: #000;
  }

  .logo {
    font-family: 'Orbitron', sans-serif;
    font-size: 28px;
    font-weight: 900;
    letter-spacing: 8px;
    color: var(--hud-accent);
    text-shadow: 0 0 20px var(--hud-accent), 0 0 40px var(--hud-glow);
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
  .time-display { font-size: 24px; font-weight: 700; color: var(--hud-accent); }
  .date-display { font-size: 11px; color: var(--hud-accent-dim); letter-spacing: 2px; }

  /* PANELS */
  .panel {
    border: 1px solid var(--hud-accent-faint);
    background: rgba(0, 10, 20, 0.6);
    padding: 16px;
    position: relative;
    overflow: hidden;
  }

  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 40px; height: 40px;
    border-top: 2px solid var(--hud-accent);
    border-left: 2px solid var(--hud-accent);
  }

  .panel::after {
    content: '';
    position: absolute;
    bottom: 0; right: 0;
    width: 40px; height: 40px;
    border-bottom: 2px solid var(--hud-accent);
    border-right: 2px solid var(--hud-accent);
  }

  .panel-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 10px;
    letter-spacing: 4px;
    color: var(--hud-accent-dim);
    margin-bottom: 12px;
    text-transform: uppercase;
  }

  /* LEFT PANEL */
  .left-panel { grid-row: 2; grid-column: 1; }

  .sys-item { margin-bottom: 14px; }

  .sys-label {
    font-size: 10px;
    color: var(--hud-accent-dim);
    letter-spacing: 2px;
    margin-bottom: 4px;
  }

  .sys-bar {
    height: 4px;
    background: var(--hud-accent-trace);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 2px;
  }

  .sys-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--hud-accent), #0055cc);
    border-radius: 2px;
    transition: width 1s ease;
    box-shadow: 0 0 8px var(--hud-accent);
  }

  .sys-value {
    font-size: 18px;
    font-weight: 700;
    color: var(--hud-accent);
    font-family: 'Orbitron', sans-serif;
  }

  .music-info {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--hud-accent-faint);
    max-height: 140px;
    overflow: hidden;
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
    background: var(--hud-accent-trace);
    border-radius: 2px;
    margin-top: 6px;
    overflow: hidden;
  }

  .volume-fill {
    height: 100%;
    background: var(--hud-accent);
    border-radius: 2px;
    transition: width 0.5s;
    box-shadow: 0 0 6px var(--hud-accent);
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
    color: var(--hud-accent-dim);
    letter-spacing: 1px;
  }

  /* CENTER */
  .center-panel {
    grid-row: 2;
    grid-column: 2;
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
  .messages-container::-webkit-scrollbar-thumb { background: var(--hud-accent-dim); }

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
    background: var(--hud-accent-trace);
    border-left: 2px solid var(--hud-accent);
    color: #fff;
    align-self: flex-start;
    max-width: 80%;
  }

  .message.user::before {
    content: 'SIR › ';
    color: var(--hud-accent);
    font-size: 10px;
    letter-spacing: 2px;
  }

  .message.jarvis {
    background: var(--hud-accent-trace);
    border-left: 2px solid var(--hud-accent);
    color: #fff;
    align-self: flex-end;
    max-width: 85%;
  }

  .message.jarvis::before {
    content: 'JARVIS › ';
    color: var(--hud-accent);
    font-size: 10px;
    letter-spacing: 2px;
  }

  /* RIGHT */
  .right-panel { grid-row: 2; grid-column: 3; }

  .weather-block { margin-bottom: 20px; }

  .weather-text {
    font-size: 12px;
    color: #00ff88;
    line-height: 1.6;
  }

  .person-card {
    padding: 8px 0;
    border-bottom: 1px solid var(--hud-accent-trace);
  }
  
  #people-list::-webkit-scrollbar { width: 3px; }
  #people-list::-webkit-scrollbar-track { background: transparent; }
  #people-list::-webkit-scrollbar-thumb { background: var(--hud-accent-dim); }

  .person-name {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    color: var(--hud-accent);
    letter-spacing: 2px;
  }

  .person-role {
    font-size: 10px;
    color: var(--hud-accent-dim);
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
    border-top: 1px solid var(--hud-accent-faint);
    padding: 0 40px;
    position: sticky;
    bottom: 0;
    z-index: 50;
    background: #000;
  }

  .mode-indicator {
    font-family: 'Orbitron', sans-serif;
    font-size: 12px;
    letter-spacing: 4px;
    color: var(--hud-accent);
    text-shadow: 0 0 10px var(--hud-glow);
  }

  .model-indicator {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--hud-accent-dim);
  }

  .reminders-list { margin-top: 4px; }

  .reminder-item {
    padding: 5px 0;
    border-bottom: 1px solid var(--hud-accent-trace);
    font-size: 11px;
    color: #00ff88;
  }

  .reminder-item .r-time {
    color: var(--hud-accent-dim);
    font-size: 10px;
    margin-left: 4px;
  }

  .log-list {
    max-height: 140px;
    overflow-y: auto;
    margin-top: 4px;
  }

  .log-list::-webkit-scrollbar { width: 2px; }
  .log-list::-webkit-scrollbar-thumb { background: var(--hud-accent-dim); }

  .log-item {
    padding: 3px 0;
    border-bottom: 1px solid var(--hud-accent-trace);
    font-size: 10px;
    line-height: 1.4;
  }

  .log-item .log-time { color: var(--hud-accent-dim); margin-right: 4px; }
  .log-item .log-user { color: #aaa; }
  .log-item .log-jarvis { color: #fff; }

  .arc-reactor {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    border: 2px solid var(--hud-accent-dim);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 20px var(--hud-glow), inset 0 0 20px var(--hud-accent-faint);
    animation: reactor-pulse 2s infinite;
  }

  @keyframes reactor-pulse {
    0%, 100% { box-shadow: 0 0 20px var(--hud-glow), inset 0 0 20px var(--hud-accent-faint); }
    50% { box-shadow: 0 0 40px var(--hud-accent), inset 0 0 30px var(--hud-accent-faint); }
  }

  .arc-inner {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: radial-gradient(circle, var(--reactor-color1), var(--reactor-color2));
    box-shadow: 0 0 15px var(--hud-accent);
  }

  /* ── MOBILE ─────────────────────────────────────────────────────────── */
  @media (max-width: 768px) {

    body { overflow: auto; height: auto; }

    .grid {
      grid-template-columns: 1fr;
      grid-template-rows: 60px auto auto auto 70px;
      height: auto;
      min-height: 100vh;
      padding: 4px;
      gap: 4px;
    }

    /* Header — менший на мобільному */
    .header {
      padding: 0 12px;
      position: sticky;
    }
    .logo { font-size: 18px; letter-spacing: 4px; }
    .time-display { font-size: 16px; }
    .date-display { font-size: 9px; }
    .status-pill { padding: 5px 12px; font-size: 11px; }

    /* Left panel — system + audio */
    .left-panel {
      grid-row: 2;
      grid-column: 1;
      max-height: 180px;
    }

    /* Center panel — communication log, головний на мобільному */
    .center-panel {
      grid-row: 3;
      grid-column: 1;
      min-height: 280px;
    }

    /* Right panel — environment */
    .right-panel {
      grid-row: 4;
      grid-column: 1;
      max-height: 200px;
    }

    /* Bottom */
    .bottom {
      grid-row: 5;
      grid-column: 1;
      padding: 0 16px;
      position: sticky;
    }
    .mode-indicator { font-size: 10px; letter-spacing: 2px; }
    .model-indicator { font-size: 9px; letter-spacing: 1px; }
    .arc-reactor { width: 48px; height: 48px; }
    .arc-inner { width: 22px; height: 22px; }

    /* Ховаємо зайве на мобільному */
    #people-list,
    .log-list,
    .reminders-list { display: none; }

    /* Повідомлення — більший шрифт */
    .message { font-size: 13px; padding: 6px 10px; }

    /* Панель кутки менші */
    .panel::before, .panel::after { width: 20px; height: 20px; }

    /* Sys bars компактніші */
    .sys-value { font-size: 14px; }
    .sys-item { margin-bottom: 6px; }
    .music-info { max-height: 80px; }
  }
</style>
</head>
<body>
<div class="scanline"></div>

<div id="sleep-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:#000;z-index:999;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;" onclick="this.style.display='none'">
  <div style="font-family:'Orbitron',sans-serif;font-size:18px;letter-spacing:8px;color:#00d4ff18;">S L E E P</div>
  <div style="font-size:10px;color:#00d4ff10;margin-top:12px;letter-spacing:4px;">CLICK TO WAKE</div>
</div>

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

  <!-- LEFT — System + Audio + Reminders -->
  <div class="panel left-panel" style="display:flex;flex-direction:column;overflow:hidden;">
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

    <div style="margin-top:auto;padding-top:10px;border-top:1px solid #00d4ff22;">
      <div class="panel-title">◈ Active Reminders</div>
      <div class="reminders-list" id="reminders-list">
        <div style="font-size:11px;color:#00d4ff33">No active reminders</div>
      </div>
    </div>
  </div>

  <!-- CENTER -->
  <div class="panel center-panel">
    <div class="panel-title">◈ Communication Log</div>
    <div class="messages-container" id="messages"></div>
  </div>

  <!-- RIGHT — Environment + Known Individuals + Activity Log -->
  <div class="panel right-panel" style="display:flex;flex-direction:column;overflow:hidden;">
    <div class="panel-title">◈ Environment</div>
    <div class="weather-block">
      <div class="weather-text" id="weather">Loading weather...</div>
    </div>
    <div class="panel-title" style="margin-top:12px">◈ Next Event</div>
    <div id="next-event-block" style="margin-bottom:12px;">
      <div id="next-event-title" style="font-size:13px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">—</div>
      <div id="next-event-time" style="font-size:11px;color:#00d4ff88;margin-top:3px;letter-spacing:1px;">—</div>
      <div id="next-event-loc" style="font-size:10px;color:#00d4ff55;margin-top:2px;"></div>
    </div>
    <div class="panel-title" style="margin-top:12px">◈ Known Individuals</div>
    <div id="people-list" style="flex:1;overflow-y:auto;"></div>
    <div style="border-top:1px solid #00d4ff22;padding-top:8px;margin-top:8px;">
      <div class="panel-title">◈ Activity Log</div>
      <div class="log-list" id="log-list" style="max-height:120px;overflow-y:auto;"></div>
    </div>
  </div>

  <!-- BOTTOM -->
  <div class="bottom">
    <div class="mode-indicator">MODE: <span id="mode">HOME</span></div>
    <div class="arc-reactor"><div class="arc-inner"></div></div>
    <div class="model-indicator">AI: <span id="model-name">{{ model }}</span></div>
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
    if (data.mode === 'ULTRON') {
      document.body.classList.add('ultron-mode');
      document.querySelector('.logo').textContent = 'U.L.T.R.O.N';
      modeEl.style.color      = '#ff2200';
      modeEl.style.textShadow = '0 0 10px #ff220055';
    } else if (data.mode === 'IRON MAN') {
      document.body.classList.remove('ultron-mode');
      document.querySelector('.logo').textContent = 'J.A.R.V.I.S';
      modeEl.style.color      = '#ff4400';
      modeEl.style.textShadow = '0 0 10px #ff440055';
    } else {
      document.body.classList.remove('ultron-mode');
      document.querySelector('.logo').textContent = 'J.A.R.V.I.S';
      modeEl.style.color      = 'var(--hud-accent)';
      modeEl.style.textShadow = '0 0 10px var(--hud-glow)';
    }
  }

  if (data.model) {
    const short = data.model.includes('/') ? data.model.split('/').pop() : data.model;
    document.getElementById('model-name').textContent = short;
  }

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

  // Активні нагадування
  if (data.reminders !== undefined) {
    const rEl = document.getElementById('reminders-list');
    if (!data.reminders || data.reminders.length === 0) {
      rEl.innerHTML = '<div style="font-size:11px;color:#00d4ff33">No active reminders</div>';
    } else {
      rEl.innerHTML = data.reminders.map(r =>
        '<div class="reminder-item">🔔 ' + r.message +
        '<span class="r-time">' + r.time_left + '</span></div>'
      ).join('');
    }
  }

  // Лог дня
  if (data.log_entry) {
    const logEl = document.getElementById('log-list');
    const div = document.createElement('div');
    div.className = 'log-item';
    div.innerHTML =
      '<span class="log-time">' + data.log_entry.time + '</span>' +
      '<span class="log-' + data.log_entry.role + '">' +
      (data.log_entry.role === 'user' ? 'SIR: ' : 'J: ') +
      data.log_entry.text.substring(0, 80) + (data.log_entry.text.length > 80 ? '…' : '') +
      '</span>';
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
    while (logEl.children.length > 30)
      logEl.removeChild(logEl.firstChild);
  }

  // Next Calendar Event
  if (data.next_event !== undefined) {
    if (!data.next_event) {
      document.getElementById('next-event-title').textContent = 'No upcoming events';
      document.getElementById('next-event-time').textContent = '—';
      document.getElementById('next-event-loc').textContent = '';
    } else {
      document.getElementById('next-event-title').textContent = data.next_event.title || '—';
      document.getElementById('next-event-time').textContent = data.next_event.time_label || '—';
      document.getElementById('next-event-loc').textContent = data.next_event.location || '';
    }
  }

  // Sleep mode
  if (data.sleep === true) {
    document.getElementById('sleep-overlay').style.display = 'flex';
  }
  if (data.sleep === false) {
    document.getElementById('sleep-overlay').style.display = 'none';
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
    model = hud_state.get("model", "llama-3.3-70b")
    # Скорочуємо довгі назви типу meta-llama/llama-4-scout-17b-16e-instruct
    short = model.split("/")[-1] if "/" in model else model
    return render_template_string(HTML_TEMPLATE, model=short)


@socketio.on('connect')
def on_connect():
    """При підключенні нового клієнта — відправляємо весь поточний стан."""
    socketio.emit('state_update', {
        'status':         hud_state.get('status', 'STANDBY'),
        'weather':        hud_state.get('weather', ''),
        'mode':           hud_state.get('mode', 'HOME'),
        'model':          hud_state.get('model', ''),
        'cpu':            hud_state.get('cpu', 0),
        'ram':            hud_state.get('ram', 0),
        'current_song':   hud_state.get('current_song', 'No music playing'),
        'is_playing':     hud_state.get('is_playing', False),
        'volume':         hud_state.get('volume', 0),
        'track_progress': hud_state.get('track_progress', 0),
        'track_duration': hud_state.get('track_duration', 0),
        'next_event':     hud_state.get('next_event'),
        'reminders':      hud_state.get('reminders', []),
    })


def update_hud(key: str, value):
    """Оновлює одне поле HUD і надсилає всім клієнтам."""
    hud_state[key] = value
    socketio.emit('state_update', {key: value})


def update_reminders(reminders: list):
    """Оновлює панель активних нагадувань. reminders = [{message, time_left}]"""
    socketio.emit('state_update', {'reminders': reminders})


def update_calendar(event: dict | None):
    """
    Оновлює блок наступної події.
    event = {title, time_label, location} або None якщо нема подій.
    """
    hud_state["next_event"] = event
    socketio.emit('state_update', {'next_event': event})


def _calendar_poller():
    """Фоновий потік — оновлює наступну подію з Calendar кожні 2 хвилини."""
    import time as _time
    _time.sleep(5)  # чекаємо поки все запуститься
    while True:
        try:
            from modules.calendar_module import CalendarModule
            from datetime import datetime, timezone, timedelta
            cal = CalendarModule()
            events = cal.get_upcoming(hours=12, max_results=1)
            if events:
                ev = events[0]
                # Рахуємо скільки часу залишилось
                try:
                    start_dt = datetime.fromisoformat(ev["start_raw"])
                    now = datetime.now(timezone.utc)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    diff = start_dt - now
                    mins = int(diff.total_seconds() / 60)
                    if mins < 0:
                        label = ev["start"]
                    elif mins < 60:
                        label = f"in {mins}m  ·  {ev['start']}"
                    else:
                        hrs = mins // 60
                        label = f"in {hrs}h {mins % 60}m  ·  {ev['start']}"
                except Exception:
                    label = ev["start"]
                update_calendar({
                    "title": ev["title"],
                    "time_label": label,
                    "location": ev.get("location", ""),
                })
            else:
                update_calendar(None)
        except Exception as e:
            pass  # Calendar може бути недоступний — мовчки пропускаємо
        _time.sleep(120)  # кожні 2 хвилини


def log_to_hud(role: str, text: str):
    """Додає запис в лог дня на HUD."""
    from datetime import datetime
    socketio.emit('state_update', {
        'log_entry': {
            'role': role,
            'text': text,
            'time': datetime.now().strftime('%H:%M'),
        }
    })


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
    threading.Thread(target=_calendar_poller, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False, log_output=False)