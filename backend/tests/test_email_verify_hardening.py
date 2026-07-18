"""Codex low-sweep identity hardening: [19] authoritative student_id from a
verified HKMU email, [22] email-token snapshot binding.

Emails are generated fresh per run (the campus DB persists across runs and
users.email has a unique index), but kept in the derivable s<7-digits> format.
"""
import uuid

from backend.app.database import get_db
from backend.app.routers.auth import _create_email_token


def _student_email():
    """A unique derivable HKMU student email + the student_id it derives to."""
    n = 1000000 + (uuid.uuid4().int % 9000000)  # 7 digits, no leading zero
    return f"s{n}@live.hkmu.edu.hk", str(n)


async def _seed_user(email, student_id=None, verified=False):
    async with get_db() as db:
        return await db.fetchval(
            "INSERT INTO users (username, password_hash, nickname, email, student_id, email_verified) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            f"u_{uuid.uuid4().hex[:6]}", "x", "nick", email, student_id, verified,
        )


# --- [19] student_id derived authoritatively from verified HKMU email ---

async def test_verify_overrides_forged_student_id(client):
    """Verifying an HKMU student email sets student_id from the email,
    overriding a user-supplied forged value."""
    email, expected_sid = _student_email()
    forged = f"F{uuid.uuid4().hex[:8]}"  # unique (student_id has a UNIQUE idx)
    uid = await _seed_user(email, student_id=forged, verified=False)
    async with get_db() as db:
        token = await _create_email_token(uid, "email_verify", 24, conn=db, email=email)

    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text

    async with get_db() as db:
        sid = await db.fetchval("SELECT student_id FROM users WHERE id=$1", uid)
        hkmu = await db.fetchval("SELECT hkmu_verified FROM users WHERE id=$1", uid)
    assert sid == expected_sid  # derived from the email, not the forged value
    assert hkmu is True


async def test_verify_keeps_student_id_when_not_derivable(client):
    """A non-derivable HKMU email (staff @hkmu.edu.hk) keeps any existing
    student_id instead of wiping it to NULL."""
    email = f"admin{uuid.uuid4().hex[:6]}@hkmu.edu.hk"
    keeper = f"K{uuid.uuid4().hex[:8]}"  # unique (student_id has a UNIQUE idx)
    uid = await _seed_user(email, student_id=keeper, verified=False)
    async with get_db() as db:
        token = await _create_email_token(uid, "email_verify", 24, conn=db, email=email)

    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text

    async with get_db() as db:
        sid = await db.fetchval("SELECT student_id FROM users WHERE id=$1", uid)
    assert sid == keeper  # not nulled


# --- [22] email-token snapshot binding ---

async def test_verify_rejects_snapshot_mismatch(client):
    """A token snapshotted to email A is rejected once the user's current email
    is B (a later bind superseded it) — the stale token can't verify."""
    email_a, _ = _student_email()
    email_b, _ = _student_email()
    uid = await _seed_user(email_b, verified=False)  # current email is B
    async with get_db() as db:
        token_a = await _create_email_token(uid, "email_verify", 24, conn=db, email=email_a)

    r = await client.post("/api/v1/auth/verify-email", json={"token": token_a})
    assert r.status_code == 400  # snapshot mismatch


async def test_verify_snapshot_match_succeeds(client):
    """Sanity: when the snapshot matches the current email, verify succeeds."""
    email, _ = _student_email()
    uid = await _seed_user(email, verified=False)
    async with get_db() as db:
        token = await _create_email_token(uid, "email_verify", 24, conn=db, email=email)

    r = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
