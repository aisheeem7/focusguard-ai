import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { DashboardBackground } from '@/components/DashboardBackground'
import { Footer } from '@/components/Footer'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Api, Auth, BACKEND_URL } from '@/lib/api'

export default function ProfilePage() {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [breakInterval, setBreakInterval] = useState(50)
  const [loading, setLoading] = useState(true)
  const [savingUsername, setSavingUsername] = useState(false)
  const [savingBreakInterval, setSavingBreakInterval] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!Auth.isLoggedIn()) {
      window.location.href = '/auth'
      return
    }
    Api.getMe()
      .then((profile) => {
        setUsername(profile.username)
        setAvatarUrl(profile.avatar_url)
        setBreakInterval(profile.break_interval_minutes)
      })
      .catch((err: Error) => setMessage({ type: 'error', text: err.message }))
      .finally(() => setLoading(false))
  }, [])

  async function handleUsernameSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = username.trim()
    if (!trimmed) return
    setSavingUsername(true)
    setMessage(null)
    try {
      const profile = await Api.updateUsername(trimmed)
      setUsername(profile.username)
      setMessage({ type: 'success', text: t('profile.username_updated') })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSavingUsername(false)
    }
  }

  async function handleBreakIntervalSubmit(e: FormEvent) {
    e.preventDefault()
    setSavingBreakInterval(true)
    setMessage(null)
    try {
      const profile = await Api.updateBreakInterval(breakInterval)
      setBreakInterval(profile.break_interval_minutes)
      setMessage({ type: 'success', text: t('profile.break_interval_updated') })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setSavingBreakInterval(false)
    }
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingAvatar(true)
    setMessage(null)
    try {
      const profile = await Api.uploadAvatar(file)
      setAvatarUrl(profile.avatar_url)
      setMessage({ type: 'success', text: t('profile.avatar_updated') })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : String(err) })
    } finally {
      setUploadingAvatar(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const avatarSrc = avatarUrl ? `${BACKEND_URL}${avatarUrl}` : null

  return (
    <div className="relative min-h-screen overflow-hidden">
      <DashboardBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12">
          <Link to="/" className="animate-fade-rise mb-8 font-serif text-3xl text-foreground">
            FocusGuard AI
          </Link>

          <div className="animate-fade-rise-delay mb-4">
            <LanguageSwitcher />
          </div>

          <div className="liquid-glass animate-fade-rise-delay w-full max-w-sm rounded-3xl px-8 py-9">
            <h1 className="mb-6 text-center font-serif text-2xl font-normal text-foreground">{t('profile.title')}</h1>

            {loading ? (
              <p className="text-center font-sans text-sm text-muted-foreground">{t('profile.loading')}</p>
            ) : (
              <>
                <div className="mb-6 flex flex-col items-center gap-3">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="group relative h-24 w-24 overflow-hidden rounded-full border border-white/15 bg-white/5"
                    disabled={uploadingAvatar}
                  >
                    {avatarSrc ? (
                      <img src={avatarSrc} alt="Profile" className="h-full w-full object-cover" />
                    ) : (
                      <span className="flex h-full w-full items-center justify-center font-serif text-3xl text-muted-foreground">
                        {username.charAt(0).toUpperCase() || '?'}
                      </span>
                    )}
                    <span className="absolute inset-0 flex items-center justify-center bg-black/50 font-sans text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                      {uploadingAvatar ? t('profile.uploading') : t('profile.change')}
                    </span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                  <p className="font-sans text-xs text-muted-foreground">{t('profile.avatar_hint')}</p>
                </div>

                {message && (
                  <div
                    className={`mb-4 rounded-2xl px-4 py-3 font-sans text-sm ${
                      message.type === 'error' ? 'bg-red-500/10 text-red-200' : 'bg-emerald-500/10 text-emerald-200'
                    }`}
                  >
                    {message.text}
                  </div>
                )}

                <form onSubmit={handleUsernameSubmit} className="flex flex-col gap-4">
                  <label className="flex flex-col gap-1.5">
                    <span className="font-sans text-xs font-medium text-muted-foreground">{t('profile.username')}</span>
                    <input
                      type="text"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent"
                    />
                  </label>

                  <Button type="submit" variant="glass" disabled={savingUsername} className="mt-2 rounded-full">
                    {savingUsername ? t('profile.saving') : t('profile.save_username')}
                  </Button>
                </form>

                <form onSubmit={handleBreakIntervalSubmit} className="mt-6 flex flex-col gap-4 border-t border-white/10 pt-6">
                  <label className="flex flex-col gap-1.5">
                    <span className="font-sans text-xs font-medium text-muted-foreground">{t('profile.break_interval_label')}</span>
                    <p className="font-sans text-xs text-muted-foreground">{t('profile.break_interval_hint')}</p>
                    <select
                      value={breakInterval}
                      onChange={(e) => setBreakInterval(parseInt(e.target.value, 10))}
                      className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 font-sans text-foreground outline-none focus-visible:border-accent"
                    >
                      {/* Same fix as LanguageSwitcher: the native open option
                          list ignores dark theme classes and stays a light
                          system background, so explicit dark text/light
                          background is needed on the options themselves. */}
                      {/* The saved value (e.g. the 50-minute default) may not
                          be one of the preset choices below - without adding
                          it explicitly, a <select> with no matching option
                          silently displays the first option while its real
                          value stays whatever was loaded, which looks like
                          the wrong interval is selected. */}
                      {Array.from(new Set([breakInterval, 15, 30, 45, 60, 90, 120]))
                        .sort((a, b) => a - b)
                        .map((mins) => (
                          <option key={mins} value={mins} style={{ color: '#1a1a1a', background: '#ffffff' }}>
                            {mins} min
                          </option>
                        ))}
                    </select>
                  </label>

                  <Button type="submit" variant="glass" disabled={savingBreakInterval} className="mt-2 rounded-full">
                    {savingBreakInterval ? t('profile.saving') : t('profile.save_break_interval')}
                  </Button>
                </form>
              </>
            )}
          </div>

          <a
            href="/app.html"
            className="animate-fade-rise-delay-2 mt-8 font-sans text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {t('profile.back_to_dashboard')}
          </a>
        </div>
        <Footer />
      </div>
    </div>
  )
}
