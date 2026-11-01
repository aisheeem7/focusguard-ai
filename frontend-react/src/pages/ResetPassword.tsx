import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { VideoBackground } from '@/components/VideoBackground'
import { Footer } from '@/components/Footer'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Api } from '@/lib/api'

const inputClass =
  'rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent'

// Opened from the "Reset your password" email: /reset-password?token=...
export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(token ? null : t('reset.no_token'))
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!token) return
    if (password !== confirm) {
      setError(t('reset.mismatch'))
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await Api.resetPassword(token, password)
      window.location.href = '/app.html'
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
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
            <h1 className="mb-6 text-center font-serif text-2xl font-normal text-foreground">{t('reset.title')}</h1>

            {error && (
              <div className="mb-4 rounded-2xl bg-red-500/10 px-4 py-3 font-sans text-sm text-red-200">
                {error}
              </div>
            )}

            {token ? (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <label className="flex flex-col gap-1.5">
                  <span className="font-sans text-xs font-medium text-muted-foreground">{t('reset.new_password')}</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={inputClass}
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="font-sans text-xs font-medium text-muted-foreground">{t('reset.confirm_password')}</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className={inputClass}
                  />
                </label>
                <Button type="submit" variant="glass" disabled={submitting} className="mt-2 rounded-full">
                  {submitting ? t('reset.saving') : t('reset.save')}
                </Button>
              </form>
            ) : null}

            <Link
              to="/auth?mode=forgot"
              className="mt-5 block text-center font-sans text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {t('reset.request_new_link')}
            </Link>
          </div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
