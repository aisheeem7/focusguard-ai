import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { VideoBackground } from '@/components/VideoBackground'
import { Footer } from '@/components/Footer'
import { Api, Auth } from '@/lib/api'

// Opened from the "Confirm your email" email: /verify-email?token=...
export default function VerifyEmailPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [state, setState] = useState<{ status: 'checking' | 'done' | 'error'; text: string }>(
    token ? { status: 'checking', text: '' } : { status: 'error', text: t('verify.no_token') },
  )
  // Each link works once, so StrictMode's second effect run in development
  // mustn't send it again.
  const sent = useRef(false)

  useEffect(() => {
    if (sent.current || !token) return
    sent.current = true
    Api.verifyEmail(token)
      .then(({ message }) => setState({ status: 'done', text: t('verify.success', { email: message }) }))
      .catch((err: Error) => setState({ status: 'error', text: err.message }))
  }, [token, t])

  return (
    <div className="relative min-h-screen overflow-hidden">
      <VideoBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
          <Link to="/" className="animate-fade-rise mb-8 font-serif text-3xl text-foreground">
            FocusGuard AI
          </Link>

          <div className="liquid-glass animate-fade-rise-delay w-full max-w-sm rounded-3xl px-8 py-9 text-center">
            <h1 className="mb-4 font-serif text-2xl font-normal text-foreground">{t('verify.title')}</h1>
            {state.status === 'checking' ? (
              <p className="font-sans text-sm text-muted-foreground">{t('verify.checking')}</p>
            ) : (
              <div
                className={`rounded-2xl px-4 py-3 font-sans text-sm ${
                  state.status === 'error' ? 'bg-red-500/10 text-red-200' : 'bg-emerald-500/10 text-emerald-200'
                }`}
              >
                {state.text}
              </div>
            )}
            <a
              href={Auth.isLoggedIn() ? '/app.html' : '/auth'}
              className="mt-6 block font-sans text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {Auth.isLoggedIn() ? t('verify.go_to_dashboard') : t('verify.go_to_sign_in')}
            </a>
          </div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
