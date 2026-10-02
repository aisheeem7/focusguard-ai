import { StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import './lib/i18n'
import App from './App.tsx'

// PWA installability (Milestone 2): registers the service worker
// vite-plugin-pwa generates at build time. Only present in a real build
// (`npm run build` + serving dist/) - `virtual:pwa-register` resolves to
// a no-op stub during `npm run dev`, so this is always safe to call.
// registerType: 'autoUpdate' in vite.config.ts means a new version
// activates and reloads automatically, no "update available" prompt needed.
registerSW({ immediate: true })

// Translation JSON is fetched over HTTP (i18next-http-backend), so the
// first render needs to wait for it - react-i18next's useTranslation()
// suspends by default, which needs a Suspense boundary above it or it
// throws. A blank fallback is fine here since the fetch is near-instant
// (same-origin static file) and the app is a single page, not a list.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={null}>
      <App />
    </Suspense>
  </StrictMode>,
)
