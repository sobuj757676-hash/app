"""Supervisor entrypoint; the authenticated API in /api is the single source.
The older backend modules are retained for history, not imported at runtime.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')
sys.path.insert(0, str(Path(__file__).parents[1] / 'api'))
from index import app, db  # noqa: E402,F401
