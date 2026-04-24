"""
/api/notes — CRUD for drafts + publish/unpublish (direct DB bridge to posts).

Publish inserts a row into the `posts` table in the same DB — no HTTP proxy.
The scheduler runner picks it up the same way as any other post card.
"""

import logging
from datetime import timedelta, timezone

from flask import Blueprint, request, jsonify
from db import get_db, new_id, now_utc, now_iso, build_scheduled_time, row_to_dict
from routes.guides import upsert_guide

log = logging.getLogger(__name__)
bp  = Blueprint('notes', __name__)


# Fields the client can set via PUT. `status` is server-controlled.
NOTE_FIELDS = (
    'topic_id', 'title', 'text', 'reply_text', 'category', 'project',
    'rating', 'stage', 'link', 'outcome', 'notes_internal', 'tracking_id',
)


def _note_payload(d, existing=None):
    """Normalize a note payload, falling back to existing values."""
    ex = dict(existing) if existing else {}
    out = {}
    for f in NOTE_FIELDS:
        out[f] = d[f] if f in d else ex.get(f, None)
    out['status'] = ex.get('status', 'draft')
    if out.get('category') is None:
        out['category'] = 'update'
    for f in ('title', 'text', 'reply_text', 'project', 'stage',
              'link', 'outcome', 'notes_internal'):
        if out.get(f) is None:
            out[f] = ''
    return out


# ─── CRUD ────────────────────────────────────────────────────────────────────

@bp.route('/api/notes', methods=['GET'])
def api_get_notes():
    topic_id = request.args.get('topic_id')
    with get_db() as conn:
        if topic_id == 'none':
            rows = conn.execute(
                "SELECT * FROM notes WHERE topic_id IS NULL ORDER BY updated_at DESC"
            ).fetchall()
        elif topic_id:
            rows = conn.execute(
                "SELECT * FROM notes WHERE topic_id=? ORDER BY updated_at DESC", (topic_id,)
            ).fetchall()
        else:
            q = request.args.get('q', '').strip()
            if q:
                like = f'%{q}%'
                rows = conn.execute(
                    """SELECT * FROM notes
                       WHERE title LIKE ? OR text LIKE ? OR reply_text LIKE ? OR notes_internal LIKE ?
                       ORDER BY updated_at DESC""",
                    (like, like, like, like)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/notes/<nid>', methods=['GET'])
def api_get_note(nid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))


@bp.route('/api/notes', methods=['POST'])
def api_create_note():
    d  = request.json or {}
    p  = _note_payload(d)
    nid = new_id()
    ts  = now_iso()
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO notes
               (id, topic_id, title, text, reply_text, category, project,
                rating, stage, link, outcome, notes_internal, status,
                tracking_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (nid, p['topic_id'], p['title'], p['text'], p['reply_text'],
             p['category'], p['project'], p['rating'], p['stage'],
             p['link'], p['outcome'], p['notes_internal'], p['status'],
             p.get('tracking_id'), ts, ts)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/notes/<nid>', methods=['PUT'])
def api_update_note(nid):
    d = request.json or {}
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        p = _note_payload(d, existing)
        conn.execute(
            '''UPDATE notes SET topic_id=?, title=?, text=?, reply_text=?,
               category=?, project=?, rating=?, stage=?, link=?, outcome=?,
               notes_internal=?, status=?, tracking_id=?, updated_at=?
               WHERE id=?''',
            (p['topic_id'], p['title'], p['text'], p['reply_text'],
             p['category'], p['project'], p['rating'], p['stage'],
             p['link'], p['outcome'],
             p['notes_internal'], p['status'], p.get('tracking_id'), now_iso(), nid)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
    return jsonify(dict(row))


@bp.route('/api/notes/<nid>', methods=['DELETE'])
def api_delete_note(nid):
    with get_db() as conn:
        conn.execute("DELETE FROM notes WHERE id=?", (nid,))
        conn.commit()
    return jsonify({'ok': True})


@bp.route('/api/notes/<nid>/duplicate', methods=['POST'])
def api_duplicate_note(nid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        orig = dict(row)
        dup_id = new_id()
        ts = now_iso()
        conn.execute(
            '''INSERT INTO notes
               (id, topic_id, title, text, reply_text, category, project,
                rating, stage, link, outcome, notes_internal, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (dup_id, orig['topic_id'],
             (orig['title'] or 'Untitled') + ' (copy)',
             orig['text'], orig['reply_text'], orig['category'],
             orig['project'], orig['rating'], orig['stage'],
             orig['link'], orig['outcome'], orig['notes_internal'],
             'draft', ts, ts)
        )
        conn.commit()
        new_row = conn.execute("SELECT * FROM notes WHERE id=?", (dup_id,)).fetchone()
    return jsonify(dict(new_row)), 201


# ─── PUBLISH / UNPUBLISH ────────────────────────────────────────────────────
# Direct DB bridge: publish INSERTs into the `posts` table,
# unpublish DELETEs from it. No HTTP proxy needed since it's the same DB.

def _post_payload(note):
    """Build the fields to write into the posts table.
    Content + metadata only — NO time, NO account_slot.
    Uses a placeholder date (tomorrow) so the scheduler doesn't fire it
    prematurely. The user sets the real date in the scheduler dashboard.
    """
    placeholder_date = (now_utc() + timedelta(days=1)).strftime('%Y-%m-%d')
    return {
        'type':     note['category'] or 'update',
        'text':     note['text'] or '',
        'reply_text': note['reply_text'] or '',
        'notes':    note['notes_internal'] or '',
        'project':  note['project'] or '',
        'rating':   note['rating'],
        'stage':    note['stage'] or '',
        'link':     note['link'] or '',
        'outcome':  note['outcome'] or '',
        'date':     placeholder_date,
        'time':     '09:00',
    }


@bp.route('/api/notes/<nid>/publish', methods=['POST'])
def api_publish_note(nid):
    """Push note content to the posts table.
    - New: INSERT into posts.
    - Already published (sent_post_id set): UPDATE existing post (re-sync).
    """
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        if not row:
            return jsonify({'error': 'Note not found'}), 404
        note = dict(row)
        p = _post_payload(note)
        st = build_scheduled_time(p['date'], p['time'], randomize=True)

        resynced = False
        if note.get('sent_post_id'):
            # Re-sync: update existing post card
            existing = conn.execute(
                "SELECT id FROM posts WHERE id=?", (note['sent_post_id'],)
            ).fetchone()
            if existing:
                conn.execute(
                    '''UPDATE posts SET type=?, text=?, reply_text=?, notes=?,
                       project=?, rating=?, stage=? WHERE id=?''',
                    (p['type'], p['text'], p['reply_text'], p['notes'],
                     p['project'], p['rating'], p['stage'],
                     note['sent_post_id'])
                )
                if p['type'] == 'guide' and p['project']:
                    upsert_guide(conn, note['sent_post_id'], p, p['date'])
                resynced = True
                pid = note['sent_post_id']
            else:
                # Card was deleted in scheduler — fall through to create
                note['sent_post_id'] = None

        if not note.get('sent_post_id'):
            # Create new post card
            pid = new_id()
            conn.execute(
                '''INSERT INTO posts
                   (id, account_slot, type, text, reply_text, notes,
                    scheduled_time, recurring, status, project, rating, stage, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (pid, '', p['type'], p['text'], p['reply_text'], p['notes'],
                 st, 'none', 'pending',
                 p['project'], p['rating'], p['stage'],
                 now_utc().isoformat())
            )
            if p['type'] == 'guide' and p['project']:
                upsert_guide(conn, pid, p, p['date'])

        conn.execute(
            "UPDATE notes SET status='published', sent_post_id=?, updated_at=? WHERE id=?",
            (pid, now_iso(), nid)
        )
        # Auto-check "posted about" in linked tracking row
        if note.get('tracking_id'):
            conn.execute(
                "UPDATE tracking SET posted_about=TRUE, updated_at=? WHERE id=?",
                (now_iso(), note['tracking_id'])
            )
        conn.commit()
        post_row = conn.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()

    return jsonify({
        'ok': True,
        'post': row_to_dict(post_row) if post_row else {'id': pid},
        'resynced': resynced,
    })


@bp.route('/api/notes/<nid>/unpublish', methods=['POST'])
def api_unpublish_note(nid):
    """Revert to draft: delete the matching post card, reset local status."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        if not row:
            return jsonify({'error': 'Note not found'}), 404
        note = dict(row)

        if note.get('sent_post_id'):
            conn.execute("DELETE FROM posts WHERE id=?", (note['sent_post_id'],))
            conn.execute("DELETE FROM guides WHERE id=?", (note['sent_post_id'],))
            conn.execute("DELETE FROM guide_history WHERE guide_id=?", (note['sent_post_id'],))

        conn.execute(
            "UPDATE notes SET status='draft', sent_post_id=NULL, updated_at=? WHERE id=?",
            (now_iso(), nid)
        )
        conn.commit()
    return jsonify({'ok': True})
