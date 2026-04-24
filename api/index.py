"""Vercel serverless entry point."""
import sys, os, traceback
# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import app
except Exception:
    # If the app fails to import, create a minimal Flask app that shows the error
    from flask import Flask, jsonify
    app = Flask(__name__)
    _err = traceback.format_exc()

    @app.route('/<path:_any>')
    @app.route('/')
    def error_page(_any=''):
        return jsonify({'startup_error': _err}), 500
