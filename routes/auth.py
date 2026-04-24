"""
OAuth 2.0 PKCE flow for X API authentication.
"""

import secrets, hashlib, base64, logging
from datetime import timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, request, jsonify, redirect

from config import (
    CLIENT_ID, CLIENT_SECRET, REDIRECT_URI,
    X_AUTH_URL, X_TOKEN_URL, X_ME_URL, SCOPES,
)
from db import get_db, now_utc
from services.notifications import notify

log = logging.getLogger(__name__)
bp  = Blueprint('auth', __name__)


def pkce_pair():
    verifier  = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return verifier, challenge


@bp.route('/api/auth/start/<slot>')
def auth_start(slot):
    try:
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(20)

        with get_db() as conn:
            cutoff = (now_utc() - timedelta(minutes=10)).isoformat()
            conn.execute("DELETE FROM oauth_state WHERE created_at < ?", (cutoff,))
            conn.execute(
                "INSERT INTO oauth_state (state, slot, code_verifier, created_at) VALUES (?,?,?,?)",
                (state, slot, verifier, now_utc().isoformat())
            )
            conn.commit()

        params = {
            'response_type': 'code', 'client_id': CLIENT_ID,
            'redirect_uri': REDIRECT_URI, 'scope': SCOPES,
            'state': state, 'code_challenge': challenge,
            'code_challenge_method': 'S256',
        }
        return redirect(X_AUTH_URL + '?' + urlencode(params))
    except Exception as exc:
        log.exception("auth_start error")
        return f"Error starting auth: {exc}", 500


@bp.route('/callback')
def oauth_callback():
    code  = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    if error:
        log.warning("OAuth error from X: %s", error)
        return redirect(f'/?auth_error={error}')

    if not code or not state:
        return redirect('/?auth_error=missing_params')

    with get_db() as conn:
        stored = conn.execute(
            "SELECT * FROM oauth_state WHERE state=?", (state,)
        ).fetchone()

        if not stored:
            log.warning("Callback: state not found: %s", state)
            return redirect('/?auth_error=invalid_state')

        slot     = stored['slot']
        verifier = stored['code_verifier']
        conn.execute("DELETE FROM oauth_state WHERE state=?", (state,))
        conn.commit()

    token_data = {
        'code': code, 'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI, 'code_verifier': verifier,
    }
    if CLIENT_SECRET:
        token_auth = (CLIENT_ID, CLIENT_SECRET)
    else:
        token_data['client_id'] = CLIENT_ID
        token_auth = None

    try:
        resp = requests.post(X_TOKEN_URL, data=token_data, auth=token_auth, timeout=15)
    except Exception as exc:
        log.error("Token exchange network error: %s", exc)
        return redirect('/?auth_error=network_error')

    if resp.status_code != 200:
        log.error("Token exchange failed (%s): %s", resp.status_code, resp.text[:500])
        return redirect(f'/?auth_error=token_exchange_failed&detail={resp.status_code}')

    td            = resp.json()
    access_token  = td['access_token']
    refresh_token = td.get('refresh_token', '')
    expiry        = (now_utc() + timedelta(seconds=td.get('expires_in', 7200))).isoformat()

    me = requests.get(X_ME_URL, headers={'Authorization': f'Bearer {access_token}'}, timeout=10)
    username = (me.json().get('data', {}).get('username', slot)
                if me.status_code == 200 else slot)

    with get_db() as conn:
        conn.execute(
            '''INSERT INTO accounts (slot,username,access_token,refresh_token,token_expiry)
               VALUES (?,?,?,?,?)
               ON CONFLICT(slot) DO UPDATE SET
                 username=excluded.username, access_token=excluded.access_token,
                 refresh_token=excluded.refresh_token, token_expiry=excluded.token_expiry''',
            (slot, username, access_token, refresh_token, expiry)
        )
        conn.commit()

    log.info("Connected slot=%s → @%s", slot, username)
    notify(f"Account connected: @{username} ({slot})", 'success')
    return redirect(f'/?auth_success=1&slot={slot}&username={username}')


@bp.route('/api/auth/disconnect/<slot>', methods=['POST'])
def auth_disconnect(slot):
    with get_db() as conn:
        conn.execute("DELETE FROM accounts WHERE slot=?", (slot,))
        conn.commit()
    return jsonify({'ok': True})
