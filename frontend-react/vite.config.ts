import path from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // Auto-activates a new service worker (and reloads) as soon as one
      // is available, instead of waiting for the user to accept a "new
      // version available" prompt - this app has no such prompt UI, and
      // silently serving a stale precached dashboard would be worse than
      // an occasional automatic reload.
      registerType: 'autoUpdate',
      // This app registers the service worker itself (see src/main.tsx,
      // matching the mentor's registerSW() snippet) rather than having
      // the plugin auto-inject a <script> tag - injectRegister: false
      // avoids double-registering.
      injectRegister: false,
      manifest: {
        name: 'FocusGuard AI',
        short_name: 'FocusGuard',
        description: 'Digital attention-management: tracks your apps and tabs, classifies focus vs distraction, and helps you build better habits.',
        theme_color: '#9A80D9', // --lavender-deep
        background_color: '#F1ECFB', // --lavender-bg
        display: 'standalone',
        // The actual working dashboard, not the marketing landing page -
        // launching the installed app should drop you straight into it
        // (app.html redirects to /auth itself if you're not logged in).
        start_url: '/app.html',
        scope: '/',
        icons: [
          { src: 'focusguard-icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'focusguard-icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'focusguard-icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // The default outDir (dist) already contains BOTH the built
        // React shell (assets/*) and the legacy vanilla dashboard's
        // files (app.html, js/, css/, locales/*.json) - they land there
        // together because frontend/ is synced into public/ before each
        // build (see frontend-react/public/ - byte-identical copies of
        // frontend/{app.html,js,css,locales}). One broad glob precaches
        // the whole installable app, not just the React pages.
        globPatterns: ['**/*.{js,css,html,json,png,svg,ico,webmanifest}'],
        // Two independent page roots share this origin (React's SPA at
        // /,/auth,/profile and the standalone app.html dashboard) - no
        // navigateFallback is configured, so an offline navigation to a
        // not-yet-cached page fails visibly instead of silently being
        // routed to the wrong app's shell.
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
