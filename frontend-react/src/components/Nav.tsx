import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'

const NAV_LINK_KEYS = ['home', 'focus_mode', 'streaks', 'leaderboard', 'insights'] as const

export function Nav() {
  const { t } = useTranslation()

  // Equal side columns keep the links centred on the page, not between
  // a narrow logo and the wider buttons. Where the row is too narrow for
  // that, the links move to their own centred row underneath.
  return (
    <nav className="relative z-10 grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-4 px-6 pb-6 pt-3 min-[1180px]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
      <Link to="/" className="col-start-1 row-start-1 justify-self-start font-serif text-2xl tracking-tight text-foreground">
        FocusGuard AI
      </Link>

      <ul className="col-span-2 row-start-2 hidden items-center justify-center gap-8 md:flex min-[1180px]:col-span-1 min-[1180px]:col-start-2 min-[1180px]:row-start-1">
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

      <div className="col-start-2 row-start-1 flex items-center gap-3 justify-self-end min-[1180px]:col-start-3">
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
