"""[3][7][11][14] Web Push SSRF / DoS regression.

Two attack surfaces on the push path:

1. SSRF — ``/push/subscribe`` accepted any ``endpoint`` URL and stored it; the
   server then POSTed the VAPID payload to it, so a client could point the
   server at an internal target (loopback, 169.254.169.254, RFC1918). Now
   ``validate_push_endpoint`` rejects anything that isn't HTTPS on a known
   browser push-service hostname.
2. Amplification / blocking — no per-user subscription cap (one trigger → N
   outbound calls) and a synchronous, timeout-less ``webpush`` call in the async
   path. Now capped at MAX_PUSH_SUBS_PER_USER and sent off-thread with a hard
   timeout.

The SSRF allowlist and the cap are unit-tested directly and at the HTTP
boundary; the async/timeout send is structural (no live push service in CI).
"""
import uuid

import pytest

from backend.app.config import MAX_PUSH_SUBS_PER_USER
from backend.app.services.push_service import (
    send_push_to_user, validate_push_endpoint,
)


# --- validate_push_endpoint (SSRF guard), pure function ---

async def test_validate_accepts_known_push_providers():
    for ep in [
        "https://fcm.googleapis.com/fcm/connect/abc",
        "https://android.googleapis.com/wp/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/x",
        "https://push.services.mozilla.com/x",
        "https://web.push.apple.com/Q/abc",
    ]:
        validate_push_endpoint(ep)  # must not raise


async def test_validate_rejects_ssrf_targets():
    bad = [
        "http://fcm.googleapis.com/x",                # not https
        "https://localhost:8080/secret",              # loopback hostname
        "https://127.0.0.1:9000/",                    # loopback IP literal
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://10.0.0.5/admin",                     # RFC1918 private
        "https://192.168.1.1/",                       # RFC1918 private
        "https://internal.corp.local/x",              # non-allowlisted host
        "https://evil.example.com/fcm",               # lookalike, not allowlisted
        "not-even-a-url",
        "",
    ]
    for ep in bad:
        with pytest.raises(ValueError):
            validate_push_endpoint(ep)


# --- /push/subscribe SSRF boundary (needs DB) ---

async def test_subscribe_rejects_ssrf_endpoint(client, make_user):
    """An internal/lookalike endpoint is rejected at the HTTP boundary."""
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}
    for bad_ep in [
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost:9000/probe",
        "https://evil.example.com/lookalike",
        "http://fcm.googleapis.com/x",  # right host, wrong scheme
    ]:
        r = await client.post(
            "/api/v1/push/subscribe",
            headers=headers,
            json={"subscription": {
                "endpoint": bad_ep, "keys": {"p256dh": "p", "auth": "a"},
            }},
        )
        assert r.status_code == 400, (bad_ep, r.text)


async def test_subscribe_accepts_real_provider(client, make_user):
    """A legitimate FCM endpoint is stored (201)."""
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/push/subscribe",
        headers={"Authorization": f"Bearer {token}"},
        json={"subscription": {
            "endpoint": "https://fcm.googleapis.com/fcm/connect/real",
            "keys": {"p256dh": "p256dh-val", "auth": "auth-val"},
        }},
    )
    assert r.status_code == 201, r.text


# --- per-user cap (amplification bound, needs DB) ---

async def test_subscribe_cap_rejects_excess(client, make_user):
    """At MAX subs, a new distinct endpoint is rejected (400 Too many)."""
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(MAX_PUSH_SUBS_PER_USER):
        r = await client.post(
            "/api/v1/push/subscribe",
            headers=headers,
            json={"subscription": {
                "endpoint": f"https://fcm.googleapis.com/fcm/c/{i}",
                "keys": {"p256dh": "p", "auth": "a"},
            }},
        )
        assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/push/subscribe",
        headers=headers,
        json={"subscription": {
            "endpoint": "https://fcm.googleapis.com/fcm/c/overflow",
            "keys": {"p256dh": "p", "auth": "a"},
        }},
    )
    assert r.status_code == 400
    assert "Too many" in r.text


async def test_resubscribe_same_endpoint_not_counted_against_cap(client, make_user):
    """Re-subscribing an endpoint the user already owns is an UPDATE, not a new
    device — must stay 201 even when the user is at the cap (browser refreshes
    keys for the same endpoint)."""
    _, token = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(MAX_PUSH_SUBS_PER_USER):
        await client.post(
            "/api/v1/push/subscribe",
            headers=headers,
            json={"subscription": {
                "endpoint": f"https://fcm.googleapis.com/fcm/r/{i}",
                "keys": {"p256dh": "p", "auth": "a"},
            }},
        )
    # re-subscribe endpoint 0 (already mine) with refreshed keys → still 201
    r = await client.post(
        "/api/v1/push/subscribe",
        headers=headers,
        json={"subscription": {
            "endpoint": "https://fcm.googleapis.com/fcm/r/0",
            "keys": {"p256dh": "p-new", "auth": "a-new"},
        }},
    )
    assert r.status_code == 201, r.text


# --- send_push early-return (no VAPID / no subs), structural ---

async def test_send_push_without_vapid_is_noop():
    """VAPID_PRIVATE_KEY is empty in the test env → returns before any DB work."""
    await send_push_to_user(1, {"type": "message"})  # must not raise
