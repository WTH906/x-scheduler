# X Post Scheduler — Setup & Auth Guide

## What you need before starting

- A **X Developer account**
- Python 3.9+ installed
- Both X accounts you want to post from

---

## Step 1 — Create a Developer App on X

1. Go to [developer.x.com](https://developer.x.com) and log in
2. Click **"+ Create Project"** → give it a name, pick a use case
3. Create an **App** inside the project

---

## Step 2 — Configure OAuth 2.0

In the app **Settings → User authentication settings**, click **Edit**:

| Setting | Value |
|---|---|
| App permissions | **Read and Write** |
| Type of App | **Web App, Automated App or Bot** |
| Callback URI | `http://127.0.0.1:5000/callback` |
| Website URL | `http://127.0.0.1` (placeholder) |

Save. X will show you a **Client ID** and possibly a **Client Secret**.

---

## Step 3 — Configure the App

```bash
cp config.json.example config.json
nano config.json
```

Fill in:
```json
{
  "CLIENT_ID":     "YOUR_CLIENT_ID_FROM_X_DEVELOPER_PORTAL",
  "CLIENT_SECRET": "YOUR_CLIENT_SECRET_OR_LEAVE_EMPTY",
  "REDIRECT_URI":  "http://127.0.0.1:5000/callback",
  "SECRET_KEY":    "any_random_string_you_make_up",
  "TIMEZONE":      "Europe/Prague",
  "WEBHOOK_URL":   ""
}
```

### Timezone

Set `TIMEZONE` to your IANA timezone (e.g. `Europe/Prague`, `America/New_York`, `Asia/Tokyo`).
All scheduled times in the UI are treated as this timezone. The scheduler compares against
this timezone when deciding whether to fire a post.

### Notifications (optional)

Set `WEBHOOK_URL` to receive alerts when posts fail. Supported:

- **Telegram**: `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>`
- **Discord**: Your Discord webhook URL
- **Slack**: Your Slack incoming webhook URL

Leave empty for log-only notifications.

---

## Step 4 — Install Dependencies & Run

```bash
cd x-scheduler
pip install -r requirements.txt
python app.py
```

You should see:
```
  X Scheduler → http://127.0.0.1:5000
  Timezone: Europe/Prague
  Notifications: log only
```

---

## Step 5 — Connect Your Accounts

1. Open http://127.0.0.1:5000
2. Click **Accounts** → **Connect** next to account1
3. Log into X as Account 1 → click **Authorize app**
4. You'll see a success toast

Repeat for account2 (use incognito/different profile if needed).

---

## How Tokens Work

```
You (browser) ──► https://x.com/i/oauth2/authorize?...
     │   X shows: "Allow Post Scheduler to access your account?"
     │   You click Authorize
     │   X redirects to http://127.0.0.1:5000/callback?code=...
     │
Local Server ──► Exchanges code for tokens ──► Stores in scheduler.db
                 access_token (2h TTL, auto-refreshed)
                 refresh_token (long-lived)
```

---

## Retry Logic

If a post fails due to a transient error (429 rate limit, 500/502/503/504), the scheduler
retries up to 3 times with increasing delays (10s, 30s, 90s). Permanent errors (e.g. 401,
403) fail immediately. Failed posts trigger a webhook notification if configured.

## Rate Limiting

When multiple posts are due in the same scheduler cycle, the app inserts an 8-second delay
between each post to avoid hitting X's rate limits.

---

## Running 24/7 with systemd

Create `/etc/systemd/system/xscheduler.service`:
```ini
[Unit]
Description=X Post Scheduler
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/path/to/x-scheduler
ExecStart=/usr/bin/python3 /path/to/x-scheduler/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable xscheduler
sudo systemctl start xscheduler
journalctl -u xscheduler -f
```

---

## Files Reference

| File | Purpose |
|---|---|
| `app.py` | Flask backend, OAuth, scheduler, X API, notifications |
| `config.json` | Your credentials + timezone + webhook (never commit) |
| `scheduler.db` | SQLite database — posts, guides, tokens |
| `static/index.html` | Frontend UI |
| `requirements.txt` | Python dependencies |

---

## Troubleshooting

**"token_exchange_failed" on callback**
→ Check that Callback URI in X Developer Portal exactly matches `config.json`

**Posts stuck as "pending"**
→ Check terminal logs. Usually means the account token is invalid — disconnect and reconnect.

**Posts firing at wrong time**
→ Check `TIMEZONE` in `config.json`. The scheduler compares post times against this timezone.

**Port 5000 in use**
→ Change port in `app.py` last line and update `REDIRECT_URI` everywhere.
