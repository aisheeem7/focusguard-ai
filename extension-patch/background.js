/**
 * FocusGuard AI - Human Attention Preservation & Digital Distraction Intelligence Platform
 * Background Service Worker (Manifest V3)
 *
 * Core Responsibilities:
 * 1. Active Domain Detection: Detects normalized web domains (HTTP/HTTPS only).
 * 2. Session Tracking: Tracks browsing duration per domain and outputs Team 2 JSON records.
 * 3. Switch Tracking: Records domain switch events (from -> to) with timestamps.
 * 4. 1-Hour Switch Window: Tracks switch counts in fixed 1-hour windows (e.g. 09:00-10:00).
 * 5. Distraction Classification: Evaluates productivity (< 10 Productive, 10 Neutral, > 10 Distracted).
 * 6. Popup Focus Preservation: Prevents popup opens from terminating sessions or creating fake switches.
 */

/* ==========================================================================
   0. Backend Sync Integration (added - connects to shared Module 2 backend)
   ========================================================================== */

const BACKEND_URL = 'http://127.0.0.1:8000';

// His 'unknown' bucket (YouTube, Reddit) maps to 'ambiguous' conceptually
// on the system side, but the backend's analytics doesn't have that
// bucket yet, so 'unknown' safely maps to 'neutral' for now. A proper
// resolver prompt for the extension (matching the system side's) is a
// good Milestone 2 addition.
function mapCategoryToBackend(hisCategory) {
  switch (hisCategory) {
    case 'educational': return 'productive';
    case 'non_educational': return 'distraction';
    case 'unknown': return 'neutral';
    default: return 'neutral';
  }
}

// Previously this silently logged into (or auto-registered) a fixed
// 'focusguard_extension' service account when no token was cached, so
// every browsing session/switch synced to a shadow account completely
// disconnected from whatever account the user actually signed into on
// the web dashboard - streaks, records and insights there never saw
// this data. Now it only returns credentials the popup's Account
// section actually stored (via a real login to the user's own
// account), and returns null otherwise so callers skip syncing until
// the user connects - see popup.js's connectAccount().
async function ensureBackendAuth() {
  const cached = await chrome.storage.local.get(['backend_token', 'backend_user_id', 'backend_username', 'backend_link_auto']);
  // A token cached before the Account section existed has no
  // backend_username (only connectAccount() in popup.js ever sets that
  // key) - it's a leftover login to the old auto-created placeholder
  // account, not a real one the user chose. Silently keeping it forever
  // would keep syncing to the wrong account with no way for the user to
  // notice. Self-heal by dropping it here, so the next sync attempt
  // (and the popup's Account section) both show "not connected" until
  // the user picks their real account.
  if (cached.backend_token && cached.backend_user_id && !cached.backend_username) {
    console.log('[FocusGuard->Backend] Clearing a pre-Account-section login - please reconnect your real account from the popup.');
    await chrome.storage.local.remove(['backend_token', 'backend_user_id', 'backend_username']);
    return null;
  }
  // An account connected by hand in the popup always wins. Otherwise
  // follow whichever account is signed in on the dashboard (the device
  // link), so the extension tracks from the moment the browser opens
  // without a separate login - and follows sign-outs/account switches.
  if (cached.backend_token && cached.backend_user_id && !cached.backend_link_auto) {
    return { token: cached.backend_token, userId: cached.backend_user_id };
  }
  // Callers arriving while a check is already in flight (session post,
  // live status and presence ping all fire together at startup) wait for
  // that same answer instead of briefly seeing "not connected".
  if (!deviceLinkInFlight && Date.now() - lastDeviceLinkCheck >= DEVICE_LINK_REFRESH_MS) {
    lastDeviceLinkCheck = Date.now();
    deviceLinkInFlight = adoptDeviceLink(cached).finally(() => { deviceLinkInFlight = null; });
  }
  if (deviceLinkInFlight) {
    const linked = await deviceLinkInFlight;
    if (linked !== undefined) return linked;
  }
  if (cached.backend_token && cached.backend_user_id) {
    return { token: cached.backend_token, userId: cached.backend_user_id };
  }
  return null;
}

const DEVICE_LINK_REFRESH_MS = 30 * 1000;
let lastDeviceLinkCheck = 0;
let deviceLinkInFlight = null;

// Returns the auth to use, null once the dashboard has signed out, or
// undefined when there's nothing new to act on (backend offline, or not
// linked and never was) - the caller then falls back to what's cached.
async function adoptDeviceLink(cached) {
  const link = await fetchDeviceLink();
  if (link) {
    if (link.api_token !== cached.backend_token) {
      await chrome.storage.local.set({
        backend_token: link.api_token, backend_user_id: link.user_id,
        backend_username: link.username, backend_link_auto: true,
      });
      console.log(`[FocusGuard->Backend] Tracking as '${link.username}' (signed in on the dashboard).`);
      sendPresencePing(link.api_token).catch(() => {});
    }
    return { token: link.api_token, userId: link.user_id };
  }
  if (link === null && cached.backend_link_auto) {
    await chrome.storage.local.remove(['backend_token', 'backend_user_id', 'backend_username', 'backend_link_auto']);
    return null;
  }
  return undefined;
}

// Returns the dashboard's linked account, null if nobody is signed in,
// or undefined if the backend couldn't be reached (keep what we have).
// Disabled after the user disconnects from the popup, until they connect
// again - otherwise it would quietly re-link a moment later.
async function fetchDeviceLink() {
  try {
    const { backend_link_disabled } = await chrome.storage.local.get(['backend_link_disabled']);
    if (backend_link_disabled) return null;
    const resp = await fetch(`${BACKEND_URL}/device-link`);
    if (resp.status === 404) return null;
    if (!resp.ok) return undefined;
    return await resp.json();
  } catch (err) {
    return undefined;
  }
}

// Which browser this extension runs in, matching the process names
// window_tracker.py checks - lets the system tracker leave this
// browser's windows to the extension instead of counting them twice.
function detectBrowserClient() {
  const ua = (typeof navigator !== 'undefined' && navigator.userAgent) || '';
  if (/Edg\//.test(ua)) return 'msedge';
  if (/OPR\//.test(ua)) return 'opera';
  if (/Vivaldi/.test(ua)) return 'vivaldi';
  if (typeof navigator !== 'undefined' && navigator.brave) return 'brave';
  if (/Firefox\//.test(ua)) return 'firefox';
  return 'chrome';
}
const BROWSER_CLIENT = detectBrowserClient();

// "This browser is covered by the extension" check-in, every minute via
// chrome.alarms (which, unlike setInterval, wakes the MV3 service worker)
// - even while the browser is in the background, so the system tracker
// knows to step aside the instant you switch back to it.
const PRESENCE_ALARM = 'fg_presence';
async function sendPresencePing(tokenOverride) {
  let token = tokenOverride;
  if (!token) {
    const auth = await ensureBackendAuth();
    if (!auth) return;
    token = auth.token;
  }
  try {
    await fetch(`${BACKEND_URL}/extension/ping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ client: BROWSER_CLIENT }),
    });
  } catch (err) { /* backend offline - next alarm retries */ }
}

async function postSessionToBackend(session) {
  try {
    const auth = await ensureBackendAuth();
    if (!auth) {
      console.log('[FocusGuard->Backend] Not connected to an account yet - open the popup to connect.');
      return;
    }
    const { token } = auth;
    const payload = {
      source: 'extension',
      name: session.name || session.domain,
      category: mapCategoryToBackend(session.category),
      start_time: session.start_time,
      end_time: session.end_time,
      duration: session.duration,
    };
    const resp = await fetch(`${BACKEND_URL}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      console.warn('[FocusGuard->Backend] session post failed:', resp.status);
    } else {
      console.log('[FocusGuard->Backend] session posted:', payload.name, payload.category);
    }
  } catch (err) {
    console.warn('[FocusGuard->Backend] session post error (backend offline?):', err.message);
  }
}

// Feature 7 (novelty): pushes "here's what I'm looking at right now" so
// the web dashboard's Focus Mode page can show a live current-tab card.
// Best-effort, like every other backend sync call here - never blocks
// tracking if the backend or the account connection isn't available.
async function postLiveStatusToBackend(name, categoryRaw) {
  try {
    const auth = await ensureBackendAuth();
    if (!auth) return;
    const { token } = auth;
    const resp = await fetch(`${BACKEND_URL}/live-status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ source: 'extension', name, category: mapCategoryToBackend(categoryRaw), client: BROWSER_CLIENT }),
    });
    if (!resp.ok) {
      console.warn('[FocusGuard->Backend] live-status post failed:', resp.status);
    }
  } catch (err) {
    console.warn('[FocusGuard->Backend] live-status post error (backend offline?):', err.message);
  }
}

// Feature 8: one shared break-interval preference across the web
// dashboard, window_tracker.py, and this extension, instead of each
// surface hardcoding its own default. Cached locally with a short
// refresh window so checkBreakReminder (which runs frequently) doesn't
// hit /users/me on every check.
const BREAK_INTERVAL_CACHE_KEY = 'break_interval_minutes';
const BREAK_INTERVAL_FETCHED_AT_KEY = 'break_interval_fetched_at';
const BREAK_INTERVAL_REFRESH_MS = 5 * 60 * 1000;

async function fetchBreakIntervalFromBackend() {
  try {
    const auth = await ensureBackendAuth();
    if (!auth) return;
    const { token } = auth;
    const resp = await fetch(`${BACKEND_URL}/users/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const data = await resp.json();
    if (typeof data.break_interval_minutes === 'number') {
      await chrome.storage.local.set({
        [BREAK_INTERVAL_CACHE_KEY]: data.break_interval_minutes,
        [BREAK_INTERVAL_FETCHED_AT_KEY]: Date.now(),
      });
    }
  } catch (err) {
    console.warn('[FocusGuard->Backend] break-interval fetch error:', err.message);
  }
}

// Returns the configured interval in minutes, refreshing the cache in
// the background (fire-and-forget) when it's stale, so this call never
// blocks the caller on a network round-trip. Falls back to 50 minutes
// (the old hardcoded default) before the first successful fetch.
async function getBreakIntervalMinutes(now = Date.now()) {
  const data = await chrome.storage.local.get([BREAK_INTERVAL_CACHE_KEY, BREAK_INTERVAL_FETCHED_AT_KEY]);
  const stale = !data[BREAK_INTERVAL_FETCHED_AT_KEY] || (now - data[BREAK_INTERVAL_FETCHED_AT_KEY]) > BREAK_INTERVAL_REFRESH_MS;
  if (stale) fetchBreakIntervalFromBackend().catch(() => {});
  return typeof data[BREAK_INTERVAL_CACHE_KEY] === 'number' ? data[BREAK_INTERVAL_CACHE_KEY] : 50;
}

async function postSwitchToBackend(fromDomain, toDomain, toCategoryRaw) {
  try {
    const auth = await ensureBackendAuth();
    if (!auth) {
      console.log('[FocusGuard->Backend] Not connected to an account yet - open the popup to connect.');
      return;
    }
    const { token } = auth;
    const mappedCategory = mapCategoryToBackend(toCategoryRaw);
    const counts = await chrome.storage.local.get(['ext_total_switch_count', 'ext_distraction_switch_count']);
    const total = (counts.ext_total_switch_count || 0) + 1;
    const distraction = counts.ext_distraction_switch_count || 0;
    const newDistraction = mappedCategory === 'distraction' ? distraction + 1 : distraction;
    await chrome.storage.local.set({
      ext_total_switch_count: total,
      ext_distraction_switch_count: newDistraction,
    });
    const payload = {
      source: 'extension',
      from_app: fromDomain,
      to_app: toDomain,
      category: mappedCategory,
      total_switch_count: total,
      distraction_switch_count: newDistraction,
    };
    const resp = await fetch(`${BACKEND_URL}/switches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      console.warn('[FocusGuard->Backend] switch post failed:', resp.status);
    } else {
      console.log('[FocusGuard->Backend] switch posted:', fromDomain, '->', toDomain, `(total=${total}, distraction=${newDistraction})`);
    }
  } catch (err) {
    console.warn('[FocusGuard->Backend] switch post error (backend offline?):', err.message);
  }
}

/* ==========================================================================
   1. Constants & Configuration
   ========================================================================== */

const MAX_SESSIONS = 500;
const MAX_SWITCH_EVENTS = 500;
const MAX_HOURLY_SUMMARIES = 100;
const SWITCH_THRESHOLD = 10;

const DOMAIN_CATEGORIES = {
  'github.com': 'educational',
  'stackoverflow.com': 'educational',
  'coursera.org': 'educational',
  'udemy.com': 'educational',
  'instagram.com': 'non_educational',
  'netflix.com': 'non_educational',
  'youtube.com': 'unknown',
  'vimeo.com': 'unknown',
  'dailymotion.com': 'unknown'
};

// Domains where the domain alone can't tell productive from distracting
// apart (youtube.com hosts both tutorials and music videos) - any
// domain mapped to 'unknown' above qualifies automatically, so adding
// more later is just adding them to DOMAIN_CATEGORIES with 'unknown'.
// For these, the page/tab TITLE gets classified instead (see
// classifyByTitleAsync) - keyword-matched first, then the backend's
// same LLM chain used for everything else.
const AMBIGUOUS_TITLE_DOMAINS = new Set(
  Object.keys(DOMAIN_CATEGORIES).filter((d) => DOMAIN_CATEGORIES[d] === 'unknown')
);

const MAX_CACHE_ENTRIES = 2000;
const CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const CACHE_STORAGE_KEY = 'domain_classification_cache';

const RESOLVER_ENDPOINT = 'http://127.0.0.1:8000/classify-domain';
// A cache miss now costs an LLM call chain (Claude -> Gemini -> fallback)
// server-side instead of a static DB lookup, so this needs more room than
// the old 3s - still fully async/non-blocking (see classifyDomain, which
// never awaits this), just gives first-ever lookups a real chance to land.
const RESOLVER_TIMEOUT_MS = 8000;

const SLEEP_GAP_THRESHOLD_MS = 60 * 1000;
const HEARTBEAT_INTERVAL_MS = 10 * 1000;

let domainClassificationCache = {};
const pendingDomainResolutions = new Map();
let activeDomainResolver = null;
let currentSession = null;
let lastActiveDomain = null;
let sessionMutex = Promise.resolve();

function withSessionLock(fn) {
  const result = sessionMutex.then(async () => {
    return await fn();
  });
  sessionMutex = result.catch((err) => {
    console.error('[FocusGuard Lock Error]', err);
  });
  return result;
}

function getDomainFromUrl(url) {
  if (!url || typeof url !== 'string') return null;
  try {
    const parsedUrl = new URL(url);
    if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:') return null;
    return parsedUrl.hostname ? parsedUrl.hostname.toLowerCase() : null;
  } catch (error) {
    return null;
  }
}

function normalizeDomain(hostname) {
  if (!hostname || typeof hostname !== 'string') return null;
  const cleanHost = hostname.trim().toLowerCase();
  if (cleanHost.startsWith('www.')) return cleanHost.slice(4);
  return cleanHost;
}

function sanitizeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch (e) {
    return null;
  }
}

async function loadClassificationCache(now = Date.now()) {
  try {
    const data = await chrome.storage.local.get([CACHE_STORAGE_KEY]);
    const rawCache = data[CACHE_STORAGE_KEY] || {};
    domainClassificationCache = {};
    let hasExpired = false;
    for (const [domain, entry] of Object.entries(rawCache)) {
      if (entry && entry.category && typeof entry.timestamp === 'number') {
        const ttl = typeof entry.ttl === 'number' ? entry.ttl : CACHE_TTL_MS;
        if (now - entry.timestamp < ttl) {
          domainClassificationCache[domain] = entry;
        } else {
          hasExpired = true;
        }
      }
    }
    if (hasExpired) {
      await chrome.storage.local.set({ [CACHE_STORAGE_KEY]: domainClassificationCache });
    }
    return domainClassificationCache;
  } catch (err) {
    console.error('[FocusGuard] Error loading classification cache:', err);
    return domainClassificationCache;
  }
}

function getCachedDomainCategory(domain, now = Date.now()) {
  if (!domain || typeof domain !== 'string') return null;
  const clean = domain.trim().toLowerCase();
  const direct = domainClassificationCache[clean];
  if (direct && direct.category && typeof direct.timestamp === 'number') {
    const ttl = typeof direct.ttl === 'number' ? direct.ttl : CACHE_TTL_MS;
    if (now - direct.timestamp < ttl) return direct.category;
  }
  const parts = clean.split('.');
  for (let i = 1; i < parts.length - 1; i++) {
    const parent = parts.slice(i).join('.');
    const parentEntry = domainClassificationCache[parent];
    if (parentEntry && parentEntry.category && typeof parentEntry.timestamp === 'number') {
      const ttl = typeof parentEntry.ttl === 'number' ? parentEntry.ttl : CACHE_TTL_MS;
      if (now - parentEntry.timestamp < ttl) return parentEntry.category;
    }
  }
  return null;
}

async function setCachedDomainCategory(domain, category, options = {}) {
  if (!domain || typeof domain !== 'string') return null;
  const clean = domain.trim().toLowerCase();
  const validCategories = ['educational', 'non_educational', 'unknown'];
  const targetCategory = validCategories.includes(category) ? category : 'unknown';
  const entry = {
    domain: clean,
    category: targetCategory,
    timestamp: typeof options.timestamp === 'number' ? options.timestamp : Date.now(),
    ttl: typeof options.ttl === 'number' ? options.ttl : CACHE_TTL_MS,
    confidence: typeof options.confidence === 'number' ? options.confidence : 1.0,
    source: options.source || 'cache'
  };
  domainClassificationCache[clean] = entry;
  const keys = Object.keys(domainClassificationCache);
  if (keys.length > MAX_CACHE_ENTRIES) {
    const sorted = Object.values(domainClassificationCache).sort((a, b) => a.timestamp - b.timestamp);
    const toKeep = sorted.slice(sorted.length - MAX_CACHE_ENTRIES);
    domainClassificationCache = {};
    for (const item of toKeep) domainClassificationCache[item.domain] = item;
  }
  try {
    await chrome.storage.local.set({ [CACHE_STORAGE_KEY]: domainClassificationCache });
  } catch (err) {
    console.error('[FocusGuard] Error saving classification cache:', err);
  }
  return entry;
}

async function purgeExpiredCache(now = Date.now()) {
  let purgedCount = 0;
  const updatedCache = {};
  for (const [domain, entry] of Object.entries(domainClassificationCache)) {
    if (entry && entry.timestamp) {
      const ttl = typeof entry.ttl === 'number' ? entry.ttl : CACHE_TTL_MS;
      if (now - entry.timestamp < ttl) {
        updatedCache[domain] = entry;
      } else {
        purgedCount++;
      }
    }
  }
  domainClassificationCache = updatedCache;
  if (purgedCount > 0) {
    try {
      await chrome.storage.local.set({ [CACHE_STORAGE_KEY]: domainClassificationCache });
    } catch (e) {}
  }
  return purgedCount;
}

async function fetchDomainClassification(domain) {
  if (!domain || typeof domain !== 'string') return null;
  const clean = normalizeDomain(domain) || domain;
  let timeoutId = null;
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  if (controller) {
    timeoutId = setTimeout(() => { try { controller.abort(); } catch (e) {} }, RESOLVER_TIMEOUT_MS);
  }
  try {
    const auth = await ensureBackendAuth();
    if (!auth) return { category: 'unknown', confidence: 0.0, source: 'not_connected' };
    const { token } = auth;
    const fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ domain: clean })
    };
    if (controller) fetchOptions.signal = controller.signal;
    const response = await fetch(RESOLVER_ENDPOINT, fetchOptions);
    if (timeoutId) clearTimeout(timeoutId);
    if (!response.ok) return { category: 'unknown', confidence: 0.0, source: `http_${response.status}` };
    const data = await response.json();
    if (data && data.category) {
      const validCategories = ['educational', 'non_educational', 'unknown'];
      const rawCat = validCategories.includes(data.category) ? data.category : 'unknown';
      const confidence = typeof data.confidence === 'number' ? data.confidence : 0.0;
      const finalCat = confidence >= 0.80 ? rawCat : 'unknown';
      return { category: finalCat, confidence: confidence, source: data.source || 'server_domain_db' };
    }
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    return { category: 'unknown', confidence: 0.0, source: 'network_fallback' };
  }
  return null;
}

// In-memory only (never persisted to chrome.storage, unlike
// domainClassificationCache) - keyed by the exact title text, since
// caching a title-based result under the DOMAIN would be wrong (one
// tutorial video's "productive" result would then apply to every other
// youtube.com video, including the next music video). Session-lifetime
// is enough: it just avoids re-asking about the same still-open video
// on every heartbeat tick.
const titleClassificationCache = new Map();

async function classifyByTitleAsync(domain, title) {
  if (!title || typeof title !== 'string') return null;
  const key = title.trim().toLowerCase();
  if (!key) return null;
  if (titleClassificationCache.has(key)) return titleClassificationCache.get(key);
  let timeoutId = null;
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  if (controller) {
    timeoutId = setTimeout(() => { try { controller.abort(); } catch (e) {} }, RESOLVER_TIMEOUT_MS);
  }
  try {
    const auth = await ensureBackendAuth();
    if (!auth) return null;
    const { token } = auth;
    const fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ domain, title }),
    };
    if (controller) fetchOptions.signal = controller.signal;
    const response = await fetch(RESOLVER_ENDPOINT, fetchOptions);
    if (timeoutId) clearTimeout(timeoutId);
    if (!response.ok) return null;
    const data = await response.json();
    const validCategories = ['educational', 'non_educational', 'unknown'];
    const cat = data && validCategories.includes(data.category) ? data.category : 'unknown';
    titleClassificationCache.set(key, cat);
    return cat;
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    return null;
  }
}

// Shared by startSession (a brand-new ambiguous-domain session) and the
// tabs.onUpdated same-domain-title-changed case (navigating to a
// different video within one open YouTube tab, an SPA navigation that
// never changes the domain). Resolves in the background and, if the
// user is still on that same tab when the answer comes back, updates
// the live session's category in place - this is what lets a music
// video get correctly flagged as a distraction (notifications, the
// focus-mode grace-period clock) even though "youtube.com" alone
// looked neutral the instant the tab opened.
async function reclassifyActiveSessionByTitle(tabId, domain, title) {
  const titleCategory = await classifyByTitleAsync(domain, title);
  if (!titleCategory || titleCategory === 'unknown') return;
  await applyCategoryToActiveSession(tabId, domain, titleCategory, `Title-based reclassification: "${title}"`);
}

// Updates the still-open session in place once a slower classification
// lands, and takes the same actions a known site gets right away -
// live status (Focus Mode's grace clock) and the distraction nudge.
async function applyCategoryToActiveSession(tabId, domain, category, reason) {
  const current = await getActiveSession();
  if (current && (current.tabId === tabId || current.tab_id === tabId) && (current.domain === domain || current.name === domain)) {
    if (current.category === category) return;
    current.category = category;
    await setActiveSession(current);
    console.log(`[FocusGuard] ${reason} -> ${category}`);
    postLiveStatusToBackend(current.name || current.domain, category).catch(() => {});
    await evaluateAndNotifyDistraction({ domain, category, switch_count: 0 }, Date.now());
  }
}

// A site the extension hasn't seen before starts as 'unknown' (neutral)
// so tracking never waits on the network. Previously it then stayed
// neutral for that whole visit even after the backend classified it -
// a brand-new distracting site never triggered anything until the next
// visit. Now: ask about the domain, and if the domain alone can't tell
// (or is a mixed site like youtube.com), judge the page title instead.
async function refineUnknownSessionCategory(tabId, domain, title) {
  if (!AMBIGUOUS_TITLE_DOMAINS.has(domain)) {
    const byDomain = await classifyDomainAsync(domain);
    if (byDomain && byDomain !== 'unknown') {
      await applyCategoryToActiveSession(tabId, domain, byDomain, `Domain classified: ${domain}`);
      return;
    }
  }
  if (title) await reclassifyActiveSessionByTitle(tabId, domain, title);
}

activeDomainResolver = fetchDomainClassification;

function registerDomainResolver(resolverFn) {
  if (typeof resolverFn === 'function' || resolverFn === null) activeDomainResolver = resolverFn;
}

async function resolveUnknownDomainAsync(domain) {
  if (!activeDomainResolver || typeof activeDomainResolver !== 'function') return null;
  if (!domain || typeof domain !== 'string') return null;
  const clean = normalizeDomain(domain) || domain;
  if (pendingDomainResolutions.has(clean)) return await pendingDomainResolutions.get(clean);
  const resolutionPromise = (async () => {
    try {
      const result = await activeDomainResolver(clean);
      if (result && result.category) {
        const validCategories = ['educational', 'non_educational', 'unknown'];
        const cat = validCategories.includes(result.category) ? result.category : 'unknown';
        await setCachedDomainCategory(clean, cat, { confidence: result.confidence, source: result.source || 'async_resolver' });
        return cat;
      }
    } catch (err) {
      console.warn('[FocusGuard] Async domain resolver error for', domain, err);
    } finally {
      pendingDomainResolutions.delete(clean);
    }
    return 'unknown';
  })();
  pendingDomainResolutions.set(clean, resolutionPromise);
  return await resolutionPromise;
}

function classifyDomain(domainOrUrl) {
  if (!domainOrUrl || typeof domainOrUrl !== 'string') return 'unknown';
  let cleanDomain = domainOrUrl.trim().toLowerCase();
  if (cleanDomain.includes('://') || cleanDomain.startsWith('http')) {
    const extracted = getDomainFromUrl(cleanDomain);
    cleanDomain = normalizeDomain(extracted) || cleanDomain;
  } else {
    cleanDomain = normalizeDomain(cleanDomain) || cleanDomain;
  }
  if (Object.prototype.hasOwnProperty.call(DOMAIN_CATEGORIES, cleanDomain)) return DOMAIN_CATEGORIES[cleanDomain];
  const parts = cleanDomain.split('.');
  for (let i = 1; i < parts.length - 1; i++) {
    const parentDomain = parts.slice(i).join('.');
    if (Object.prototype.hasOwnProperty.call(DOMAIN_CATEGORIES, parentDomain)) return DOMAIN_CATEGORIES[parentDomain];
  }
  const cachedCategory = getCachedDomainCategory(cleanDomain);
  if (cachedCategory) return cachedCategory;
  if (activeDomainResolver) resolveUnknownDomainAsync(cleanDomain).catch(() => {});
  return 'unknown';
}

async function classifyDomainAsync(domainOrUrl) {
  if (!domainOrUrl || typeof domainOrUrl !== 'string') return 'unknown';
  let cleanDomain = domainOrUrl.trim().toLowerCase();
  if (cleanDomain.includes('://') || cleanDomain.startsWith('http')) {
    const extracted = getDomainFromUrl(cleanDomain);
    cleanDomain = normalizeDomain(extracted) || cleanDomain;
  } else {
    cleanDomain = normalizeDomain(cleanDomain) || cleanDomain;
  }
  if (Object.prototype.hasOwnProperty.call(DOMAIN_CATEGORIES, cleanDomain)) return DOMAIN_CATEGORIES[cleanDomain];
  const parts = cleanDomain.split('.');
  for (let i = 1; i < parts.length - 1; i++) {
    const parentDomain = parts.slice(i).join('.');
    if (Object.prototype.hasOwnProperty.call(DOMAIN_CATEGORIES, parentDomain)) return DOMAIN_CATEGORIES[parentDomain];
  }
  const cachedCategory = getCachedDomainCategory(cleanDomain);
  if (cachedCategory) return cachedCategory;
  if (activeDomainResolver) {
    const resolved = await resolveUnknownDomainAsync(cleanDomain);
    if (resolved) return resolved;
  }
  return 'unknown';
}

function getCurrentHourWindow(dateInput = new Date()) {
  const d = new Date(dateInput);
  if (isNaN(d.getTime())) return '00:00-01:00';
  const startHour = d.getHours();
  const endHour = (startHour + 1) % 24;
  const pad = (num) => String(num).padStart(2, '0');
  return `${pad(startHour)}:00-${pad(endHour)}:00`;
}

const NOTIFICATION_COOLDOWN_MS = 15 * 60 * 1000;
const NOTIFICATION_STORAGE_KEY = 'last_distraction_notification';
let lastDistractionState = 'productive';

function checkDistractionTransition(newState) {
  const previous = lastDistractionState;
  lastDistractionState = newState;
  try {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ lastDistractionState: newState }).catch(() => {});
    }
  } catch (e) {}
  return (previous === 'productive' || previous === 'neutral') && newState === 'distracted';
}

async function sendDistractionNotification(now = Date.now()) {
  try {
    const data = await chrome.storage.local.get([NOTIFICATION_STORAGE_KEY]);
    const lastNotif = typeof data[NOTIFICATION_STORAGE_KEY] === 'number' ? data[NOTIFICATION_STORAGE_KEY] : 0;
    if (now - lastNotif < NOTIFICATION_COOLDOWN_MS) {
      console.log(`[FocusGuard] Distraction notification suppressed by cooldown (${Math.round((NOTIFICATION_COOLDOWN_MS - (now - lastNotif)) / 1000)}s remaining)`);
      return false;
    }
    if (typeof chrome !== 'undefined' && chrome.notifications && typeof chrome.notifications.create === 'function') {
      const iconUrl = (typeof chrome.runtime !== 'undefined' && typeof chrome.runtime.getURL === 'function')
        ? chrome.runtime.getURL('icons/icon48.png') : 'icons/icon48.png';
      const notifOptions = {
        type: 'basic', iconUrl: iconUrl, title: 'FocusGuard AI',
        message: 'You may be getting distracted. Take a moment to refocus.',
        priority: 2, requireInteraction: false
      };
      await new Promise((resolve) => {
        try {
          chrome.notifications.create(`fg_distraction_${now}`, notifOptions, (notificationId) => {
            if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
              console.warn('[FocusGuard] Notification create warning:', chrome.runtime.lastError.message);
            }
            resolve(notificationId);
          });
        } catch (e) {
          if (chrome.notifications.create.length <= 2) {
            chrome.notifications.create(`fg_distraction_${now}`, notifOptions).then(resolve).catch(resolve);
          } else {
            resolve(null);
          }
        }
      });
    }
    await chrome.storage.local.set({ [NOTIFICATION_STORAGE_KEY]: now });
    console.log('[FocusGuard] Distraction notification triggered successfully.');
    return true;
  } catch (err) {
    console.warn('[FocusGuard] Failed to send distraction notification:', err);
    return false;
  }
}

async function evaluateAndNotifyDistraction(context = {}, now = Date.now()) {
  const distractionInfo = calculateDistractionState(context);
  const isTransition = checkDistractionTransition(distractionInfo.state);
  let notificationSent = false;
  if (isTransition && distractionInfo.state === 'distracted') {
    notificationSent = await sendDistractionNotification(now);
  }
  return { distractionInfo, notificationSent, isTransition };
}

function calculateDistractionState(context = {}) {
  const switchCount = typeof context.switch_count === 'number' ? Math.max(0, context.switch_count) : 0;
  const category = context.category || (context.domain ? classifyDomain(context.domain) : 'unknown');
  const isIdle = Boolean(context.is_idle);
  if (switchCount > SWITCH_THRESHOLD) {
    return { state: 'distracted', reason: 'high_switch_frequency', switch_count: switchCount };
  }
  if (switchCount === SWITCH_THRESHOLD) {
    return { state: 'neutral', reason: 'threshold_boundary', switch_count: switchCount };
  }
  if (category === 'educational') {
    return { state: 'productive', reason: isIdle ? 'idle_state' : 'educational_stable', switch_count: switchCount };
  }
  if (category === 'non_educational') {
    // Previously this returned 'neutral' unconditionally, so a distraction
    // notification could only ever fire off the switch-frequency branch
    // above (>10 switches/hour) - just landing on a distraction site never
    // triggered one. Landing on a known distraction domain while not idle
    // is exactly the case the notification is supposed to catch.
    return { state: isIdle ? 'neutral' : 'distracted', reason: isIdle ? 'idle_state' : 'non_educational_usage', switch_count: switchCount };
  }
  return { state: 'neutral', reason: isIdle ? 'idle_state' : 'unknown_domain', switch_count: switchCount };
}

/* ==========================================================================
   1b. Break Reminders (mirrors window_tracker.py's Feature 6: a continuous
   productive streak, tracked independently of hourly switch counts, that
   prompts a break once it crosses a threshold - resets on any switch away
   from an educational domain or on idle/lock.)
   ========================================================================== */

const BREAK_REMINDER_THRESHOLD_MS = 50 * 60 * 1000;
const BREAK_REMINDER_STORAGE_KEY = 'productive_streak_start';

async function updateProductiveStreak(category, isIdle, now = Date.now()) {
  try {
    const isProductive = category === 'educational' && !isIdle;
    const data = await chrome.storage.local.get([BREAK_REMINDER_STORAGE_KEY]);
    const streakStart = typeof data[BREAK_REMINDER_STORAGE_KEY] === 'number' ? data[BREAK_REMINDER_STORAGE_KEY] : null;
    if (isProductive) {
      if (streakStart === null) {
        await chrome.storage.local.set({ [BREAK_REMINDER_STORAGE_KEY]: now });
      }
    } else if (streakStart !== null) {
      await chrome.storage.local.set({ [BREAK_REMINDER_STORAGE_KEY]: null });
    }
  } catch (err) {
    console.warn('[FocusGuard] Error updating productive streak:', err);
  }
}

async function sendBreakReminderNotification(now = Date.now(), intervalMinutes = 50) {
  try {
    if (typeof chrome !== 'undefined' && chrome.notifications && typeof chrome.notifications.create === 'function') {
      const iconUrl = (typeof chrome.runtime !== 'undefined' && typeof chrome.runtime.getURL === 'function')
        ? chrome.runtime.getURL('icons/icon48.png') : 'icons/icon48.png';
      const notifOptions = {
        type: 'basic', iconUrl: iconUrl, title: 'Time for a quick break?',
        message: `You've been focused for ${intervalMinutes} minutes straight. A short break helps you keep this up.`,
        priority: 1, requireInteraction: false
      };
      await new Promise((resolve) => {
        try {
          chrome.notifications.create(`fg_break_${now}`, notifOptions, (notificationId) => {
            if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.lastError) {
              console.warn('[FocusGuard] Break notification create warning:', chrome.runtime.lastError.message);
            }
            resolve(notificationId);
          });
        } catch (e) {
          resolve(null);
        }
      });
    }
    console.log('[FocusGuard] Break reminder notification triggered successfully.');
    return true;
  } catch (err) {
    console.warn('[FocusGuard] Failed to send break reminder notification:', err);
    return false;
  }
}

async function checkBreakReminder(now = Date.now()) {
  try {
    const data = await chrome.storage.local.get([BREAK_REMINDER_STORAGE_KEY]);
    const streakStart = typeof data[BREAK_REMINDER_STORAGE_KEY] === 'number' ? data[BREAK_REMINDER_STORAGE_KEY] : null;
    if (streakStart === null) return false;
    const intervalMinutes = await getBreakIntervalMinutes(now);
    const thresholdMs = intervalMinutes * 60 * 1000;
    if (now - streakStart >= thresholdMs) {
      await sendBreakReminderNotification(now, intervalMinutes);
      // Restart the clock instead of clearing it, so a user who keeps
      // working gets reminded again after another full threshold - mirrors
      // window_tracker.py resetting _productive_streak_start after firing.
      await chrome.storage.local.set({ [BREAK_REMINDER_STORAGE_KEY]: now });
      return true;
    }
    return false;
  } catch (err) {
    console.warn('[FocusGuard] Error checking break reminder:', err);
    return false;
  }
}

/* ==========================================================================
   1c. Focus Mode distraction nagging - while a focus session is active
   (started from the web dashboard or window_tracker.py --focus) and the
   current tab is a distraction, fires a notification every check (this
   is called on a 15s timer) warning that the session will break, until
   either the user switches back or the backend's own grace-period clock
   (fed by the live-status pushes this file already makes - see
   postLiveStatusToBackend) actually breaks it.
   ========================================================================== */

const FOCUS_NAG_INTERVAL_MS = 15 * 1000;
let lastKnownFocusSessionId = null;
let lastKnownFocusStatus = null;

async function sendFocusNagNotification(secondsRemaining) {
  try {
    if (typeof chrome === 'undefined' || !chrome.notifications || typeof chrome.notifications.create !== 'function') return;
    const iconUrl = (typeof chrome.runtime !== 'undefined' && typeof chrome.runtime.getURL === 'function')
      ? chrome.runtime.getURL('icons/icon48.png') : 'icons/icon48.png';
    await new Promise((resolve) => {
      chrome.notifications.create(`fg_focus_nag_${Date.now()}`, {
        type: 'basic', iconUrl, title: 'Get back to focus!',
        message: `You're on a distraction during your focus session. Switch back or it ends in ${secondsRemaining}s.`,
        priority: 2, requireInteraction: false,
      }, () => resolve());
    });
  } catch (err) {
    console.warn('[FocusGuard] Failed to send focus nag notification:', err);
  }
}

async function sendFocusSessionEndedNotification(status) {
  try {
    if (typeof chrome === 'undefined' || !chrome.notifications || typeof chrome.notifications.create !== 'function') return;
    const iconUrl = (typeof chrome.runtime !== 'undefined' && typeof chrome.runtime.getURL === 'function')
      ? chrome.runtime.getURL('icons/icon48.png') : 'icons/icon48.png';
    const message = status === 'broken'
      ? "Focus session ended - too much time spent on a distraction."
      : 'Focus session complete - nice work!';
    await new Promise((resolve) => {
      chrome.notifications.create(`fg_focus_end_${Date.now()}`, {
        type: 'basic', iconUrl, title: 'FocusGuard AI',
        message, priority: status === 'broken' ? 2 : 1, requireInteraction: false,
      }, () => resolve());
    });
  } catch (err) {
    console.warn('[FocusGuard] Failed to send focus-session-ended notification:', err);
  }
}

async function checkFocusDistraction() {
  try {
    const auth = await ensureBackendAuth();
    if (!auth) return;
    const { token } = auth;
    const resp = await fetch(`${BACKEND_URL}/focus-sessions/active`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (resp.status === 404) {
      lastKnownFocusSessionId = null;
      lastKnownFocusStatus = null;
      return;
    }
    if (!resp.ok) return;
    const session = await resp.json();

    if (lastKnownFocusSessionId === session.id && lastKnownFocusStatus === 'active' && session.status !== 'active') {
      await sendFocusSessionEndedNotification(session.status);
    }
    lastKnownFocusSessionId = session.id;
    lastKnownFocusStatus = session.status;
    if (session.status !== 'active') return;

    const active = await getActiveSession();
    const isDistracted = Boolean(active && !active.isPaused && active.category === 'non_educational');
    if (isDistracted && session.grace_seconds_remaining > 0) {
      await sendFocusNagNotification(session.grace_seconds_remaining);
    }
  } catch (err) {
    console.warn('[FocusGuard] Error checking focus-mode distraction:', err);
  }
}

function classifySwitchCount(count) {
  if (count < SWITCH_THRESHOLD) return 'productive';
  if (count === SWITCH_THRESHOLD) return 'neutral';
  return 'distracted';
}

function formatTimeHHMM(dateInput) {
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return '00:00';
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
  } catch (e) {
    return '00:00';
  }
}

function generateSessionId() {
  return 'fg_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
}

function cleanupOldSessions(items, limit = MAX_SESSIONS) {
  if (!Array.isArray(items)) return [];
  if (items.length > limit) return items.slice(0, limit);
  return items;
}

async function getActiveSession() {
  if (currentSession !== null) return currentSession;
  try {
    const data = await chrome.storage.local.get(['currentSession']);
    currentSession = data.currentSession || null;
    return currentSession;
  } catch (error) {
    console.error('[FocusGuard] Error reading active session from storage:', error);
    return null;
  }
}

async function setActiveSession(session) {
  currentSession = session;
  try {
    await chrome.storage.local.set({ currentSession: session });
  } catch (error) {
    console.error('[FocusGuard] Error writing active session to storage:', error);
  }
}

async function getStoredSessions() {
  try {
    const data = await chrome.storage.local.get(['sessions']);
    return Array.isArray(data.sessions) ? data.sessions : [];
  } catch (error) {
    console.error('[FocusGuard] Error reading sessions from storage:', error);
    return [];
  }
}

async function syncHourlyState(targetDate = new Date()) {
  try {
    const data = await chrome.storage.local.get(['current_hour', 'hourly_summaries']);
    const expectedWindow = getCurrentHourWindow(targetDate);
    let currentHour = data.current_hour;
    let summaries = Array.isArray(data.hourly_summaries) ? data.hourly_summaries : [];
    if (!currentHour || currentHour.hour !== expectedWindow) {
      if (currentHour && currentHour.hour && typeof currentHour.switch_count === 'number') {
        summaries = cleanupOldSessions([currentHour, ...summaries], MAX_HOURLY_SUMMARIES);
      }
      currentHour = { hour: expectedWindow, switch_count: 0, classification: classifySwitchCount(0) };
      lastDistractionState = 'productive';
      await chrome.storage.local.set({
        current_hour: currentHour, switch_count: 0, hourly_summaries: summaries, lastDistractionState: 'productive'
      });
    }
    return { current_hour: currentHour, hourly_summaries: summaries };
  } catch (error) {
    console.error('[FocusGuard] Error syncing hourly state:', error);
    return { current_hour: { hour: getCurrentHourWindow(targetDate), switch_count: 0, classification: 'productive' }, hourly_summaries: [] };
  }
}

async function recordSwitchEvent(fromDomain, toDomain, eventDate = new Date()) {
  if (!fromDomain || !toDomain || fromDomain === toDomain) return;
  const timestampIso = new Date(eventDate).toISOString();
  const switchEvent = {
    from: fromDomain, to: toDomain,
    from_category: classifyDomain(fromDomain), to_category: classifyDomain(toDomain),
    timestamp: timestampIso
  };
  try {
    const { current_hour } = await syncHourlyState(eventDate);
    const data = await chrome.storage.local.get(['switch_events']);
    const existingEvents = Array.isArray(data.switch_events) ? data.switch_events : [];
    const newSwitchCount = (current_hour.switch_count || 0) + 1;
    const updatedCurrentHour = { hour: current_hour.hour, switch_count: newSwitchCount, classification: classifySwitchCount(newSwitchCount) };
    const updatedEvents = [switchEvent, ...existingEvents];
    const boundedEvents = cleanupOldSessions(updatedEvents, MAX_SWITCH_EVENTS);
    await chrome.storage.local.set({
      current_hour: updatedCurrentHour, switch_count: newSwitchCount, switch_events: boundedEvents, lastActiveDomain: toDomain
    });

    // Sync this switch event to the shared backend (Module 2), non-blocking.
    postSwitchToBackend(fromDomain, toDomain, switchEvent.to_category).catch(() => {});

    lastActiveDomain = toDomain;
    console.log('[FocusGuard Switch Event]');
    console.log(JSON.stringify(switchEvent, null, 2));
    console.log('[FocusGuard Switch Count]', newSwitchCount);
    await evaluateAndNotifyDistraction({ domain: toDomain, category: classifyDomain(toDomain), switch_count: newSwitchCount }, new Date(eventDate).getTime());
    await updateProductiveStreak(switchEvent.to_category, false, new Date(eventDate).getTime());
  } catch (error) {
    console.error('[FocusGuard] Error recording switch event:', error);
  }
}

async function saveSession(session) {
  if (!session || (!session.domain && !session.name)) return;
  try {
    const existingSessions = await getStoredSessions();
    const updatedSessions = [session, ...existingSessions];
    const boundedSessions = cleanupOldSessions(updatedSessions, MAX_SESSIONS);
    await chrome.storage.local.set({ sessions: boundedSessions });
    console.log('[FocusGuard] Session saved to storage successfully.');

    // Sync this session to the shared backend (Module 2), non-blocking.
    postSessionToBackend(session).catch(() => {});
  } catch (error) {
    console.error('[FocusGuard] Failed to save session to storage:', error);
  }
}

function updateSessionActivity(session, now = Date.now()) {
  if (!session) return null;
  const nowMs = typeof now === 'number' ? now : new Date(now).getTime();
  if (session.isPaused) return session;
  const lastActive = typeof session.lastActiveTime === 'number' ? session.lastActiveTime : new Date(session.startTime || session.timestamp).getTime();
  const gap = nowMs - lastActive;
  if (gap > 0) {
    if (gap <= SLEEP_GAP_THRESHOLD_MS) {
      session.accumulatedActiveMs = (session.accumulatedActiveMs || 0) + gap;
    } else {
      console.log(`[FocusGuard] Sleep/suspend gap of ${Math.round(gap / 1000)}s excluded from session duration.`);
    }
  }
  session.lastActiveTime = nowMs;
  return session;
}

async function pauseActiveSession(now = Date.now(), state = 'idle') {
  const active = await getActiveSession();
  if (!active) return null;
  const nowMs = typeof now === 'number' ? now : new Date(now).getTime();
  updateSessionActivity(active, nowMs);
  active.isPaused = true;
  active.idleState = state;
  active.lastPauseTime = nowMs;
  await setActiveSession(active);
  console.log(`[FocusGuard] Session paused (${state}) at ${formatTimeHHMM(new Date(nowMs))}`);
  return active;
}

async function resumeActiveSession(now = Date.now()) {
  const active = await getActiveSession();
  if (!active) return null;
  const nowMs = typeof now === 'number' ? now : new Date(now).getTime();
  active.isPaused = false;
  active.idleState = 'active';
  active.lastActiveTime = nowMs;
  active.lastPauseTime = null;
  await setActiveSession(active);
  console.log(`[FocusGuard] Session resumed (active) at ${formatTimeHHMM(new Date(nowMs))}`);
  return active;
}

async function handleIdleStateChange(newState, now = Date.now()) {
  console.log(`[FocusGuard] chrome.idle state transition: ${newState}`);
  if (newState === 'locked' || newState === 'idle') {
    await pauseActiveSession(now, newState);
    await updateProductiveStreak(null, true, now);
  } else if (newState === 'active') {
    await resumeActiveSession(now);
  }
}

async function endSession(endDate = new Date()) {
  const active = await getActiveSession();
  if (!active || (!active.domain && !active.name)) {
    await setActiveSession(null);
    return null;
  }
  const endTimestamp = new Date(endDate);
  const endTimestampMs = endTimestamp.getTime();
  const endTimeIso = endTimestamp.toISOString();
  const startTimestamp = new Date(active.startTime || active.timestamp);
  const startTimestampMs = startTimestamp.getTime();
  updateSessionActivity(active, endTimestampMs);
  let rawDuration;
  if (typeof active.accumulatedActiveMs === 'number' && active.accumulatedActiveMs > 0) {
    rawDuration = Math.round(active.accumulatedActiveMs / 1000);
  } else if (active.isPaused && typeof active.accumulatedActiveMs === 'number') {
    rawDuration = Math.round(active.accumulatedActiveMs / 1000);
  } else {
    const totalDeltaMs = endTimestampMs - startTimestampMs;
    if (totalDeltaMs > SLEEP_GAP_THRESHOLD_MS && active.lastActiveTime && active.lastActiveTime > startTimestampMs) {
      rawDuration = Math.round(Math.max(0, active.lastActiveTime - startTimestampMs) / 1000);
    } else {
      rawDuration = Math.round(totalDeltaMs / 1000);
    }
  }
  const durationSeconds = Math.max(1, rawDuration);
  const targetDomain = active.name || active.domain;
  const domainCategory = active.category || classifyDomain(targetDomain);
  let currentSwitchCount = 0;
  try {
    const hourlyData = await chrome.storage.local.get(['current_hour']);
    if (hourlyData.current_hour && typeof hourlyData.current_hour.switch_count === 'number') {
      currentSwitchCount = hourlyData.current_hour.switch_count;
    }
  } catch (e) {}
  const distractionInfo = calculateDistractionState({ domain: targetDomain, category: domainCategory, switch_count: currentSwitchCount, duration: durationSeconds });
  await evaluateAndNotifyDistraction({ domain: targetDomain, category: domainCategory, switch_count: currentSwitchCount, duration: durationSeconds }, endTimestamp.getTime());
  const completedSession = {
    source: 'extension',
    name: targetDomain,
    start_time: active.start_time || formatTimeHHMM(startTimestamp),
    end_time: formatTimeHHMM(endTimestamp),
    duration: durationSeconds,
    category: domainCategory,
    distraction_state: distractionInfo.state,
    hostname: active.hostname || targetDomain,
    tab_id: active.tabId || active.tab_id,
    url: active.url || (active.hostname ? `https://${active.hostname}/` : null),
    timestamp: active.startTime || active.timestamp || startTimestamp.toISOString(),
    id: active.id || generateSessionId(),
    domain: targetDomain,
    startTime: active.startTime || startTimestamp.toISOString(),
    endTime: endTimeIso,
    durationSeconds: durationSeconds
  };
  console.log('[Team 2 Activity Record Generated]');
  console.log(JSON.stringify(completedSession, null, 2));
  await saveSession(completedSession);
  await setActiveSession(null);
  return completedSession;
}

async function startSession(tabId, url, startDate = new Date(), title = null) {
  await syncHourlyState(startDate);
  const hostname = getDomainFromUrl(url);
  if (!hostname) {
    console.log('[FocusGuard] Non-web or internal URL ignored:', url);
    await endSession(startDate);
    return null;
  }
  const domain = normalizeDomain(hostname);
  const active = await getActiveSession();
  if (active && (active.tabId === tabId || active.tab_id === tabId) && (active.domain === domain || active.name === domain)) {
    return active;
  }
  let previousDomain = active ? (active.name || active.domain) : lastActiveDomain;
  if (!previousDomain && lastActiveDomain) previousDomain = lastActiveDomain;
  await endSession(startDate);
  if (previousDomain && domain && previousDomain !== domain) {
    await recordSwitchEvent(previousDomain, domain, startDate);
  } else {
    lastActiveDomain = domain;
    await chrome.storage.local.set({ lastActiveDomain: domain });
  }
  const startTimeDate = new Date(startDate);
  const startTimeIso = startTimeDate.toISOString();
  const startTimeMs = startTimeDate.getTime();
  const cleanUrl = sanitizeUrl(url);
  const domainCategory = classifyDomain(domain);
  const newSession = {
    id: generateSessionId(), tabId: tabId, tab_id: tabId, domain: domain, name: domain,
    category: domainCategory, hostname: hostname, url: cleanUrl,
    startTime: startTimeIso, timestamp: startTimeIso, start_time: formatTimeHHMM(startTimeDate),
    lastActiveTime: startTimeMs, accumulatedActiveMs: 0, isPaused: false, idleState: 'active', lastPauseTime: null
  };
  await setActiveSession(newSession);
  console.log(`[FocusGuard] Domain detected: ${domain}`);
  console.log(`[FocusGuard] Session started: ${domain} (Tab: ${tabId}) at ${formatTimeHHMM(startTimeDate)} [${startTimeIso}]`);
  postLiveStatusToBackend(domain, domainCategory).catch(() => {});
  // Not known yet, or a mixed site (youtube.com etc.) - classify in the
  // background without blocking session start on a network round-trip,
  // updating this same session in place once it resolves.
  if (domainCategory === 'unknown') {
    refineUnknownSessionCategory(tabId, domain, title).catch(() => {});
  }
  return newSession;
}

async function getActiveBrowserTab() {
  try {
    if (chrome.windows && chrome.windows.getLastFocused) {
      try {
        const lastWin = await chrome.windows.getLastFocused({ populate: true, windowTypes: ['normal'] });
        if (lastWin && Array.isArray(lastWin.tabs)) {
          const activeTab = lastWin.tabs.find((t) => t.active);
          if (activeTab) return activeTab;
        }
      } catch (e) {}
    }
    const tabsInFocused = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tabsInFocused && tabsInFocused.length > 0 && tabsInFocused[0].url) return tabsInFocused[0];
    const allActive = await chrome.tabs.query({ active: true });
    if (allActive && allActive.length > 0) {
      const webTab = allActive.find((t) => t.url && getDomainFromUrl(t.url));
      return webTab || allActive[0];
    }
    return null;
  } catch (error) {
    console.warn('[FocusGuard] Error querying active browser tab:', error);
    return null;
  }
}

async function reconcileActiveTab() {
  try {
    const activeTab = await getActiveBrowserTab();
    if (!activeTab || !activeTab.url) return await getActiveSession();
    const hostname = getDomainFromUrl(activeTab.url);
    if (!hostname) {
      const current = await getActiveSession();
      if (current) await endSession();
      return null;
    }
    const domain = normalizeDomain(hostname);
    const current = await getActiveSession();
    if (current && (current.tabId === activeTab.id || current.tab_id === activeTab.id) && (current.domain === domain || current.name === domain)) {
      return current;
    }
    return await startSession(activeTab.id, activeTab.url, new Date(), activeTab.title);
  } catch (error) {
    console.warn('[FocusGuard] Error reconciling active tab:', error);
    return await getActiveSession();
  }
}

chrome.tabs.onActivated.addListener((activeInfo) => {
  withSessionLock(async () => {
    console.log('[FocusGuard] Tab activated:', activeInfo.tabId);
    try {
      const tab = await chrome.tabs.get(activeInfo.tabId);
      if (tab && tab.url) {
        await startSession(tab.id, tab.url, new Date(), tab.title);
      } else {
        await endSession();
      }
    } catch (error) {
      console.warn('[FocusGuard] Unable to fetch activated tab info:', error);
    }
  });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // A title-only change (changeInfo = {title: "..."}) fires on SPA
  // navigation - switching to a different YouTube video without a full
  // page reload, which never sets changeInfo.url. Previously this
  // guard dropped that event entirely, so a video swap on an already-
  // open tab never got reclassified.
  if (!changeInfo.url && changeInfo.status !== 'complete' && !changeInfo.title) return;
  const currentUrl = changeInfo.url || tab.url;
  if (!currentUrl) return;
  withSessionLock(async () => {
    try {
      const activeTab = await getActiveBrowserTab();
      if (!activeTab || activeTab.id !== tabId) return;
      const newHostname = getDomainFromUrl(currentUrl);
      const newDomain = normalizeDomain(newHostname);
      const active = await getActiveSession();
      if (active && (active.tabId === tabId || active.tab_id === tabId) && (active.domain === newDomain || active.name === newDomain)) {
        // Same domain, same tracked tab - if this is an ambiguous
        // domain and the title just changed (a new video on the same
        // youtube.com tab), reclassify without resetting the session.
        if (changeInfo.title && newDomain && (AMBIGUOUS_TITLE_DOMAINS.has(newDomain) || classifyDomain(newDomain) === 'unknown')) {
          reclassifyActiveSessionByTitle(tabId, newDomain, changeInfo.title).catch(() => {});
        }
        return;
      }
      if (newDomain) {
        console.log('[FocusGuard] In-tab navigation detected to new domain:', currentUrl);
        await startSession(tabId, currentUrl, new Date(), tab.title);
      } else {
        console.log('[FocusGuard] In-tab navigation to non-web URL:', currentUrl);
        await endSession();
      }
    } catch (error) {
      console.warn('[FocusGuard] Error handling tab update:', error);
    }
  });
});

chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
  withSessionLock(async () => {
    const active = await getActiveSession();
    if (active && (active.tabId === tabId || active.tab_id === tabId)) {
      console.log('[FocusGuard] Tracked tab closed:', tabId);
      await endSession();
    }
  });
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    // Focus left the browser entirely - for a system app, or nothing.
    // Previously this did nothing ("preserving active session state"),
    // so the last browser tab stayed "active" and kept winning the
    // live-status freshness race against window_tracker.py's readings
    // even while the user was genuinely in a different application -
    // system-app activity could never show up anywhere while any
    // browser window had recently been used. Pausing here (same
    // mechanism already used for chrome.idle) stops the heartbeat from
    // claiming this tab is still current.
    console.log('[FocusGuard] Focus shifted away from the browser - pausing the active session.');
    withSessionLock(async () => { await pauseActiveSession(Date.now(), 'blurred'); });
    return;
  }
  withSessionLock(async () => {
    console.log('[FocusGuard] Browser window focused:', windowId);
    try {
      const [activeTab] = await chrome.tabs.query({ active: true, windowId: windowId });
      if (activeTab && activeTab.url) {
        const hostname = getDomainFromUrl(activeTab.url);
        if (hostname) {
          const domain = normalizeDomain(hostname);
          const active = await getActiveSession();
          if (active && (active.tabId === activeTab.id || active.tab_id === activeTab.id) && (active.domain === domain || active.name === domain)) {
            if (active.isPaused) await resumeActiveSession(Date.now());
            return;
          }
          await startSession(activeTab.id, activeTab.url, new Date(), activeTab.title);
        } else {
          await endSession();
        }
      }
    } catch (error) {
      console.warn('[FocusGuard] Error on window focus change:', error);
    }
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === 'POPUP_OPENED') {
    withSessionLock(async () => {
      const active = await getActiveSession();
      if (active && !active.isPaused) {
        updateSessionActivity(active, Date.now());
        await setActiveSession(active);
      }
      return await reconcileActiveTab();
    }).then((session) => {
      sendResponse({ currentSession: session });
    }).catch((err) => {
      console.error('[FocusGuard] Error handling POPUP_OPENED message:', err);
      sendResponse({ currentSession: null });
    });
    return true;
  }
});

if (typeof chrome !== 'undefined' && chrome.idle && chrome.idle.onStateChanged) {
  try {
    if (typeof chrome.idle.setDetectionInterval === 'function') chrome.idle.setDetectionInterval(60);
  } catch (e) {}
  chrome.idle.onStateChanged.addListener((newState) => {
    withSessionLock(async () => { await handleIdleStateChange(newState); });
  });
}

if (typeof setInterval !== 'undefined') {
  const heartbeatTimer = setInterval(async () => {
    try {
      const now = Date.now();
      const active = await getActiveSession();
      if (active && !active.isPaused) {
        updateSessionActivity(active, now);
        await setActiveSession(active);
        await updateProductiveStreak(active.category, false, now);
        postLiveStatusToBackend(active.name || active.domain, active.category).catch(() => {});
      } else {
        await updateProductiveStreak(null, true, now);
      }
      await checkBreakReminder(now);
    } catch (e) {}
  }, HEARTBEAT_INTERVAL_MS);
  if (heartbeatTimer && typeof heartbeatTimer.unref === 'function') heartbeatTimer.unref();

  const focusNagTimer = setInterval(() => {
    checkFocusDistraction().catch(() => {});
  }, FOCUS_NAG_INTERVAL_MS);
  if (focusNagTimer && typeof focusNagTimer.unref === 'function') focusNagTimer.unref();
}

if (typeof chrome !== 'undefined' && chrome.alarms) {
  chrome.alarms.create(PRESENCE_ALARM, { periodInMinutes: 1 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === PRESENCE_ALARM) sendPresencePing().catch(() => {});
  });
}
sendPresencePing().catch(() => {});

chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('[FocusGuard] Extension installed/updated. Reason:', details.reason);
  const installData = await chrome.storage.local.get(['sessions', 'currentSession', 'switch_events', 'lastActiveDomain', 'current_hour', 'hourly_summaries']);
  const updates = {};
  if (!Array.isArray(installData.sessions)) updates.sessions = [];
  if (!Array.isArray(installData.switch_events)) updates.switch_events = [];
  if (!Array.isArray(installData.hourly_summaries)) updates.hourly_summaries = [];
  if (Object.keys(updates).length > 0) await chrome.storage.local.set(updates);
  await syncHourlyState();
  await loadClassificationCache();
  const stateData = await chrome.storage.local.get(['currentSession', 'lastActiveDomain', 'lastDistractionState', 'current_hour']);
  lastActiveDomain = stateData.lastActiveDomain || (stateData.currentSession ? (stateData.currentSession.name || stateData.currentSession.domain) : null);
  if (stateData.lastDistractionState) {
    lastDistractionState = stateData.lastDistractionState;
  } else if (stateData.current_hour && stateData.current_hour.classification) {
    lastDistractionState = stateData.current_hour.classification;
  }
  withSessionLock(async () => { await reconcileActiveTab(); });
});

chrome.runtime.onStartup.addListener(async () => {
  console.log('[FocusGuard] Browser startup initiated');
  await syncHourlyState();
  await loadClassificationCache();
  const data = await chrome.storage.local.get(['currentSession', 'lastActiveDomain', 'lastDistractionState', 'current_hour']);
  lastActiveDomain = data.lastActiveDomain || (data.currentSession ? (data.currentSession.name || data.currentSession.domain) : null);
  if (data.lastDistractionState) {
    lastDistractionState = data.lastDistractionState;
  } else if (data.current_hour && data.current_hour.classification) {
    lastDistractionState = data.current_hour.classification;
  }
  withSessionLock(async () => { await reconcileActiveTab(); });
});

withSessionLock(async () => {
  await syncHourlyState();
  await loadClassificationCache();
  const data = await chrome.storage.local.get(['currentSession', 'lastActiveDomain', 'lastDistractionState', 'current_hour']);
  lastActiveDomain = data.lastActiveDomain || (data.currentSession ? (data.currentSession.name || data.currentSession.domain) : null);
  if (data.lastDistractionState) {
    lastDistractionState = data.lastDistractionState;
  } else if (data.current_hour && data.current_hour.classification) {
    lastDistractionState = data.current_hour.classification;
  }
  await reconcileActiveTab();
});

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    DOMAIN_CATEGORIES, MAX_CACHE_ENTRIES, CACHE_TTL_MS, CACHE_STORAGE_KEY, RESOLVER_ENDPOINT, RESOLVER_TIMEOUT_MS,
    pendingDomainResolutions, fetchDomainClassification, classifyDomain, classifyDomainAsync,
    getCachedDomainCategory, setCachedDomainCategory, loadClassificationCache, purgeExpiredCache,
    registerDomainResolver, resolveUnknownDomainAsync, getDomainFromUrl, normalizeDomain, sanitizeUrl,
    startSession, endSession, recordSwitchEvent, syncHourlyState, classifySwitchCount, getCurrentHourWindow,
    calculateDistractionState, checkDistractionTransition, NOTIFICATION_COOLDOWN_MS, NOTIFICATION_STORAGE_KEY,
    sendDistractionNotification, evaluateAndNotifyDistraction, SLEEP_GAP_THRESHOLD_MS, HEARTBEAT_INTERVAL_MS,
    updateSessionActivity, handleIdleStateChange, pauseActiveSession, resumeActiveSession,
    getActiveSession, setActiveSession,
    BREAK_REMINDER_THRESHOLD_MS, BREAK_REMINDER_STORAGE_KEY, updateProductiveStreak,
    sendBreakReminderNotification, checkBreakReminder,
    postSessionToBackend, postSwitchToBackend, mapCategoryToBackend, ensureBackendAuth,
    postLiveStatusToBackend, fetchDeviceLink, detectBrowserClient, sendPresencePing,
    applyCategoryToActiveSession, refineUnknownSessionCategory,
    fetchBreakIntervalFromBackend, getBreakIntervalMinutes,
    BREAK_INTERVAL_CACHE_KEY, BREAK_INTERVAL_FETCHED_AT_KEY, BREAK_INTERVAL_REFRESH_MS,
    checkFocusDistraction, sendFocusNagNotification, sendFocusSessionEndedNotification, FOCUS_NAG_INTERVAL_MS,
    AMBIGUOUS_TITLE_DOMAINS, classifyByTitleAsync, reclassifyActiveSessionByTitle
  };
}
