"""
/api/tracking — CRUD for project tracking rows.
"""

import logging
from flask import Blueprint, request, jsonify
from db import get_db, new_id, now_iso

log = logging.getLogger(__name__)
bp  = Blueprint('tracking', __name__)


@bp.route('/api/tracking', methods=['GET'])
def api_get_tracking():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tracking ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/tracking', methods=['POST'])
def api_create_tracking():
    d   = request.json or {}
    tid = new_id()
    ts  = now_iso()
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO tracking
               (id, project, note_id, posted_about, interacted, quick_notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)''',
            (tid, d.get('project', ''), d.get('note_id'),
             False, False, d.get('quick_notes', ''), ts, ts)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tracking WHERE id=?", (tid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/tracking/<tid>', methods=['PUT'])
def api_update_tracking(tid):
    d = request.json or {}
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM tracking WHERE id=?", (tid,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        ex = dict(existing)
        conn.execute(
            '''UPDATE tracking SET project=?, posted_about=?, interacted=?,
               quick_notes=?, updated_at=? WHERE id=?''',
            (d.get('project', ex['project']),
             d.get('posted_about', ex['posted_about']),
             d.get('interacted', ex['interacted']),
             d.get('quick_notes', ex['quick_notes']),
             now_iso(), tid)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM tracking WHERE id=?", (tid,)).fetchone()
    return jsonify(dict(row))


@bp.route('/api/tracking/<tid>', methods=['DELETE'])
def api_delete_tracking(tid):
    with get_db() as conn:
        # Unlink any notes pointing to this tracking row
        conn.execute("UPDATE notes SET tracking_id=NULL WHERE tracking_id=?", (tid,))
        conn.execute("DELETE FROM tracking WHERE id=?", (tid,))
        conn.commit()
    return jsonify({'ok': True})
