"""
/api/guides — guide tracking with stage history.
Also exports upsert_guide() for use by posts.py and notes.py.
"""

import logging
from flask import Blueprint, request, jsonify
from db import get_db, now_utc

log = logging.getLogger(__name__)
bp  = Blueprint('guides', __name__)


def upsert_guide(conn, gid, data, date_str):
    """Create or update a guide entry. Called from posts and notes routes."""
    existing  = conn.execute("SELECT * FROM guides WHERE id=?", (gid,)).fetchone()
    new_stage = data.get('stage', 'early')
    if existing:
        if new_stage != dict(existing)['stage']:
            conn.execute("INSERT INTO guide_history (guide_id,stage,date) VALUES (?,?,?)",
                         (gid, new_stage, date_str))
        conn.execute(
            "UPDATE guides SET project=?,date=?,stage=?,rating=?,notes=?,link=?,outcome=? WHERE id=?",
            (data.get('project',''), date_str, new_stage, data.get('rating', 5),
             data.get('notes',''), data.get('link',''), data.get('outcome',''), gid)
        )
    else:
        conn.execute(
            "INSERT INTO guides (id,project,date,stage,rating,notes,link,outcome) VALUES (?,?,?,?,?,?,?,?)",
            (gid, data.get('project',''), date_str, new_stage, data.get('rating', 5),
             data.get('notes',''), data.get('link',''), data.get('outcome',''))
        )
        conn.execute("INSERT INTO guide_history (guide_id,stage,date) VALUES (?,?,?)",
                     (gid, new_stage, date_str))
    conn.commit()


@bp.route('/api/guides', methods=['GET'])
def api_get_guides():
    try:
        with get_db() as conn:
            guide_rows = conn.execute("SELECT * FROM guides").fetchall()
            result = []
            for guide_row in guide_rows:
                guide_dict = dict(guide_row)
                hist = conn.execute(
                    "SELECT stage,date FROM guide_history WHERE guide_id=? ORDER BY id",
                    (guide_dict['id'],)
                ).fetchall()
                guide_dict['history'] = [dict(h) for h in hist]
                result.append(guide_dict)
        return jsonify(result)
    except Exception as exc:
        log.exception("api_get_guides error")
        return jsonify({'error': str(exc)}), 500


@bp.route('/api/guides/<gid>', methods=['PUT'])
def api_update_guide(gid):
    try:
        data     = request.json
        date_str = data.get('date', now_utc().date().isoformat())
        with get_db() as conn:
            upsert_guide(conn, gid, data, date_str)
            guide_row  = conn.execute("SELECT * FROM guides WHERE id=?", (gid,)).fetchone()
            guide_dict = dict(guide_row)
            hist = conn.execute(
                "SELECT stage,date FROM guide_history WHERE guide_id=? ORDER BY id", (gid,)
            ).fetchall()
            guide_dict['history'] = [dict(h) for h in hist]
        return jsonify(guide_dict)
    except Exception as exc:
        log.exception("api_update_guide error")
        return jsonify({'error': str(exc)}), 500
