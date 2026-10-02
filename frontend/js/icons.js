/**
 * icons.js
 *
 * A small set of flat, rounded line icons in a single consistent style,
 * used instead of emoji throughout FocusGuard AI. Each icon inherits
 * its color from the surrounding element (uses currentColor), so the
 * existing pastel accent colors (in tokens.css) apply automatically -
 * no per-icon color choices to maintain separately.
 */

const ICONS = {
  brand: `<path d="M12 3 L20 8 V16 L12 21 L4 16 V8 Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="12" cy="12" r="3" fill="currentColor"/>`,
  home: `<path d="M4 11.5 L12 5 L20 11.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 10.5 V19 H10 V14.5 H14 V19 H18 V10.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>`,
  timer: `<circle cx="12" cy="13" r="7.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 13 V9.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M12 13 L14.6 14.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M9.8 3.5 H14.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="13" r="0.9" fill="currentColor"/>`,
  flame: `<path d="M12 3.2 C13 7 17 9 17 13.4 C17 17.5 14.4 19.8 12 19.8 C9.6 19.8 7 17.5 7 13.4 C7 12 7.6 11 8.3 10.2 C8.3 12 9.3 12.8 10 12.8 C9.4 10.6 10.4 8 12 3.2 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="12" cy="15" r="1.4" fill="currentColor"/>`,
  trophy: `<path d="M7 5 H17 V10 C17 13 14.8 15 12 15 C9.2 15 7 13 7 10 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M7 6.5 H4.5 C4.5 9.5 5.8 11 7.8 11.3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M17 6.5 H19.5 C19.5 9.5 18.2 11 16.2 11.3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M12 15 V18" stroke="currentColor" stroke-width="1.7"/><path d="M9 20.3 H15 L14 18 H10 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 6.5 L12.6 8 L14.2 8.1 L13 9.1 L13.4 10.6 L12 9.7 L10.6 10.6 L11 9.1 L9.8 8.1 L11.4 8 Z" fill="currentColor"/>`,
  scroll: `<path d="M6.5 4 H15 L17.5 6.5 V17 A2 2 0 0 1 15.5 19 H6.5 A2 2 0 0 1 4.5 17 V6 A2 2 0 0 1 6.5 4 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M15 4 V6.5 H17.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 10.3 H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M8 13.3 H13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>`,
  check: `<circle cx="12" cy="12" r="8.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8.3 12.3 L10.7 14.7 L15.7 9.7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  cross: `<circle cx="12" cy="12" r="8.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9 9 L15 15 M15 9 L9 15" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
  star: `<path d="M12 4 L14.2 9.6 L20 10.2 L15.6 14 L17 19.8 L12 16.6 L7 19.8 L8.4 14 L4 10.2 L9.8 9.6 Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>`,
  user: `<circle cx="12" cy="9" r="3.4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5 19.3 C5 15.8 8.1 13.5 12 13.5 C15.9 13.5 19 15.8 19 19.3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  refresh: `<path d="M18 8 A7 7 0 1 0 19 13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M18 4 V8.5 H13.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>`,
  shield: `<path d="M12 3.3 L19 6.3 V11.3 C19 15.8 16 19.3 12 20.3 C8 19.3 5 15.8 5 11.3 V6.3 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 12 L11.3 14.3 L15.5 10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  ai: `<path d="M12 3.5 L13.4 9.3 L19 11 L13.4 12.7 L12 18.5 L10.6 12.7 L5 11 L10.6 9.3 Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M18.5 4 L19.1 6.4 L21.3 7 L19.1 7.6 L18.5 10 L17.9 7.6 L15.7 7 L17.9 6.4 Z" fill="currentColor"/>`,
  settings: `<circle cx="12" cy="12" r="3.1" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 3.5 V6 M12 18 V20.5 M20.5 12 H18 M6 12 H3.5 M18 6 L16.2 7.8 M7.8 16.2 L6 18 M18 18 L16.2 16.2 M7.8 7.8 L6 6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  target: `<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="4.6" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/>`,
  sun: `<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 3 V5 M12 19 V21 M3 12 H5 M19 12 H21 M5.6 5.6 L7 7 M17 17 L18.4 18.4 M5.6 18.4 L7 17 M17 7 L18.4 5.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>`,
  moon: `<path d="M19.5 14.5 A8 8 0 1 1 9.5 4.5 A6.3 6.3 0 0 0 19.5 14.5 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>`,
  globe: `<circle cx="12" cy="12" r="8.3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.7 12 H20.3 M12 3.7 C9.6 6.3 9.6 17.7 12 20.3 M12 3.7 C14.4 6.3 14.4 17.7 12 20.3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>`,
  sidebar: `<rect x="3.8" y="4.8" width="16.4" height="14.4" rx="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9.5 4.8 V19.2" stroke="currentColor" stroke-width="1.7"/><path d="M6 8.5 H7.4 M6 11 H7.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>`,
  expand: `<path d="M4.5 9 V4.5 H9 M15 4.5 H19.5 V9 M19.5 15 V19.5 H15 M9 19.5 H4.5 V15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  shrink: `<path d="M9 4.5 V9 H4.5 M19.5 9 H15 V4.5 M15 19.5 V15 H19.5 M4.5 15 H9 V19.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  logout: `<path d="M14 4.5 H17.5 A2 2 0 0 1 19.5 6.5 V17.5 A2 2 0 0 1 17.5 19.5 H14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M10.5 8 L6.5 12 L10.5 16 M6.5 12 H15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
  badge: `<path d="M12 2.8 L19.8 7.3 V16.7 L12 21.2 L4.2 16.7 V7.3 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 8 L13.2 10.6 L16 10.9 L13.9 12.8 L14.5 15.6 L12 14.2 L9.5 15.6 L10.1 12.8 L8 10.9 L10.8 10.6 Z" fill="currentColor"/>`,
  lock: `<rect x="5.5" y="10.5" width="13" height="9.5" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8.5 10.5 V8 A3.5 3.5 0 0 1 15.5 8 V10.5" fill="none" stroke="currentColor" stroke-width="1.7"/>`,
  clock: `<circle cx="12" cy="12" r="8.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 7.5 V12 L15.2 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
};

function icon(name, size = 24) {
  const paths = ICONS[name] || '';
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${paths}</svg>`;
}

function renderIcon(container, name, size = 24) {
  container.innerHTML = icon(name, size);
}

// Filled, two-tone icons for achievements (streak flame, trophy, rank
// medals, badges) - used where the app previously showed emoji, so they
// match the lavender theme instead of each OS's own emoji art. Every
// call gets its own gradient ids: an SVG gradient referenced by id stops
// rendering if the first element with that id sits in a hidden view.
let _colorIconSeq = 0;

const MEDAL_METALS = {
  1: ['#F7D58B', '#E0A85C', '#B97F2E'], // gold
  2: ['#EEEAF7', '#C3BAD8', '#8F84AE'], // silver, lavender-tinted
  3: ['#F1C29C', '#CD8A5A', '#9A5B33'], // bronze
};

const COLOR_ICONS = {
  flame: (g) => `
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#C9B8ED"/><stop offset="0.45" stop-color="#E3A6BC"/><stop offset="1" stop-color="#E0A85C"/>
      </linearGradient>
    </defs>
    <path d="M12 2.6 C13.3 6.5 17.8 8.9 17.8 14 C17.8 18.3 15.1 21.2 12 21.2 C8.9 21.2 6.2 18.3 6.2 14 C6.2 12.2 6.9 10.8 7.8 9.9 C7.9 12 9 13 9.9 13 C9.2 10.3 10.2 7.3 12 2.6 Z" fill="url(#${g}a)"/>
    <path d="M12 13 C13.4 14.5 14.6 15.6 14.6 17.3 C14.6 18.9 13.4 19.9 12 19.9 C10.6 19.9 9.4 18.9 9.4 17.3 C9.4 15.9 10.7 14.5 12 13 Z" fill="#FFF6EA" opacity="0.85"/>`,
  trophy: (g) => `
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#F7D58B"/><stop offset="1" stop-color="#C98E3C"/>
      </linearGradient>
    </defs>
    <path d="M7 6.2 H4.5 C4.5 9.3 5.9 11 8 11.3" fill="none" stroke="#E0A85C" stroke-width="1.6" stroke-linecap="round"/>
    <path d="M17 6.2 H19.5 C19.5 9.3 18.1 11 16 11.3" fill="none" stroke="#E0A85C" stroke-width="1.6" stroke-linecap="round"/>
    <path d="M6.8 4.2 H17.2 V9.6 C17.2 12.8 14.9 15.1 12 15.1 C9.1 15.1 6.8 12.8 6.8 9.6 Z" fill="url(#${g}a)"/>
    <rect x="10.9" y="14.8" width="2.2" height="3" fill="#C98E3C"/>
    <path d="M8.2 20.8 H15.8 L14.8 17.6 H9.2 Z" fill="#9A80D9"/>
    <path d="M12 6.4 L12.7 8 L14.4 8.1 L13.1 9.2 L13.5 10.9 L12 10 L10.5 10.9 L10.9 9.2 L9.6 8.1 L11.3 8 Z" fill="#FFF6EA" opacity="0.9"/>`,
  medal: (g, { rank = 1 } = {}) => {
    const [light, mid, dark] = MEDAL_METALS[rank] || MEDAL_METALS[1];
    return `
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="${light}"/><stop offset="0.55" stop-color="${mid}"/><stop offset="1" stop-color="${dark}"/>
      </linearGradient>
    </defs>
    <path d="M7.6 2.4 H11 L13.4 9.4 H10 Z" fill="#9A80D9"/>
    <path d="M16.4 2.4 H13 L10.6 9.4 H14 Z" fill="#C9B8ED"/>
    <circle cx="12" cy="15.2" r="6.2" fill="url(#${g}a)"/>
    <circle cx="12" cy="15.2" r="4.6" fill="none" stroke="${light}" stroke-width="0.9" opacity="0.8"/>
    <text x="12" y="17.6" text-anchor="middle" font-family="Inter, system-ui, sans-serif" font-size="6.6" font-weight="700" fill="${dark}">${rank}</text>`;
  },
  bolt: (g) => `
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#C9B8ED"/><stop offset="1" stop-color="#9A80D9"/>
      </linearGradient>
    </defs>
    <path d="M13.6 2.4 L5.6 13.4 H11 L10 21.6 L18.4 10 H13 Z" fill="url(#${g}a)" stroke="#F7D58B" stroke-width="0.8" stroke-linejoin="round"/>`,
  crown: (g) => `
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#F7D58B"/><stop offset="1" stop-color="#C98E3C"/>
      </linearGradient>
    </defs>
    <path d="M3.8 8.2 L8.2 12 L12 4.8 L15.8 12 L20.2 8.2 L18.6 17.4 H5.4 Z" fill="url(#${g}a)"/>
    <rect x="5.4" y="17.9" width="13.2" height="2.4" rx="1" fill="#9A80D9"/>
    <circle cx="12" cy="13.6" r="1.3" fill="#E3A6BC"/>`,
};

function colorIcon(name, size = 24, opts = {}) {
  const draw = COLOR_ICONS[name];
  if (!draw) return icon(name, size);
  const g = `fgci${++_colorIconSeq}`;
  return `<svg class="color-icon" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${draw(g, opts)}</svg>`;
}

// Badge medallions for the Badges page: a hexagon in the badge's tier
// colour (lavender / rose / gold - all from the app palette) with one of
// the app's own line icons in the middle. Locked badges are dimmed in CSS.
const BADGE_TIER_COLORS = {
  1: ['#E4DAF7', '#B9A3EC', '#8467D0'], // common - lavender
  2: ['#F6D9E4', '#E3A6BC', '#B5668A'], // rare - rose
  3: ['#F7D58B', '#E0A85C', '#B97F2E'], // epic - gold
};

function badgeArt(glyph, tier = 1, size = 72) {
  const [light, mid, dark] = BADGE_TIER_COLORS[tier] || BADGE_TIER_COLORS[1];
  const g = `fgba${++_colorIconSeq}`;
  const hex = 'M32 3.5 L56.5 17.5 V46.5 L32 60.5 L7.5 46.5 V17.5 Z';
  return `<svg class="badge-art" viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true">
    <defs>
      <linearGradient id="${g}a" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="${light}"/><stop offset="0.5" stop-color="${mid}"/><stop offset="1" stop-color="${dark}"/>
      </linearGradient>
      <linearGradient id="${g}b" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${hex}" fill="url(#${g}a)" stroke="${dark}" stroke-width="1.5" stroke-linejoin="round"/>
    <path d="M32 9.5 L51 20.5 V43.5 L32 54.5 L13 43.5 V20.5 Z" fill="none" stroke="#ffffff" stroke-opacity="0.45" stroke-width="1.2" stroke-linejoin="round"/>
    <path d="${hex}" fill="url(#${g}b)"/>
    <svg x="18" y="18" width="28" height="28" viewBox="0 0 24 24" style="color:#ffffff">${ICONS[glyph] || ICONS.star}</svg>
  </svg>`;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { icon, renderIcon, ICONS, colorIcon, badgeArt };
}
