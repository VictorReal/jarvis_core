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
    "activity": [],
    "ticker": {"finance": [], "news": []},
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>JARVIS HUD</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<link rel="stylesheet" href="/hud_styles.css">
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
    <div class="sys-grid">
      <div class="sys-left">
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
      </div>
      <div class="sys-right">
        <div class="sys-stat"><span class="sys-stat-label">UPTIME</span><span class="sys-stat-val" id="uptime-val">—</span></div>
        <div class="sys-stat"><span class="sys-stat-label">DISK</span><span class="sys-stat-val" id="disk-val">—</span></div>
        <div class="sys-stat"><span class="sys-stat-label">NET</span><span class="sys-stat-val" id="net-val">↓0 ↑0</span></div>
      </div>
    </div>

    <div class="music-info">
      <div class="panel-title">◈ Audio Stream</div>
      <div class="song-name">
        <span id="song-name">No music playing</span>
      </div>

      <div class="audio-row">
        <div class="music-controls">
          <button class="music-btn" id="btn-prev" title="Previous" onclick="musicAction('prev')">⏮</button>
          <button class="music-btn music-btn-main" id="btn-toggle" title="Play / Pause" onclick="musicAction('toggle')">&#x25B6;&#xFE0E;</button>
          <button class="music-btn" id="btn-next" title="Next" onclick="musicAction('next')">⏭</button>
        </div>
        <div class="vol-inline">
          <span class="vol-icon" id="vol-icon" onclick="musicAction('mute')" title="Mute / Unmute" style="cursor:pointer">🔊</span>
          <div class="volume-bar" id="vol-bar-track" title="Click to set volume">
            <div class="volume-fill" id="vol-bar" style="width:0%"></div>
          </div>
        </div>
      </div>

      <!-- прогрес-бар треку (клікабельний для seek) -->
      <div class="volume-bar progress-slim" id="progress-track" title="Click to seek">
        <div class="progress-fill" id="progress-bar" style="width:0%"></div>
      </div>
      <!-- час прихований для компактності, лишений для JS -->
      <div style="display:none">
        <span id="progress-time">0:00</span>
        <span id="duration-time">0:00</span>
      </div>
      <!-- play-icon прихований, лишений для сумісності зі станом -->
      <span id="play-icon" style="display:none">—</span>
    </div>

    <!-- YouTube — між Audio і Reminders -->
    <div class="yt-block sec-divider">
      <div class="panel-title">◈ YouTube</div>
      <div class="yt-search-row" id="yt-search-row">
        <input type="text" id="yt-input" class="yt-input" placeholder="Search YouTube…"
               onkeydown="if(event.key==='Enter')ytSearch()">
        <button class="yt-btn" onclick="ytSearch()" title="Search">⌕</button>
      </div>
      <button class="yt-back-btn" id="yt-back-btn" onclick="ytBack()" style="display:none" title="Back to search">‹ Search</button>
      <div class="yt-body">
        <div class="yt-results" id="yt-results"></div>
        <div class="yt-mini" id="yt-mini" style="display:none">
          <div id="yt-mini-frame"></div>
        </div>
      </div>
    </div>

    <!-- Об'єднане вікно: Reminders ⇄ Next Event (перемикач) -->
    <div class="switch-block sec-divider faint">
      <div class="switch-head">
        <span class="panel-title" id="switch-title" style="margin:0">◈ Activity Log</span>
        <div style="display:flex;gap:6px;align-items:center">
          <button class="switch-btn" id="activity-expand-btn" onclick="openActivityOverlay()" title="Expand log">⤢</button>
          <button class="switch-btn" id="switch-btn" onclick="cycleSwitchView()" title="Switch">⇄</button>
        </div>
      </div>
      <!-- Activity Log view (default) -->
      <div id="view-activity">
        <div class="log-list log-list-compact" id="log-list"></div>
      </div>
      <!-- Reminders view -->
      <div id="view-reminders" style="display:none">
        <div class="reminders-list" id="reminders-list">
          <div style="font-size:11px;color:#00d4ff33">No active reminders</div>
        </div>
      </div>
      <!-- Next Event view -->
      <div id="view-event" style="display:none">
        <div id="next-event-block">
          <div id="next-event-title" style="font-size:12px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">—</div>
          <div id="next-event-time" style="font-size:10px;color:var(--hud-accent-dim);margin-top:2px;letter-spacing:1px;">—</div>
          <div id="next-event-loc" style="font-size:10px;color:var(--hud-accent-dim);margin-top:1px;opacity:0.7;"></div>
        </div>
      </div>
    </div>

    <!-- Activity overlay — на всю ліву колонку -->
    <div class="activity-overlay" id="activity-overlay">
      <div class="activity-overlay-head">
        <span>◈ Activity Log — Full</span>
        <button class="activity-close" onclick="closeActivityOverlay()">CLOSE ✕</button>
      </div>
      <div class="activity-overlay-list" id="activity-overlay-list"></div>
    </div>

    <!-- Бігуча стрічка — прикріплена знизу колонки -->
    <div class="ticker-wrap">
      <div class="ticker-row ticker-news" id="ticker-news-row">
        <div class="ticker-track" id="ticker-news">Loading news…</div>
      </div>
      <div class="ticker-row ticker-fin" id="ticker-fin-row">
        <div class="ticker-track" id="ticker-fin">Loading markets…</div>
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
    <div class="panel-title sec-gap">◈ Health</div>
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

    <div class="panel-title sec-gap">◈ Finance</div>
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

    <div class="panel-title sec-gap">◈ Mood</div>
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

    <div class="panel-title sec-gap">◈ Known Individuals</div>
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
<script src="/hud_script.js"></script>
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

import os as _os
_ASSETS_DIR = _os.path.join(_os.path.dirname(__file__), "hud_assets")


@app.route('/hud_styles.css')
def _hud_styles():
    from flask import Response
    with open(_os.path.join(_ASSETS_DIR, "hud_styles.css"), encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/css")


@app.route('/hud_script.js')
def _hud_script():
    from flask import Response
    with open(_os.path.join(_ASSETS_DIR, "hud_script.js"), encoding="utf-8") as f:
        return Response(f.read(), mimetype="application/javascript")


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
        'activity':       hud_state.get('activity', []),
        'ticker':         hud_state.get('ticker', {'finance': [], 'news': []}),
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


# --- Прямий канал для керування музикою (без LLM, миттєво) ---
_music_action_callback = None

def set_music_action_callback(fn):
    """fn(action: str, value=None) — мапиться на music_module у main."""
    global _music_action_callback
    _music_action_callback = fn

@socketio.on('music_action')
def on_music_action(data):
    """Прямі дії плеєра з HUD: play / pause / toggle / volume."""
    if not _music_action_callback:
        return
    action = (data or {}).get('action', '')
    value = (data or {}).get('value')
    if not action:
        return
    import threading
    threading.Thread(target=_music_action_callback, args=(action, value), daemon=True).start()


# --- YouTube пошук з HUD ---
_youtube_search_callback = None

def set_youtube_search_callback(fn):
    """fn(query: str) -> dict (результат пошуку). Підключається в main."""
    global _youtube_search_callback
    _youtube_search_callback = fn

@socketio.on('youtube_search')
def on_youtube_search(data):
    """Пошук YouTube з HUD-поля. Емітить назад результати."""
    query = (data or {}).get('query', '').strip()
    if not query:
        return
    if not _youtube_search_callback:
        socketio.emit('youtube_results', {"ok": False, "error": "YouTube offline"})
        return
    def _run():
        try:
            res = _youtube_search_callback(query)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        socketio.emit('youtube_results', res)
    import threading
    threading.Thread(target=_run, daemon=True).start()


def push_youtube_results(res: dict):
    """Дозволяє агенту (голосовий пошук) запушити результати в HUD."""
    socketio.emit('youtube_results', res)


@socketio.on('youtube_started')
def on_youtube_started(data):
    """HUD почав грати відео → ставимо музику на паузу (взаємна пауза)."""
    if _music_action_callback:
        import threading
        threading.Thread(target=_music_action_callback, args=("pause_for_youtube", None), daemon=True).start()


def update_hud(key: str, value):
    """Оновлює одне поле HUD і надсилає всім клієнтам."""
    hud_state[key] = value
    socketio.emit('state_update', {key: value})


def update_ticker(data: dict):
    """Оновлює бігучу стрічку (фінанси + новини). Зберігає для нових клієнтів."""
    hud_state["ticker"] = data
    socketio.emit('state_update', {'ticker': data})


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
    """Додає запис в лог дня на HUD + у серверну історію активності."""
    from datetime import datetime
    t = datetime.now().strftime('%H:%M')
    socketio.emit('state_update', {
        'log_entry': {
            'role': role,
            'text': text,
            'time': t,
        }
    })
    # дублюємо в історію активності, щоб overlay (/activity) показував і переписку
    try:
        prefix = "SIR: " if role == "user" else "J: "
        entry = {"text": prefix + str(text), "kind": "chat", "time": t}
        _activity_log.append(entry)
        if len(_activity_log) > _ACTIVITY_MAX:
            del _activity_log[:len(_activity_log) - _ACTIVITY_MAX]
        hud_state["activity"] = _activity_log[-10:]
    except Exception:
        pass


def add_message(role: str, text: str):
    """Додає повідомлення в лог розмови."""
    socketio.emit('state_update', {'new_message': {'role': role, 'text': text}})


# --- Централізований журнал подій системи (Activity Log) ---
# Окремо від переписки: тут автономні дії JARVIS (тригери, погода, нагадування...).
_activity_log = []          # історія подій сесії (для оверлея)
_ACTIVITY_MAX = 200         # скільки тримати в пам'яті

def log_activity(event: str, kind: str = "info"):
    """
    Записує системну подію у стрічку Activity.
    kind: info | trigger | reminder | weather | music | calendar | mood | error
    """
    from datetime import datetime
    entry = {
        "text": str(event),
        "kind": kind,
        "time": datetime.now().strftime("%H:%M:%S"),
    }
    _activity_log.append(entry)
    if len(_activity_log) > _ACTIVITY_MAX:
        del _activity_log[:len(_activity_log) - _ACTIVITY_MAX]
    # зберігаємо останні в hud_state, щоб новий клієнт одразу бачив
    hud_state["activity"] = _activity_log[-10:]
    socketio.emit('state_update', {'activity_event': entry})


def get_activity_log() -> list:
    """Повна історія подій сесії — для оверлея (етап Б)."""
    return list(_activity_log)


@app.route('/activity')
def _activity_route():
    from flask import jsonify
    return jsonify(get_activity_log())


def _system_monitor():
    """Фоновий потік — CPU/RAM/Disk/Net/Uptime кожні 3 секунди."""
    import time as _t
    _boot = _t.time()
    _last_net = psutil.net_io_counters()
    _last_t = _t.time()
    while True:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        try:
            disk = psutil.disk_usage("/").percent
        except Exception:
            disk = 0
        # мережа — швидкість за інтервал
        now = _t.time()
        net = psutil.net_io_counters()
        dt = max(0.1, now - _last_t)
        down = (net.bytes_recv - _last_net.bytes_recv) / dt / 1024  # KB/s
        up   = (net.bytes_sent - _last_net.bytes_sent) / dt / 1024
        _last_net, _last_t = net, now
        # uptime
        up_s = int(now - _boot)
        h, m, s = up_s // 3600, (up_s % 3600) // 60, up_s % 60
        uptime = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        socketio.emit('state_update', {
            'cpu': cpu, 'ram': ram, 'disk': round(disk),
            'net_down': round(down), 'net_up': round(up), 'uptime': uptime,
        })
        _t.sleep(2)


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