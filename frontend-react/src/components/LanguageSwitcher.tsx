import { useTranslation } from 'react-i18next'

import { SUPPORTED_LANGUAGES } from '@/lib/i18n'

export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const { i18n, t } = useTranslation()

  return (
    <select
      aria-label={t('language_picker.label')}
      value={i18n.resolvedLanguage ?? 'en'}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      className={`rounded-full border border-white/10 bg-white/5 px-3 py-2 font-sans text-sm text-foreground outline-none focus-visible:border-accent ${className}`}
    >
      {SUPPORTED_LANGUAGES.map((lang) => (
        // The open option list is rendered natively by the OS/browser,
        // not this page - it ignores dark Tailwind classes and stays a
        // light system background regardless, so text-foreground (near
        // white) was invisible against it. Inline styles with explicit
        // dark text/light background fix the open list; the closed
        // control above (which does follow the dark theme) is untouched.
        <option key={lang.code} value={lang.code} style={{ color: '#1a1a1a', background: '#ffffff' }}>
          {lang.label}
        </option>
      ))}
    </select>
  )
}
