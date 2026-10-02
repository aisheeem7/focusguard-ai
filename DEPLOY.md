# Deploying FocusGuard AI online

This puts FocusGuard on the internet so anyone can sign up from one link, and friends can share a group leaderboard. The app looks and works exactly the same as the local version.

| What | Where | Cost |
|---|---|---|
| Website + backend | [Render](https://render.com) (runs the `Dockerfile`) | Free tier |
| Database | [Neon](https://neon.tech) (PostgreSQL) | Free tier |
| Downloads (tracker `.exe`, extension `.zip`) | GitHub Releases | Free |

Running locally (`python launch_focusguard.py`) is unaffected by any of this.

---

## 1. Create the database (Neon, ~3 min)

1. Sign up at **neon.tech** and create a project (any name, e.g. `focusguard`).
2. On the project dashboard, copy the **connection string**. It looks like
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`

Keep it private: it's the password to your database.

## 2. Deploy the website (Render, ~10 min)

1. Sign up at **render.com** with your GitHub account and allow access to the `focusguard-ai` repository.
2. **New → Blueprint**, pick `focusguard-ai`. Render reads `render.yaml` and asks for:
   - `DATABASE_URL`: paste the Neon connection string.
   - `GEMINI_API_KEY`: optional, for AI insights (free key at aistudio.google.com). Leave the other keys empty if you don't have them. Insights still work without any key: they're written from your stats instead.
3. Click **Apply**. The first build takes a few minutes.
4. Your site is live at `https://focusguard-ai.onrender.com` (or the name Render shows). Open it, create an account, done.

**Free-tier note:** Render's free plan sleeps after ~15 minutes without visitors, and the first visit afterwards takes about a minute. To keep it awake, add the site URL as a free monitor at [uptimerobot.com](https://uptimerobot.com) (check every 10 minutes), or switch the service to a paid plan.

## 3. Build the downloads (~5 min, on Windows)

The tracker and extension need to know your site's address. This bakes it into the copies you share; the source code keeps pointing at `127.0.0.1` for local use.

```bash
python -m pip install pyinstaller
python scripts/build_release.py --server https://focusguard-ai.onrender.com
```

This creates:
- `release/FocusGuard-Tracker.exe`: Windows desktop tracker (no Python needed)
- `release/FocusGuard-extension.zip`: Chrome extension

## 4. Publish the downloads (GitHub Release)

Other people can only download release files from a **public** repository. If `focusguard-ai` is private, make it public first: **Settings → Change visibility**. Your `.env` and database are never in the repo.

```bash
gh release create v1.0 release/FocusGuard-Tracker.exe release/FocusGuard-extension.zip \
  --title "FocusGuard AI v1.0" --notes "Website: https://focusguard-ai.onrender.com"
```

Share these two links:
- **App:** `https://focusguard-ai.onrender.com`
- **Downloads:** `https://github.com/aisheeem7/focusguard-ai/releases/latest`

---

## What your users do

1. **Open the app link and sign up.** Optional: click the install icon in the address bar to get it as a desktop app.
2. **Browser tracking:** download `FocusGuard-extension.zip`, unzip it, then in `chrome://extensions` turn on **Developer mode** and choose **Load unpacked** on the unzipped folder. Open the extension and sign in under **Account**.
3. **Desktop tracking (Windows):** download and run `FocusGuard-Tracker.exe`, then sign in once in its window and say yes to **Start FocusGuard automatically with Windows**. It then runs in the background from every Windows sign-in, and the dashboard's Overview shows it as connected. Windows may warn about an unrecognised app because the file isn't code-signed; click **More info → Run anyway**.

Optional: publishing the extension on the Chrome Web Store ($5 one-time developer fee, plus a review) lets people install it in one click instead of step 2.

---

## How online mode differs (behind the scenes)

The Docker image sets `FOCUSGUARD_MODE=cloud`. In that mode:
- **Database:** data lives in PostgreSQL (`DATABASE_URL`), and profile photos are stored there too, because hosted disks are wiped on redeploy.
- **Sign-ins:** sharing the dashboard's sign-in with "this computer" is off, since a shared server has many users. The extension and tracker sign in themselves, through their existing login forms.
- **Site address:** the website talks to whichever server it was loaded from, so no address is configured.

To check everything against PostgreSQL locally: `TEST_DATABASE_URL=postgresql://... python -m pytest backend/tests`.
