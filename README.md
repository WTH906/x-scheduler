# X Scheduler + Notes — Vercel Deploy

Same app as the local version, converted for Vercel + Supabase.

- **`/`** — Scheduler dashboard
- **`/notes`** — Notes drafting app
- **`/api/cron/post`** — Vercel Cron fires every minute, posts due tweets

---

## Deploy in 4 steps

### 1. Supabase (database)

1. Go to [supabase.com](https://supabase.com), create a new project
2. Go to **Settings → Database → Connection string → URI**
3. Select **Transaction pooler** (port 6543)
4. Copy the connection string — looks like:
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
5. That's your `DATABASE_URL`. Tables are created automatically on first request.

### 2. Push code to GitHub

Create a repo, push this folder to it.

### 3. Vercel

1. Go to [vercel.com](https://vercel.com), import your GitHub repo
2. Framework preset: **Other**
3. Go to **Settings → Environment Variables** and add:

   | Variable | Value | Required |
   |----------|-------|----------|
   | `DATABASE_URL` | Your Supabase connection string | Yes |
   | `CLIENT_ID` | Your X app client ID | Yes |
   | `CLIENT_SECRET` | Your X app client secret | If your app has one |
   | `REDIRECT_URI` | `https://your-app.vercel.app/callback` | Yes |
   | `SECRET_KEY` | Any random string | Recommended |
   | `TIMEZONE` | e.g. `Europe/Prague` | Recommended |
   | `WEBHOOK_URL` | Telegram/Discord/Slack webhook | Optional |

4. Deploy.

### 4. Update X Developer Portal

Add your Vercel URL as an allowed callback:
```
https://your-app.vercel.app/callback
```

In the X Developer Portal → Your App → Settings → User authentication settings → Callback URI.

---

## Vercel Cron

`vercel.json` defines a cron that hits `/api/cron/post` every minute. This replaces APScheduler from the local version.

Vercel auto-generates a `CRON_SECRET` and passes it as `Authorization: Bearer <secret>` — the endpoint rejects anything without it, so nobody can trigger posting by hitting the URL manually.

**Important:** Vercel Cron is available on the **Pro plan** ($20/month). On the free Hobby plan, cron jobs don't run. If you're on Hobby, you can use an external cron service (cron-job.org, Upstash QStash) to hit `/api/cron/post` every minute — just set your own `CRON_SECRET` env var and pass it as a Bearer token.

---

## What changed from the local version

| File | Change |
|------|--------|
| `config.py` | Reads env vars instead of `config.json` |
| `db.py` | Postgres (psycopg2) with auto `?` → `%s` wrapper |
| `app.py` | No APScheduler, added `/api/cron/post`, init_db on cold start |
| `services/scheduler_runner.py` | Uses `get_db()` instead of raw `sqlite3` |
| `routes/topics.py` | 3 lines: `fetchone()[0]` → `fetchone()['cnt']` |
| `vercel.json` | Routing + cron config |
| `api/index.py` | Vercel entry point |
| Everything else | **Identical** to local version |

The X API posting code (`services/xapi.py`, `services/scheduler_runner.py`) is untouched — same logic, same error handling, same retry behavior.

---

## Project structure

```
x-scheduler-vercel/
├── api/
│   └── index.py                  # Vercel entry point
├── vercel.json                   # Routing + cron
├── app.py                        # Flask app
├── config.py                     # Env var config
├── db.py                         # Postgres connection + helpers
├── requirements.txt
├── .env.example
│
├── routes/
│   ├── auth.py                   # OAuth PKCE
│   ├── accounts.py               # /api/accounts
│   ├── posts.py                  # /api/posts CRUD
│   ├── guides.py                 # /api/guides
│   ├── topics.py                 # /api/topics CRUD
│   └── notes.py                  # /api/notes + publish/unpublish
│
├── services/
│   ├── xapi.py                   # X API posting (untouched)
│   ├── scheduler_runner.py       # Posting loop (called by cron)
│   └── notifications.py          # Webhooks
│
└── static/
    ├── scheduler.html
    └── notes.html
```

## Running locally against Supabase

You can still run this locally for development:

```bash
pip install -r requirements.txt
export DATABASE_URL="your_supabase_connection_string"
export CLIENT_ID="your_client_id"
export REDIRECT_URI="http://127.0.0.1:5000/callback"
python -c "from app import app; app.run(port=5000)"
```

Same data, same DB — what you draft locally shows up on Vercel and vice versa.
