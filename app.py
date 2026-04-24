"""
X Scheduler + Notes — Vercel deployment.

  /           → Scheduler dashboard
  /notes      → Notes drafting app
  /api/cron/post → Vercel Cron endpoint (every minute)
"""

import os, logging
from flask import Flask, send_from_directory, jsonify, request

from config import SECRET_KEY, TIMEZONE, WEBHOOK_URL, CRON_SECRET
from db import init_db, get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
app.secret_key = SECRET_KEY


# ─── CORS ────────────────────────────────────────────────────────────────────

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return resp

@app.route('/api/<path:_any>', methods=['OPTIONS'])
def cors_preflight(_any):
    return '', 204


# ─── REGISTER BLUEPRINTS ────────────────────────────────────────────────────

from routes.auth     import bp as auth_bp
from routes.accounts import bp as accounts_bp
from routes.posts    import bp as posts_bp
from routes.guides   import bp as guides_bp
from routes.topics   import bp as topics_bp
from routes.notes    import bp as notes_bp
from routes.tracking import bp as tracking_bp

app.register_blueprint(auth_bp)
app.register_blueprint(accounts_bp)
app.register_blueprint(posts_bp)
app.register_blueprint(guides_bp)
app.register_blueprint(topics_bp)
app.register_blueprint(notes_bp)
app.register_blueprint(tracking_bp)


# ─── CRON ENDPOINT ──────────────────────────────────────────────────────────
# Vercel Cron hits this every minute. Protected by CRON_SECRET.

@app.route('/api/cron/post')
def cron_post():
    # Vercel sends Authorization: Bearer <CRON_SECRET>
    auth = request.headers.get('Authorization', '')
    if CRON_SECRET and auth != f'Bearer {CRON_SECRET}':
        return jsonify({'error': 'unauthorized'}), 401

    from services.scheduler_runner import run_scheduler
    run_scheduler()
    return jsonify({'ok': True})


# ─── HEALTH CHECK ───────────────────────────────────────────────────────────

@app.route('/api/health')
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return jsonify({'status': 'ok', 'timezone': TIMEZONE})
    except Exception as exc:
        return jsonify({'status': 'error', 'detail': str(exc)}), 500


# ─── STATIC PAGES ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'scheduler.html')

@app.route('/notes')
def notes_page():
    return send_from_directory('static', 'notes.html')


# ─── DB INIT ON COLD START ──────────────────────────────────────────────────
# Vercel cold starts import this module — init_db ensures tables exist.
try:
    init_db()
except Exception as exc:
    log.warning("init_db on import failed (DB may not be configured yet): %s", exc)
