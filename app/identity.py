"""Display names, privacy masking, and activity events."""
from __future__ import annotations

import hashlib
import hmac
import re

from .clock import now
from .occurrence import joined_occurrence


def public_user(row):
    return dict(
        id=row['id'],
        name=row['name'],
        email=row['email'],
        verified=bool(row['verified']),
        vehicle=row['vehicle'],
    )


def event(db, oid, actor, message):
    db.execute(
        'INSERT INTO events(occurrence_id,actor_id,message,created_at) VALUES(?,?,?,?)',
        (oid, actor, message, now().timestamp()),
    )


def identity_name(db, viewer_id, subject_id, oid):
    user = db.execute('SELECT name FROM users WHERE id=?', (subject_id,)).fetchone()
    if user is None:
        return 'Former member', False
    if viewer_id == subject_id:
        return user['name'], True
    o = joined_occurrence(db, oid)
    confirmed = {
        r[0]
        for r in db.execute(
            "SELECT requester_id FROM applications WHERE occurrence_id=? AND status='confirmed'",
            (oid,),
        )
    }
    participants = confirmed | {o['owner_id']}
    revealed = viewer_id in participants and subject_id in participants
    if revealed:
        return user['name'], True
    salt = db.execute("SELECT value FROM app_settings WHERE key='identity_salt'").fetchone()[0]
    code = hmac.new(salt.encode(), str(subject_id).encode(), hashlib.sha256).hexdigest()[:6].upper()
    return 'Loop Member ' + code, False


def private_text(db, value, viewer_id, oid):
    value = str(value or '')
    for person in db.execute('SELECT id,name,email FROM users').fetchall():
        display, revealed = identity_name(db, viewer_id, person['id'], oid)
        if not revealed:
            value = re.sub(re.escape(person['name']), lambda m: display, value, flags=re.I)
            value = re.sub(re.escape(person['email']), '[contact shared after matching]', value, flags=re.I)
    return value
