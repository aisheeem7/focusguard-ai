/**
 * api.js
 *
 * Thin wrapper around the backend's REST API. Stores the auth token in
 * localStorage (per-browser, not shared) so a page refresh doesn't log
 * you out. Change BACKEND_URL below if your backend runs somewhere
 * other than the default local address.
 */

// The backend that served this page - http://127.0.0.1:8000 when run
// locally, the site's own address when deployed online. Only the Vite
// dev server (5173/4173) or a page opened from disk talks to the local
// backend explicitly.
const BACKEND_URL = window.FOCUS_GROVE_BACKEND_URL || (
  /^https?:$/.test(window.location.protocol) && !['5173', '4173'].includes(window.location.port)
    ? window.location.origin
    : 'http://127.0.0.1:8000'
);

const Auth = {
  getToken() { return localStorage.getItem('fg_token'); },
  getUserId() {
    const id = localStorage.getItem('fg_user_id');
    return id ? parseInt(id, 10) : null;
  },
  getUsername() { return localStorage.getItem('fg_username'); },
  setSession({ api_token, user_id, username }) {
    localStorage.setItem('fg_token', api_token);
    localStorage.setItem('fg_user_id', String(user_id));
    if (username) localStorage.setItem('fg_username', username);
  },
  clearSession() {
    localStorage.removeItem('fg_token');
    localStorage.removeItem('fg_user_id');
    localStorage.removeItem('fg_username');
  },
  isLoggedIn() { return !!this.getToken(); },
};

async function apiRequest(path, { method = 'GET', body = null, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = Auth.getToken();
    if (!token) throw new Error('Not logged in');
    headers['Authorization'] = `Bearer ${token}`;
  }
  const resp = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const errBody = await resp.json();
      if (errBody.detail) detail = errBody.detail;
    } catch (e) { /* response wasn't JSON */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  if (resp.status === 204) return null;
  return resp.json();
}

const Api = {
  async register(username, password) {
    const data = await apiRequest('/users/register', { method: 'POST', body: { username, password }, auth: false });
    Auth.setSession(data);
    return data;
  },
  async login(username, password) {
    const data = await apiRequest('/users/login', { method: 'POST', body: { username, password }, auth: false });
    Auth.setSession(data);
    return data;
  },
  async getAnalytics(userId, { date, source } = {}) {
    const params = new URLSearchParams();
    if (date) params.set('date', date);
    if (source) params.set('source', source);
    const qs = params.toString() ? `?${params}` : '';
    return apiRequest(`/analytics/${userId}${qs}`);
  },
  async getStreaks(userId, threshold = 10) {
    return apiRequest(`/streaks/${userId}?threshold=${threshold}`);
  },
  async getMyGroup() {
    try {
      return await apiRequest('/groups/me');
    } catch (e) {
      if (e.status === 404) return null;
      throw e;
    }
  },
  async createGroup(name) {
    return apiRequest('/groups', { method: 'POST', body: { name } });
  },
  async joinGroup(joinCode) {
    return apiRequest('/groups/join', { method: 'POST', body: { join_code: joinCode } });
  },
  async leaveGroup() {
    return apiRequest('/groups/leave', { method: 'POST' });
  },
  async getLeaderboard(days = 7) {
    try {
      return await apiRequest(`/leaderboard?days=${days}`);
    } catch (e) {
      if (e.status === 400) return null; // no group joined yet
      throw e;
    }
  },
  async getActiveFocusSession() {
    try {
      return await apiRequest('/focus-sessions/active');
    } catch (e) {
      if (e.status === 404) return null;
      throw e;
    }
  },
  async startFocusSession(durationMinutes) {
    return apiRequest('/focus-sessions/start', { method: 'POST', body: { duration_minutes: durationMinutes } });
  },
  async endFocusSession(sessionId) {
    return apiRequest(`/focus-sessions/${sessionId}/end`, { method: 'POST' });
  },
  async startBreak(sessionId) {
    return apiRequest(`/focus-sessions/${sessionId}/break/start`, { method: 'POST' });
  },
  async endBreak(sessionId) {
    return apiRequest(`/focus-sessions/${sessionId}/break/end`, { method: 'POST' });
  },
  async getFocusHistory(limit = 10) {
    return apiRequest(`/focus-sessions/history?limit=${limit}`);
  },
  async getBadges(userId) {
    return apiRequest(`/badges/${userId}`);
  },
  async getHistory(userId, days = 7) {
    return apiRequest(`/history/${userId}?days=${days}`);
  },
  async updateProfile(payload) {
    return apiRequest('/users/me', { method: 'PATCH', body: payload });
  },
  async getInsights(userId, { days = 7, force = false, language = 'en' } = {}) {
    return apiRequest(`/insights/${userId}?days=${days}&force=${force}&language=${language}`);
  },
  async getMe() {
    return apiRequest('/users/me');
  },
  // Shares the signed-in account with this machine's system tracker and
  // browser extension (and starts the tracker if it isn't running), so
  // they track under it without logins of their own.
  async linkDevice() {
    return apiRequest('/device-link', { method: 'POST' });
  },
  async unlinkDevice() {
    return apiRequest('/device-link', { method: 'DELETE' });
  },
  async getLiveStatus(userId) {
    try {
      return await apiRequest(`/live-status/${userId}`);
    } catch (e) {
      if (e.status === 404) return null; // nothing has reported in yet
      throw e;
    }
  },
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Api, Auth, BACKEND_URL };
}
