# Focus Grove — Frontend

A pastel, storybook-themed companion dashboard for the distraction
tracker backend. Built as plain HTML/CSS/JS on purpose — no build step,
no framework, no npm install required to run it, so it's easy for you
to keep editing directly.

Your fox mascot, **Ember**, appears throughout as the through-line
character. See the design notes at the bottom for the reasoning behind
the palette/type/layout choices.

## What's real here

Every page in this folder calls your **actual backend** over its real
REST API — nothing here is mocked or hardcoded. It was tested against a
live running instance of `backend/main.py` before being handed to you,
including a real register → login → dashboard flow driven through
actual form submissions.

**What this frontend can't do**: it can't detect which app/window is
active on your desktop, or which browser tab you're on — that's the
job of `window_tracker.py` and the browser extension, which is exactly
why those exist as separate pieces. This frontend is a dashboard for
viewing and acting on the data they send to the backend (checking your
streak, starting a Focus Mode session, viewing the leaderboard, reading
your weekly insight) — not a replacement for them.

## Files

```
frontend/
├── index.html       Landing page (hero, feature overview)
├── auth.html         Login / sign up
├── app.html           Main dashboard (all 6 features)
├── css/
│   ├── tokens.css      Design tokens - colors, type, shared components
│   ├── landing.css      Landing-page-specific styles
│   ├── auth.css          Auth-page-specific styles
│   └── dashboard.css      Dashboard-specific styles
└── js/
    ├── mascot.js     Ember the fox - one reusable inline SVG, a few poses
    ├── api.js         Backend API wrapper (fetch calls, token storage)
    └── app.js          Dashboard logic (nav, each feature's view)
```

## Running it

**1. Start your backend first** (from the `backend/` folder):
```bash
uvicorn main:app --reload --port 8000
```
CORS is already enabled on the backend (added specifically for this
frontend) so it can be called from a different local origin.

**2. Serve this folder** — don't just double-click `index.html` (some
browsers block `fetch()` from `file://` pages). Easiest option, from
inside `frontend/`:
```bash
python -m http.server 5500
```
Then open **http://127.0.0.1:5500/index.html** in your browser.

**3. If your backend runs somewhere other than `127.0.0.1:8000`**, set
it before the other scripts load — add this line right before the
`<script src="js/api.js">` tag on any page:
```html
<script>window.FOCUS_GROVE_BACKEND_URL = 'http://your-backend-host:8000';</script>
```

## How it's organized (for editing later)

- **`js/api.js`** is the only file that knows about your backend's
  actual endpoint shapes. If an endpoint's response format ever
  changes, this is the one file to update — every page just calls
  `Api.something()` and doesn't know or care about the raw HTTP details.
- **`js/mascot.js`** is a single function, `renderEmber(container, pose,
  size)`. Add a new pose by adding a key to `EMBER_ACCESSORIES` and
  some extra SVG paths - the base fox body stays the same everywhere.
- **`css/tokens.css`** holds every color/spacing/type value as a CSS
  variable. Change the palette here once, and it updates everywhere -
  don't hardcode hex values in the other CSS files.
- **`app.html`** has one `<section class="view">` per feature, all
  present in the DOM at once; `app.js`'s `switchView()` just toggles
  which one is visible and lazy-loads its data the first time you visit
  it. Adding a 7th feature later means: one new `<li class="path-item">`
  in the sidebar, one new `<section class="view">`, and one new
  `load___View()` function in `app.js`.

## Design notes

**Concept**: "Focus Grove" - a small woodland the student and Ember
share. Each feature is a "clearing" you visit rather than a plain stats
page, which is what makes it feel gamified rather than clinical.

**Palette** (chosen specifically for this brief, not a generic default):
Cream Fog `#FBF3EA`, Meadow Mint `#B8E0D2`, Blush Petal `#F6C6D0`, Dusk
Lavender `#C9BFE8`, Ember Orange `#F4A261` (streaks/achievements),
Pine Ink `#2F3E36` (text).

**Type**: Fredoka (rounded display headlines) + Nunito Sans (body/data)
- two clearly distinct, both rounded and friendly, no serif.

**Known limitation**: this was built and tested in an environment
without a real browser available, so real-DOM/API-integration testing
was done via jsdom (a simulated DOM in Node) rather than an actual
Chrome/Firefox window. Every view was confirmed to render correctly
with zero JS errors and correct real data from a live backend, but a
final look in your actual browser is worth doing before you call it
done - minor visual spacing issues, if any, would only show up there.
