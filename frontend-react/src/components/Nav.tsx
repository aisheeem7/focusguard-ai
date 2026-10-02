import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'

const NAV_LINK_KEYS = ['home', 'focus_mode', 'streaks', 'leaderboard', 'insights'] as const

export function Nav() {
  const { t } = useTranslation()

  return (
    <nav className="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-8 py-6">
      <Link to="/" className="font-serif text-2xl tracking-tight text-foreground">
        FocusGuard AI
      </Link>

      <ul className="hidden items-center gap-8 md:flex">
        {NAV_LINK_KEYS.map((key) => (
          <li key={key}>
            <a
              href="/app.html"
              className="font-sans text-sm text-muted-foreground transition-colors duration-200 hover:text-foreground"
            >
              {t(`nav.${key}`)}
            </a>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-3">
        <LanguageSwitcher />
        <Button asChild variant="glass" className="rounded-full">
          <Link to="/auth">{t('nav.sign_in')}</Link>
        </Button>
        <Button asChild variant="primary" className="rounded-full">
          <Link to="/auth?mode=signup">{t('nav.sign_up')}</Link>
        </Button>
      </div>
    </nav>
  )
}
