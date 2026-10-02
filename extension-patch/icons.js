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
  clock: `<circle cx="12" cy="12" r="8.3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 7.5 V12 L15.2 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>`,
};

function icon(name, size = 24) {
  const paths = ICONS[name] || '';
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${paths}</svg>`;
}

function renderIcon(container, name, size = 24) {
  container.innerHTML = icon(name, size);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { icon, renderIcon, ICONS };
}
