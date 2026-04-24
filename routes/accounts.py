"""
/api/accounts — list connected X accounts.
"""

import logging
from flask import Blueprint, jsonify
from db import get_db

log = logging.getLogger(__name__)
bp  = Blueprint('accounts', __name__)


@bp.route('/api/accounts')
def api_accounts():
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT slot, username FROM accounts ORDER BY slot").fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        log.exception("api_accounts error")
        return jsonify({'error': str(exc)}), 500
