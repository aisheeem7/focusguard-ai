import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { VideoBackground } from '@/components/VideoBackground'
import { Footer } from '@/components/Footer'
import { GoogleSignInButton } from '@/components/GoogleSignInButton'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Api, Auth, type AuthConfig } from '@/lib/api'

type Mode = 'login' | 'signup' | 'forgot'

const inputClass =
  'rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent'

function initialMode(param: string | null): Mode {
  return param === 'signup' || param === 'forgot' ? param : 'login'
}

export default function AuthPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>(initialMode(searchParams.get('mode')))
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [identifier, setIdentifier] = useState('')
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (Auth.isLoggedIn()) window.location.href = '/app.html'
  }, [])

  useEffect(() => {
    // An older server without these features just shows the plain form.
    Api.getAuthConfig()
      .then(setConfig)
      .catch(() => setConfig({ google_client_id: null, email_enabled: false }))
  }, [])

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setNotice(null)
  }

  function showError(err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    setError(message === 'Failed to fetch' ? t('auth.backend_unreachable') : message)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'login') {
        await Api.login(username.trim(), password)
      } else {
        await Api.register(username.trim(), password, email.trim() || undefined)
      }
      window.location.href = '/app.html'
    } catch (err) {
      showError(err)
      setSubmitting(false)
    }
  }

  async function handleForgot(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await Api.forgotPassword(identifier.trim())
      setNotice(t('auth.reset_sent'))
    } catch (err) {
      showError(err)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogleCredential(credential: string) {
    setError(null)
    try {
      await Api.googleSignIn(credential)
      window.location.href = '/app.html'
    } catch (err) {
      showError(err)
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
            {mode === 'forgot' ? (
              <h1 className="mb-2 text-center font-serif text-2xl font-normal text-foreground">{t('auth.forgot_title')}</h1>
            ) : (
              <div className="mb-6 flex gap-2 rounded-full bg-white/5 p-1">
                <button
                  type="button"
                  onClick={() => switchMode('login')}
                  className={`flex-1 rounded-full py-2 font-sans text-sm font-medium transition-colors duration-200 ${
                    mode === 'login' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t('auth.sign_in')}
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('signup')}
                  className={`flex-1 rounded-full py-2 font-sans text-sm font-medium transition-colors duration-200 ${
                    mode === 'signup' ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t('auth.create_account')}
                </button>
              </div>
            )}

            {error && (
              <div className="mb-4 rounded-2xl bg-red-500/10 px-4 py-3 font-sans text-sm text-red-200">
                {error}
              </div>
            )}
            {notice && (
              <div className="mb-4 rounded-2xl bg-emerald-500/10 px-4 py-3 font-sans text-sm text-emerald-200">
                {notice}
              </div>
            )}

            {mode === 'forgot' ? (
              <>
                <p className="mb-5 text-center font-sans text-sm text-muted-foreground">{t('auth.forgot_hint')}</p>
                <form onSubmit={handleForgot} className="flex flex-col gap-4">
                  <label className="flex flex-col gap-1.5">
                    <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.identifier')}</span>
                    <input
                      type="text"
                      autoComplete="username"
                      required
                      value={identifier}
                      onChange={(e) => setIdentifier(e.target.value)}
                      className={inputClass}
                    />
                  </label>
                  <Button type="submit" variant="glass" disabled={submitting} className="mt-2 rounded-full">
                    {t('auth.send_reset_link')}
                  </Button>
                </form>
                <button
                  type="button"
                  onClick={() => switchMode('login')}
                  className="mt-5 w-full text-center font-sans text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  {t('auth.back_to_sign_in')}
                </button>
              </>
            ) : (
              <>
                <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                  <label className="flex flex-col gap-1.5">
                    <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.username')}</span>
                    <input
                      type="text"
                      autoComplete="username"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className={inputClass}
                    />
                  </label>
                  {mode === 'signup' && config?.email_enabled && (
                    <label className="flex flex-col gap-1.5">
                      <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.email_optional')}</span>
                      <input
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className={inputClass}
                      />
                    </label>
                  )}
                  <label className="flex flex-col gap-1.5">
                    <span className="font-sans text-xs font-medium text-muted-foreground">{t('auth.password')}</span>
                    <input
                      type="password"
                      autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className={inputClass}
                    />
                  </label>
                  {mode === 'login' && config?.email_enabled && (
                    <button
                      type="button"
                      onClick={() => {
                        setIdentifier(username)
                        switchMode('forgot')
                      }}
                      className="-mt-2 self-end font-sans text-xs text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {t('auth.forgot_password')}
                    </button>
                  )}

                  <Button type="submit" variant="glass" disabled={submitting} className="mt-2 rounded-full">
                    {mode === 'login' ? t('auth.sign_in') : t('auth.create_account')}
                  </Button>
                </form>

                {config?.google_client_id && (
                  <>
                    <div className="my-5 flex items-center gap-3 font-sans text-xs text-muted-foreground">
                      <span className="h-px flex-1 bg-white/10" />
                      {t('auth.or')}
                      <span className="h-px flex-1 bg-white/10" />
                    </div>
                    <GoogleSignInButton
                      clientId={config.google_client_id}
                      text={mode === 'signup' ? 'signup_with' : 'signin_with'}
                      onCredential={handleGoogleCredential}
                      onError={setError}
                    />
                  </>
                )}

                {mode === 'signup' && (
                  <p className="mt-5 font-sans text-xs text-muted-foreground">
                    {config?.email_enabled ? t('auth.signup_note_email') : t('auth.signup_note')}
                  </p>
                )}
              </>
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
