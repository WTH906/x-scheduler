"""
X API v2 — tweet posting and OAuth token management.
This module is intentionally left as close to the original as possible.
"""

import logging
from datetime import timedelta

import requests

from config import (
    CLIENT_ID, CLIENT_SECRET,
    X_TOKEN_URL, X_TWEET_URL,
)
from db import get_db, now_utc

log = logging.getLogger(__name__)


# ─── TOKEN MANAGEMENT ────────────────────────────────────────────────────────

def get_valid_token(slot: str):
    """Returns (access_token, None) or (None, error_str). Auto-refreshes."""
    from datetime import timezone
    with get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE slot=?", (slot,)).fetchone()
        if not row or not row['refresh_token']:
            return None, f"Account '{slot}' not connected"

        expiry_str = row['token_expiry']
        if expiry_str:
            try:
                from datetime import datetime
                expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
                if now_utc() < expiry - timedelta(minutes=5):
                    return row['access_token'], None
            except Exception:
                pass

        log.info("Refreshing token for slot=%s", slot)
        refresh_data = {
            'grant_type':    'refresh_token',
            'refresh_token': row['refresh_token'],
        }
        if CLIENT_SECRET:
            refresh_auth = (CLIENT_ID, CLIENT_SECRET)
        else:
            refresh_data['client_id'] = CLIENT_ID
            refresh_auth = None
        resp = requests.post(X_TOKEN_URL, data=refresh_data, auth=refresh_auth, timeout=15)

        if resp.status_code != 200:
            return None, f"Token refresh failed: HTTP {resp.status_code}"

        td = resp.json()
        new_access  = td['access_token']
        new_refresh = td.get('refresh_token', row['refresh_token'])
        new_expiry  = (now_utc() + timedelta(seconds=td.get('expires_in', 7200))).isoformat()
        conn.execute(
            "UPDATE accounts SET access_token=?,refresh_token=?,token_expiry=? WHERE slot=?",
            (new_access, new_refresh, new_expiry, slot)
        )
        conn.commit()
        return new_access, None


# ─── TWEET POSTING ───────────────────────────────────────────────────────────

def post_tweet(access_token: str, text: str, reply_to_id: str = None):
    """Post a tweet. Returns (tweet_id, error_str, http_status)."""
    payload = {'text': text}
    if reply_to_id:
        payload['reply'] = {'in_reply_to_tweet_id': reply_to_id}
    try:
        resp = requests.post(
            X_TWEET_URL, json=payload,
            headers={'Authorization': f'Bearer {access_token}',
                     'Content-Type': 'application/json'},
            timeout=20,
        )
    except requests.exceptions.RequestException as exc:
        return None, f"Network error: {exc}", 0

    if resp.status_code == 201:
        return resp.json()['data']['id'], None, 201

    return None, f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code
