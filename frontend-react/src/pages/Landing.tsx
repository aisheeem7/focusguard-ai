import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Nav } from '@/components/Nav'
import { VideoBackground } from '@/components/VideoBackground'
import { Footer } from '@/components/Footer'

export default function Landing() {
  const { t } = useTranslation()

  return (
    <div className="relative min-h-screen overflow-hidden">
      <VideoBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        <Nav />

        <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
          <h1 className="animate-fade-rise font-serif text-5xl leading-[0.95] font-normal tracking-tight text-foreground sm:text-7xl md:text-8xl">
            {t('landing.title_before')}{' '}
            <span className="text-accent">{t('landing.title_accent')}</span>
          </h1>

          <p className="animate-fade-rise-delay mt-4 font-sans text-sm text-muted-foreground">
            {t('landing.subtitle')}
          </p>

          <div className="animate-fade-rise-delay-2 mt-6">
            <Button asChild variant="glass" className="rounded-full">
              <Link to="/auth?mode=signup">{t('landing.cta')}</Link>
            </Button>
          </div>
        </main>

        <Footer />
      </div>
    </div>
  )
}
