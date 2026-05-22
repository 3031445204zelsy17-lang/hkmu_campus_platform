import json
import logging

from pywebpush import webpush, WebPushException

from ..config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS
from ..database import get_db

logger = logging.getLogger(__name__)


def get_vapid_public_key() -> str:
    return VAPID_PUBLIC_KEY


async def save_subscription(user_id: int, subscription: dict) -> int:
    db = await get_db()
    endpoint = subscription["endpoint"]
    p256dh = subscription["keys"]["p256dh"]
    auth = subscription["keys"]["auth"]

    cur = await db.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh_key, auth_key)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            p256dh_key = excluded.p256dh_key,
            auth_key = excluded.auth_key,
            user_id = excluded.user_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, endpoint, p256dh, auth),
    )
    await db.commit()
    return cur.lastrowid


async def remove_subscription(user_id: int, endpoint: str) -> None:
    db = await get_db()
    await db.execute(
        "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
        (user_id, endpoint),
    )
    await db.commit()


async def remove_all_subscriptions(user_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (user_id,))
    await db.commit()


async def send_push_to_user(user_id: int, payload: dict) -> None:
    if not VAPID_PRIVATE_KEY:
        return

    db = await get_db()
    cur = await db.execute(
        "SELECT endpoint, p256dh_key, auth_key FROM push_subscriptions WHERE user_id = ?",
        (user_id,),
    )
    rows = await cur.fetchall()

    if not rows:
        return

    dead_endpoints = []

    for row in rows:
        subscription_info = {
            "endpoint": row["endpoint"],
            "keys": {"p256dh": row["p256dh_key"], "auth": row["auth_key"]},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS,
            )
        except WebPushException as exc:
            if exc.response and exc.response.status_code in (404, 410):
                dead_endpoints.append(row["endpoint"])
            else:
                logger.warning("Push failed for user %s: %s", user_id, exc)
        except Exception as exc:
            logger.warning("Push error for user %s: %s", user_id, exc)

    if dead_endpoints:
        placeholders = ",".join("?" * len(dead_endpoints))
        await db.execute(
            f"DELETE FROM push_subscriptions WHERE endpoint IN ({placeholders})",
            dead_endpoints,
        )
        await db.commit()
