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
    min-width: 160px;
    justify-content: center;
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
  .header-right { display: flex; align-items: center; gap: 16px; }
  .cc-blink {
    font-size: 24px;
    cursor: pointer;
    user-select: none;
    line-height: 1;
    transition: transform 0.2s, filter 0.2s;
    filter: drop-shadow(0 0 5px var(--hud-glow));
  }
  .cc-blink:hover {
    transform: scale(1.18);
    filter: drop-shadow(0 0 12px var(--hud-accent));
  }
  @media (max-width: 768px) {
    .cc-blink { font-size: 19px; margin-left: 15px;}
  }

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
    margin-bottom: 8px;
    text-transform: uppercase;
  }

  /* LEFT PANEL */
  .left-panel { grid-row: 2; grid-column: 1; }

  .sys-item { margin-bottom: 10px; }

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
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--hud-accent-faint);
    max-height: 140px;
    overflow: hidden;
  }
  .left-panel, .right-panel, .music-info, .song-name { min-width: 0; }

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
    min-width: 0;
    max-width: 100%;
  }
  
  #song-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
      display: block;
  max-width: 100%;
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

  .message.ultron {
    background: rgba(255,34,0,0.06);
    border-left: 2px solid #ff2200;
    color: #fff;
    align-self: flex-end;
    max-width: 85%;
  }

  .message.ultron::before {
    content: 'ULTRON › ';
    color: #ff2200;
    font-size: 10px;
    letter-spacing: 2px;
  }

  /* RIGHT */
  .right-panel { grid-row: 2; grid-column: 3; }

  /* ── РІВНИЙ РИТМ СЕКЦІЙ ПРАВОЇ КОЛОНКИ ───────────────────────────
     Єдиний відступ над КОЖНИМ заголовком секції замість різних
     inline margin-top. Перший заголовок (Environment) — без відступу. */
  .right-panel .panel-title { margin-top: 17px; margin-bottom: 7px; }
  .right-panel > .panel-title:first-child { margin-top: 0; }
  /* перебиваємо inline margin-top:8px на Health/Finance/Mood/Individuals */
  .right-panel .panel-title[style] { margin-top: 17px !important; }
  /* міні-панелі тулимо щільно до свого заголовка */
  .right-panel .health-mini,
  .right-panel .people-mini { margin-top: 0; }

  .weather-block { margin-bottom: 2px; }

  .weather-text {
    font-size: 12px;
    color: #00ff88;
    line-height: 1.6;
  }

  .person-card {
    padding: 8px 0;
    border-bottom: 1px solid var(--hud-accent-trace);
  }

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

  /* ── PEOPLE MINI + MODAL ───────────────────────────────────────── */
  .people-mini {
    margin-top: 12px;
    padding: 8px 10px;
    border: 1px solid var(--hud-accent-faint);
    border-radius: 3px;
    cursor: pointer;
    transition: all 0.2s;
    background: var(--hud-accent-trace);
  }
  .people-mini:hover {
    background: var(--hud-accent-faint);
    box-shadow: 0 0 10px var(--hud-glow);
  }
  .people-mini-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .people-mini-count {
    font-family: 'Orbitron', sans-serif;
    font-size: 9px;
    letter-spacing: 3px;
    color: var(--hud-accent-dim);
  }
  .people-mini-count .num {
    color: var(--hud-accent);
    font-size: 14px;
    font-weight: 700;
  }
  .people-mini-list {
    font-size: 10px;
    color: var(--hud-accent-dim);
    line-height: 1.5;
  }
  .people-mini-list .pm-name {
    color: #fff;
  }

  /* People modal — переюзить health-стилі */
  #people-modal .health-modal-inner { max-width: 1100px; }

  .people-search {
    width: 100%;
    background: var(--hud-accent-trace);
    border: 1px solid var(--hud-accent-faint);
    color: #fff;
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    padding: 10px 14px;
    margin-bottom: 18px;
    border-radius: 2px;
    outline: none;
    letter-spacing: 1px;
  }
  .people-search:focus {
    border-color: var(--hud-accent);
    box-shadow: 0 0 10px var(--hud-glow);
  }
  .people-search::placeholder { color: var(--hud-accent-dim); }

  .people-group { margin-bottom: 22px; }
  .people-group-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--hud-accent);
    text-transform: uppercase;
    padding-bottom: 6px;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--hud-accent-faint);
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .people-group-title .pg-count {
    font-size: 10px;
    color: var(--hud-accent-dim);
    letter-spacing: 2px;
  }
  .people-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }
  .people-detail-card {
    border: 1px solid var(--hud-accent-faint);
    background: var(--hud-accent-trace);
    padding: 14px 16px;
    position: relative;
  }
  .people-detail-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 16px; height: 16px;
    border-top: 2px solid var(--hud-accent);
    border-left: 2px solid var(--hud-accent);
  }
  .people-detail-card .pdc-name {
    font-family: 'Orbitron', sans-serif;
    font-size: 13px;
    color: var(--hud-accent);
    letter-spacing: 2px;
    margin-bottom: 4px;
    text-shadow: 0 0 6px var(--hud-glow);
  }
  .people-detail-card .pdc-rel {
    font-size: 10px;
    color: var(--hud-accent-dim);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .people-detail-card .pdc-facts {
    font-size: 11px;
    color: #fff;
    line-height: 1.5;
  }
  .people-detail-card .pdc-fact {
    padding: 2px 0;
    border-bottom: 1px dotted var(--hud-accent-trace);
  }
  .people-detail-card .pdc-fact:last-child { border-bottom: none; }
  .people-detail-card .pdc-empty {
    color: var(--hud-accent-dim);
    font-style: italic;
  }

  .people-empty {
    text-align: center;
    padding: 40px;
    color: var(--hud-accent-dim);
    font-size: 12px;
    letter-spacing: 2px;
  }

  @media (max-width: 768px) {
    .people-cards { grid-template-columns: 1fr; }
  }

  /* BOTTOM */
  .bottom {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    border-top: 1px solid var(--hud-accent-faint);
    padding: 0 20px;
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
    justify-self: start;
    white-space: nowrap;
  }

  .model-indicator {
    font-family: 'Orbitron', sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    color: var(--hud-accent-dim);
    justify-self: end;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
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

    .header { padding: 0 12px; position: sticky; gap: inherit; }
    .logo { font-size: 16px; letter-spacing: 3px; }
    .time-display { font-size: 16px; }
    .date-display { font-size: 9px; }
    .status-pill { padding: 5px 8px; font-size: 9px; letter-spacing: 2px; min-width: unset; }
    .header-right { display: flex; align-items: center; gap: 5px; }
    
    /* Панелі: природна висота, БЕЗ обрізання (раніше max-height+hidden ховали секції) */
    .left-panel, .right-panel {
      grid-column: 1;
      max-height: none !important;
      overflow: visible !important;
    }
    .left-panel  { grid-row: 2; }
    .center-panel { grid-row: 3; grid-column: 1; min-height: 280px; }
    .right-panel { grid-row: 4; }

    .bottom { grid-row: 5; grid-column: 1; padding: 0 12px; position: sticky; }
    .mode-indicator { font-size: 9px; letter-spacing: 2px; }
    .model-indicator { font-size: 8px; letter-spacing: 1px; max-width: 120px; }
    .arc-reactor { width: 48px; height: 48px; }
    .arc-inner { width: 22px; height: 22px; }

    /* ── АКОРДЕОН-СЕКЦІЇ ─── JS робить заголовки клікабельними картками */
    .panel-title.m-head {
      cursor: pointer;
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 12px; margin: 4px 0 0 !important;
      border: 1px solid var(--hud-accent-faint);
      border-radius: 4px; background: var(--hud-accent-trace);
      font-size: 11px;
    }
    .panel-title.m-head::after {
      content: "▸"; font-size: 10px; transition: transform 0.2s; opacity: 0.7;
    }
    .panel-title.m-head.open::after { transform: rotate(90deg); }
    .m-head .m-preview {
      font-size: 9px; color: var(--hud-accent2); letter-spacing: 1px;
      margin-left: auto; margin-right: 8px; max-width: 45%;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .m-section-body {
      overflow: hidden; max-height: 1500px;
      transition: max-height 0.25s ease, opacity 0.2s;
      padding: 8px 4px 4px;
    }
    .m-section-body.collapsed {
      max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0;
    }
    /* На мобільному показуємо log і reminders (раніше display:none) */
    .log-list { display: block; max-height: 160px; }
    .reminders-list { display: block; }

    .panel::before, .panel::after { width: 20px; height: 20px; }
    .sys-value { font-size: 14px; }
    .sys-item { margin-bottom: 6px; }
    .music-info { max-height: none; }

  }
  .health-mini {
margin-top: 6px;
padding: 8px 10px;
border: 1px solid var(--hud-accent-faint);
border-radius: 3px;
cursor: pointer;
transition: all 0.2s;
background: var(--hud-accent-trace);
}
.health-mini:hover {
background: var(--hud-accent-faint);
box-shadow: 0 0 10px var(--hud-glow);
}
.health-mini-title {
font-family: 'Orbitron', sans-serif;
font-size: 9px;
letter-spacing: 3px;
color: var(--hud-accent-dim);
margin-bottom: 6px;
display: flex;
justify-content: space-between;
align-items: center;
}
.health-mini-title .open-hint {
font-size: 8px;
color: var(--hud-accent-dim);
letter-spacing: 1px;
}
.health-mini-row {
display: grid;
grid-template-columns: 1fr 1fr 1fr;
gap: 8px;
font-family: 'Share Tech Mono', monospace;
}
.health-mini-stat {
text-align: center;
border-right: 1px solid var(--hud-accent-trace);
}
.health-mini-stat:last-child { border-right: none; }
.health-mini-stat .value {
font-family: 'Orbitron', sans-serif;
font-size: 16px;
font-weight: 700;
color: var(--hud-accent);
text-shadow: 0 0 6px var(--hud-glow);
}
.health-mini-stat .label {
font-size: 8px;
letter-spacing: 1px;
color: var(--hud-accent-dim);
margin-top: 2px;
text-transform: uppercase;
}
.health-mini-stat .sub {
font-size: 8px;
color: var(--hud-accent-dim);
margin-top: 1px;
white-space: nowrap;
overflow: hidden;
text-overflow: ellipsis;
}
.health-mini-stat { min-width: 0; }
/* MODAL */
.health-modal {
display: none;
position: fixed;
inset: 0;
background: rgba(0, 5, 15, 0.96);
z-index: 500;
overflow-y: auto;
backdrop-filter: blur(4px);
}
.health-modal.open { display: block; }
.health-modal::-webkit-scrollbar { width: 3px; }
.health-modal::-webkit-scrollbar-track { background: transparent; }
.health-modal::-webkit-scrollbar-thumb { background: var(--hud-accent-dim); border-radius: 2px; }
.health-modal::-webkit-scrollbar-thumb:hover { background: var(--hud-accent); }
.health-modal-inner {
max-width: 1400px;
margin: 0 auto;
padding: 28px 32px;
}
.health-modal-header {
display: flex;
justify-content: space-between;
align-items: center;
margin-bottom: 24px;
padding-bottom: 14px;
border-bottom: 1px solid var(--hud-accent-faint);
}
.health-modal-title {
font-family: 'Orbitron', sans-serif;
font-size: 22px;
font-weight: 900;
letter-spacing: 6px;
color: var(--hud-accent);
text-shadow: 0 0 15px var(--hud-glow);
}
.health-modal-close {
background: transparent;
border: 1px solid var(--hud-accent-dim);
color: var(--hud-accent);
font-family: 'Orbitron', sans-serif;
font-size: 11px;
letter-spacing: 2px;
padding: 8px 16px;
cursor: pointer;
border-radius: 2px;
transition: all 0.2s;
}
.health-modal-close:hover {
background: var(--hud-accent-faint);
box-shadow: 0 0 10px var(--hud-glow);
}
.period-tabs {
display: flex;
gap: 8px;
margin-bottom: 20px;
}
.period-tab {
flex: 1;
background: transparent;
border: 1px solid var(--hud-accent-faint);
color: var(--hud-accent-dim);
font-family: 'Orbitron', sans-serif;
font-size: 11px;
letter-spacing: 3px;
padding: 10px;
cursor: pointer;
transition: all 0.2s;
text-transform: uppercase;
}
.period-tab:hover { color: var(--hud-accent); border-color: var(--hud-accent-dim); }
.period-tab.active {
background: var(--hud-accent-faint);
color: var(--hud-accent);
border-color: var(--hud-accent);
box-shadow: 0 0 12px var(--hud-glow);
}
.health-summary-grid {
display: grid;
grid-template-columns: repeat(4, 1fr);
gap: 14px;
margin-bottom: 24px;
}
.summary-card {
border: 1px solid var(--hud-accent-faint);
background: var(--hud-accent-trace);
padding: 14px 16px;
position: relative;
overflow: hidden;
}
.summary-card::before {
content: '';
position: absolute;
top: 0; left: 0;
width: 20px; height: 20px;
border-top: 2px solid var(--hud-accent);
border-left: 2px solid var(--hud-accent);
}
.summary-card .icon {
font-size: 16px;
margin-bottom: 4px;
}
.summary-card .card-title {
font-family: 'Orbitron', sans-serif;
font-size: 9px;
letter-spacing: 2px;
color: var(--hud-accent-dim);
text-transform: uppercase;
margin-bottom: 8px;
}
.summary-card .card-main {
font-family: 'Orbitron', sans-serif;
font-size: 22px;
font-weight: 700;
color: var(--hud-accent);
text-shadow: 0 0 8px var(--hud-glow);
margin-bottom: 4px;
}
.summary-card .card-sub {
font-size: 10px;
color: var(--hud-accent-dim);
line-height: 1.5;
}
.health-charts-grid {
display: grid;
grid-template-columns: 1fr 1fr;
gap: 16px;
margin-bottom: 20px;
}
.chart-card {
border: 1px solid var(--hud-accent-faint);
background: var(--hud-accent-trace);
padding: 12px;
position: relative;
}
.chart-card .chart-title {
font-family: 'Orbitron', sans-serif;
font-size: 10px;
letter-spacing: 3px;
color: var(--hud-accent-dim);
margin-bottom: 10px;
text-transform: uppercase;
}
.chart-card img {
width: 100%;
height: auto;
display: block;
border-radius: 2px;
}
.chart-loading {
color: var(--hud-accent-dim);
font-size: 11px;
padding: 40px;
text-align: center;
}
.health-actions {
display: flex;
justify-content: flex-end;
gap: 10px;
margin-top: 20px;
}
.health-btn {
background: transparent;
border: 1px solid var(--hud-accent-dim);
color: var(--hud-accent);
font-family: 'Orbitron', sans-serif;
font-size: 11px;
letter-spacing: 2px;
padding: 10px 18px;
cursor: pointer;
border-radius: 2px;
transition: all 0.2s;
}
.health-btn:hover {
background: var(--hud-accent-faint);
box-shadow: 0 0 10px var(--hud-glow);
}
.health-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── INSIGHTS блок під графіками (спільний для всіх модалів) ───────── */
.insights-box {
  margin-top: 20px;
  border: 1px solid var(--hud-accent-faint);
  border-radius: 4px;
  background: var(--hud-accent-trace);
  padding: 16px 18px;
}
.insights-title {
  font-family: 'Orbitron', sans-serif;
  font-size: 11px;
  letter-spacing: 3px;
  color: var(--hud-accent);
  text-transform: uppercase;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.insights-list { list-style: none; padding: 0; margin: 0; }
.insights-list li {
  font-size: 12px;
  color: #d4e8ff;
  line-height: 1.5;
  padding: 6px 0 6px 18px;
  position: relative;
  border-bottom: 1px solid var(--hud-accent-trace);
}
.insights-list li:last-child { border-bottom: none; }
.insights-list li::before {
  content: "▸";
  position: absolute;
  left: 0;
  color: var(--hud-accent2);
}
.insights-empty { font-size: 12px; color: var(--hud-accent-dim); font-style: italic; }

/* ── MOOD quick-log ─────────────────────────────────────────────── */
.mood-log-box {
  border: 1px solid var(--hud-accent-faint);
  border-radius: 4px;
  padding: 14px;
  margin-bottom: 16px;
  background: var(--hud-accent-trace);
}
.mood-log-label {
  font-family: 'Orbitron', sans-serif;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--hud-accent-dim);
  margin-bottom: 8px;
}
.mood-score-row { display: flex; gap: 5px; flex-wrap: wrap; }
.mood-score {
  flex: 1;
  min-width: 30px;
  text-align: center;
  padding: 8px 0;
  border: 1px solid var(--hud-accent-dim);
  border-radius: 2px;
  color: var(--hud-accent);
  cursor: pointer;
  font-family: 'Share Tech Mono', monospace;
  font-size: 14px;
  transition: all 0.15s;
}
.mood-score:hover { background: var(--hud-accent-faint); }
.mood-score.selected {
  background: var(--hud-accent);
  color: #000;
  box-shadow: 0 0 10px var(--hud-glow);
}
.mood-tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.mood-tag-chip {
  padding: 4px 10px;
  border: 1px solid var(--hud-accent-dim);
  border-radius: 12px;
  font-size: 11px;
  color: var(--hud-accent-dim);
  cursor: pointer;
  transition: all 0.15s;
}
.mood-tag-chip:hover { color: var(--hud-accent); }
.mood-tag-chip.selected {
  background: var(--hud-accent-faint);
  color: var(--hud-accent2);
  border-color: var(--hud-accent2);
}
.mood-note-input {
  width: 100%;
  margin-top: 10px;
  background: transparent;
  border: 1px solid var(--hud-accent-dim);
  border-radius: 2px;
  color: var(--hud-accent);
  padding: 8px;
  font-family: 'Share Tech Mono', monospace;
  font-size: 12px;
}
.mood-note-input::placeholder { color: var(--hud-accent-dim); }
.mood-log-box .health-btn { margin-top: 10px; }
.mood-log-status { font-size: 11px; color: var(--hud-accent2); margin-top: 8px; min-height: 14px; }

@media (max-width: 768px) {
.health-summary-grid { grid-template-columns: repeat(2, 1fr); }
.health-charts-grid { grid-template-columns: 1fr; }
.health-modal-inner { padding: 16px; }
.health-modal-title { font-size: 16px; letter-spacing: 3px; }
.period-tab { font-size: 9px; padding: 8px 4px; letter-spacing: 1px; }
}
</style>
</head>
<body>
<div class="scanline"></div>

<div id="sleep-overlay" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:#000;z-index:999;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;" onclick="this.style.display='none'">
  <div style="font-family:'Orbitron',sans-serif;font-size:18px;letter-spacing:8px;color:#00d4ff18;">S L E E P</div>
  <div style="font-size:10px;color:#00d4ff10;margin-top:12px;letter-spacing:4px;">CLICK TO WAKE</div>
</div>

<!-- INPUT OVERLAY — відкривається по кліку на кульку -->
<div id="input-overlay" style="
  display:none; position:fixed; bottom:90px; left:50%; transform:translateX(-50%);
  width:min(600px,90vw); z-index:200;
  background:rgba(0,10,20,0.95); border:1px solid var(--hud-accent-dim);
  border-radius:4px; padding:12px 16px;
  box-shadow:0 0 30px var(--hud-glow);
">
  <div style="font-family:'Orbitron',sans-serif;font-size:9px;letter-spacing:3px;color:var(--hud-accent-dim);margin-bottom:8px;">DIRECT INPUT</div>
  <div style="display:flex;gap:8px;align-items:center;">
    <input id="hud-input" type="text" autocomplete="off" spellcheck="false"
      placeholder="Enter command, Sir..."
      style="
        flex:1; background:transparent; border:none; border-bottom:1px solid var(--hud-accent-dim);
        color:#fff; font-family:'Share Tech Mono',monospace; font-size:14px;
        padding:6px 0; outline:none; letter-spacing:1px;
      "
    />
    <button onclick="sendHudInput()" style="
      background:transparent; border:1px solid var(--hud-accent-dim);
      color:var(--hud-accent); font-family:'Orbitron',sans-serif;
      font-size:10px; letter-spacing:2px; padding:6px 12px;
      cursor:pointer; border-radius:2px;
    ">SEND</button>
  </div>
</div>
<!-- HEALTH MODAL -->
<div id="health-modal" class="health-modal">
  <div class="health-modal-inner">
    <div class="health-modal-header">
      <div class="health-modal-title">◈ HEALTH ANALYTICS</div>
      <button class="health-modal-close" onclick="closeHealthModal()">CLOSE [ESC]</button>
    </div>
    <div class="period-tabs">
      <button class="period-tab" data-period="today" onclick="switchPeriod('today')">TODAY</button>
      <button class="period-tab active" data-period="week" onclick="switchPeriod('week')">WEEK</button>
      <button class="period-tab" data-period="month" onclick="switchPeriod('month')">MONTH</button>
      <button class="period-tab" data-period="year" onclick="switchPeriod('year')">YEAR</button>
    </div>

    <div class="health-summary-grid">
      <div class="summary-card">
        <div class="icon">👟</div>
        <div class="card-title">STEPS</div>
        <div class="card-main" id="sc-steps">—</div>
        <div class="card-sub" id="sc-steps-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">🛌</div>
        <div class="card-title">SLEEP</div>
        <div class="card-main" id="sc-sleep">—</div>
        <div class="card-sub" id="sc-sleep-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">❤️</div>
        <div class="card-title">HEART RATE</div>
        <div class="card-main" id="sc-hr">—</div>
        <div class="card-sub" id="sc-hr-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">🏋️</div>
        <div class="card-title">EXERCISE</div>
        <div class="card-main" id="sc-ex">—</div>
        <div class="card-sub" id="sc-ex-sub">—</div>
      </div>
    </div>

    <div class="health-charts-grid">
      <div class="chart-card">
        <div class="chart-title">◈ Daily Steps</div>
        <img id="chart-steps-daily" alt="Daily steps"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Steps by Weekday</div>
        <img id="chart-steps-weekday" alt="Steps by weekday"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Sleep Duration</div>
        <img id="chart-sleep-duration" alt="Sleep duration"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Sleep Stages</div>
        <img id="chart-sleep-stages" alt="Sleep stages"/>
      </div>
    </div>

    <div class="insights-box">
      <div class="insights-title">◈ JARVIS Insights</div>
      <ul class="insights-list" id="health-insights"><li class="insights-empty">Analyzing...</li></ul>
    </div>

    <div class="health-actions">
      <button class="health-btn" onclick="refreshHealthCache()">⟳ REFRESH DATA</button>
      <button class="health-btn" onclick="sendHealthToTelegram(this)">📲 SEND TO TELEGRAM</button>
          </div>
        </div>
      </div>
    
<!-- MONEY MODAL -->
<div id="money-modal" class="health-modal">
  <div class="health-modal-inner">
    <div class="health-modal-header">
      <div class="health-modal-title">◈ FINANCE ANALYTICS</div>
      <button class="health-modal-close" onclick="closeMoneyModal()">CLOSE [ESC]</button>
    </div>

    <div class="period-tabs">
      <button class="period-tab" data-period="week" onclick="switchMoneyPeriod('week')">WEEK</button>
      <button class="period-tab active" data-period="month" onclick="switchMoneyPeriod('month')">MONTH</button>
      <button class="period-tab" data-period="year" onclick="switchMoneyPeriod('year')">YEAR</button>
      <button class="period-tab" data-period="all" onclick="switchMoneyPeriod('all')">ALL TIME</button>
    </div>

    <div class="health-summary-grid">
      <div class="summary-card">
        <div class="icon">💸</div>
        <div class="card-title">SPENT</div>
        <div class="card-main" id="mc-spent">—</div>
        <div class="card-sub" id="mc-spent-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">💵</div>
        <div class="card-title">EARNED</div>
        <div class="card-main" id="mc-earned">—</div>
        <div class="card-sub" id="mc-earned-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">📊</div>
        <div class="card-title">NET</div>
        <div class="card-main" id="mc-net">—</div>
        <div class="card-sub" id="mc-net-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">🎯</div>
        <div class="card-title">SAVINGS RATE</div>
        <div class="card-main" id="mc-savings">—</div>
        <div class="card-sub" id="mc-savings-sub">—</div>
      </div>
    </div>

    <div class="health-charts-grid">
      <div class="chart-card">
        <div class="chart-title">◈ By Category</div>
        <img id="chart-money-categories" alt="Categories"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Monthly: Income vs Expenses</div>
        <img id="chart-money-monthly" alt="Monthly"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Daily Spending</div>
        <img id="chart-money-daily" alt="Daily"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ 50/30/20 Rule</div>
        <img id="chart-money-budget" alt="50/30/20"/>
      </div>
    </div>

    <div class="insights-box">
      <div class="insights-title">◈ JARVIS Insights</div>
      <ul class="insights-list" id="money-insights"><li class="insights-empty">Analyzing...</li></ul>
    </div>

    <div class="health-actions">
      <button class="health-btn" onclick="refreshMoneyCache()">⟳ REFRESH DATA</button>
      <button class="health-btn" onclick="sendMoneyToTelegram(this)">📲 SEND TO TELEGRAM</button>
    </div>
  </div>
</div>

<!-- MOOD MODAL -->
<div id="mood-modal" class="health-modal">
  <div class="health-modal-inner">
    <div class="health-modal-header">
      <div class="health-modal-title">◈ MOOD ANALYTICS</div>
      <button class="health-modal-close" onclick="closeMoodModal()">CLOSE [ESC]</button>
    </div>

    <!-- Quick log: шкала 1-10 + теги + нотатка -->
    <div class="mood-log-box">
      <div class="mood-log-label">HOW ARE YOU, SIR? — tap a score</div>
      <div class="mood-score-row" id="mood-score-row"></div>
      <div class="mood-log-label" style="margin-top:10px">TAGS (optional)</div>
      <div class="mood-tag-row" id="mood-tag-row"></div>
      <input type="text" id="mood-note" class="mood-note-input" placeholder="optional note..."/>
      <button class="health-btn" id="mood-log-btn" onclick="submitMood()" disabled>✓ LOG MOOD</button>
      <div class="mood-log-status" id="mood-log-status"></div>
    </div>

    <div class="period-tabs">
      <button class="period-tab" data-period="week" onclick="switchMoodPeriod('week')">WEEK</button>
      <button class="period-tab active" data-period="month" onclick="switchMoodPeriod('month')">MONTH</button>
      <button class="period-tab" data-period="year" onclick="switchMoodPeriod('year')">YEAR</button>
      <button class="period-tab" data-period="all" onclick="switchMoodPeriod('all')">ALL TIME</button>
    </div>

    <div class="health-summary-grid">
      <div class="summary-card">
        <div class="icon">🧠</div>
        <div class="card-title">AVERAGE</div>
        <div class="card-main" id="moodc-avg">—</div>
        <div class="card-sub" id="moodc-avg-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">📈</div>
        <div class="card-title">TREND</div>
        <div class="card-main" id="moodc-trend">—</div>
        <div class="card-sub" id="moodc-trend-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">☀️</div>
        <div class="card-title">AM / PM</div>
        <div class="card-main" id="moodc-ampm">—</div>
        <div class="card-sub" id="moodc-ampm-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">📅</div>
        <div class="card-title">BEST DAY</div>
        <div class="card-main" id="moodc-streak">—</div>
        <div class="card-sub" id="moodc-streak-sub">—</div>
      </div>
    </div>

    <div class="health-charts-grid">
      <div class="chart-card">
        <div class="chart-title">◈ Mood Trend</div>
        <img id="chart-mood-trend" alt="Trend"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Tag Frequency</div>
        <img id="chart-mood-tags" alt="Tags"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Score Distribution</div>
        <img id="chart-mood-distribution" alt="Distribution"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Mood by Day</div>
        <img id="chart-mood-hourly" alt="Hourly"/>
      </div>
    </div>

    <div class="insights-box">
      <div class="insights-title">◈ JARVIS Insights</div>
      <ul class="insights-list" id="mood-insights"><li class="insights-empty">Analyzing...</li></ul>
    </div>

    <div class="health-actions">
      <button class="health-btn" onclick="refreshMoodCache()">⟳ REFRESH DATA</button>
      <button class="health-btn" onclick="sendMoodToTelegram(this)">📲 SEND TO TELEGRAM</button>
    </div>
  </div>
</div>

<!-- CROSS-CORRELATION MODAL -->
<div id="corr-modal" class="health-modal">
  <div class="health-modal-inner">
    <div class="health-modal-header">
      <div class="health-modal-title">⚡ CROSS-CORRELATION</div>
      <button class="health-modal-close" onclick="closeCorrModal()">CLOSE [ESC]</button>
    </div>

    <div class="health-summary-grid" id="corr-metrics-grid">
      <div class="summary-card">
        <div class="icon">📊</div>
        <div class="card-title">METRICS</div>
        <div class="card-main" id="corr-metrics-count">—</div>
        <div class="card-sub" id="corr-metrics-list">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">📅</div>
        <div class="card-title">DAYS</div>
        <div class="card-main" id="corr-days">—</div>
        <div class="card-sub" id="corr-days-sub">overlap</div>
      </div>
      <div class="summary-card">
        <div class="icon">🔗</div>
        <div class="card-title">TOP LINK</div>
        <div class="card-main" id="corr-top">—</div>
        <div class="card-sub" id="corr-top-sub">—</div>
      </div>
      <div class="summary-card">
        <div class="icon">🎯</div>
        <div class="card-title">STRENGTH</div>
        <div class="card-main" id="corr-strength">—</div>
        <div class="card-sub" id="corr-strength-sub">—</div>
      </div>
    </div>

    <div class="health-charts-grid">
      <div class="chart-card">
        <div class="chart-title">◈ Correlation Matrix</div>
        <img id="chart-corr-matrix" alt="Matrix"/>
      </div>
      <div class="chart-card">
        <div class="chart-title">◈ Normalized Timeline</div>
        <img id="chart-corr-timeline" alt="Timeline"/>
      </div>
    </div>
    <div class="health-charts-grid">
      <div class="chart-card" style="grid-column:1 / -1;">
        <div class="chart-title">◈ Full Dashboard</div>
        <img id="chart-corr-dashboard" alt="Dashboard"/>
      </div>
    </div>

    <div class="insights-box">
      <div class="insights-title">◈ JARVIS Insights</div>
      <ul class="insights-list" id="corr-insights"><li class="insights-empty">Analyzing correlations...</li></ul>
    </div>

    <div class="health-actions">
      <button class="health-btn" onclick="refreshCorr()">⟳ REFRESH DATA</button>
      <button class="health-btn" onclick="sendCorrToTelegram(this)">📲 SEND TO TELEGRAM</button>
    </div>
  </div>
</div>

<!-- PEOPLE MODAL -->
<div id="people-modal" class="health-modal">
  <div class="health-modal-inner">
    <div class="health-modal-header">
      <div class="health-modal-title">◈ KNOWN INDIVIDUALS</div>
      <button class="health-modal-close" onclick="closePeopleModal()">CLOSE [ESC]</button>
    </div>

    <input type="text" id="people-search" class="people-search"
           placeholder="🔍 Search by name, relationship, or fact..."
           oninput="filterPeople(this.value)" />

    <div id="people-groups"></div>
  </div>
</div>
      <div class="grid">

  <!-- HEADER -->
  <div class="header">
    <div class="logo">J.A.R.V.I.S.</div>
    <div class="status-pill" id="status-pill">
      <div class="status-dot" id="status-dot"></div>
      <span id="status-text">STANDBY</span>
    </div>
    <div class="header-right">
      <div class="cc-blink" id="cc-blink" onclick="openCorrModal()" title="Cross-Correlation Insights">◈</div>
      <div class="datetime">
        <div class="time-display" id="time">00:00</div>
        <div class="date-display" id="date">--</div>
      </div>
    </div>
  </div>

  <!-- LEFT — System + Audio + Activity Log + Next Event + Reminders -->
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

    <!-- Activity Log — одразу під музикою, гнучко займає вільне місце -->
    <div style="margin-top:8px;padding-top:6px;border-top:1px solid var(--hud-accent-trace);flex:1;display:flex;flex-direction:column;min-height:0;">
      <div class="panel-title">◈ Activity Log</div>
      <div class="log-list" id="log-list" style="flex:1;overflow-y:auto;min-height:0;"></div>
    </div>

    <!-- Next Event — над Reminders -->
    <div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--hud-accent-trace);">
      <div class="panel-title">◈ Next Event</div>
      <div id="next-event-block">
        <div id="next-event-title" style="font-size:12px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">—</div>
        <div id="next-event-time" style="font-size:10px;color:var(--hud-accent-dim);margin-top:2px;letter-spacing:1px;">—</div>
        <div id="next-event-loc" style="font-size:10px;color:var(--hud-accent-dim);margin-top:1px;opacity:0.7;"></div>
      </div>
    </div>

    <!-- Active Reminders — pinned внизу -->
    <div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--hud-accent-faint);">
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

  <!-- RIGHT — Environment + Analytics minis (Health, Finance, People) -->
  <div class="panel right-panel" style="display:flex;flex-direction:column;overflow:hidden;">
    <div class="panel-title">◈ Environment</div>
    <div class="weather-block">
      <div class="weather-text" id="weather">Loading weather...</div>
    </div>
    <div class="panel-title" style="margin-top:8px">◈ Health</div>
    <div class="health-mini" onclick="openHealthModal()" id="health-mini">
      <div class="health-mini-title">
        <span>❤️ TODAY</span>
        <span class="open-hint">▸ open</span>
      </div>
      <div class="health-mini-row">
        <div class="health-mini-stat">
          <div class="value" id="hm-steps">—</div>
          <div class="label">Steps</div>
          <div class="sub" id="hm-steps-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="hm-sleep">—</div>
          <div class="label">Sleep h</div>
          <div class="sub" id="hm-sleep-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="hm-hr">—</div>
          <div class="label">HR bpm</div>
          <div class="sub" id="hm-hr-sub"></div>
        </div>
      </div>
    </div>

    <div class="panel-title" style="margin-top:8px">◈ Finance</div>
    <div class="health-mini" onclick="openMoneyModal()" id="money-mini">
      <div class="health-mini-title">
        <span>💰 THIS MONTH</span>
        <span class="open-hint">▸ open</span>
      </div>
      <div class="health-mini-row">
        <div class="health-mini-stat">
          <div class="value" id="mm-spent">—</div>
          <div class="label">Spent</div>
          <div class="sub" id="mm-spent-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="mm-earned">—</div>
          <div class="label">Earned</div>
          <div class="sub" id="mm-earned-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="mm-net">—</div>
          <div class="label">Net</div>
          <div class="sub" id="mm-net-sub"></div>
        </div>
      </div>
    </div>

    <div class="panel-title" style="margin-top:8px">◈ Mood</div>
    <div class="health-mini" onclick="openMoodModal()" id="mood-mini">
      <div class="health-mini-title">
        <span>🧠 TODAY</span>
        <span class="open-hint">▸ open</span>
      </div>
      <div class="health-mini-row">
        <div class="health-mini-stat">
          <div class="value" id="mood-latest">—</div>
          <div class="label">Latest</div>
          <div class="sub" id="mood-latest-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="mood-avg">—</div>
          <div class="label">Avg /10</div>
          <div class="sub" id="mood-trend-sub"></div>
        </div>
        <div class="health-mini-stat">
          <div class="value" id="mood-streak">—</div>
          <div class="label">Days</div>
          <div class="sub"></div>
        </div>
      </div>
    </div>

    <div class="panel-title" style="margin-top:8px">◈ Known Individuals</div>
    <div class="people-mini" onclick="openPeopleModal()" id="people-mini">
      <div class="people-mini-header">
        <span class="people-mini-count">👥 <span class="num" id="pm-count">0</span> RECORDED</span>
        <span class="open-hint" style="font-size:8px;color:var(--hud-accent-dim);letter-spacing:1px;">▸ open</span>
      </div>
      <div class="people-mini-list" id="pm-names">No individuals yet</div>
    </div>
  </div>

  <!-- BOTTOM -->
  <div class="bottom">
    <div class="mode-indicator">MODE: <span id="mode">HOME</span></div>
    <div class="arc-reactor" id="reactor-btn" onclick="toggleInput()" style="cursor:pointer;" title="Click to type"><div class="arc-inner"></div></div>
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
      document.querySelector('.logo').textContent = 'U.L.T.R.O.N. ';
      modeEl.style.color      = '#ff2200';
      modeEl.style.textShadow = '0 0 10px #ff220055';
    } else if (data.mode === 'IRON MAN') {
      document.body.classList.remove('ultron-mode');
      document.querySelector('.logo').textContent = 'J.A.R.V.I.S. ';
      modeEl.style.color      = '#ff4400';
      modeEl.style.textShadow = '0 0 10px #ff440055';
    } else {
      document.body.classList.remove('ultron-mode');
      document.querySelector('.logo').textContent = 'J.A.R.V.I.S. ';
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
    window._allPeople = data.people || [];
    updatePeopleMini(data.people);
    // Якщо модал відкритий — перерендерити
    if (document.getElementById('people-modal').classList.contains('open')) {
      renderPeopleModal(window._allPeople, document.getElementById('people-search').value);
    }
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

// ── HUD Input (клік на кульку) ────────────────────────────────────────────
function toggleInput() {
  const overlay = document.getElementById('input-overlay');
  const visible = overlay.style.display === 'flex';
  overlay.style.display = visible ? 'none' : 'flex';
  if (!visible) {
    setTimeout(() => document.getElementById('hud-input').focus(), 50);
  }
}

function sendHudInput() {
  const input = document.getElementById('hud-input');
  const text = input.value.trim();
  if (!text) return;
  socket.emit('hud_command', { text });
  input.value = '';
  input.focus();
}

document.addEventListener('keydown', (e) => {
  const overlay = document.getElementById('input-overlay');
  if (overlay.style.display === 'flex') {
    if (e.key === 'Enter') sendHudInput();
    if (e.key === 'Escape') overlay.style.display = 'none';
  }
});
let currentHealthPeriod = 'week';
function loadHealthMini() {
fetch('/health/today')
.then(r => r.json())
.then(d => {
if (!d.available) {
document.getElementById('hm-steps').textContent = '—';
document.getElementById('hm-steps-sub').textContent = 'no data';
return;
}
if (d.steps_today !== undefined) {
document.getElementById('hm-steps').textContent = d.steps_today.toLocaleString();
document.getElementById('hm-steps-sub').textContent = d.steps_today_label || '';
}
if (d.sleep_last_h !== undefined) {
document.getElementById('hm-sleep').textContent = d.sleep_last_h;
document.getElementById('hm-sleep-sub').textContent = d.sleep_last_date || '';
}
if (d.hr_latest !== undefined) {
document.getElementById('hm-hr').textContent = d.hr_latest;
const resting = d.hr_resting_week;
document.getElementById('hm-hr-sub').textContent = resting ? ('rest ' + resting) : '';
}
})
.catch(err => console.warn('health/today failed', err));
}
loadHealthMini();
setInterval(loadHealthMini, 5 * 60 * 1000);  // оновлення раз на 5 хв
function openHealthModal() {
document.getElementById('health-modal').classList.add('open');
switchPeriod(currentHealthPeriod);
loadHealthInsights(currentHealthPeriod);
}
function closeHealthModal() {
document.getElementById('health-modal').classList.remove('open');
}
function switchPeriod(period) {
currentHealthPeriod = period;
document.querySelectorAll('.period-tab').forEach(t => {
t.classList.toggle('active', t.dataset.period === period);
});
loadHealthSummary(period);
reloadCharts(period);
}
function loadHealthSummary(period) {
fetch('/health/summary?period=' + period)
.then(r => r.json())
.then(d => {
if (!d.available) return;
  // Steps card
  if (d.steps) {
    document.getElementById('sc-steps').textContent =
      (d.steps.avg_steps || 0).toLocaleString();
    const goal = d.steps.goal_met_pct;
    document.getElementById('sc-steps-sub').textContent =
      'avg/day · ' + (d.steps.total_steps || 0).toLocaleString() +
      ' total · goal ' + (goal !== undefined ? goal + '%' : '—');
  }

  // Sleep card
  if (d.sleep && d.sleep.nights) {
    document.getElementById('sc-sleep').textContent =
      (d.sleep.avg_duration_h || 0) + 'h';
    let sub = d.sleep.nights + ' nights · eff ' + (d.sleep.avg_efficiency || 0) + '%';
    if (d.sleep_stages) {
      sub += ' · REM ' + (d.sleep_stages.REM || 0) + '%';
    }
    document.getElementById('sc-sleep-sub').textContent = sub;
  } else {
    document.getElementById('sc-sleep').textContent = '—';
    document.getElementById('sc-sleep-sub').textContent = 'no data';
  }

  // HR card
  if (d.heart_rate && d.heart_rate.samples) {
    document.getElementById('sc-hr').textContent =
      (d.heart_rate.avg_hr || 0) + ' bpm';
    document.getElementById('sc-hr-sub').textContent =
      d.heart_rate.samples + ' samples · rest ' +
      (d.heart_rate.resting_avg || '—') + ' · max ' + d.heart_rate.max_hr;
  } else {
    document.getElementById('sc-hr').textContent = '—';
    document.getElementById('sc-hr-sub').textContent = 'no data';
  }

  // Exercise card
  if (d.exercise && d.exercise.sessions) {
    document.getElementById('sc-ex').textContent = d.exercise.sessions;
    document.getElementById('sc-ex-sub').textContent =
      d.exercise.total_minutes + ' min · ' + d.exercise.total_km + ' km · ' +
      d.exercise.top_type;
  } else {
    document.getElementById('sc-ex').textContent = '—';
    document.getElementById('sc-ex-sub').textContent = 'no workouts';
  }
});
}

function reloadCharts(period) {
const t = Date.now();  // cache-busting
  document.getElementById('chart-steps-daily').src    = `/health/chart?panel=steps_daily&period=${period}&t=${t}`;
  document.getElementById('chart-steps-weekday').src  = `/health/chart?panel=steps_weekday&period=${period}&t=${t}`;
  document.getElementById('chart-sleep-duration').src = `/health/chart?panel=sleep_duration&period=${period}&t=${t}`;
  document.getElementById('chart-sleep-stages').src   = `/health/chart?panel=sleep_stages&period=${period}&t=${t}`;
}
function refreshHealthCache() {
fetch('/health/refresh', { method: 'POST' })
.then(() => {
loadHealthMini();
switchPeriod(currentHealthPeriod);
});
}
function sendHealthToTelegram(btn) {
btn.disabled = true;
const originalText = btn.textContent;
btn.textContent = '⌛ SENDING...';
fetch('/health/telegram', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ period: currentHealthPeriod }),
})
.then(r => r.json())
.then(d => {
btn.textContent = d.ok ? '✓ SENT' : '✗ FAILED';
setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
})
.catch(() => {
btn.textContent = '✗ ERROR';
setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
});
}
// ESC щоб закрити модал
document.addEventListener('keydown', (e) => {
if (e.key === 'Escape' && document.getElementById('health-modal').classList.contains('open')) {
closeHealthModal();
}
});
// Клік повз модал — закрити
document.getElementById('health-modal').addEventListener('click', (e) => {
if (e.target.id === 'health-modal') closeHealthModal();
});
// ── MONEY PANEL ───────────────────────────────────────────────────────────
let currentMoneyPeriod = 'month';

function loadMoneyMini() {
  fetch('/money/today')
    .then(r => r.json())
    .then(d => {
      if (!d.available) {
        document.getElementById('mm-spent').textContent = '—';
        document.getElementById('mm-spent-sub').textContent = 'no data';
        return;
      }
      const cur = d.currency || '';
      document.getElementById('mm-spent').textContent = (d.month_spent || 0).toLocaleString();
      document.getElementById('mm-spent-sub').textContent = cur;
      document.getElementById('mm-earned').textContent = (d.month_earned || 0).toLocaleString();
      document.getElementById('mm-earned-sub').textContent = cur;
      const net = d.month_net || 0;
      document.getElementById('mm-net').textContent = (net >= 0 ? '+' : '') + net.toLocaleString();
      document.getElementById('mm-net-sub').textContent = cur;
      // Колір Net: зелений якщо додатній, червоний якщо мінус
      document.getElementById('mm-net').style.color = net >= 0 ? 'var(--hud-accent2)' : '#ff3b30';
    })
    .catch(err => console.warn('money/today failed', err));
}
loadMoneyMini();
setInterval(loadMoneyMini, 5 * 60 * 1000);

function openMoneyModal() {
  document.getElementById('money-modal').classList.add('open');
  switchMoneyPeriod(currentMoneyPeriod);
  loadMoneyInsights(currentMoneyPeriod);
}
function closeMoneyModal() {
  document.getElementById('money-modal').classList.remove('open');
}

function switchMoneyPeriod(period) {
  currentMoneyPeriod = period;
  document.querySelectorAll('#money-modal .period-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.period === period);
  });
  loadMoneySummary(period);
  reloadMoneyCharts(period);
}

function loadMoneySummary(period) {
  fetch('/money/summary?period=' + period)
    .then(r => r.json())
    .then(d => {
      if (!d.available || !d.summary) return;
      const s = d.summary;
      const cur = s.currency || '';

      document.getElementById('mc-spent').textContent = (s.total_spent || 0).toLocaleString();
      document.getElementById('mc-spent-sub').textContent =
        s.expenses_count + ' txn · daily ' + (s.daily_avg_spend || 0).toLocaleString() + ' ' + cur;

      document.getElementById('mc-earned').textContent = (s.total_earned || 0).toLocaleString();
      document.getElementById('mc-earned-sub').textContent = s.income_count + ' transactions · ' + cur;

      const net = s.net || 0;
      const netEl = document.getElementById('mc-net');
      netEl.textContent = (net >= 0 ? '+' : '') + net.toLocaleString();
      netEl.style.color = net >= 0 ? 'var(--hud-accent2)' : '#ff3b30';
      document.getElementById('mc-net-sub').textContent = cur + ' · ' + s.days + ' days';

      // Savings rate + 50/30/20 compliance
      const sr = s.savings_rate;
      document.getElementById('mc-savings').textContent = (sr !== null && sr !== undefined) ? sr + '%' : '—';
      if (d.budget && d.budget.available) {
        const b = d.budget;
        const ok = (v) => v ? '✓' : '✗';
        document.getElementById('mc-savings-sub').textContent =
          `${ok(b.needs_ok)} N ${b.needs_used_pct}%  ` +
          `${ok(b.wants_ok)} W ${b.wants_used_pct}%  ` +
          `${ok(b.savings_ok)} S ${b.savings_done_pct}%`;
        // Колір: зелений якщо overall_ok, червоний якщо ні
        document.getElementById('mc-savings').style.color =
          b.overall_ok ? 'var(--hud-accent2)' : '#ff3b30';
      } else if (d.needs_wants) {
        document.getElementById('mc-savings-sub').textContent =
          'needs ' + d.needs_wants.needs_pct + '% · wants ' + d.needs_wants.wants_pct + '%';
      } else {
        document.getElementById('mc-savings-sub').textContent = '';
      }
    });
}

function reloadMoneyCharts(period) {
  const t = Date.now();
  document.getElementById('chart-money-categories').src = `/money/chart?panel=categories&period=${period}&t=${t}`;
  document.getElementById('chart-money-monthly').src    = `/money/chart?panel=monthly&period=${period}&t=${t}`;
  document.getElementById('chart-money-daily').src      = `/money/chart?panel=daily&period=${period}&t=${t}`;
  document.getElementById('chart-money-budget').src     = `/money/chart?panel=budget&period=${period}&t=${t}`;
}

function refreshMoneyCache() {
  fetch('/money/refresh', { method: 'POST' })
    .then(() => { loadMoneyMini(); switchMoneyPeriod(currentMoneyPeriod); });
}

function sendMoneyToTelegram(btn) {
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = '⌛ SENDING...';
  fetch('/money/telegram', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period: currentMoneyPeriod }),
  })
    .then(r => r.json())
    .then(d => {
      btn.textContent = d.ok ? '✓ SENT' : '✗ FAILED';
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    })
    .catch(() => {
      btn.textContent = '✗ ERROR';
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    });
}

// ESC щоб закрити модал
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('money-modal').classList.contains('open')) {
    closeMoneyModal();
  }
});

// Клік повз модал — закрити
document.getElementById('money-modal').addEventListener('click', (e) => {
  if (e.target.id === 'money-modal') closeMoneyModal();
});


// ── MOOD MINI + MODAL ──────────────────────────────────────────────────────
let currentMoodPeriod = 'month';
let moodSelectedScore = null;
let moodSelectedTags = [];

function loadMoodMini() {
  fetch('/mood/today')
    .then(r => r.json())
    .then(d => {
      if (d.count === 0 || d.latest === null || d.latest === undefined) {
        document.getElementById('mood-latest').textContent = '—';
        document.getElementById('mood-latest-sub').textContent = 'no data';
        document.getElementById('mood-avg').textContent = '—';
        document.getElementById('mood-streak').textContent = '0';
        return;
      }
      document.getElementById('mood-latest').textContent = d.latest;
      document.getElementById('mood-latest-sub').textContent =
        (d.latest_tags && d.latest_tags.length) ? d.latest_tags[0] : '';
      document.getElementById('mood-avg').textContent = (d.avg !== null ? d.avg : '—');
      const arrow = d.trend === 'up' ? '▲ up' : d.trend === 'down' ? '▼ down' : '— flat';
      document.getElementById('mood-trend-sub').textContent = arrow;
      document.getElementById('mood-avg').style.color =
        d.trend === 'up' ? 'var(--hud-accent2)' : d.trend === 'down' ? '#ff3b30' : 'var(--hud-accent)';
      document.getElementById('mood-streak').textContent = d.days_logged || 0;
    })
    .catch(err => console.warn('mood/today failed', err));
}
loadMoodMini();
setInterval(loadMoodMini, 5 * 60 * 1000);

function buildMoodControls() {
  // Шкала 1-10
  const sr = document.getElementById('mood-score-row');
  if (sr && !sr.dataset.built) {
    for (let i = 1; i <= 10; i++) {
      const b = document.createElement('div');
      b.className = 'mood-score';
      b.textContent = i;
      b.onclick = () => {
        moodSelectedScore = i;
        document.querySelectorAll('#mood-score-row .mood-score')
          .forEach(el => el.classList.toggle('selected', el.textContent == i));
        document.getElementById('mood-log-btn').disabled = false;
      };
      sr.appendChild(b);
    }
    sr.dataset.built = '1';
  }
  // Теги — тягнемо канонічний список з бекенду
  const tr = document.getElementById('mood-tag-row');
  if (tr && !tr.dataset.built) {
    fetch('/mood/tags').then(r => r.json()).then(d => {
      (d.tags || []).forEach(tag => {
        const c = document.createElement('div');
        c.className = 'mood-tag-chip';
        c.textContent = tag;
        c.onclick = () => {
          const idx = moodSelectedTags.indexOf(tag);
          if (idx >= 0) { moodSelectedTags.splice(idx, 1); c.classList.remove('selected'); }
          else { moodSelectedTags.push(tag); c.classList.add('selected'); }
        };
        tr.appendChild(c);
      });
      tr.dataset.built = '1';
    });
  }
}

function resetMoodForm() {
  moodSelectedScore = null;
  moodSelectedTags = [];
  document.querySelectorAll('#mood-score-row .mood-score').forEach(el => el.classList.remove('selected'));
  document.querySelectorAll('#mood-tag-row .mood-tag-chip').forEach(el => el.classList.remove('selected'));
  document.getElementById('mood-note').value = '';
  document.getElementById('mood-log-btn').disabled = true;
}

function submitMood() {
  if (moodSelectedScore === null) return;
  const btn = document.getElementById('mood-log-btn');
  btn.disabled = true;
  const status = document.getElementById('mood-log-status');
  status.textContent = '⌛ logging...';
  fetch('/mood/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      score: moodSelectedScore,
      tags: moodSelectedTags.join(';'),
      note: document.getElementById('mood-note').value,
    }),
  })
    .then(r => r.json())
    .then(d => {
      status.textContent = d.ok ? '✓ ' + (d.status || 'logged') : '✗ failed';
      resetMoodForm();
      loadMoodMini();
      switchMoodPeriod(currentMoodPeriod);
      setTimeout(() => { status.textContent = ''; }, 4000);
    })
    .catch(() => { status.textContent = '✗ error'; btn.disabled = false; });
}

function openMoodModal() {
  document.getElementById('mood-modal').classList.add('open');
  buildMoodControls();
  switchMoodPeriod(currentMoodPeriod);
  loadMoodInsights(currentMoodPeriod);
}
function closeMoodModal() {
  document.getElementById('mood-modal').classList.remove('open');
}

function switchMoodPeriod(period) {
  currentMoodPeriod = period;
  document.querySelectorAll('#mood-modal .period-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.period === period);
  });
  loadMoodSummary(period);
  reloadMoodCharts(period);
}

function loadMoodSummary(period) {
  fetch('/mood/summary?period=' + period)
    .then(r => r.json())
    .then(d => {
      const s = d.stats || {};
      if (!s.count) {
        ['moodc-avg','moodc-trend','moodc-ampm','moodc-streak'].forEach(id =>
          document.getElementById(id).textContent = '—');
        document.getElementById('moodc-avg-sub').textContent = 'no data';
        return;
      }
      document.getElementById('moodc-avg').textContent = s.avg + '/10';
      document.getElementById('moodc-avg-sub').textContent =
        s.count + ' entries · range ' + s.min + '-' + s.max;

      const tl = { up: '▲ improving', down: '▼ declining', flat: '— stable' };
      document.getElementById('moodc-trend').textContent = tl[s.trend] || '—';
      document.getElementById('moodc-trend').style.color =
        s.trend === 'up' ? 'var(--hud-accent2)' : s.trend === 'down' ? '#ff3b30' : 'var(--hud-accent)';
      document.getElementById('moodc-trend-sub').textContent =
        (s.positive_pct !== null ? s.positive_pct + '% positive' : '');

      const m = d.morning_vs_evening || {};
      document.getElementById('moodc-ampm').textContent =
        (m.morning !== null ? m.morning : '—') + ' / ' + (m.evening !== null ? m.evening : '—');
      document.getElementById('moodc-ampm-sub').textContent =
        'AM ' + (m.morning_n || 0) + ' · PM ' + (m.evening_n || 0);

      document.getElementById('moodc-streak').textContent = s.best_day || '—';
      document.getElementById('moodc-streak-sub').textContent =
        (s.days_logged || 0) + ' days logged';
    });
}

function reloadMoodCharts(period) {
  const t = Date.now();
  document.getElementById('chart-mood-trend').src        = `/mood/chart/trend?period=${period}&t=${t}`;
  document.getElementById('chart-mood-tags').src         = `/mood/chart/tags?period=${period}&t=${t}`;
  document.getElementById('chart-mood-distribution').src = `/mood/chart/distribution?period=${period}&t=${t}`;
  document.getElementById('chart-mood-hourly').src       = `/mood/chart/hourly?period=${period}&t=${t}`;
}

function refreshMoodCache() {
  fetch('/mood/refresh', { method: 'POST' })
    .then(() => { loadMoodMini(); switchMoodPeriod(currentMoodPeriod); });
}

function sendMoodToTelegram(btn) {
  btn.disabled = true;
  const originalText = btn.textContent;
  btn.textContent = '⌛ SENDING...';
  fetch('/mood/telegram', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period: currentMoodPeriod }),
  })
    .then(r => r.json())
    .then(d => {
      btn.textContent = d.ok ? '✓ SENT' : '✗ FAILED';
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    })
    .catch(() => {
      btn.textContent = '✗ ERROR';
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    });
}

// ESC щоб закрити модал
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('mood-modal').classList.contains('open')) {
    closeMoodModal();
  }
});
// Клік повз модал — закрити
document.getElementById('mood-modal').addEventListener('click', (e) => {
  if (e.target.id === 'mood-modal') closeMoodModal();
});


// ── PEOPLE MINI + MODAL ───────────────────────────────────────────────────
window._allPeople = [];

function updatePeopleMini(people) {
  const count = people.length;
  document.getElementById('pm-count').textContent = count;
  const namesEl = document.getElementById('pm-names');
  if (count === 0) {
    namesEl.textContent = 'No individuals yet';
  } else {
    const top = people.slice(0, 3).map(p =>
      `<span class="pm-name">${p.name}</span>`
    ).join(' · ');
    const extra = count > 3 ? ` <span style="opacity:0.6">+${count - 3} more</span>` : '';
    namesEl.innerHTML = top + extra;
  }
}

function openPeopleModal() {
  document.getElementById('people-modal').classList.add('open');
  document.getElementById('people-search').value = '';
  renderPeopleModal(window._allPeople, '');
  setTimeout(() => document.getElementById('people-search').focus(), 100);
}

function closePeopleModal() {
  document.getElementById('people-modal').classList.remove('open');
}

function filterPeople(query) {
  renderPeopleModal(window._allPeople, query);
}

function renderPeopleModal(people, query) {
  const container = document.getElementById('people-groups');
  const q = (query || '').toLowerCase().trim();

  // Фільтрація
  let filtered = people;
  if (q) {
    filtered = people.filter(p => {
      const hay = (
        (p.name || '') + ' ' +
        (p.relationship || '') + ' ' +
        (p.facts || []).join(' ')
      ).toLowerCase();
      return hay.includes(q);
    });
  }

  if (filtered.length === 0) {
    container.innerHTML = `<div class="people-empty">${
      q ? 'No matches for "' + escapeHtml(query) + '"' : 'No individuals recorded yet'
    }</div>`;
    return;
  }

  // Групування по relationship
  const groups = {};
  filtered.forEach(p => {
    const rel = (p.relationship || 'unknown').toLowerCase();
    if (!groups[rel]) groups[rel] = [];
    groups[rel].push(p);
  });

  // Порядок груп: family, friend, coworker, потім інше за алфавітом, в кінці unknown
  const priorityOrder = ['family', 'friend', 'coworker', 'colleague', 'partner', 'classmate'];
  const sortedRels = Object.keys(groups).sort((a, b) => {
    if (a === 'unknown') return 1;
    if (b === 'unknown') return -1;
    const ai = priorityOrder.indexOf(a);
    const bi = priorityOrder.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });

  container.innerHTML = sortedRels.map(rel => {
    const peopleInGroup = groups[rel];
    const cards = peopleInGroup.map(p => {
      const facts = (p.facts || []);
      const factsHtml = facts.length === 0
        ? '<div class="pdc-empty">No facts recorded</div>'
        : facts.map(f => `<div class="pdc-fact">• ${escapeHtml(f)}</div>`).join('');
      return `
        <div class="people-detail-card">
          <div class="pdc-name">${escapeHtml(p.name.toUpperCase())}</div>
          <div class="pdc-rel">${escapeHtml(p.relationship || 'unknown')}</div>
          <div class="pdc-facts">${factsHtml}</div>
        </div>
      `;
    }).join('');
    return `
      <div class="people-group">
        <div class="people-group-title">
          <span>${escapeHtml(rel)}</span>
          <span class="pg-count">${peopleInGroup.length} ${peopleInGroup.length === 1 ? 'person' : 'people'}</span>
        </div>
        <div class="people-cards">${cards}</div>
      </div>
    `;
  }).join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// ESC щоб закрити модал
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.getElementById('people-modal').classList.contains('open')) {
    closePeopleModal();
  }
});

// Клік повз модал — закрити
document.getElementById('people-modal').addEventListener('click', (e) => {
  if (e.target.id === 'people-modal') closePeopleModal();
});
// ── МОБІЛЬНИЙ АКОРДЕОН ─────────────────────────────────────────────────────
const MOBILE_BP = 768;
let _mobileAccordionBuilt = false;

function _wrapSectionBodies(panel) {
  const titles = Array.from(panel.querySelectorAll('.panel-title'));
  titles.forEach(title => {
    if (title.dataset.mReady) return;
    const body = document.createElement('div');
    body.className = 'm-section-body collapsed';
    let node = title.nextElementSibling;
    const toMove = [];
    while (node && !node.classList.contains('panel-title')) {
      if (node.querySelector && node.querySelector('.panel-title')) break;
      toMove.push(node);
      node = node.nextElementSibling;
    }
    if (toMove.length === 0) { title.dataset.mReady = '1'; return; }
    title.after(body);
    toMove.forEach(el => body.appendChild(el));
    title.classList.add('m-head');
    const preview = document.createElement('span');
    preview.className = 'm-preview';
    title.appendChild(preview);
    title._preview = preview;
    title._body = body;
    title.addEventListener('click', () => {
      const open = body.classList.toggle('collapsed') === false;
      title.classList.toggle('open', open);
    });
    title.dataset.mReady = '1';
  });
}

function _updatePreview(title, text) {
  if (title && title._preview) title._preview.textContent = text || '';
}

function buildMobileAccordion() {
  if (_mobileAccordionBuilt) return;
  if (window.innerWidth > MOBILE_BP) return;
  ['.left-panel', '.right-panel'].forEach(sel => {
    const p = document.querySelector(sel);
    if (p) _wrapSectionBodies(p);
  });
  _mobileAccordionBuilt = true;
  refreshMobilePreviews();
}

function refreshMobilePreviews() {
  if (window.innerWidth > MOBILE_BP) return;
  const byText = (t) => Array.from(document.querySelectorAll('.panel-title.m-head'))
    .find(el => el.firstChild && el.firstChild.textContent &&
                el.firstChild.textContent.includes(t));
  const sys = byText('System Status');
  if (sys) _updatePreview(sys, 'CPU ' + (document.getElementById('cpu-val')?.textContent || 0) +
                                '% RAM ' + (document.getElementById('ram-val')?.textContent || 0) + '%');
  const audio = byText('Audio Stream');
  if (audio) _updatePreview(audio, document.getElementById('song-name')?.textContent || '');
  const env = byText('Environment');
  if (env) _updatePreview(env, (document.getElementById('weather')?.textContent || '').split('\\n')[0].slice(0, 22));
  const h = byText('Health');
  if (h) _updatePreview(h, (document.getElementById('hm-steps')?.textContent || '—') + ' steps');
  const f = byText('Finance');
  if (f) _updatePreview(f, 'net ' + (document.getElementById('mm-net')?.textContent || '—'));
  const m = byText('Mood');
  if (m) _updatePreview(m, (document.getElementById('mood-latest')?.textContent || '—') + '/10');
  const ind = byText('Known Individuals');
  if (ind) _updatePreview(ind, (document.getElementById('pm-count')?.textContent || 0) + ' recorded');
}

window.addEventListener('load', buildMobileAccordion);
window.addEventListener('resize', () => {
  if (window.innerWidth <= MOBILE_BP) buildMobileAccordion();
});
setInterval(refreshMobilePreviews, 5000);

// ====================== CROSS-CORRELATION MODAL ======================
function openCorrModal() {
  document.getElementById('corr-modal').classList.add('open');
  loadCorrSummary();
  reloadCorrCharts();
}
function closeCorrModal() {
  document.getElementById('corr-modal').classList.remove('open');
}

function loadCorrSummary() {
  fetch('/correlation/summary')
    .then(r => r.json())
    .then(d => {
      if (!d.available) {
        document.getElementById('corr-metrics-count').textContent = '0';
        document.getElementById('corr-metrics-list').textContent = 'no data';
        renderInsights('corr-insights', d.insights || []);
        return;
      }
      document.getElementById('corr-metrics-count').textContent = (d.metric_keys || []).length;
      document.getElementById('corr-metrics-list').textContent = (d.metrics || []).join(', ');
      document.getElementById('corr-days').textContent = d.days || 0;
      document.getElementById('corr-days-sub').textContent = 'full overlap ' + (d.full_overlap_days || 0);
      var pairs = d.pairs || [];
      if (pairs.length) {
        var p = pairs[0];
        document.getElementById('corr-top').textContent = 'r=' + p.r;
        document.getElementById('corr-top-sub').textContent = p.a + ' / ' + p.b;
        document.getElementById('corr-strength').textContent = p.strength;
        document.getElementById('corr-strength-sub').textContent = p.n + ' days';
        document.getElementById('corr-strength').style.color =
          p.strength === 'strong' ? 'var(--hud-accent2)' :
          p.strength === 'notable' ? 'var(--hud-accent)' : 'var(--hud-accent-dim)';
      }
      renderInsights('corr-insights', d.insights || []);
    })
    .catch(function(e) { console.warn('corr summary failed', e); });
}

function reloadCorrCharts() {
  var t = Date.now();
  document.getElementById('chart-corr-matrix').src    = '/correlation/chart?panel=matrix&t=' + t;
  document.getElementById('chart-corr-timeline').src  = '/correlation/chart?panel=timeline&t=' + t;
  document.getElementById('chart-corr-dashboard').src = '/correlation/chart?panel=dashboard&t=' + t;
}

function refreshCorr() {
  fetch('/correlation/refresh', { method: 'POST' })
    .then(function() { loadCorrSummary(); reloadCorrCharts(); });
}

function sendCorrToTelegram(btn) {
  btn.disabled = true;
  var original = btn.textContent;
  btn.textContent = '\u231b SENDING...';
  fetch('/correlation/telegram', { method: 'POST' })
    .then(r => r.json())
    .then(function(d) {
      btn.textContent = d.ok ? '\u2713 SENT' : '\u2717 FAILED';
      setTimeout(function() { btn.textContent = original; btn.disabled = false; }, 2000);
    })
    .catch(function() {
      btn.textContent = '\u2717 ERROR';
      setTimeout(function() { btn.textContent = original; btn.disabled = false; }, 2000);
    });
}

// ── Спільний рендер insights-списку ──────────────────────────────────
function renderInsights(elemId, items) {
  var el = document.getElementById(elemId);
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = '<li class="insights-empty">No insights yet.</li>';
    return;
  }
  el.innerHTML = items.map(function(t) {
    return '<li>' + String(t).replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</li>';
  }).join('');
}

// ── Наповнення insights health/money/mood (окремі endpoints) ─────────
function loadHealthInsights(period) {
  fetch('/health/insights?period=' + (period || 'week'))
    .then(r => r.json())
    .then(function(d) { renderInsights('health-insights', d.insights || []); })
    .catch(function() {});
}
function loadMoneyInsights(period) {
  fetch('/money/insights?period=' + (period || 'month'))
    .then(r => r.json())
    .then(function(d) { renderInsights('money-insights', d.insights || []); })
    .catch(function() {});
}
function loadMoodInsights(period) {
  fetch('/mood/insights?period=' + (period || 'month'))
    .then(r => r.json())
    .then(function(d) { renderInsights('mood-insights', d.insights || []); })
    .catch(function() {});
}

// ESC + клік-поза для corr-модала
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && document.getElementById('corr-modal').classList.contains('open')) {
    closeCorrModal();
  }
});
document.getElementById('corr-modal').addEventListener('click', function(e) {
  if (e.target.id === 'corr-modal') closeCorrModal();
});
</script>
<script src="/boot.js"></script>
</body>
</html>
"""
try:
    from modules.health_analytics.hud_endpoints import register_health_routes
    register_health_routes(app)
except Exception as e:
    print(f"[HUD] Health routes не зареєстровані: {e}")

try:
    from modules.money_analytics.hud_endpoints import register_money_routes
    register_money_routes(app)
except Exception as e:
    print(f"[HUD] Money routes не зареєстровані: {e}")

try:
    from modules.mood_analytics.hud_endpoints import register_mood_routes
    register_mood_routes(app)
except Exception as e:
    print(f"[HUD] Mood routes не зареєстровані: {e}")

try:
    from modules.correlation_analytics.hud_endpoints import register_correlation_routes
    register_correlation_routes(app)
except Exception as e:
    print(f"[HUD] Correlation routes не зареєстровані: {e}")

try:
    from modules.boot_animation import register_boot
    register_boot(app)
except Exception as e:
    print(f"[HUD] Boot animation не зареєстровано: {e}")

@app.route('/')
def index():
    model = hud_state.get("model", "llama-3.3-70b")
    # Скорочуємо довгі назви типу meta-llama/llama-4-scout-17b-16e-instruct
    short = model.split("/")[-1] if "/" in model else model
    return render_template_string(HTML_TEMPLATE, model=short)


@socketio.on('connect')
def on_connect():
    """При підключенні нового клієнта — відправляємо весь поточний стан."""
    # Профілі людей: якщо стан ще не наповнено (HUD стартував раніше за
    # першу відповідь агента) — читаємо прямо з диску, щоб Individuals
    # показувались одразу, а не лише після першого повідомлення в чат.
    people = hud_state.get('people') or []
    if not people:
        try:
            from modules.people_module import get_all_profiles
            people = get_all_profiles()
            hud_state['people'] = people
        except Exception as e:
            print(f"[HUD] Не вдалось завантажити профілі при підключенні: {e}")

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
        'people':         people,
    })



# Callback який main.py підключає для обробки команд з HUD input
_hud_command_callback = None

def set_hud_command_callback(fn):
    global _hud_command_callback
    _hud_command_callback = fn

@socketio.on('hud_command')
def on_hud_command(data):
    """Отримує текстову команду з браузера (клік на кульку)."""
    text = data.get('text', '').strip()
    if not text or not _hud_command_callback:
        return
    import threading
    threading.Thread(target=_hud_command_callback, args=(text,), daemon=True).start()


def update_hud(key: str, value):
    """Оновлює одне поле HUD і надсилає всім клієнтам."""
    hud_state[key] = value
    socketio.emit('state_update', {key: value})


def update_reminders(reminders: list):
    """Оновлює панель активних нагадувань. reminders = [{message, time_left}]"""
    hud_state['reminders'] = reminders          # зберігаємо, щоб on_connect віддав одразу
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
    # Наповнюємо профілі одразу при старті — щоб Individuals були готові
    # ще до першого повідомлення (а не лише після відповіді агента).
    try:
        from modules.people_module import get_all_profiles
        hud_state['people'] = get_all_profiles()
    except Exception as e:
        print(f"[HUD] Профілі при старті не завантажені: {e}")
    threading.Thread(target=_system_monitor, daemon=True).start()
    threading.Thread(target=_calendar_poller, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()
    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False, log_output=False)