"""
/api/topics — CRUD for note topic folders.
"""

import logging
from flask import Blueprint, request, jsonify
from db import get_db, new_id, now_iso

log = logging.getLogger(__name__)
bp  = Blueprint('topics', __name__)


@bp.route('/api/topics', methods=['GET'])
def api_get_topics():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM topics ORDER BY order_index, name"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['count'] = conn.execute(
                "SELECT COUNT(*) AS cnt FROM notes WHERE topic_id=?", (d['id'],)
            ).fetchone()['cnt']
            out.append(d)
    return jsonify(out)


@bp.route('/api/topics', methods=['POST'])
def api_create_topic():
    d  = request.json or {}
    tid = new_id()
    ts  = now_iso()
    with get_db() as conn:
        max_idx = conn.execute("SELECT COALESCE(MAX(order_index),0) AS max_idx FROM topics").fetchone()['max_idx']
        conn.execute(
            "INSERT INTO topics (id, name, color, icon, order_index, created_at) VALUES (?,?,?,?,?,?)",
            (tid, d.get('name','Untitled'), d.get('color','#7c6fff'),
             d.get('icon','◆'), max_idx + 1, ts)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/topics/<tid>', methods=['PUT'])
def api_update_topic(tid):
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            "UPDATE topics SET name=?, color=?, icon=? WHERE id=?",
            (d.get('name',''), d.get('color','#7c6fff'), d.get('icon','◆'), tid)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'error':'Not found'}), 404
    return jsonify(dict(row))


@bp.route('/api/topics/<tid>', methods=['DELETE'])
def api_delete_topic(tid):
    cascade = request.args.get('cascade')
    with get_db() as conn:
        if cascade == '1':
            conn.execute("DELETE FROM notes WHERE topic_id=?", (tid,))
        else:
            conn.execute("UPDATE notes SET topic_id=NULL WHERE topic_id=?", (tid,))
        conn.execute("DELETE FROM topics WHERE id=?", (tid,))
        conn.commit()
    return jsonify({'ok': True})


@bp.route('/api/seed', methods=['POST'])
def api_seed():
    """Seed starter topics if the DB is empty. Idempotent."""
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM topics").fetchone()['cnt']
        if count > 0:
            return jsonify({'ok': True, 'seeded': False, 'reason': 'topics already exist'})
        ts = now_iso()
        defaults = [
            ('DeFi',       '#60a5fa', '◆',  0),
            ('Vibecoding', '#a594ff', '⚡', 1),
            ('Guides',     '#fb923c', '★',  2),
            ('Thoughts',   '#f472b6', '✦',  3),
        ]
        for name, color, icon, idx in defaults:
            conn.execute(
                "INSERT INTO topics (id,name,color,icon,order_index,created_at) VALUES (?,?,?,?,?,?)",
                (new_id(), name, color, icon, idx, ts)
            )
        conn.commit()
    return jsonify({'ok': True, 'seeded': True})
