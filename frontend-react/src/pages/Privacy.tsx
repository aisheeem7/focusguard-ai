import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { DashboardBackground } from '@/components/DashboardBackground'
import { Footer } from '@/components/Footer'

// Linked from Google's sign-in screen, so it's a plain public page that
// needs no account. English only: it's the version Google reviews.
const UPDATED = '1 November 2026'
const ISSUES_URL = 'https://github.com/aisheeem7/focusguard-ai/issues'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 font-serif text-xl font-normal text-foreground">{title}</h2>
      <div className="flex flex-col gap-3 font-sans text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  )
}

export default function PrivacyPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <DashboardBackground />

      <div className="relative z-10 flex min-h-screen flex-col">
        <div className="flex flex-1 flex-col items-center px-6 py-12">
          <Link to="/" className="mb-8 font-serif text-3xl text-foreground">
            FocusGuard AI
          </Link>

          <article className="liquid-glass w-full max-w-2xl rounded-3xl px-8 py-9">
            <h1 className="font-serif text-3xl font-normal text-foreground">Privacy policy</h1>
            <p className="mt-2 font-sans text-xs text-muted-foreground">Last updated {UPDATED}</p>
            <p className="mt-6 font-sans text-sm leading-relaxed text-muted-foreground">
              FocusGuard AI helps you see where your attention goes on your computer. It's a student project built
              during the Infosys Springboard Internship 2026. This page explains what it stores, why, and what you can
              do about it.
            </p>

            <Section title="What we collect">
              <p>
                <strong className="text-foreground">Your account:</strong> your username, your password (stored only
                as a one-way hash, never readable), your profile photo if you add one, your break-reminder setting and
                the study group you join.
              </p>
              <p>
                <strong className="text-foreground">Your email, if you add one:</strong> used only to confirm it's
                yours and to send password-reset links.
              </p>
              <p>
                <strong className="text-foreground">If you sign in with Google:</strong> we receive your Google
                account's ID and email address. We don't receive your Google password, contacts, files or anything
                else from your Google account.
              </p>
              <p>
                <strong className="text-foreground">Your activity, if you install a tracker:</strong> the browser
                extension and desktop tracker send the names of the apps you use and the websites you visit (the site
                address, and the page title for videos), when and for how long, how often you switch, and whether each
                one counts as productive, distracting or neutral. They don't record what you type, your screen, or the
                contents of pages or files.
              </p>
            </Section>

            <Section title="How we use it">
              <p>To show your dashboard, streaks, badges, Focus Mode sessions and your group's leaderboard.</p>
              <p>
                To sort apps and sites into categories and to write your weekly insight, the name of an app or site, or
                a summary of your totals, may be sent to an AI service (Anthropic, Google Gemini or CheaperInference).
                Your username, email and password are never sent to them.
              </p>
              <p>We don't sell your data, show ads or share it with anyone else.</p>
            </Section>

            <Section title="Who can see it">
              <p>
                Only you can see your activity. If you join a study group, its members see your username, profile
                photo, and productive and distracting time on the leaderboard.
              </p>
            </Section>

            <Section title="Where it's kept">
              <p>
                The website runs on Render, and your data is stored in a database hosted by Neon. Emails are sent
                through Gmail. If you run FocusGuard on your own computer instead, everything stays on that computer.
              </p>
            </Section>

            <Section title="Your choices">
              <p>
                You can change your username, photo and email on your profile page, and stop tracking at any time by
                removing the extension or stopping the desktop tracker. To have your account and all its data deleted,
                open a request on{' '}
                <a href={ISSUES_URL} className="text-foreground underline underline-offset-2">
                  the project's GitHub page
                </a>{' '}
                (don't include your password) and it will be deleted within 30 days.
              </p>
            </Section>

            <Section title="Changes and contact">
              <p>
                If this policy changes, the date at the top changes too. Questions are welcome on{' '}
                <a href={ISSUES_URL} className="text-foreground underline underline-offset-2">
                  GitHub
                </a>
                .
              </p>
            </Section>
          </article>

          <Link to="/" className="mt-8 font-sans text-sm text-muted-foreground transition-colors hover:text-foreground">
            ← Back to home
          </Link>
        </div>
        <Footer />
      </div>
    </div>
  )
}
