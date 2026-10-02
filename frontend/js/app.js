/**
 * app.js
 *
 * Dashboard logic: navigation between views, and wiring each view to
 * real backend data via api.js. Everything here reads/writes your
 * actual backend - nothing is mocked.
 */

if (!Auth.isLoggedIn()) {
  window.location.href = '/auth';
}

const userId = Auth.getUserId();
let activeFocusPoll = null;
let focusTicker = null;
let focusLocal = null; // { remainingSeconds, plannedSeconds }
let focusOnBreak = false; // tracks which render branch is showing, so the poll can detect a break-state flip triggered elsewhere (e.g. another tab)
let currentTabPoll = null;
const loadedViews = new Set();

const RING_SIZE = 200, RING_STROKE = 14;
const RING_R = (RING_SIZE - RING_STROKE) / 2;
const RING_C = 2 * Math.PI * RING_R;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function minutes(seconds) { return Math.round(seconds / 60); }

// ---- Gamified touches: rank medals + badge icons (Streaks/Leaderboard) ----

function rankMedal(rank) {
  if (rank >= 1 && rank <= 3) return colorIcon('medal', 28, { rank });
  return `#${rank}`;
}

const BADGE_ICONS = {
  '3-Day Streak': 'flame',
  'Week Warrior': 'bolt',
  'Two-Week Titan': 'medal',
  'Month Master': 'crown',
};
function badgeIcon(name) {
  const iconName = BADGE_ICONS[name];
  return iconName ? colorIcon(iconName, 16) : icon('star', 16);
}

// The backend always sends badge names in English (see BADGE_THRESHOLDS
// in backend/main.py) - map them to translated display names here
// rather than translating server-side, so BADGE_ICONS' lookup (keyed by
// the original English names) stays untouched regardless of language.
const BADGE_NAME_KEYS = {
  '3-Day Streak': 'dashboard.streak.badge_3day',
  'Week Warrior': 'dashboard.streak.badge_week',
  'Two-Week Titan': 'dashboard.streak.badge_twoweek',
  'Month Master': 'dashboard.streak.badge_month',
};
function translateBadgeName(name) {
  const key = BADGE_NAME_KEYS[name];
  return key ? t(key) : name;
}

// ---- Navigation ----

const VALID_VIEWS = ['overview', 'focus', 'streak', 'badges', 'board', 'insight', 'history'];

function switchView(viewName, { updateHash = true } = {}) {
  document.querySelectorAll('.path-item').forEach(el => el.classList.toggle('active', el.dataset.view === viewName));
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${viewName}`));

  // Keeps the current section in the URL (without piling up history
  // entries for every click) so reloading the page - or bookmarking a
  // link to it - lands back on that same section instead of always
  // snapping back to Overview.
  if (updateHash) history.replaceState(null, '', `#${viewName}`);

  if (viewName !== 'focus' && activeFocusPoll) {
    clearInterval(activeFocusPoll);
    activeFocusPoll = null;
    stopFocusTicker();
  }
  if (viewName !== 'focus' && currentTabPoll) {
    clearInterval(currentTabPoll);
    currentTabPoll = null;
  }

  if (!loadedViews.has(viewName)) {
    loadedViews.add(viewName);
    if (viewName === 'overview') loadOverview();
    if (viewName === 'focus') { loadFocusView(); startCurrentTabPoll(); }
    if (viewName === 'streak') loadStreakView();
    if (viewName === 'board') loadBoardView();
    if (viewName === 'badges') loadBadgesView();
    if (viewName === 'insight') loadInsightView();
    if (viewName === 'history') loadHistoryView();
  } else if (viewName === 'focus') {
    loadFocusView(); // focus state can change while away, always refresh
    startCurrentTabPoll();
  }
}

document.querySelectorAll('.path-item').forEach(el => {
  el.addEventListener('click', () => switchView(el.dataset.view));
});

document.getElementById('logout-btn').addEventListener('click', async () => {
  // Stops the tracker/extension syncing to this account too.
  try { await Api.unlinkDevice(); } catch (e) { /* backend offline - still sign out */ }
  Auth.clearSession();
  window.location.href = '/';
});

// ---- Shell: mascots + user chip + language switcher ----

function initLanguageSwitcher() {
  const select = document.getElementById('language-select');
  select.innerHTML = I18N_SUPPORTED.map((lang) =>
    `<option value="${lang.code}">${escapeHtml(lang.label)}</option>`
  ).join('');
  select.value = getCurrentLanguage();
  select.addEventListener('change', () => setLanguage(select.value));
  // Re-render whichever view is currently showing whenever the language
  // changes, so JS-built content (not just data-i18n static markup)
  // picks up the new language immediately instead of on next reload.
  onLanguageChange(() => {
    select.value = getCurrentLanguage();
    let username = Auth.getUsername() || t('dashboard.overview.default_username');
    document.getElementById('overview-greeting').textContent = t('dashboard.overview.welcome_back', { username });
    loadedViews.forEach((viewName) => {
      if (viewName === 'overview') loadOverview();
      if (viewName === 'focus') loadFocusView();
      if (viewName === 'streak') loadStreakView();
      if (viewName === 'board') loadBoardView();
      if (viewName === 'badges') loadBadgesView();
      if (viewName === 'insight') loadInsightView();
      if (viewName === 'history') loadHistoryView();
    });
  });
}

// Dark (the cinematic default) or light. The choice lives in
// localStorage so the inline <head> script in app.html can apply it
// before first paint on the next visit.
const THEME_STORAGE_KEY = 'fg_theme';

function currentTheme() {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

function applyTheme(theme) {
  if (theme === 'light') document.documentElement.dataset.theme = 'light';
  else delete document.documentElement.dataset.theme;
  try { localStorage.setItem(THEME_STORAGE_KEY, theme); } catch (e) { /* storage blocked - theme just won't persist */ }
  updateThemeToggle();
}

function updateThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  const isLight = currentTheme() === 'light';
  // Shows the icon of the mode you'd switch TO, like most OS toggles.
  renderIcon(btn, isLight ? 'moon' : 'sun', 18);
  const label = t(isLight ? 'dashboard.nav.switch_to_dark' : 'dashboard.nav.switch_to_light');
  btn.setAttribute('aria-label', label);
  btn.title = label;
  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) themeColor.content = isLight ? '#F5F1FC' : '#0a0812';
}

function initThemeToggle() {
  updateThemeToggle();
  document.getElementById('theme-toggle').addEventListener('click', () => {
    applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
  });
  onLanguageChange(updateThemeToggle);
}

// Collapsible sidebar (icons only when collapsed), remembered across
// visits - the inline <head> script in app.html applies it before paint.
const SIDEBAR_STORAGE_KEY = 'fg_sidebar';

function isSidebarCollapsed() {
  return document.documentElement.dataset.sidebar === 'collapsed';
}

function updateSidebarToggle() {
  const btn = document.getElementById('sidebar-toggle');
  const label = t(isSidebarCollapsed() ? 'dashboard.nav.expand_sidebar' : 'dashboard.nav.collapse_sidebar');
  btn.setAttribute('aria-label', label);
  btn.title = label;
  btn.setAttribute('aria-expanded', String(!isSidebarCollapsed()));
  // Collapsed, the labels are hidden - keep each item named on hover.
  document.querySelectorAll('.path-item').forEach((el) => {
    const labelEl = el.querySelector('[data-i18n]');
    if (isSidebarCollapsed() && labelEl) el.title = labelEl.textContent;
    else el.removeAttribute('title');
  });
}

function initSidebarToggle() {
  renderIcon(document.getElementById('sidebar-toggle'), 'sidebar', 18);
  updateSidebarToggle();
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    const collapse = !isSidebarCollapsed();
    if (collapse) document.documentElement.dataset.sidebar = 'collapsed';
    else delete document.documentElement.dataset.sidebar;
    try { localStorage.setItem(SIDEBAR_STORAGE_KEY, collapse ? 'collapsed' : 'expanded'); } catch (e) { /* not remembered */ }
    updateSidebarToggle();
  });
  onLanguageChange(updateSidebarToggle);
}

function initShell() {
  renderIcon(document.getElementById('chip-icon'), 'user', 18);
  renderIcon(document.getElementById('logout-icon'), 'logout', 18);
  renderIcon(document.getElementById('lang-icon'), 'globe', 16);
  renderIcon(document.getElementById('stone-overview'), 'home', 15);
  renderIcon(document.getElementById('stone-focus'), 'timer', 15);
  renderIcon(document.getElementById('stone-streak'), 'flame', 15);
  renderIcon(document.getElementById('stone-board'), 'trophy', 15);
  renderIcon(document.getElementById('stone-badges'), 'badge', 15);
  renderIcon(document.getElementById('stone-insight'), 'scroll', 15);
  renderIcon(document.getElementById('stone-history'), 'clock', 15);
  renderIcon(document.getElementById('refresh-icon'), 'refresh', 15);
  initLanguageSwitcher();
  initThemeToggle();
  initSidebarToggle();

  const username = Auth.getUsername() || t('dashboard.overview.default_username');
  document.getElementById('chip-username').textContent = username;
  document.getElementById('overview-greeting').textContent = t('dashboard.overview.welcome_back', { username });

  Api.linkDevice().catch(() => { /* best-effort: tracking just stays on whatever was linked */ });

  Api.getMe().then((profile) => {
    document.getElementById('chip-username').textContent = profile.username;
    document.getElementById('overview-greeting').textContent = t('dashboard.overview.welcome_back', { username: profile.username });
    if (profile.avatar_url) {
      const chipIcon = document.getElementById('chip-icon');
      chipIcon.innerHTML = `<img src="${BACKEND_URL}${profile.avatar_url}" alt="">`;
    }
  }).catch(() => { /* profile fetch failing shouldn't block the rest of the dashboard */ });
}

// ---- Overview ----

async function loadOverview() {
  // Started together, and each card renders as soon as its own data
  // lands - none of them waits behind the (slower, LLM-backed) insights.
  const insightsReq = Api.getInsights(userId, { language: getCurrentLanguage() });
  const streaksReq = Api.getStreaks(userId);
  const boardReq = Api.getLeaderboard();
  const activityReq = Api.getHistory(userId, ACTIVITY_WEEKS * 7);
  [insightsReq, streaksReq, boardReq, activityReq].forEach((req) => req.catch(() => {}));
  activityReq.then((history) => renderActivityGrid(history.daily_totals))
    .catch((err) => {
      document.getElementById('activity-grid').innerHTML = `<div class="loading-row">${escapeHtml(err.message)}</div>`;
    });

  const statsDone = (async () => { try {
    const insights = await insightsReq;
    const totals = insights.category_totals_seconds;
    document.getElementById('overview-stats').innerHTML = `
      <div class="stat-tile"><div class="icon">${icon('timer', 22)}</div><div class="num">${minutes(totals.productive)}m</div><div class="label">${t('dashboard.overview.productive_7d')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('cross', 22)}</div><div class="num">${minutes(totals.distraction)}m</div><div class="label">${t('dashboard.overview.distracted_7d')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('scroll', 22)}</div><div class="num">${insights.session_count}</div><div class="label">${t('dashboard.overview.sessions_tracked')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('target', 22)}</div><div class="num">${insights.distraction_switch_count}</div><div class="label">${t('dashboard.overview.distracting_switches')}</div></div>
    `;
  } catch (err) {
    document.getElementById('overview-stats').innerHTML = `<div class="loading-row">${t('dashboard.overview.couldnt_load_stats', { message: escapeHtml(err.message) })}</div>`;
  } })();

  const streakDone = (async () => { try {
    const streaks = await streaksReq;
    document.getElementById('overview-streak-mini').innerHTML = `
      <div class="stat-tile" style="border:none; background:none; padding:0.4em 0 0;">
        <div class="icon">${colorIcon('flame', 30)}</div>
        <div class="num" style="font-size:2.2rem;">${t('dashboard.overview.streak_days', { count: streaks.current_streak })}</div>
        <div class="label">${t('dashboard.overview.best_ever', { count: streaks.longest_streak })}</div>
      </div>`;
  } catch (err) {
    document.getElementById('overview-streak-mini').textContent = t('dashboard.overview.couldnt_load_streak');
  } })();

  const boardDone = (async () => { try {
    const board = await boardReq;
    const el = document.getElementById('overview-board-mini');
    if (!board) {
      el.innerHTML = t('dashboard.overview.no_group_yet');
    } else {
      el.innerHTML = board.entries.slice(0, 3).map(e =>
        `<div class="board-row"><span class="board-rank medal">${rankMedal(e.rank)}</span><span class="board-name">${escapeHtml(e.username)}</span><span class="board-score">${e.focus_score}%</span></div>`
      ).join('');
    }
  } catch (err) {
    document.getElementById('overview-board-mini').textContent = t('dashboard.overview.couldnt_load_leaderboard');
  } })();

  await Promise.all([statsDone, streakDone, boardDone]);
}

// ---- Activity grid (Overview) ----
// GitHub/LeetCode-style: one box per day for the last ACTIVITY_WEEKS
// weeks, a column per week (Mon at the top). A box fills on any day with
// tracked activity, deeper for more productive time. Dates are UTC days,
// matching how the backend buckets sessions (see /history).

const ACTIVITY_WEEKS = 26;
const DAY_MS = 24 * 60 * 60 * 1000;

function activityLevel(day) {
  if (!day) return 0;
  const total = day.productive_seconds + day.distraction_seconds + day.neutral_seconds;
  if (total <= 0) return 0;
  const productiveMinutes = day.productive_seconds / 60;
  if (productiveMinutes < 30) return 1;
  if (productiveMinutes < 90) return 2;
  if (productiveMinutes < 180) return 3;
  return 4;
}

function renderActivityGrid(dailyTotals) {
  const lang = getCurrentLanguage();
  const byDate = new Map(dailyTotals.map((d) => [d.date, d]));
  const now = new Date();
  const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const todayDow = (new Date(todayUtc).getUTCDay() + 6) % 7; // Mon = 0
  const firstDay = todayUtc - ((ACTIVITY_WEEKS - 1) * 7 + todayDow) * DAY_MS;
  const monthFmt = new Intl.DateTimeFormat(lang, { month: 'short', timeZone: 'UTC' });
  const dateFmt = new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const weekdayFmt = new Intl.DateTimeFormat(lang, { weekday: 'short', timeZone: 'UTC' });

  let cells = '';
  let months = '';
  let activeDays = 0;
  let lastMonth = null;
  for (let w = 0; w < ACTIVITY_WEEKS; w++) {
    const weekStart = new Date(firstDay + w * 7 * DAY_MS);
    const month = weekStart.getUTCMonth();
    months += `<span>${month !== lastMonth && w < ACTIVITY_WEEKS - 1 ? escapeHtml(monthFmt.format(weekStart)) : ''}</span>`;
    lastMonth = month;
    for (let d = 0; d < 7; d++) {
      const dayMs = firstDay + (w * 7 + d) * DAY_MS;
      if (dayMs > todayUtc) { cells += '<span class="activity-cell future"></span>'; continue; }
      const iso = new Date(dayMs).toISOString().slice(0, 10);
      const day = byDate.get(iso);
      const level = activityLevel(day);
      if (level > 0) activeDays += 1;
      const label = level > 0
        ? t('dashboard.overview.activity_day', { date: dateFmt.format(dayMs), minutes: minutes(day.productive_seconds) })
        : t('dashboard.overview.activity_none', { date: dateFmt.format(dayMs) });
      cells += `<span class="activity-cell level-${level}${dayMs === todayUtc ? ' today' : ''}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"></span>`;
    }
  }
  // Mon / Wed / Fri labels on the left, like GitHub's.
  const weekdays = [0, 1, 2, 3, 4, 5, 6].map((d) => {
    const label = d % 2 === 0 && d < 6 ? weekdayFmt.format(new Date(firstDay + d * DAY_MS)) : '';
    return `<span>${escapeHtml(label)}</span>`;
  }).join('');
  const legend = [0, 1, 2, 3, 4].map((l) => `<span class="activity-cell level-${l}"></span>`).join('');

  document.getElementById('activity-summary').textContent = t('dashboard.overview.activity_summary', { count: activeDays });
  const grid = document.getElementById('activity-grid');
  grid.innerHTML = `
    <div class="activity-scroll">
      <div class="activity-layout" style="--weeks:${ACTIVITY_WEEKS}">
        <div class="activity-months">${months}</div>
        <div class="activity-weekdays">${weekdays}</div>
        <div class="activity-cells" role="img" aria-label="${escapeHtml(t('dashboard.overview.activity_summary', { count: activeDays }))}">${cells}</div>
      </div>
    </div>
    <div class="activity-legend">${t('dashboard.overview.activity_less')} ${legend} ${t('dashboard.overview.activity_more')}</div>
  `;
  // Newest weeks are on the right - on narrow screens, start scrolled there.
  const scroller = grid.querySelector('.activity-scroll');
  scroller.scrollLeft = scroller.scrollWidth;
}

// ---- Focus Mode ----

// Feature 7 (novelty): shows whichever surface most recently reported
// in - the browser extension for a tab, window_tracker.py for a system
// app - so Focus Mode always reflects what you're actually doing right
// now, not just your Pomodoro state.
function currentTabPillClass(category) {
  if (category === 'productive') return 'pill pill-focus';
  if (category === 'distraction') return 'pill pill-alert';
  return 'pill';
}

function currentTabLabel(category) {
  if (category === 'productive') return t('dashboard.focus.category_productive');
  if (category === 'distraction') return t('dashboard.focus.category_distracted');
  return t('dashboard.focus.category_neutral');
}

async function loadCurrentTabCard() {
  const card = document.getElementById('current-tab-card');
  if (!card) return;
  const rightNowHeading = `<h4 style="margin:0 0 0.6em; font-size:var(--step--1); color:var(--text-soft);">${t('dashboard.focus.right_now')}</h4>`;
  try {
    const status = await Api.getLiveStatus(userId);
    if (!status || status.stale) {
      card.innerHTML = `
        ${rightNowHeading}
        <p style="color:var(--text-soft); margin:0 auto;">${t('dashboard.focus.not_tracking')}</p>
      `;
      return;
    }
    const sourceLabel = status.source === 'extension' ? t('dashboard.focus.browser_tab') : t('dashboard.focus.system_app');
    card.innerHTML = `
      ${rightNowHeading}
      <div style="display:flex; align-items:center; justify-content:space-between; gap:var(--space-2);">
        <div style="min-width:0;">
          <div style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(status.name)}</div>
          <div style="font-size:var(--step--1); color:var(--text-soft);">${sourceLabel}</div>
        </div>
        <span class="${currentTabPillClass(status.category)}">${currentTabLabel(status.category)}</span>
      </div>
    `;
  } catch (err) {
    card.innerHTML = `
      ${rightNowHeading}
      <p style="color:var(--text-soft); margin:0 auto;">${t('dashboard.focus.couldnt_reach_backend')}</p>
    `;
  }
}

function startCurrentTabPoll() {
  if (currentTabPoll) clearInterval(currentTabPoll);
  loadCurrentTabCard();
  currentTabPoll = setInterval(loadCurrentTabCard, 5000);
}

async function loadFocusView() {
  const card = document.getElementById('focus-card');
  let session;
  try {
    session = await Api.getActiveFocusSession();
  } catch (err) {
    card.innerHTML = `<p>${t('dashboard.focus.couldnt_reach_backend_msg', { message: escapeHtml(err.message) })}</p>`;
    return;
  }

  if (session && session.status === 'active') {
    renderFocusSession(session);
    startFocusPoll();
  } else {
    renderFocusStartForm();
  }
}

// Single dispatcher for "what does an active-or-just-finished focus
// session look like right now" - used by the initial load, the poll
// loop, and both break-transition handlers, so there's one place that
// decides among running / on-break / finished instead of three.
function renderFocusSession(session) {
  if (!session || session.status !== 'active') { renderFinishedFocus(session); return; }
  if (session.on_break) renderPausedFocus(session); else renderActiveFocus(session);
}

// Shared poll loop for an active focus session, used both right after
// starting one and after resuming an already-active one on view load.
function startFocusPoll() {
  if (activeFocusPoll) clearInterval(activeFocusPoll);
  activeFocusPoll = setInterval(async () => {
    try {
      const updated = await Api.getActiveFocusSession();
      if (!updated || updated.status !== 'active') {
        clearInterval(activeFocusPoll);
        activeFocusPoll = null;
        stopFocusTicker();
        renderFinishedFocus(updated);
        return;
      }
      if (updated.on_break !== focusOnBreak) {
        // Break state flipped from elsewhere (e.g. another open tab) -
        // switch render branch instead of just patching the numbers.
        renderFocusSession(updated);
      } else if (!updated.on_break) {
        // Re-sync the local counter from the backend's true value
        // without touching the DOM - the per-second ticker owns the
        // display, this just corrects any drift.
        focusLocal = { remainingSeconds: updated.remaining_seconds, plannedSeconds: updated.planned_duration_seconds };
        updateDistractionWarning(updated);
      }
    } catch (err) { /* transient network hiccup - try again next tick */ }
  }, 4000);
}

function flashFocusMessage(text) {
  const card = document.getElementById('focus-card');
  if (!card) return;
  const el = document.createElement('div');
  el.className = 'auth-msg';
  el.style.marginTop = 'var(--space-2)';
  el.style.textAlign = 'center';
  el.textContent = text;
  card.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

async function handleTakeBreak(sessionId) {
  stopFocusTicker();
  try {
    const updated = await Api.startBreak(sessionId);
    renderFocusSession(updated);
  } catch (err) { /* leave the running view as-is; next poll corrects */ }
}

async function handleEndBreak(sessionId) {
  try {
    const result = await Api.endBreak(sessionId);
    renderFocusSession(result.session);
    if (result.penalty_applied) {
      flashFocusMessage(t('dashboard.focus.break_penalty_msg', { minutes: Math.round(result.penalty_seconds / 60) }));
    }
  } catch (err) { /* leave the paused view as-is; next poll corrects */ }
}

// Reflects the same grace-period clock the extension's every-15s nagging
// notification is built on (see background.js's checkFocusDistraction) -
// shown here too so the web dashboard tells the same story.
function updateDistractionWarning(session) {
  const el = document.getElementById('focus-distraction-warning');
  if (!el) return;
  if (session.distraction_seconds_accumulated > 0) {
    el.style.display = '';
    el.textContent = t('dashboard.focus.distraction_warning', { seconds: session.grace_seconds_remaining });
  } else {
    el.style.display = 'none';
  }
}

// Builds the ring's static markup once; updatePomodoroDisplay() then only
// touches the two values that actually change (dashoffset + digits) each
// second, so the DOM node is never destroyed - CSS transitions/animations
// on it keep running continuously instead of restarting every tick.
function pomodoroRingMarkup() {
  const c = RING_SIZE / 2;
  return `
    <div class="pomodoro-orb">
      <div class="pomodoro-glow"></div>
      <svg viewBox="0 0 ${RING_SIZE} ${RING_SIZE}" class="pomodoro-ring">
        <defs>
          <linearGradient id="pomodoro-ring-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" style="stop-color:var(--ring-a)"/>
            <stop offset="100%" style="stop-color:var(--ring-b)"/>
          </linearGradient>
        </defs>
        <circle cx="${c}" cy="${c}" r="${RING_R}" fill="none" stroke="var(--lavender-bg-deep)" stroke-width="${RING_STROKE}"/>
        <circle class="pomodoro-progress" cx="${c}" cy="${c}" r="${RING_R}" fill="none" stroke="url(#pomodoro-ring-grad)" stroke-width="${RING_STROKE}"
          stroke-linecap="round" stroke-dasharray="${RING_C}" stroke-dashoffset="0"
          transform="rotate(-90 ${c} ${c})"/>
      </svg>
      <div class="pomodoro-time" id="pomodoro-time"></div>
    </div>
  `;
}

function updatePomodoroDisplay(remainingSeconds, plannedSeconds) {
  const planned = Math.max(1, plannedSeconds);
  const progress = Math.min(1, Math.max(0, (planned - remainingSeconds) / planned));
  const progressEl = document.querySelector('.pomodoro-progress');
  const timeEl = document.getElementById('pomodoro-time');
  if (progressEl) progressEl.style.strokeDashoffset = String(RING_C * progress);
  if (timeEl) {
    const mins = Math.floor(remainingSeconds / 60);
    const secs = remainingSeconds % 60;
    timeEl.textContent = `${mins}:${String(secs).padStart(2, '0')}`;
  }
}

function startFocusTicker() {
  // Only replace the interval - stopFocusTicker() would also clear the
  // focusLocal countdown the caller just set, freezing the display until
  // the next 4s poll re-filled it.
  if (focusTicker) clearInterval(focusTicker);
  focusTicker = setInterval(() => {
    if (!focusLocal) return;
    focusLocal.remainingSeconds = Math.max(0, focusLocal.remainingSeconds - 1);
    updatePomodoroDisplay(focusLocal.remainingSeconds, focusLocal.plannedSeconds);
  }, 1000);
}

function stopFocusTicker() {
  if (focusTicker) { clearInterval(focusTicker); focusTicker = null; }
  focusLocal = null;
}

// Full screen for a running session: just the timer card, filling the
// screen, so nothing else on the page competes for attention.
function focusFullscreenButtonMarkup() {
  return `<button class="btn btn-secondary focus-fullscreen-btn" id="focus-fullscreen-btn"></button>`;
}

function updateFocusFullscreenButton() {
  const btn = document.getElementById('focus-fullscreen-btn');
  if (!btn) return;
  const isFull = document.fullscreenElement === document.getElementById('focus-card');
  btn.innerHTML = `${icon(isFull ? 'shrink' : 'expand', 16)} <span>${t(isFull ? 'dashboard.focus.exit_fullscreen' : 'dashboard.focus.enter_fullscreen')}</span>`;
}

function wireFocusFullscreenButton() {
  const btn = document.getElementById('focus-fullscreen-btn');
  if (!btn) return;
  if (!document.fullscreenEnabled) { btn.remove(); return; }
  updateFocusFullscreenButton();
  btn.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.getElementById('focus-card').requestFullscreen();
    } catch (e) { /* browser refused - stay as is */ }
  });
}

function exitFocusFullscreen() {
  if (document.fullscreenElement === document.getElementById('focus-card')) document.exitFullscreen().catch(() => {});
}

document.addEventListener('fullscreenchange', updateFocusFullscreenButton);

function renderActiveFocus(session) {
  focusOnBreak = false;
  document.getElementById('focus-card').innerHTML = `
    ${pomodoroRingMarkup()}
    <p class="focus-encourage">${t('dashboard.focus.encourage')}</p>
    <p id="focus-distraction-warning" class="focus-status-msg broken" style="display:none; font-size:var(--step--1); padding:0.6em 1em; margin-top:var(--space-2);"></p>
    <div style="text-align:center; display:flex; gap:var(--space-2); justify-content:center; flex-wrap:wrap;">
      <button class="btn btn-secondary" id="take-break-btn">${t('dashboard.focus.take_a_break')}</button>
      <button class="btn btn-secondary" id="give-up-btn">${t('dashboard.focus.give_up_early')}</button>
      ${focusFullscreenButtonMarkup()}
    </div>
  `;
  wireFocusFullscreenButton();
  focusLocal = { remainingSeconds: session.remaining_seconds, plannedSeconds: session.planned_duration_seconds };
  updatePomodoroDisplay(focusLocal.remainingSeconds, focusLocal.plannedSeconds);
  updateDistractionWarning(session);
  startFocusTicker();
  document.getElementById('take-break-btn').addEventListener('click', () => handleTakeBreak(session.id));
  document.getElementById('give-up-btn').addEventListener('click', async () => {
    if (activeFocusPoll) { clearInterval(activeFocusPoll); activeFocusPoll = null; }
    stopFocusTicker();
    const result = await Api.endFocusSession(session.id);
    renderFinishedFocus(result);
  });
}

// While on break, the ring/time is drawn once at its frozen value and
// never ticks - matches the backend freezing elapsed/remaining for the
// whole duration of session.break_started_at (see _focus_true_elapsed_seconds).
function renderPausedFocus(session) {
  focusOnBreak = true;
  stopFocusTicker();
  document.getElementById('focus-card').innerHTML = `
    ${pomodoroRingMarkup()}
    <p class="focus-encourage">${t('dashboard.focus.on_break')}</p>
    <div style="text-align:center; display:flex; gap:var(--space-2); justify-content:center; flex-wrap:wrap;">
      <button class="btn btn-primary" id="im-back-btn">${t('dashboard.focus.im_back')}</button>
      ${focusFullscreenButtonMarkup()}
    </div>
  `;
  wireFocusFullscreenButton();
  updatePomodoroDisplay(session.remaining_seconds, session.planned_duration_seconds);
  document.getElementById('im-back-btn').addEventListener('click', () => handleEndBreak(session.id));
}

function renderFinishedFocus(session) {
  exitFocusFullscreen();
  if (!session) { renderFocusStartForm(); return; }
  const isComplete = session.status === 'completed';
  const minTracked = t('dashboard.focus.min_tracked', { count: minutes(session.elapsed_seconds) });
  const distractionSuffix = session.distraction_seconds_accumulated > 0
    ? t('dashboard.focus.distraction_time_spent', { seconds: session.distraction_seconds_accumulated })
    : '';
  document.getElementById('focus-card').innerHTML = `
    <div class="focus-status-msg ${isComplete ? 'complete' : 'broken'}">
      <span style="display:inline-flex; vertical-align:middle; margin-right:0.4em;">${icon(isComplete ? 'check' : 'cross', 22)}</span>
      ${isComplete ? t('dashboard.focus.session_complete') : t('dashboard.focus.session_broken')}
    </div>
    <p style="text-align:center; color:var(--text-soft); margin:0 auto;">
      ${minTracked}${distractionSuffix}.
    </p>
    <div style="text-align:center; margin-top:var(--space-2);">
      <button class="btn btn-primary" id="start-again-btn">${t('dashboard.focus.start_another')}</button>
    </div>
  `;
  document.getElementById('start-again-btn').addEventListener('click', renderFocusStartForm);
}

function renderFocusStartForm() {
  exitFocusFullscreen();
  document.getElementById('focus-card').innerHTML = `
    <p class="no-badges-msg" style="margin-bottom:var(--space-3);">${t('dashboard.focus.no_active_session')}</p>
    <form id="start-focus-form" class="focus-idle-form">
      <div class="field">
        <label for="focus-minutes">${t('dashboard.focus.minutes_label')}</label>
        <input type="number" id="focus-minutes" min="1" max="180" value="25" required>
      </div>
      <button type="submit" class="btn btn-primary">${t('dashboard.focus.start_focus_mode')}</button>
    </form>
    <div id="focus-start-error" class="auth-msg error" style="display:none; margin-top:var(--space-2);"></div>
  `;
  document.getElementById('start-focus-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const mins = parseInt(document.getElementById('focus-minutes').value, 10);
    try {
      const session = await Api.startFocusSession(mins);
      renderFocusSession(session);
      startFocusPoll();
    } catch (err) {
      const errEl = document.getElementById('focus-start-error');
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });
}

// ---- Streaks ----

async function loadStreakView() {
  try {
    const streaks = await Api.getStreaks(userId);
    document.getElementById('streak-stats').innerHTML = `
      <div class="stat-tile"><div class="icon">${colorIcon('flame', 30)}</div><div class="num">${streaks.current_streak}</div><div class="label">${t('dashboard.streak.current_streak')}</div></div>
      <div class="stat-tile"><div class="icon">${colorIcon('trophy', 30)}</div><div class="num">${streaks.longest_streak}</div><div class="label">${t('dashboard.streak.best_ever')}</div></div>
    `;
    const badgeHtml = streaks.badges.length
      ? `<div class="badge-row">${streaks.badges.map(b => `<span class="pill pill-achieve">${badgeIcon(b)} ${escapeHtml(translateBadgeName(b))}</span>`).join('')}</div>`
      : `<p class="no-badges-msg">${t('dashboard.streak.no_badges')}</p>`;
    document.getElementById('streak-badges').innerHTML = badgeHtml;

    const daysHtml = streaks.days.length
      ? streaks.days.slice().reverse().map(d => `
          <div class="board-row">
            <span class="pill ${d.is_success ? 'pill-achieve' : 'pill-alert'}">${d.is_success ? '✅ ' + t('dashboard.streak.focused') : '⚠️ ' + t('dashboard.streak.missed')}</span>
            <span class="board-name">${escapeHtml(d.date)}</span>
            <span style="color:var(--text-soft); font-size:0.85rem;">${t('dashboard.streak.day_summary', { minutes: minutes(d.productive_seconds), count: d.distraction_switches })}</span>
          </div>`).join('')
      : `<div class="empty-state">${t('dashboard.streak.no_tracked_days')}</div>`;
    document.getElementById('streak-days').innerHTML = daysHtml;
  } catch (err) {
    document.getElementById('streak-stats').innerHTML = `<div class="loading-row">${t('dashboard.streak.couldnt_load_streaks', { message: escapeHtml(err.message) })}</div>`;
  }
}

// ---- Badges ----
// The catalog (ids, tiers, targets, progress) comes from the backend;
// names, descriptions and artwork live here. Badges are listed in the
// backend's order, which runs roughly from first steps to long-haul.

const BADGE_GLYPHS = {
  first_spark: 'ai', ember_keeper: 'flame', flow_weaver: 'flame', unbreakable: 'shield',
  deep_diver: 'target', iron_will: 'shield', pomodoro_pro: 'timer', focus_titan: 'timer',
  ten_hour_club: 'clock', centurion: 'clock', zen_master: 'check', early_bird: 'sun',
  night_owl: 'moon', squad_up: 'user', top_of_pack: 'trophy',
};
const BADGE_TIER_KEYS = { 1: 'dashboard.badges.tier_common', 2: 'dashboard.badges.tier_rare', 3: 'dashboard.badges.tier_epic' };

async function loadBadgesView() {
  const gridEl = document.getElementById('badge-grid');
  try {
    const data = await Api.getBadges(userId);
    const pct = data.total ? Math.round((data.earned_count / data.total) * 100) : 0;
    document.getElementById('badges-summary').innerHTML = `
      <div class="badges-summary-text">${t('dashboard.badges.unlocked_count', { earned: data.earned_count, total: data.total })}</div>
      <div class="board-bar-wrap badges-summary-bar"><span class="board-bar" style="width:${pct}%;"></span></div>
    `;
    // Unlocked first, so progress is the first thing you see.
    const ordered = [...data.badges.filter((b) => b.earned), ...data.badges.filter((b) => !b.earned)];
    gridEl.innerHTML = ordered.map((b) => {
      const name = t(`dashboard.badges.items.${b.id}.name`);
      const desc = t(`dashboard.badges.items.${b.id}.desc`);
      const status = b.earned
        ? `<span class="badge-status earned">${icon('check', 14)} ${t('dashboard.badges.earned')}</span>`
        : `<div class="badge-progress">
             <div class="board-bar-wrap"><span class="board-bar" style="width:${Math.round((b.progress / b.target) * 100)}%;"></span></div>
             <span class="badge-progress-num">${b.progress} / ${b.target}</span>
           </div>`;
      return `
        <div class="badge-card ${b.earned ? 'earned' : 'locked'} tier-${b.tier}">
          <div class="badge-art-wrap">
            ${badgeArt(BADGE_GLYPHS[b.id] || 'star', b.tier, 72)}
            ${b.earned ? '' : `<span class="badge-lock" aria-hidden="true">${icon('lock', 14)}</span>`}
          </div>
          <div class="badge-tier">${t(BADGE_TIER_KEYS[b.tier])}</div>
          <div class="badge-name">${escapeHtml(name)}</div>
          <p class="badge-desc">${escapeHtml(desc)}</p>
          ${status}
        </div>`;
    }).join('');
  } catch (err) {
    gridEl.innerHTML = `<div class="loading-row">${t('dashboard.badges.couldnt_load', { message: escapeHtml(err.message) })}</div>`;
  }
}

// ---- Leaderboard ----

async function loadBoardView() {
  const card = document.getElementById('board-card');
  let group;
  try {
    group = await Api.getMyGroup();
  } catch (err) {
    card.innerHTML = `<p>${t('dashboard.board.couldnt_reach_backend_msg', { message: escapeHtml(err.message) })}</p>`;
    return;
  }

  if (!group) {
    card.innerHTML = `
      <div class="empty-state">
        <p>${t('dashboard.board.no_group')}</p>
        <div class="group-form-grid">
          <form id="create-group-form" class="group-form-col">
            <div class="field"><label for="group-name">${t('dashboard.board.new_group_name')}</label><input type="text" id="group-name" placeholder="Study Squad" required></div>
            <button type="submit" class="btn btn-primary group-form-btn">${t('dashboard.board.create_group')}</button>
          </form>
          <div class="group-form-divider">${t('dashboard.board.or')}</div>
          <form id="join-group-form" class="group-form-col">
            <div class="field"><label for="join-code">${t('dashboard.board.join_code_label')}</label><input type="text" id="join-code" placeholder="ABC123" required></div>
            <button type="submit" class="btn btn-primary group-form-btn">${t('dashboard.board.join_group')}</button>
          </form>
        </div>
        <div id="group-form-error" class="auth-msg error" style="display:none; margin-top:var(--space-2);"></div>
      </div>
    `;
    document.getElementById('create-group-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await Api.createGroup(document.getElementById('group-name').value.trim());
        loadBoardView();
      } catch (err) { showGroupFormError(err.message); }
    });
    document.getElementById('join-group-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await Api.joinGroup(document.getElementById('join-code').value.trim());
        loadBoardView();
      } catch (err) { showGroupFormError(err.message); }
    });
    return;
  }

  try {
    const board = await Api.getLeaderboard();
    const maxScore = Math.max(...board.entries.map(e => e.focus_score), 1);
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:var(--space-2);">
        <h3>${escapeHtml(board.group_name)}</h3>
        <span class="pill pill-focus">${t('dashboard.board.join_code_pill', { code: escapeHtml(group.join_code) })}</span>
      </div>
      ${board.entries.map(e => `
        <div class="board-row ${e.rank === 1 ? 'rank-1' : ''}">
          <span class="board-rank medal">${rankMedal(e.rank)}</span>
          <span class="board-name">${escapeHtml(e.username)}</span>
          <span class="board-bar-wrap"><span class="board-bar" style="width:${(e.focus_score / maxScore) * 100}%;"></span></span>
          <span class="board-score">${e.focus_score}%</span>
        </div>
      `).join('')}
      <div class="board-actions">
        <button class="btn btn-ghost" id="leave-group-btn">${icon('logout', 16)} <span>${t('dashboard.board.leave_group')}</span></button>
      </div>
    `;
    document.getElementById('leave-group-btn').addEventListener('click', async () => {
      if (!window.confirm(t('dashboard.board.leave_group_confirm', { name: board.group_name }))) return;
      try {
        await Api.leaveGroup();
        loadBoardView(); // shows the create/join form for the next group
        if (loadedViews.has('overview')) loadOverview();
      } catch (err) {
        flashBoardError(err.message);
      }
    });
  } catch (err) {
    card.innerHTML = `<p>${t('dashboard.board.couldnt_load_leaderboard', { message: escapeHtml(err.message) })}</p>`;
  }
}

function flashBoardError(text) {
  const card = document.getElementById('board-card');
  const el = document.createElement('div');
  el.className = 'auth-msg error';
  el.textContent = text;
  card.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

function showGroupFormError(text) {
  const el = document.getElementById('group-form-error');
  el.textContent = text;
  el.style.display = 'block';
}

// ---- Insights ----

async function loadInsightView(force = false) {
  try {
    const insights = await Api.getInsights(userId, { force, language: getCurrentLanguage() });
    const totals = insights.category_totals_seconds;
    document.getElementById('insight-stats').innerHTML = `
      <div class="stat-tile"><div class="icon">${icon('timer', 22)}</div><div class="num">${minutes(totals.productive)}m</div><div class="label">${t('dashboard.insight.productive')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('cross', 22)}</div><div class="num">${minutes(totals.distraction)}m</div><div class="label">${t('dashboard.insight.distracted')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('refresh', 22)}</div><div class="num">${insights.total_switch_count}</div><div class="label">${t('dashboard.insight.total_switches')}</div></div>
      <div class="stat-tile"><div class="icon">${icon('scroll', 22)}</div><div class="num">${insights.session_count}</div><div class="label">${t('dashboard.insight.sessions')}</div></div>
    `;
    document.getElementById('insight-text').textContent = insights.insight_text;
  } catch (err) {
    document.getElementById('insight-text').textContent = t('dashboard.insight.couldnt_load_insights', { message: err.message });
  }
}

document.getElementById('refresh-insight-btn').addEventListener('click', () => {
  document.getElementById('insight-text').textContent = t('dashboard.insight.rereading');
  loadInsightView(true);
});

// ---- History ----

const HISTORY_CATEGORY_COLORS = {
  productive: 'var(--accent-success)',
  distraction: 'var(--accent-alert)',
  neutral: 'var(--lavender-mid)',
};

function historySourceLabel(source) {
  // Reuses the same source labels already shown on the "Right now" card
  // (dashboard.focus.browser_tab/system_app) rather than duplicating
  // them under a new namespace.
  if (source === 'extension') return t('dashboard.focus.browser_tab');
  if (source === 'system') return t('dashboard.focus.system_app');
  return t('dashboard.history.source_combined');
}

// Hand-rolled inline SVG - no charting library, matching the rest of
// this no-build-step dashboard (see pomodoroRingMarkup for the same
// approach). One stacked bar per day: productive/distraction/neutral
// seconds scaled to the busiest day in the window.
function historyChartMarkup(dailyTotals) {
  if (!dailyTotals.length) return `<div class="empty-state">${t('dashboard.history.no_data')}</div>`;

  const width = 640, height = 180, barGap = 14, labelHeight = 24;
  const chartHeight = height - labelHeight;
  const barWidth = Math.min(48, (width - barGap * (dailyTotals.length + 1)) / dailyTotals.length);
  const maxTotal = Math.max(
    1, ...dailyTotals.map(d => d.productive_seconds + d.distraction_seconds + d.neutral_seconds)
  );

  let x = barGap;
  const bars = dailyTotals.map((d) => {
    const segments = [
      ['productive', d.productive_seconds],
      ['distraction', d.distraction_seconds],
      ['neutral', d.neutral_seconds],
    ];
    let y = chartHeight;
    const rects = segments.map(([cat, secs]) => {
      const segHeight = (secs / maxTotal) * (chartHeight - 8);
      y -= segHeight;
      return `<rect x="${x}" y="${y.toFixed(1)}" width="${barWidth}" height="${segHeight.toFixed(1)}" fill="${HISTORY_CATEGORY_COLORS[cat]}" rx="3"/>`;
    }).join('');
    const label = new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short' });
    const barX = x;
    x += barWidth + barGap;
    return `${rects}<text x="${barX + barWidth / 2}" y="${height - 6}" text-anchor="middle" font-size="11" fill="var(--text-soft)">${escapeHtml(label)}</text>`;
  }).join('');

  return `
    <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto;" role="img" aria-label="${t('dashboard.history.chart_heading')}">
      ${bars}
    </svg>
    <div style="display:flex; gap:var(--space-3); justify-content:center; margin-top:var(--space-2); font-size:var(--step--1); color:var(--text-soft);">
      <span><span style="display:inline-block; width:10px; height:10px; border-radius:3px; background:${HISTORY_CATEGORY_COLORS.productive}; margin-right:0.4em;"></span>${t('dashboard.insight.productive')}</span>
      <span><span style="display:inline-block; width:10px; height:10px; border-radius:3px; background:${HISTORY_CATEGORY_COLORS.distraction}; margin-right:0.4em;"></span>${t('dashboard.insight.distracted')}</span>
      <span><span style="display:inline-block; width:10px; height:10px; border-radius:3px; background:${HISTORY_CATEGORY_COLORS.neutral}; margin-right:0.4em;"></span>${t('dashboard.history.neutral')}</span>
    </div>
  `;
}

async function loadHistoryView() {
  try {
    const history = await Api.getHistory(userId, 7);

    document.getElementById('history-top-distraction').innerHTML = history.top_distraction_app
      ? `<div class="num" style="font-size:var(--step-2);">${escapeHtml(history.top_distraction_app.name)}</div>
         <div class="label" style="color:var(--text-soft);">${t('dashboard.history.time_spent', { minutes: minutes(history.top_distraction_app.total_seconds) })}</div>`
      : `<div class="empty-state">${t('dashboard.history.no_distraction_data')}</div>`;

    document.getElementById('history-best-day').innerHTML = history.most_productive_day
      ? `<div class="num" style="font-size:var(--step-2);">${escapeHtml(history.most_productive_day.date)}</div>
         <div class="label" style="color:var(--text-soft);">${t('dashboard.history.time_spent', { minutes: minutes(history.most_productive_day.productive_seconds) })}</div>`
      : `<div class="empty-state">${t('dashboard.history.no_data')}</div>`;

    document.getElementById('history-chart').innerHTML = historyChartMarkup(history.daily_totals);

    document.getElementById('history-top-apps').innerHTML = history.top_apps.length
      ? history.top_apps.map(a => `
          <div class="board-row">
            <span class="pill ${a.category === 'distraction' ? 'pill-alert' : a.category === 'productive' ? 'pill-achieve' : 'pill-focus'}">${escapeHtml(a.category)}</span>
            <span class="board-name">${escapeHtml(a.name)}</span>
            <span class="board-bar-wrap"><span class="board-bar" style="width:${Math.min(100, (a.total_seconds / history.top_apps[0].total_seconds) * 100)}%; background:${HISTORY_CATEGORY_COLORS[a.category] || 'var(--lavender-deep)'};"></span></span>
            <span style="color:var(--text-soft); font-size:0.85rem; min-width:9em; text-align:right;">${historySourceLabel(a.source)} &middot; ${minutes(a.total_seconds)}m</span>
          </div>`).join('')
      : `<div class="empty-state">${t('dashboard.history.no_data')}</div>`;
  } catch (err) {
    document.getElementById('history-chart').innerHTML = `<div class="loading-row">${t('dashboard.history.couldnt_load', { message: escapeHtml(err.message) })}</div>`;
  }
}

// ---- Boot ----

// Translations must be loaded before initShell()/switchView() run - both
// call t() while building their first markup.
(async () => {
  await initI18n();
  initShell();
  const initialView = VALID_VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  switchView(initialView);
})();

window.addEventListener('hashchange', () => {
  const viewName = VALID_VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  switchView(viewName, { updateHash: false });
});
