import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

// Google's own sign-in button (Google Identity Services). It hands back an
// ID token, which the backend checks with Google before signing anyone in.
const GSI_SRC = 'https://accounts.google.com/gsi/client'

interface GoogleIdentity {
  accounts: {
    id: {
      initialize(options: { client_id: string; callback: (response: { credential: string }) => void }): void
      renderButton(parent: HTMLElement, options: Record<string, unknown>): void
    }
  }
}

let gsiPromise: Promise<GoogleIdentity> | null = null

function loadGsi(): Promise<GoogleIdentity> {
  gsiPromise ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GSI_SRC
    script.async = true
    script.onload = () => resolve((window as unknown as { google: GoogleIdentity }).google)
    script.onerror = () => {
      gsiPromise = null
      reject(new Error('Could not load Google sign-in'))
    }
    document.head.appendChild(script)
  })
  return gsiPromise
}

interface Props {
  clientId: string
  text: 'signin_with' | 'signup_with'
  onCredential: (credential: string) => void
  onError: (message: string) => void
}

export function GoogleSignInButton({ clientId, text, onCredential, onError }: Props) {
  const { i18n } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  // Google keeps the first callback it's given, so it calls through refs
  // to always reach the latest handlers.
  const onCredentialRef = useRef(onCredential)
  const onErrorRef = useRef(onError)
  useEffect(() => {
    onCredentialRef.current = onCredential
    onErrorRef.current = onError
  })

  useEffect(() => {
    let cancelled = false
    loadGsi()
      .then((google) => {
        if (cancelled || !containerRef.current) return
        google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => onCredentialRef.current(response.credential),
        })
        containerRef.current.innerHTML = ''
        google.accounts.id.renderButton(containerRef.current, {
          theme: 'filled_black',
          size: 'large',
          shape: 'pill',
          text,
          width: 280,
          locale: i18n.language,
        })
      })
      .catch((err: Error) => onErrorRef.current(err.message))
    return () => {
      cancelled = true
    }
  }, [clientId, text, i18n.language])

  return <div ref={containerRef} className="flex min-h-11 justify-center" />
}
