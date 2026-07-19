"""Minimal in-process TTL cache (Phase 4 perf).

Read-heavy / write-rare reference data (the course catalogue — 107 programmes /
~4700 courses, seeded once) and short-lived anonymous public responses (the
posts feed) don't need to re-hit Postgres on every request. This is a tiny
dependency-free TTL cache (no cachetools / Redis) — appropriate for the current
single-instance deployment. Per-instance: correct under 1 replica; a shared
store would be needed once we go multi-replica.

Not locked: FastAPI serves async on one event loop, and the only mutation
points (``set`` / expired ``pop``) are atomic at the Python-statement level for
a best-effort cache — a concurrent miss simply rebuilds an entry.
"""

import time


class TTLCache:
    """A small ``key -> (value, expiry_monotonic)`` store.

    ``max_entries`` caps growth; once reached the whole store clears rather
    than evicting one key — fine for the intended callers, whose key space is
    tiny (one entry per programme code, or per anonymous feed query).
    """

    def __init__(self, ttl_seconds: float, max_entries: int = 64):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value) -> None:
        if len(self._store) >= self._max:
            self._store.clear()
        self._store[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()
