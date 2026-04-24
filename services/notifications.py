"""
Webhook notifications (Telegram, Discord, Slack).
Falls back to log-only if no webhook configured.
"""

import logging
import requests
from config import WEBHOOK_URL

log = logging.getLogger(__name__)


def notify(message: str, level: str = 'info'):
    prefix = {'info': 'ℹ️', 'success': '✅', 'error': '❌', 'warning': '⚠️'}.get(level, '')
    full_msg = f"{prefix} X Scheduler: {message}"

    if level == 'error':
        log.error("NOTIFY: %s", message)
    else:
        log.info("NOTIFY: %s", message)

    if not WEBHOOK_URL:
        return

    try:
        if 'discord' in WEBHOOK_URL:
            payload = {'content': full_msg}
        elif 'api.telegram.org' in WEBHOOK_URL:
            payload = {'text': full_msg, 'parse_mode': 'HTML'}
        elif 'slack' in WEBHOOK_URL:
            payload = {'text': full_msg}
        else:
            payload = {'text': full_msg}

        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as exc:
        log.warning("Webhook failed: %s", exc)
