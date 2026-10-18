"""Password hashing helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from .errors import require


def hash_password(password):
    require(isinstance(password, str) and 10 <= len(password) <= 200, 'Password must contain 10–200 characters.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
    return salt.hex() + ':' + digest.hex()


def check_password(password, encoded):
    if not isinstance(password, str) or len(password) > 200:
        return False
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False
