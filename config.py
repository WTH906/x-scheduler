"""
Configuration — reads from environment variables (Vercel-native).

Required env vars:
  DATABASE_URL    — Supabase Postgres connection string
  CLIENT_ID       — X API app client ID

Optional env vars:
  CLIENT_SECRET   — X API app client secret (empty for public apps)
  REDIRECT_URI    — OAuth callback URL (default: https://your-app.vercel.app/callback)
  SECRET_KEY      — Flask secret key
  TIMEZONE        — e.g. Europe/Prague (default: UTC)
  WEBHOOK_URL     — Telegram/Discord/Slack webhook
  CRON_SECRET     — Vercel cron job secret (auto-set by Vercel)
"""

import os, secrets
from zoneinfo import ZoneInfo

DATABASE_URL  = os.environ.get('DATABASE_URL', '')
CLIENT_ID     = os.environ.get('CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET', '')
REDIRECT_URI  = os.environ.get('REDIRECT_URI', 'http://127.0.0.1:5000/callback')
SECRET_KEY    = os.environ.get('SECRET_KEY', secrets.token_hex(32))
TIMEZONE      = os.environ.get('TIMEZONE', 'UTC')
WEBHOOK_URL   = os.environ.get('WEBHOOK_URL', '')
CRON_SECRET   = os.environ.get('CRON_SECRET', '')

# Validate timezone
try:
    LOCAL_TZ = ZoneInfo(TIMEZONE)
except Exception:
    TIMEZONE = 'UTC'
    LOCAL_TZ = ZoneInfo('UTC')

# X API constants
X_AUTH_URL  = 'https://x.com/i/oauth2/authorize'
X_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
X_TWEET_URL = 'https://api.twitter.com/2/tweets'
X_ME_URL    = 'https://api.twitter.com/2/users/me'
SCOPES      = 'tweet.write tweet.read users.read offline.access'

# Retry config
MAX_RETRIES    = 3
RETRY_BACKOFF  = [10, 30, 90]
RETRYABLE_CODES = {429, 500, 502, 503, 504}
POST_DELAY = 8
