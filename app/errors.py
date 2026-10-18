"""HTTP-facing domain errors."""
from __future__ import annotations


class Problem(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def require(condition, message, status=422):
    if not condition:
        raise Problem(status, message)
