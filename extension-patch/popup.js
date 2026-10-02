/**
 * popup.js
 *
 * Reads the same chrome.storage.local keys background.js already
 * writes (currentSession, current_hour, sessions) - no new storage
 * format introduced, this just renders what's already there using the
 * shared FocusGuard AI theme.
 */

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function classificationPillClass(classification) {
  if (classification === 'productive') return 'pill pill-focus';
  if (classification === 'distracted') return 'pill pill-alert';
  return 'pill';
}

function computeLiveElapsedSeconds(session) {
  if (!session) return 0;
  const base = session.accumulatedActiveMs || 0;
  if (session.isPaused) return Math.round(base / 1000);
  const lastActive = typeof session.lastActiveTime === 'number' ? session.lastActiveTime : Date.now();
  const extra = Math.max(0, Date.now() - lastActive);
  return Math.round((base + extra) / 1000);
}

const BACKEND_URL = 'http://127.0.0.1:8000';
let tickInterval = null;

// Account connection: the extension used to silently log into (or
// auto-create) a fixed service account, so tracked browsing never
// showed up in the user's real streaks/leaderboard/insights. Now the
// user connects their actual web-dashboard account here once; the
// token/user_id this stores is exactly what background.js's
// ensureBackendAuth() reads before syncing anything.
async function renderAccountSection() {
  const connectedEl = document.getElementById('account-connected');
  const formEl = document.getElementById('account-form');
  let { backend_token, backend_user_id, backend_username } = await chrome.storage.local.get(
    ['backend_token', 'backend_user_id', 'backend_username']
  );
  // Same self-healing check as background.js's ensureBackendAuth(): a
  // token with no backend_username predates the Account section and is
  // a leftover login to the old placeholder account, not one the user
  // actually chose - drop it so the popup shows "connect" immediately
  // on open instead of a misleading "Connected as user #N".
  if (backend_token && backend_user_id && !backend_username) {
    await chrome.storage.local.remove(['backend_token', 'backend_user_id', 'backend_username']);
    backend_token = null;
    backend_user_id = null;
  }
  if (backend_token && backend_user_id) {
    connectedEl.style.display = '';
    formEl.style.display = 'none';
    document.getElementById('account-username').textContent = backend_username || `user #${backend_user_id}`;
  } else {
    connectedEl.style.display = 'none';
    formEl.style.display = '';
  }
}

async function connectAccount(username, password, isNewAccount) {
  const errorEl = document.getElementById('account-error');
  errorEl.style.display = 'none';
  const endpoint = isNewAccount ? '/users/register' : '/users/login';
  try {
    const resp = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const detail = resp.status === 401
        ? 'Incorrect username or password.'
        : resp.status === 400
        ? 'That username is already taken.'
        : `Could not reach the backend (HTTP ${resp.status}).`;
      errorEl.textContent = detail;
      errorEl.style.display = '';
      return;
    }
    const data = await resp.json();
    await chrome.storage.local.set({
      backend_token: data.api_token,
      backend_user_id: data.user_id,
      backend_username: username,
    });
    // Connected by hand: pin this account (no longer just following the
    // dashboard), and share it with the system tracker - which also
    // starts the tracker if it isn't running yet.
    await chrome.storage.local.remove(['backend_link_auto', 'backend_link_disabled']);
    fetch(`${BACKEND_URL}/device-link`, {
      method: 'POST', headers: { 'Authorization': `Bearer ${data.api_token}` },
    }).catch(() => {});
    await renderAccountSection();
    loadWeeklyInsight();
  } catch (err) {
    errorEl.textContent = "Couldn't reach the backend - is it running?";
    errorEl.style.display = '';
  }
}

async function disconnectAccount() {
  await chrome.storage.local.remove(['backend_token', 'backend_user_id', 'backend_username', 'backend_link_auto']);
  // Otherwise the background worker would quietly re-adopt the
  // dashboard's account a moment later - stays off until reconnected.
  await chrome.storage.local.set({ backend_link_disabled: true });
  await renderAccountSection();
}

// Fires chrome.notifications.create() directly, bypassing all
// distraction-detection logic, so a "still no notifications" report
// can be narrowed down to either the OS/Chrome notification pipeline
// (this test also fails) or the detection logic (this test succeeds
// but real distraction/break alerts still don't show).
function sendTestNotification() {
  const resultEl = document.getElementById('test-notification-result');
  resultEl.textContent = 'Sending...';
  const iconUrl = chrome.runtime.getURL('icons/icon48.png');
  chrome.notifications.create(`fg_test_${Date.now()}`, {
    type: 'basic',
    iconUrl,
    title: 'FocusGuard AI test',
    message: 'If you can see this, OS notifications are working.',
    priority: 2,
  }, (notificationId) => {
    if (chrome.runtime.lastError) {
      resultEl.textContent = `Failed: ${chrome.runtime.lastError.message}. Check Windows notification settings (Focus Assist) and Chrome's own notification permission.`;
    } else {
      resultEl.textContent = `Sent (id: ${notificationId}). Didn't see it? Check Windows Focus Assist / Chrome notification settings - the extension did its part.`;
    }
  });
}

// Weekly insight (novelty feature: when the user is in a group, the same
// AI-written summary shown on the web dashboard also comments on group
// standing, not just solo stats) - fetched once per popup open, not on
// every 1s render tick, since it's backed by a 6-hour server-side cache
// and there's no reason to hammer the backend for unchanged text.
async function loadWeeklyInsight() {
  const el = document.getElementById('insight-text');
  try {
    const { backend_token, backend_user_id } = await chrome.storage.local.get(['backend_token', 'backend_user_id']);
    if (!backend_token || !backend_user_id) {
      el.textContent = 'Not synced with the backend yet.';
      return;
    }
    const resp = await fetch(`${BACKEND_URL}/insights/${backend_user_id}?days=7`, {
      headers: { 'Authorization': `Bearer ${backend_token}` },
    });
    if (!resp.ok) {
      el.textContent = "Couldn't load this week's insight.";
      return;
    }
    const data = await resp.json();
    el.textContent = data.insight_text;
  } catch (err) {
    el.textContent = "Couldn't reach the backend.";
  }
}

// Feature 7 (novelty), popup side: this used to show only the
// extension's OWN locally-ticked browser tab, so the moment you
// switched to a system app (VS Code, a game, anything outside the
// browser) the popup kept showing stale browser-tab data forever -
// window_tracker.py's readings never appeared here at all, only on the
// web dashboard. Falls back to the shared /live-status reading (the
// same one the dashboard's "Right now" card uses) whenever there's no
// genuinely active local browser session, so a system app shows up
// here too. Throttled independently of the 1s local-render tick so it
// doesn't hammer the network every second.
let lastSharedStatus = null;
let lastSharedStatusFetch = 0;
const SHARED_STATUS_POLL_MS = 5000;

async function fetchSharedLiveStatus() {
  const now = Date.now();
  if (lastSharedStatus !== null && now - lastSharedStatusFetch < SHARED_STATUS_POLL_MS) {
    return lastSharedStatus;
  }
  lastSharedStatusFetch = now;
  try {
    const { backend_token, backend_user_id } = await chrome.storage.local.get(['backend_token', 'backend_user_id']);
    if (!backend_token || !backend_user_id) { lastSharedStatus = null; return null; }
    const resp = await fetch(`${BACKEND_URL}/live-status/${backend_user_id}`, {
      headers: { 'Authorization': `Bearer ${backend_token}` },
    });
    lastSharedStatus = resp.ok ? await resp.json() : null;
  } catch (err) {
    lastSharedStatus = null;
  }
  return lastSharedStatus;
}

function sharedCategoryLabel(category) {
  if (category === 'productive') return 'Productive';
  if (category === 'distraction') return 'Distracted';
  return 'Neutral';
}

async function renderLiveCard(session) {
  const sourceEl = document.getElementById('live-source');
  if (session && (session.domain || session.name) && !session.isPaused) {
    document.getElementById('live-domain').textContent = session.name || session.domain;
    document.getElementById('live-category').textContent =
      session.category === 'educational' ? 'Productive' :
      session.category === 'non_educational' ? 'Distraction' : 'Unclear';
    document.getElementById('live-timer').textContent = formatDuration(computeLiveElapsedSeconds(session));
    sourceEl.textContent = '';
    return;
  }

  const shared = await fetchSharedLiveStatus();
  if (!shared || shared.stale) {
    document.getElementById('live-domain').textContent = 'No active tab tracked';
    document.getElementById('live-category').textContent = '-';
    document.getElementById('live-timer').textContent = '0:00';
    sourceEl.textContent = '';
    return;
  }
  document.getElementById('live-domain').textContent = shared.name;
  document.getElementById('live-category').textContent = sharedCategoryLabel(shared.category);
  document.getElementById('live-timer').textContent = '';
  sourceEl.textContent = shared.source === 'extension' ? ' · Browser tab' : ' · System app';
}

async function renderPopup() {
  const data = await chrome.storage.local.get(['currentSession', 'current_hour', 'sessions']);
  const session = data.currentSession || null;
  const hour = data.current_hour || { switch_count: 0, classification: 'productive' };
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];

  // --- Live session (local browser tab, or the shared cross-surface reading) ---
  await renderLiveCard(session);

  // --- This hour ---
  document.getElementById('hour-count').textContent = hour.switch_count || 0;
  const pillEl = document.getElementById('hour-pill');
  pillEl.className = classificationPillClass(hour.classification);
  pillEl.textContent = hour.classification
    ? hour.classification.charAt(0).toUpperCase() + hour.classification.slice(1)
    : 'Productive';

  // --- Recent activity ---
  const listEl = document.getElementById('recent-list');
  const recent = sessions.slice(0, 5);
  if (recent.length === 0) {
    listEl.innerHTML = `<div style="color:var(--text-soft); font-size:var(--step--1);">Nothing tracked yet.</div>`;
  } else {
    listEl.innerHTML = recent.map(s => `
      <div class="activity-item">
        <span class="name">${(s.name || s.domain || 'Unknown').replace(/</g, '&lt;')}</span>
        <span class="dur">${formatDuration(s.durationSeconds || s.duration || 0)}</span>
      </div>
    `).join('');
  }
}

function boot() {
  renderIcon(document.getElementById('status-icon'), 'shield', 22);
  renderIcon(document.getElementById('icon-account'), 'user', 15);
  renderIcon(document.getElementById('icon-live'), 'timer', 15);
  renderIcon(document.getElementById('icon-hour'), 'target', 15);
  renderIcon(document.getElementById('icon-recent'), 'scroll', 15);
  renderIcon(document.getElementById('icon-insight'), 'ai', 15);
  renderIcon(document.getElementById('icon-test'), 'settings', 15);

  document.getElementById('test-notification-btn').addEventListener('click', sendTestNotification);

  renderAccountSection();
  document.getElementById('account-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const username = document.getElementById('account-username-input').value.trim();
    const password = document.getElementById('account-password-input').value;
    const isNewAccount = document.getElementById('account-new-checkbox').checked;
    if (!username || !password) return;
    connectAccount(username, password, isNewAccount);
  });
  document.getElementById('account-disconnect').addEventListener('click', disconnectAccount);

  renderPopup();
  tickInterval = setInterval(renderPopup, 1000);
  loadWeeklyInsight();

  // Let background.js know the popup opened, same message it already
  // listens for, so it reconciles the active tab if needed.
  if (chrome.runtime && chrome.runtime.sendMessage) {
    chrome.runtime.sendMessage({ type: 'POPUP_OPENED' }, () => { /* response not needed here */ });
  }
}

document.addEventListener('DOMContentLoaded', boot);

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    formatDuration, classificationPillClass, computeLiveElapsedSeconds, renderPopup, loadWeeklyInsight,
    renderAccountSection, connectAccount, disconnectAccount,
    fetchSharedLiveStatus, sharedCategoryLabel, renderLiveCard,
  };
}
