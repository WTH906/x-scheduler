"""Vercel serverless entry point."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify

_startup_error = None
try:
    import app as _app_module
    app = _app_module.app
except Exception:
    _startup_error = traceback.format_exc()
    app = Flask(__name__)

    @app.route('/<path:_any>')
    @app.route('/')
    def error_page(_any=''):
        return jsonify({'startup_error': _startup_error}), 500
