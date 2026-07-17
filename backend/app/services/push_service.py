import asyncio
import json
import logging
import os
from urllib.parse import urlparse

from pywebpush import webpush, WebPushException

from ..config import (
    VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS,
    PUSH_HTTP_TIMEOUT, MAX_PUSH_SUBS_PER_USER,
)
from ..database import get_db

logger = logging.getLogger(__name__)

# Web Push endpoints are ALWAYS one of a handful of browser-vendor push services
# — the *browser* picks the push service, not the site, so there is no legitimate
# self-hosted endpoint. That makes an hostname allowlist the correct SSRF
# defense: a subscription pointing at localhost / 169.254.169.254 / an internal
# RFC1918 host can never be a real push endpoint. Allowlisting is also stronger
# than IP-based filtering (no DNS resolution step → no DNS-rebinding window and
# no blocking lookup on the hot path). Override the set via env
# PUSH_ENDPOINT_ALLOWLIST (comma-separated hostnames).
_DEFAULT_PUSH_HOSTS = frozenset({
    "fcm.googleapis.com",                  # Chrome / Edge / Android (Firebase Cloud Messaging)
    "android.googleapis.com",              # legacy FCM
    "updates.push.services.mozilla.com",   # Firefox
    "push.services.mozilla.com",           # Firefox (alt)
    "web.push.apple.com",                  # Safari / macOS / iOS 16.4+
})


def _allowed_push_hosts() -> frozenset[str]:
    override = os.getenv("PUSH_ENDPOINT_ALLOWLIST", "").strip()
    if not override:
        return _DEFAULT_PUSH_HOSTS
    return frozenset(h.strip().lower() for h in override.split(",") if h.strip())


def get_vapid_public_key() -> str:
    return VAPID_PUBLIC_KEY


def validate_push_endpoint(endpoint: str) -> None:
    """SSRF guard for Web Push subscription endpoints (Codex [3][7][11][14]).

    A client supplies the ``endpoint`` URL its browser generated; we later POST
    the VAPID-encrypted payload to it. Without validation a malicious client can
    register an internal URL (loopback, the cloud-metadata endpoint, an RFC1918
    service) and the server becomes the SSRF requestor. Reject anything that
    isn't HTTPS on a known browser push-service hostname. Raises ValueError on
    rejection.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        raise ValueError("Push endpoint must use https")
    host = (parsed.hostname or "").lower()
    if not host or host not in _allowed_push_hosts():
        raise ValueError("Unsupported push endpoint")


async def save_subscription(user_id: int, subscription: dict) -> int:
    endpoint = subscription["endpoint"]
    p256dh = subscription["keys"]["p256dh"]
    auth = subscription["keys"]["auth"]

    validate_push_endpoint(endpoint)  # SSRF guard — raises ValueError

    async with get_db() as db:
        async with db.transaction():
            # Per-user cap: bound the send loop so one user can't amplify a
            # single push trigger into thousands of outbound HTTP calls. A
            # re-subscribe of an endpoint this user already owns is an UPDATE
            # (ON CONFLICT), not a new device, so don't count it against the cap.
            count = await db.fetchval(
                "SELECT COUNT(*) FROM push_subscriptions WHERE user_id = $1", user_id
            )
            already_mine = await db.fetchval(
                "SELECT 1 FROM push_subscriptions WHERE endpoint = $1 AND user_id = $2",
                endpoint, user_id,
            )
            if not already_mine and count >= MAX_PUSH_SUBS_PER_USER:
                raise ValueError("Too many push subscriptions for this user")

            row = await db.fetchrow(
                """
                INSERT INTO push_subscriptions (user_id, endpoint, p256dh_key, auth_key)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh_key = excluded.p256dh_key,
                    auth_key = excluded.auth_key,
                    user_id = excluded.user_id,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                user_id, endpoint, p256dh, auth,
            )
    return row["id"]


async def remove_subscription(user_id: int, endpoint: str) -> None:
    async with get_db() as db:
        await db.execute(
            "DELETE FROM push_subscriptions WHERE user_id = $1 AND endpoint = $2",
            user_id, endpoint,
        )


async def remove_all_subscriptions(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "DELETE FROM push_subscriptions WHERE user_id = $1",
            user_id,
        )


async def _send_one(subscription_info: dict, data: str) -> str | None:
    """Send one push off the event loop with a hard timeout.

    pywebpush is synchronous (``requests``-based). Calling it directly in the
    async path blocks the entire event loop for each HTTP POST, and with no
    timeout a slow / malicious endpoint could hang the worker indefinitely
    (Codex [3][7][11][14]). Offload to a worker thread, pass the requests-level
    ``timeout`` to bound the POST, and wrap in ``asyncio.wait_for`` as a hard
    cap. Returns the endpoint when the push service reports it gone (404/410) so
    the caller can prune it; otherwise None.
    """
    endpoint = subscription_info["endpoint"]
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=data,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS,
                timeout=PUSH_HTTP_TIMEOUT,
            ),
            timeout=PUSH_HTTP_TIMEOUT + 2,
        )
    except WebPushException as exc:
        if exc.response is not None and exc.response.status_code in (404, 410):
            return endpoint
        logger.warning("Push failed for %s: %s", endpoint, exc)
    except asyncio.TimeoutError:
        logger.warning("Push timed out for %s", endpoint)
    except Exception as exc:  # noqa: BLE001 — one bad push must never kill the caller
        logger.warning("Push error for %s: %s", endpoint, exc)
    return None


async def send_push_to_user(user_id: int, payload: dict) -> None:
    if not VAPID_PRIVATE_KEY:
        return

    async with get_db() as db:
        rows = await db.fetch(
            "SELECT endpoint, p256dh_key, auth_key FROM push_subscriptions WHERE user_id = $1",
            user_id,
        )

    if not rows:
        return

    data = json.dumps(payload)
    sub_infos = [
        {
            "endpoint": r["endpoint"],
            "keys": {"p256dh": r["p256dh_key"], "auth": r["auth_key"]},
        }
        for r in rows
    ]

    # Send concurrently — bounded by the per-user cap, so one slow endpoint
    # doesn't stall the rest. return_exceptions keeps one failure from
    # cancelling the batch (defense-in-depth; _send_one already swallows all).
    results = await asyncio.gather(
        *[_send_one(s, data) for s in sub_infos], return_exceptions=True
    )

    dead_endpoints = [r for r in results if isinstance(r, str)]
    if dead_endpoints:
        placeholders = ",".join(f"${i+1}" for i in range(len(dead_endpoints)))
        async with get_db() as db:
            await db.execute(
                f"DELETE FROM push_subscriptions WHERE endpoint IN ({placeholders})",
                *dead_endpoints,
            )
