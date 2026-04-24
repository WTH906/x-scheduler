"""
Database connection and helpers — Supabase (Postgres).

Uses a thin wrapper so all existing route code works unchanged:
  - conn.execute("SELECT * FROM x WHERE id=?", (val,)).fetchone()
  - Auto-converts SQLite-style `?` placeholders to Postgres `%s`
  - Returns dict-like rows (same as sqlite3.Row)
"""

import random, logging, uuid
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config import DATABASE_URL

log = logging.getLogger(__name__)


# ─── WRAPPER ─────────────────────────────────────────────────────────────────
# Lets route code use conn.execute(...).fetchone() without changes.

class CursorWrapper:
    """Wraps a psycopg2 cursor so fetchone/fetchall return dicts."""
    def __init__(self, cur):
        self._cur = cur
    def fetchone(self):
        return self._cur.fetchone()
    def fetchall(self):
        return self._cur.fetchall()
    @property
    def rowcount(self):
        return self._cur.rowcount


class ConnWrapper:
    """Wraps a psycopg2 connection.
    - execute() auto-converts ? → %s for Postgres compatibility.
    - Returns CursorWrapper so .fetchone()/.fetchall() work.
    """
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s')
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return CursorWrapper(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ─── CONNECTION ──────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield ConnWrapper(conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── INIT ────────────────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist. Safe to call on every cold start."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        statements = [
            # ── Scheduler tables ──
            '''CREATE TABLE IF NOT EXISTS oauth_state (
                state        TEXT PRIMARY KEY,
                slot         TEXT,
                code_verifier TEXT,
                created_at   TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS accounts (
                slot          TEXT PRIMARY KEY,
                username      TEXT,
                access_token  TEXT,
                refresh_token TEXT,
                token_expiry  TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS posts (
                id             TEXT PRIMARY KEY,
                account_slot   TEXT,
                type           TEXT,
                text           TEXT,
                reply_text     TEXT,
                notes          TEXT,
                scheduled_time TEXT,
                recurring      TEXT DEFAULT 'none',
                status         TEXT DEFAULT 'pending',
                retry_count    INTEGER DEFAULT 0,
                next_retry     TEXT,
                project        TEXT,
                rating         INTEGER,
                stage          TEXT,
                created_at     TEXT,
                posted_at      TEXT,
                tweet_id       TEXT,
                error_msg      TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS guides (
                id      TEXT PRIMARY KEY,
                project TEXT,
                date    TEXT,
                stage   TEXT,
                rating  INTEGER,
                notes   TEXT,
                link    TEXT,
                outcome TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS guide_history (
                id       SERIAL PRIMARY KEY,
                guide_id TEXT,
                stage    TEXT,
                date     TEXT
            )''',
            # ── Notes tables ──
            '''CREATE TABLE IF NOT EXISTS topics (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                color       TEXT DEFAULT '#7c6fff',
                icon        TEXT DEFAULT '◆',
                order_index INTEGER DEFAULT 0,
                created_at  TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS notes (
                id             TEXT PRIMARY KEY,
                topic_id       TEXT REFERENCES topics(id) ON DELETE SET NULL,
                title          TEXT DEFAULT '',
                text           TEXT DEFAULT '',
                reply_text     TEXT DEFAULT '',
                category       TEXT DEFAULT 'update',
                project        TEXT DEFAULT '',
                rating         INTEGER,
                stage          TEXT DEFAULT '',
                link           TEXT DEFAULT '',
                outcome        TEXT DEFAULT '',
                notes_internal TEXT DEFAULT '',
                status         TEXT DEFAULT 'draft',
                sent_post_id   TEXT,
                created_at     TEXT,
                updated_at     TEXT
            )''',
            # ── Tracking table ──
            '''CREATE TABLE IF NOT EXISTS tracking (
                id             TEXT PRIMARY KEY,
                project        TEXT NOT NULL DEFAULT '',
                note_id        TEXT,
                posted_about   BOOLEAN DEFAULT FALSE,
                interacted     BOOLEAN DEFAULT FALSE,
                quick_notes    TEXT DEFAULT '',
                created_at     TEXT,
                updated_at     TEXT
            )''',
        ]
        for stmt in statements:
            cur.execute(stmt)
        conn.commit()  # Lock in all CREATE TABLEs before migration

        # Migration: add tracking_id column if upgrading from pre-tracking schema.
        # Runs in its own transaction so a rollback can't wipe the table creations above.
        try:
            cur.execute("ALTER TABLE notes ADD COLUMN tracking_id TEXT")
            conn.commit()
        except Exception:
            conn.rollback()  # Column already exists — that's fine

        log.info("Database tables verified")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)

def now_iso():
    return now_utc().isoformat()

def new_id():
    return str(uuid.uuid4())

def randomize_time(date_str: str, hour: int) -> str:
    return f"{date_str}T{hour:02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"

def build_scheduled_time(date_str, time_str, randomize, existing_time=None):
    hour = int(time_str.split(':')[0])
    if randomize:
        return randomize_time(date_str, hour)
    if existing_time:
        try:
            dt = datetime.fromisoformat(existing_time)
            return f"{date_str}T{hour:02d}:{dt.minute:02d}:{dt.second:02d}"
        except Exception:
            pass
    minute = int(time_str.split(':')[1]) if ':' in time_str else 0
    return f"{date_str}T{hour:02d}:{minute:02d}:00"

def row_to_dict(row) -> dict:
    """Convert a posts row to a dict with parsed date/time fields."""
    d = dict(row)
    st = d.get('scheduled_time', '')
    if st:
        try:
            dt = datetime.fromisoformat(st)
            d['date']       = dt.strftime('%Y-%m-%d')
            d['time']       = dt.strftime('%H:%M')
            d['time_exact'] = dt.strftime('%H:%M:%S')
        except Exception:
            pass
    return d
