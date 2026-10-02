import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { VideoBackground } from '@/components/VideoBackground'
import { Footer } from '@/components/Footer'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Api, Auth } from '@/lib/api'

type Mode = 'login' | 'signup'

export default function AuthPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>(searchParams.get('mode') === 'signup' ? 'signup' : 'login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (Auth.isLoggedIn()) window.location.href = '/app.html'
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'login') {
        await Api.login(username.trim(), password)
      } else {
        await Api.register(username.trim(), password)
      }
      window.location.href = '/app.html'
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message === 'Failed to fetch' ? t('auth.backend_unreachable') : message)
      setSubmitting(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <VideoBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
          <Link to="/" className="animate-fade-rise mb-8 font-serif text-3xl text-foreground">
            FocusGuard AI
          </Link>

          <div className="animate-fade-rise-delay mb-4">
            <LanguageSwitcher />
          </div>

          <div className="liquid-glass animate-fade-rise-delay w-full max-w-sm rounded-3xl px-8 py-9">
            <div className="mb-6 flex gap-2 rounded-full bg-white/5 p-1">
              <button
                type="button"
                onClick={() => setMode('login')}
                className={`flex-1 rounded-full py-2 font-sans text-sm font-medium transition-colors duration-200 ${
                  mode === 'login' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('auth.sign_in')}
              </button>
              <button
                type="button"
                onClick={() => setMode('signup')}
                className={`flex-1 rounded-full py-2 font-sans text-sm font-medium transition-colors duration-200 ${
                  mode === 'signup' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t('auth.create_account')}
              </button>
            </div>

            {error && (
              <div className="mb-4 rounded-2xl bg-red-500/10 px-4 py-3 font-sans text-sm text-red-200">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.username')}</span>
                <input
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.password')}</span>
                <input
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent"
                />
              </label>

              <Button type="submit" variant="glass" disabled={submitting} className="mt-2 rounded-full">
                {mode === 'login' ? t('auth.sign_in') : t('auth.create_account')}
              </Button>
            </form>

            {mode === 'signup' && (
              <p className="mt-5 font-sans text-xs text-muted-foreground">{t('auth.signup_note')}</p>
            )}
          </div>

          <button
            type="button"
            onClick={() => navigate('/')}
            className="animate-fade-rise-delay-2 mt-8 font-sans text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {t('auth.back_to_home')}
          </button>
        </div>
        <Footer />
      </div>
    </div>
  )
}
