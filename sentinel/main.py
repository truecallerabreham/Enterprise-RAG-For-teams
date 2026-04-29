"""
Sentinel Application Entrypoint.

This module creates the app instance that uvicorn serves. It is intentionally
minimal — all configuration logic lives in the app factory (app.py).

Usage:
    uvicorn sentinel.main:app --host 0.0.0.0 --port 8000 --reload
"""

from sentinel.app import create_app

app = create_app()
