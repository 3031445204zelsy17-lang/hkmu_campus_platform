import time
from collections import defaultdict
from fastapi import HTTPException, status

# In-memory rate limiter — per-user sliding window
_buckets: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60):
    now = time.time()
    attempts = _buckets[key]
    attempts[:] = [t for t in attempts if now - t < window_seconds]
    if len(attempts) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
        )
    attempts.append(now)
