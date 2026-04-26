"""
/api/emoji-templates — CRUD for shared emoji combo templates.
Stored as plain strings (e.g. '❓💡'), inserted at cursor in the editor.
"""

import logging
from flask import Blueprint, request, jsonify
from db import get_db, new_id, now_iso

log = logging.getLogger(__name__)
bp  = Blueprint('emoji_templates', __name__)


@bp.route('/api/emoji-templates', methods=['GET'])
def api_get_templates():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM emoji_templates ORDER BY order_index, created_at"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/emoji-templates', methods=['POST'])
def api_create_template():
    d   = request.json or {}
    combo = (d.get('combo') or '').strip()
    if not combo:
        return jsonify({'error': 'Combo required'}), 400
    tid = new_id()
    ts  = now_iso()
    with get_db() as conn:
        max_idx = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) AS max_idx FROM emoji_templates"
        ).fetchone()['max_idx']
        conn.execute(
            "INSERT INTO emoji_templates (id, combo, order_index, created_at) VALUES (?,?,?,?)",
            (tid, combo, max_idx + 1, ts)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM emoji_templates WHERE id=?", (tid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/emoji-templates/<tid>', methods=['PUT'])
def api_update_template(tid):
    d = request.json or {}
    combo = (d.get('combo') or '').strip()
    if not combo:
        return jsonify({'error': 'Combo required'}), 400
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM emoji_templates WHERE id=?", (tid,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        conn.execute(
            "UPDATE emoji_templates SET combo=? WHERE id=?",
            (combo, tid)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM emoji_templates WHERE id=?", (tid,)).fetchone()
    return jsonify(dict(row))


@bp.route('/api/emoji-templates/<tid>', methods=['DELETE'])
def api_delete_template(tid):
    with get_db() as conn:
        conn.execute("DELETE FROM emoji_templates WHERE id=?", (tid,))
        conn.commit()
    return jsonify({'ok': True})
