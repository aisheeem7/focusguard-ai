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
4. Your site is live at the address Render shows, such as `https://focusguard-ai-y4tt.onrender.com` (Render adds a random suffix when the plain name is taken). Open it, create an account, done.

**Free-tier note:** Render's free plan sleeps after ~15 minutes without visitors, and the first visit afterwards takes about a minute. To keep it awake, add the site URL as a free monitor at [uptimerobot.com](https://uptimerobot.com) (check every 10 minutes), or switch the service to a paid plan.

## 2b. Sign in with Google and "Forgot password?" emails (optional, ~15 min)

Both use one Google Cloud project. Until you set these up, the sign-in page just doesn't show the Google button or the "Forgot password?" link.

**Why not plain Gmail SMTP?** Render's free plan blocks the email ports (25, 465, 587), so online the server sends through the Gmail API instead, which uses ordinary HTTPS.

1. Go to **console.cloud.google.com** and create a project (e.g. `focusguard`).
2. **Google Auth Platform → Branding**: set the app name (FocusGuard AI) and your support email. Under **Audience**, choose **External**, then click **Publish app**. Without publishing, only test users you list can sign in, and the Gmail refresh token stops working after 7 days.
3. **APIs & Services → Library**: search for **Gmail API** and click **Enable**.
4. **Google Auth Platform → Clients → Create client**, type **Web application**:
   - **Authorized JavaScript origins**: `https://focusguard-ai-y4tt.onrender.com` (your site), plus `http://localhost` and `http://localhost:8000` for running it locally.
   - **Authorized redirect URIs**: `https://developers.google.com/oauthplayground` (needed once, in step 5).
   - Copy the **Client ID** and **Client secret**.
5. Get a Gmail refresh token. It lets the server send email from your Gmail account, and nothing else.
   1. Open **developers.google.com/oauthplayground**. Click the gear icon, tick **Use your own OAuth credentials** and paste the client ID and secret.
   2. In **Step 1**, type `https://www.googleapis.com/auth/gmail.send` in the box and click **Authorize APIs**. Sign in with the Gmail account the emails should come from. Google warns that the app isn't verified: click **Advanced → Go to FocusGuard AI**. This is your own app, so that's expected.
   3. In **Step 2**, click **Exchange authorization code for tokens** and copy the **Refresh token**.
6. In Render, open **focusguard-ai → Environment** and add these, then save (Render restarts the site):
   - `GOOGLE_CLIENT_ID`: the client ID
   - `GOOGLE_CLIENT_SECRET`: the client secret
   - `GMAIL_ADDRESS`: the Gmail address from step 5
   - `GMAIL_REFRESH_TOKEN`: the refresh token

**Running locally:** put the same four lines in a `.env` file in the project's top folder (it's in `.gitignore`). Or, for email only, use `GMAIL_ADDRESS` plus `GMAIL_APP_PASSWORD`, an app password from **myaccount.google.com/apppasswords** (needs 2-Step Verification). Open the site at `http://localhost:8000`, not `127.0.0.1`: Google's button only works on addresses listed in step 4.

**How it behaves:**
- Users add an email when they sign up, or later on their profile page. It only counts once they click the confirmation link, so nobody can claim someone else's address.
- "Forgot password?" emails a link that works once, for 1 hour. Using it signs the account out everywhere else, so the desktop tracker and extension ask to sign in again.
- Signing in with Google uses the account that has confirmed that email, or creates a new one. New Google accounts get a username from the email address. They have no password, so to use the desktop tracker or extension they choose one with "Forgot password?".

## 3. Build the downloads (~5 min, on Windows)

The tracker and extension need to know your site's address. This bakes it into the copies you share; the source code keeps pointing at `127.0.0.1` for local use.

```bash
python -m pip install pyinstaller
python scripts/build_release.py --server https://focusguard-ai-y4tt.onrender.com   # use your own site address
```

This creates:
- `release/FocusGuard-Tracker.exe`: Windows desktop tracker (no Python needed)
- `release/FocusGuard-extension.zip`: Chrome extension

## 4. Publish the downloads (GitHub Release)

Other people can only download release files from a **public** repository. If `focusguard-ai` is private, make it public first: **Settings → Change visibility**. Your `.env` and database are never in the repo.

```bash
gh release create v1.0 release/FocusGuard-Tracker.exe release/FocusGuard-extension.zip \
  --title "FocusGuard AI v1.0" --notes "Website: https://focusguard-ai-y4tt.onrender.com"
```

**Publishing an update:** whenever the tracker or extension code changes, rebuild (step 3) and publish a new release with the next version number (`v1.2`, `v1.3`, …) instead of reusing an old one. The newest release automatically becomes the one the **Downloads** link and the dashboard's **Download for Windows** button serve. Website-only changes don't need a release, since Render redeploys on every push to `main`.

```bash
gh release create v1.2 release/FocusGuard-Tracker.exe release/FocusGuard-extension.zip \
  --title "FocusGuard v1.2" --notes "What changed in this version"
```

Share these two links (replace the app address with your own if you deployed a separate copy):
- **App:** `https://focusguard-ai-y4tt.onrender.com`
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
