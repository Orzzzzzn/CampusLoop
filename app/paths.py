"""Filesystem roots and default storage names."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_PASSWORD = 'campusloop-local-2026'
DEFAULT_DATABASE_NAME = 'campusloop.sqlite3'
