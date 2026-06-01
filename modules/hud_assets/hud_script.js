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
  // синхронізуємо головну кнопку: показуємо дію, яку зробить клік
  const toggleBtn = document.getElementById('btn-toggle');
  if (toggleBtn) toggleBtn.textContent = isPlaying ? '⏸' : '▶';
}

// ── Music controls ────────────────────────────────────────────────────────
function musicAction(action, value) {
  try {
    socket.emit('music_action', { action: action, value: value });
  } catch (e) { console.warn('music_action failed', e); }
}

// клік по volume-бару = встановити гучність (0-100 за позицією кліку)
document.addEventListener('DOMContentLoaded', function () {
  const track = document.getElementById('vol-bar-track');
  if (track) {
    track.addEventListener('click', function (e) {
      const rect = track.getBoundingClientRect();
      let pct = Math.round(((e.clientX - rect.left) / rect.width) * 100);
      pct = Math.max(0, Math.min(100, pct));
      document.getElementById('vol-bar').style.width = pct + '%';
      musicAction('volume', pct);
    });
  }
});

// ── Activity events (системні події у лог-стрічці) ────────────────────────
var ACTIVITY_COLORS = {
  info: '#00d4ff', trigger: '#ff9500', reminder: '#9b59b6',
  weather: '#00d4ff', music: '#00ff88', calendar: '#3a6df0',
  mood: '#ff5e7e', error: '#ff3b30', chat: '#3a6df0'
};
var _activityHistory = [];

function _activityRowHTML(ev) {
  var color = ACTIVITY_COLORS[ev.kind] || '#00d4ff';
  return '<span class="log-time">' + (ev.time || '') + '</span>' +
    '<span class="log-act-text"><span style="color:' + color + '">◇</span> ' +
    String(ev.text).substring(0, 90) + (String(ev.text).length > 90 ? '…' : '') +
    '</span>';
}

function renderActivityEvent(ev) {
  _activityHistory.push(ev);
  if (_activityHistory.length > 200) _activityHistory.shift();

  var logEl = document.getElementById('log-list');
  if (logEl) {
    var div = document.createElement('div');
    div.className = 'log-item log-activity';
    div.innerHTML = _activityRowHTML(ev);
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
    while (logEl.children.length > 30) logEl.removeChild(logEl.firstChild);
  }
  var ov = document.getElementById('activity-overlay-list');
  if (ov && document.getElementById('activity-overlay').classList.contains('open')) {
    var d2 = document.createElement('div');
    d2.className = 'log-item'; d2.innerHTML = _activityRowHTML(ev);
    ov.appendChild(d2); ov.scrollTop = ov.scrollHeight;
  }
}

function openActivityOverlay() {
  var ov = document.getElementById('activity-overlay');
  var list = document.getElementById('activity-overlay-list');
  if (!ov || !list) return;
  ov.classList.add('open');
  list.innerHTML = '<div style="color:#00d4ff55;font-style:italic">Loading…</div>';
  // тягнемо повну історію з сервера (переживає перезавантаження сторінки)
  fetch('/activity')
    .then(function (r) { return r.json(); })
    .then(function (events) {
      list.innerHTML = '';
      if (!events || events.length === 0) {
        list.innerHTML = '<div style="color:#00d4ff55;font-style:italic">No activity yet.</div>';
        return;
      }
      events.forEach(function (ev) {
        var d = document.createElement('div');
        d.className = 'log-item'; d.innerHTML = _activityRowHTML(ev);
        list.appendChild(d);
      });
      list.scrollTop = list.scrollHeight;
    })
    .catch(function () {
      // фолбек на локальну історію
      list.innerHTML = '';
      _activityHistory.forEach(function (ev) {
        var d = document.createElement('div');
        d.className = 'log-item'; d.innerHTML = _activityRowHTML(ev);
        list.appendChild(d);
      });
    });
}
function closeActivityOverlay() {
  var ov = document.getElementById('activity-overlay');
  if (ov) ov.classList.remove('open');
}

// ── Перемикач Reminders ⇄ Next Event ──────────────────────────────────────
var _showingReminders = true;
function toggleReminderEvent() {
  _showingReminders = !_showingReminders;
  document.getElementById('view-reminders').style.display = _showingReminders ? 'block' : 'none';
  document.getElementById('view-event').style.display = _showingReminders ? 'none' : 'block';
  document.getElementById('switch-title').textContent =
    _showingReminders ? '◈ Active Reminders' : '◈ Next Event';
}

// ── YouTube ───────────────────────────────────────────────────────────────
var _ytCurrentId = null;

function ytSearch() {
  var input = document.getElementById('yt-input');
  var q = (input.value || '').trim();
  if (!q) return;
  var res = document.getElementById('yt-results');
  res.innerHTML = '<div class="yt-hint">Searching…</div>';
  socket.emit('youtube_search', { query: q });
}

function ytRenderResults(data) {
  var res = document.getElementById('yt-results');
  if (!res) return;
  if (!data || !data.ok) {
    var err = (data && data.error) || 'Search failed';
    res.innerHTML = '<div class="yt-hint">' + err + '</div>';
    return;
  }
  if (!data.items || data.items.length === 0) {
    res.innerHTML = '<div class="yt-hint">Nothing found.</div>';
    return;
  }
  res.innerHTML = '';
  data.items.forEach(function (it) {
    var div = document.createElement('div');
    div.className = 'yt-item';
    div.onclick = function () { ytPlay(it.videoId); };
    div.innerHTML =
      '<img src="' + it.thumbnail + '" alt="">' +
      '<div class="yt-item-info">' +
        '<div class="yt-item-title">' + _esc(it.title) + '</div>' +
        '<div class="yt-item-channel">' + _esc(it.channel) + '</div>' +
      '</div>';
    res.appendChild(div);
  });
}

function _esc(s) {
  var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML;
}

function ytPlay(videoId) {
  _ytCurrentId = videoId;
  var mini = document.getElementById('yt-mini');
  var frame = document.getElementById('yt-mini-frame');
  frame.src = 'https://www.youtube.com/embed/' + videoId + '?autoplay=1';
  mini.style.display = 'block';
}

function ytExpand() {
  if (!_ytCurrentId) return;
  var frame = document.getElementById('yt-modal-frame');
  frame.src = 'https://www.youtube.com/embed/' + _ytCurrentId + '?autoplay=1';
  document.getElementById('yt-modal').classList.add('open');
}

function ytCloseModal() {
  document.getElementById('yt-modal').classList.remove('open');
  document.getElementById('yt-modal-frame').src = '';  // стоп відтворення
}

// результати пошуку (з HUD-поля або від голосового тула)
socket.on('youtube_results', function (data) { ytRenderResults(data); });

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
  if (data.uptime !== undefined) {
    var u = document.getElementById('uptime-val'); if (u) u.textContent = data.uptime;
  }
  if (data.disk !== undefined) {
    var d = document.getElementById('disk-val'); if (d) d.textContent = data.disk + '%';
  }
  if (data.net_down !== undefined || data.net_up !== undefined) {
    var n = document.getElementById('net-val');
    if (n) {
      var fmt = function (kb) { return kb >= 1024 ? (kb/1024).toFixed(1) + 'M' : Math.round(kb) + 'K'; };
      n.textContent = '↓' + fmt(data.net_down || 0) + ' ↑' + fmt(data.net_up || 0);
    }
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

  // Системна подія активності (тригери, погода, музика, нагадування...)
  if (data.activity_event) {
    renderActivityEvent(data.activity_event);
  }
  // Початковий список подій при підключенні
  if (data.activity && Array.isArray(data.activity)) {
    data.activity.forEach(renderActivityEvent);
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
if (e.key === 'Escape' && document.getElementById('yt-modal').classList.contains('open')) {
ytCloseModal();
}
});
// Клік повз модал — закрити
document.getElementById('health-modal').addEventListener('click', (e) => {
if (e.target.id === 'health-modal') closeHealthModal();
});
document.getElementById('yt-modal').addEventListener('click', (e) => {
if (e.target.id === 'yt-modal') ytCloseModal();
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