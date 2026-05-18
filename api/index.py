"""
Vercel serverless entrypoint.

The main Flask application lives at the repository root in app.py. Vercel
discovers Python serverless functions from the api/ directory, so this wrapper
imports and exposes the existing Flask app without duplicating routes.
"""
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app
