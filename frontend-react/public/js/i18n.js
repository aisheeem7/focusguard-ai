/**
 * i18n.js
 *
 * Tiny vanilla-JS translation loader for the plain-HTML dashboard (no
 * React here, so react-i18next doesn't apply - see the extension too).
 * Deliberately mirrors i18next's own conventions rather than inventing
 * a new format, so frontend-react and frontend/ pull from the exact
 * same /locales/{lang}/common.json files with no format translation
 * between them:
 *   - {{var}} interpolation
 *   - key_one / key_other plural variants, picked by vars.count
 *   - localStorage key "fg_lang" - the same one react-i18next's
 *     language-detector reads/writes, so a choice made on either
 *     surface carries over (both are served from the same origin).
 */

const I18N_STORAGE_KEY = 'fg_lang';
const I18N_FALLBACK_LANG = 'en';
const I18N_SUPPORTED = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'bn', label: 'বাংলা' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'mr', label: 'मराठी' },
];

let _dict = {};
let _currentLang = I18N_FALLBACK_LANG;
const _changeListeners = [];

function getStoredLanguage() {
  try {
    const stored = localStorage.getItem(I18N_STORAGE_KEY);
    if (stored && I18N_SUPPORTED.some((l) => l.code === stored)) return stored;
  } catch (e) { /* localStorage unavailable - fall through to default */ }
  return I18N_FALLBACK_LANG;
}

async function loadLocale(lang) {
  const resp = await fetch(`/locales/${lang}/common.json`, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`Failed to load locale ${lang}: HTTP ${resp.status}`);
  return resp.json();
}

// Flattens the nested JSON (e.g. {dashboard:{overview:{welcome_back:"..."}}})
// into dot-path keys (e.g. "dashboard.overview.welcome_back") for O(1) t() lookups.
function flatten(obj, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') {
      flatten(value, path, out);
    } else {
      out[path] = value;
    }
  }
  return out;
}

function t(key, vars = {}) {
  let resolvedKey = key;
  if (typeof vars.count === 'number') {
    const pluralKey = `${key}_${vars.count === 1 ? 'one' : 'other'}`;
    if (pluralKey in _dict) resolvedKey = pluralKey;
  }
  const template = _dict[resolvedKey] ?? _dict[key] ?? key;
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) => (vars[name] !== undefined ? vars[name] : ''));
}

// Applies translations to any static element carrying data-i18n="key"
// (textContent) or data-i18n-attr="attrName:key" (an attribute value,
// e.g. title/placeholder) - run once on load and again after a language
// switch, so markup baked into app.html doesn't need a JS render pass.
function applyStaticTranslations(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  root.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    el.getAttribute('data-i18n-attr').split(';').forEach((pair) => {
      const [attr, key] = pair.split(':');
      if (attr && key) el.setAttribute(attr.trim(), t(key.trim()));
    });
  });
}

async function setLanguage(lang) {
  if (!I18N_SUPPORTED.some((l) => l.code === lang)) lang = I18N_FALLBACK_LANG;
  try {
    _dict = flatten(await loadLocale(lang));
  } catch (err) {
    console.warn('[i18n] Failed to load locale, falling back to English:', err);
    if (lang !== I18N_FALLBACK_LANG) {
      _dict = flatten(await loadLocale(I18N_FALLBACK_LANG));
      lang = I18N_FALLBACK_LANG;
    }
  }
  _currentLang = lang;
  try { localStorage.setItem(I18N_STORAGE_KEY, lang); } catch (e) { /* ignore */ }
  applyStaticTranslations();
  _changeListeners.forEach((fn) => fn(lang));
}

function onLanguageChange(fn) { _changeListeners.push(fn); }
function getCurrentLanguage() { return _currentLang; }

async function initI18n() {
  await setLanguage(getStoredLanguage());
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    t, setLanguage, getCurrentLanguage, onLanguageChange, initI18n,
    applyStaticTranslations, I18N_SUPPORTED, I18N_STORAGE_KEY, flatten,
  };
}
