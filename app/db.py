"""SQLite schema and connection helpers."""
from __future__ import annotations

import contextlib
from pathlib import Path
import secrets
import sqlite3

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, vehicle TEXT NOT NULL DEFAULT '',
 verification_hash TEXT, verification_expires REAL, verification_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trips (
 id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), role TEXT NOT NULL,
 origin TEXT NOT NULL, destination TEXT NOT NULL, departure_hour INTEGER NOT NULL,
 arrive_by INTEGER NOT NULL, kind TEXT NOT NULL, weekdays TEXT NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL, seats INTEGER NOT NULL,
 price_cents INTEGER NOT NULL, detour_minutes INTEGER NOT NULL, note TEXT NOT NULL,
 return_hour INTEGER, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS occurrences (
 id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(id), trip_date TEXT NOT NULL,
 capacity INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
 driver_id INTEGER REFERENCES users(id), UNIQUE(trip_id, trip_date)
);
CREATE TABLE IF NOT EXISTS applications (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 requester_id INTEGER NOT NULL REFERENCES users(id), status TEXT NOT NULL,
 party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 4), auto_confirm INTEGER NOT NULL,
 meeting_origin TEXT NOT NULL, meeting_destination TEXT NOT NULL,
 created_at REAL NOT NULL, UNIQUE(occurrence_id, requester_id)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 actor_id INTEGER REFERENCES users(id), message TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, occurrence_id INTEGER NOT NULL REFERENCES occurrences(id),
 user_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
 content_hash TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(content_hash,model)
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS place_cache (cache_key TEXT PRIMARY KEY, results TEXT NOT NULL, expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS application_queue ON applications(occurrence_id,status,created_at,id);
CREATE INDEX IF NOT EXISTS occurrence_dates ON occurrences(trip_date,status);
'''


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.read() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute(
                "INSERT OR IGNORE INTO app_settings(key,value) VALUES('identity_salt',?)",
                (secrets.token_hex(32),),
            )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        return db

    @contextlib.contextmanager
    def read(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def tx(self):
        with self.read() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
