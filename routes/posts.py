"""
/api/posts — CRUD for scheduled posts.
/api/config — expose non-sensitive config to frontend.
"""

import logging
from flask import Blueprint, request, jsonify

from config import TIMEZONE
from db import get_db, now_utc, new_id, build_scheduled_time, row_to_dict
from routes.guides import upsert_guide

log = logging.getLogger(__name__)
bp  = Blueprint('posts', __name__)


@bp.route('/api/config')
def api_config():
    return jsonify({'timezone': TIMEZONE})


@bp.route('/api/posts', methods=['GET'])
def api_get_posts():
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM posts ORDER BY scheduled_time").fetchall()
        return jsonify([row_to_dict(r) for r in rows])
    except Exception as exc:
        log.exception("api_get_posts error")
        return jsonify({'error': str(exc)}), 500


@bp.route('/api/posts', methods=['POST'])
def api_create_post():
    try:
        d   = request.json
        pid = new_id()
        st  = build_scheduled_time(d['date'], d.get('time', '09:00'),
                                   randomize=d.get('randomize_minutes', True))
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO posts
                   (id,account_slot,type,text,reply_text,notes,
                    scheduled_time,recurring,status,project,rating,stage,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (pid, d.get('account_slot',''), d.get('type','update'),
                 d.get('text',''), d.get('reply_text',''), d.get('notes',''),
                 st, d.get('recurring','none'), 'pending',
                 d.get('project',''), d.get('rating'), d.get('stage',''),
                 now_utc().isoformat())
            )
            conn.commit()
            if d.get('type') == 'guide' and d.get('project'):
                upsert_guide(conn, pid, d, d['date'])
            row = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        return jsonify(row_to_dict(row)), 201
    except Exception as exc:
        log.exception("api_create_post error")
        return jsonify({'error': str(exc)}), 500


@bp.route('/api/posts/<pid>', methods=['PUT'])
def api_update_post(pid):
    try:
        d = request.json
        with get_db() as conn:
            existing = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
            if not existing:
                return jsonify({'error': 'Not found'}), 404
            st = build_scheduled_time(
                d.get('date',''), d.get('time','09:00'),
                randomize=d.get('randomize_minutes', False),
                existing_time=dict(existing).get('scheduled_time')
            )
            conn.execute(
                '''UPDATE posts SET account_slot=?,type=?,text=?,reply_text=?,notes=?,
                   scheduled_time=?,recurring=?,project=?,rating=?,stage=?,
                   status="pending",error_msg=NULL,retry_count=0,next_retry=NULL WHERE id=?''',
                (d.get('account_slot',''), d.get('type','update'), d.get('text',''),
                 d.get('reply_text',''), d.get('notes',''), st,
                 d.get('recurring','none'), d.get('project',''),
                 d.get('rating'), d.get('stage',''), pid)
            )
            conn.commit()
            if d.get('type') == 'guide' and d.get('project'):
                upsert_guide(conn, pid, d, d.get('date',''))
            row = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
        return jsonify(row_to_dict(row))
    except Exception as exc:
        log.exception("api_update_post error")
        return jsonify({'error': str(exc)}), 500


@bp.route('/api/posts/<pid>', methods=['DELETE'])
def api_delete_post(pid):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM posts WHERE id=?", (pid,))
            conn.execute("DELETE FROM guides WHERE id=?", (pid,))
            conn.execute("DELETE FROM guide_history WHERE guide_id=?", (pid,))
            conn.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        log.exception("api_delete_post error")
        return jsonify({'error': str(exc)}), 500
