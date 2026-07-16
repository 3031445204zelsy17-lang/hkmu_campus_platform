import secrets
import string
from datetime import datetime, timezone

import httpx
from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status

from ..config import FRONTEND_URL
from ..database import get_db
from ..models import (
    UserOut, UserUpdate, BindEmail,
    SuggestOut, InviteCodeOut, FriendshipOut, InviteAccept,
    UserPublicOut,
)
from ..services.auth_service import get_current_user, is_hkmu_email
from ..services.email_service import send_verification_email
from ..services.rate_limiter import check_rate_limit
from ..services.storage_service import validate_image, upload_to_supabase
from .auth import _create_email_token

router = APIRouter(prefix="/users", tags=["users"])


async def _require_admin(user: dict) -> None:
    """Raise 403 if the current user is not an admin."""
    async with get_db() as db:
        row = await db.fetchrow("SELECT identity FROM users WHERE id = $1", user["id"])
    if not row or row["identity"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")


_USER_COLS = """id, username, nickname, student_id, avatar_url, bio, identity,
    created_at, email, oauth_provider, programme_code, hkmu_verified, invite_code"""


def _user_out(row, include_email: bool = True) -> UserOut:
    """Convert an asyncpg Record to UserOut."""
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    kw = dict(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=created_at,
    )
    if include_email:
        kw["email"] = row["email"]
        kw["oauth_provider"] = row["oauth_provider"]
    kw["programme_code"] = row.get("programme_code")
    kw["hkmu_verified"] = row.get("hkmu_verified", False)
    # NOTE: invite_code is intentionally NOT emitted here. It is only exposed
    # via the dedicated /users/me/invite-code endpoint (self only). Returning
    # another user's invite_code enabled a force-friend vector
    # (/users/me/friends redeems any code → bidirectional friendship w/o consent).
    return UserOut(**kw)


def _user_public_out(row) -> UserPublicOut:
    """Public-safe view of ANOTHER user — no email / oauth / student_id /
    programme_code / hkmu_verified / invite_code."""
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return UserPublicOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=created_at,
    )


@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    async with get_db() as db:
        row = await db.fetchrow(
            f"SELECT {_USER_COLS} FROM users WHERE id = $1",
            user["id"],
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return _user_out(row)


@router.post("/me/bind-email")
async def bind_email(body: BindEmail, user: dict = Depends(get_current_user)):
    """Phase 5 P0: bind an HKMU email to an existing account (e.g. OAuth-only user) to unlock the hkmu_verified tier.

    Method C (reuse register's write-email-then-verify pattern, no schema change):
    v1 only allows bind when current email is unverified or empty (avoid clobbering a verified email);
    writes the new email with email_verified=FALSE, sends verification, and the verify-email endpoint
    unlocks hkmu_verified + backfills student_id on confirm. Re-binding a verified email is a v2 concern
    (would need email_tokens.email column, method A).
    """
    check_rate_limit(f"bind-email:{user['id']}", max_requests=3, window_seconds=300)
    if not is_hkmu_email(body.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only HKMU email is allowed")
    async with get_db() as db:
        current = await db.fetchrow(
            "SELECT email, email_verified FROM users WHERE id = $1", user["id"],
        )
        if not current:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        if current["email_verified"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already verified")
        # new email must not belong to another user
        owner = await db.fetchval(
            "SELECT id FROM users WHERE email = $1 AND id <> $2", body.email, user["id"],
        )
        if owner is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")
        now = datetime.now(timezone.utc)
        await db.execute(
            "UPDATE users SET email = $1, email_verified = FALSE, updated_at = $2 WHERE id = $3",
            body.email, now, user["id"],
        )
        token = await _create_email_token(user["id"], "email_verify", ttl_hours=24, conn=db)
        verify_url = f"{FRONTEND_URL}/#/verify-email?token={token}"
    await send_verification_email(body.email, verify_url)
    return {"message": "Verification email sent"}


# ── Phase 5: invite / suggest / friendships ──────────────────────────────────

_INVITE_CODE_LEN = 8
_INVITE_ALPHABET = string.ascii_letters + string.digits  # base62


async def _ensure_invite_code(conn, user_id: int) -> str:
    """Lazily mint a unique invite_code (concurrency-safe via the partial unique index)."""
    existing = await conn.fetchval("SELECT invite_code FROM users WHERE id = $1", user_id)
    if existing:
        return existing
    for _ in range(5):
        code = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(_INVITE_CODE_LEN))
        try:
            result = await conn.execute(
                "UPDATE users SET invite_code = $1, updated_at = $2 "
                "WHERE id = $3 AND invite_code IS NULL",
                code, datetime.now(timezone.utc), user_id,
            )
            if result.endswith("1"):
                return code
        except UniqueViolationError:
            continue  # code collision (62^8 ≈ 2e14, astronomically rare) — try another
        # 0 rows updated — a concurrent request likely just minted one
        existing = await conn.fetchval("SELECT invite_code FROM users WHERE id = $1", user_id)
        if existing:
            return existing
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to generate invite code")


@router.get("/me/invite-code", response_model=InviteCodeOut)
async def get_my_invite_code(user: dict = Depends(get_current_user)):
    """P1: lazily mint the current user's invite code + mini-program share path."""
    async with get_db() as db:
        code = await _ensure_invite_code(db, user["id"])
    return InviteCodeOut(invite_code=code, share_path=f"/pages/home/home?inv={code}")


@router.get("/suggest", response_model=list[SuggestOut])
async def suggest_users(
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """P0: recommend HKMU-verified peers (same programme first), excluding friends and prior DM partners.

    `reason` is an i18n signal for the frontend ("same_programme" | "hkmu_peer"), not display copy.
    """
    me = user["id"]
    async with get_db() as db:
        rows = await db.fetch(
            f"""
            SELECT {_USER_COLS},
                   (programme_code = (SELECT programme_code FROM users WHERE id = $1)) AS same_programme
            FROM users
            WHERE hkmu_verified = TRUE
              AND id <> $1
              AND id NOT IN (SELECT friend_id FROM friendships WHERE user_id = $1)
              AND id NOT IN (
                  SELECT receiver_id FROM messages WHERE sender_id = $1
                  UNION
                  SELECT sender_id FROM messages WHERE receiver_id = $1
              )
            ORDER BY same_programme DESC, id
            LIMIT $2
            """,
            me, limit,
        )
        results = []
        for r in rows:
            base = _user_out(r, include_email=False).model_dump()
            base["reason"] = "same_programme" if r["same_programme"] else "hkmu_peer"
            results.append(SuggestOut(**base))
        return results


@router.get("/me/friends", response_model=list[FriendshipOut])
async def list_my_friends(user: dict = Depends(get_current_user)):
    """Accepted friendships (bidirectional storage — query only WHERE user_id = me)."""
    async with get_db() as db:
        frows = await db.fetch(
            "SELECT id, friend_id, source, created_at FROM friendships "
            "WHERE user_id = $1 AND status = 'accepted' ORDER BY created_at DESC",
            user["id"],
        )
        if not frows:
            return []
        friend_ids = [r["friend_id"] for r in frows]
        urows = await db.fetch(
            f"SELECT {_USER_COLS} FROM users WHERE id = ANY($1::int[])",
            friend_ids,
        )
        user_map = {r["id"]: _user_out(r, include_email=False) for r in urows}
        results = []
        for fr in frows:
            friend = user_map.get(fr["friend_id"])
            if not friend:
                continue
            created = fr["created_at"]
            if isinstance(created, datetime):
                created = created.isoformat()
            results.append(FriendshipOut(
                id=fr["id"], friend=friend, source=fr["source"], created_at=created,
            ))
        return results


@router.post("/me/friends")
async def add_friend_by_invite(body: InviteAccept, user: dict = Depends(get_current_user)):
    """P1: redeem an invite code — auto-bidirectional friend (ON CONFLICT idempotent); self-invite is a no-op."""
    code = body.invite_code.strip()
    async with get_db() as db:
        async with db.transaction():
            inviter = await db.fetchrow(
                f"SELECT {_USER_COLS} FROM users WHERE invite_code = $1", code,
            )
            if not inviter:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite code")
            inviter_id = inviter["id"]
            if inviter_id == user["id"]:
                # self-invite: no-op (also guarded client-side)
                return {"friend": _user_out(inviter).model_dump(), "created": False}
            result = await db.execute(
                "INSERT INTO friendships (user_id, friend_id, status, source) "
                "VALUES ($1, $2, 'accepted', 'invite'), ($2, $1, 'accepted', 'invite') "
                "ON CONFLICT (user_id, friend_id) DO NOTHING",
                user["id"], inviter_id,
            )
            created = not result.endswith("0")
            return {"friend": _user_out(inviter).model_dump(), "created": created}


@router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: dict = Depends(get_current_user),
):
    updates = {}
    if body.nickname is not None:
        updates["nickname"] = body.nickname
    if body.bio is not None:
        updates["bio"] = body.bio
    if body.avatar_url is not None:
        updates["avatar_url"] = body.avatar_url
    if body.programme_code is not None:
        updates["programme_code"] = body.programme_code

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc)
    set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(updates.keys()))
    where_n = len(updates) + 1

    async with get_db() as db:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE id = ${where_n}",
            *list(updates.values()), user["id"],
        )
        row = await db.fetchrow(
            f"SELECT {_USER_COLS} FROM users WHERE id = $1",
            user["id"],
        )
        return _user_out(row)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    # Upload to Supabase Storage (mirrors POST /api/v1/upload?module=avatars).
    # Previously wrote to the container-local frontend/assets/uploads dir, which
    # was lost on every redeploy/restart.
    raw = await file.read()
    content_type = file.content_type or "application/octet-stream"

    err = validate_image(content_type, len(raw))
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)

    try:
        avatar_url = await upload_to_supabase(raw, content_type, "avatars", user["id"])
    except (RuntimeError, httpx.HTTPError):
        # RuntimeError = Supabase returned non-2xx; httpx.HTTPError = network/timeout/transport
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Avatar upload failed, please retry")

    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET avatar_url = $1, updated_at = $2 WHERE id = $3",
            avatar_url, now, user["id"],
        )
        row = await db.fetchrow(
            f"SELECT {_USER_COLS} FROM users WHERE id = $1",
            user["id"],
        )
        return _user_out(row)


@router.get("/search", response_model=list[UserOut])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        rows = await db.fetch(
            f"SELECT {_USER_COLS} FROM users WHERE (username LIKE $1 OR nickname LIKE $2) AND id != $3 LIMIT 20",
            f"%{q}%", f"%{q}%", user["id"],
        )
        return [_user_out(r, include_email=False) for r in rows]


@router.get("/{user_id}", response_model=UserPublicOut)
async def get_user(user_id: int, user: dict = Depends(get_current_user)):
    """View another user's public profile. Requires login; returns only
    public-safe fields (no email / student_id / invite_code / ...)."""
    async with get_db() as db:
        row = await db.fetchrow(
            f"SELECT {_USER_COLS} FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return _user_public_out(row)


# ── Admin endpoints ─────────────────────────────────────────────────────────


@router.get("/admin/list", response_model=list[UserOut])
async def list_all_users(
    user: dict = Depends(get_current_user),
):
    """List all users (admin only)."""
    await _require_admin(user)
    async with get_db() as db:
        rows = await db.fetch(f"SELECT {_USER_COLS} FROM users ORDER BY id")
        return [_user_out(r) for r in rows]


@router.put("/admin/{user_id}/role")
async def set_user_role(
    user_id: int,
    role: str = Query(..., pattern=r"^(admin|student)$"),
    user: dict = Depends(get_current_user),
):
    """Promote or demote a user (admin only)."""
    await _require_admin(user)
    async with get_db() as db:
        result = await db.execute(
            "UPDATE users SET identity = $1 WHERE id = $2",
            role, user_id,
        )
        if result.endswith("0"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"message": f"User {user_id} role set to {role}"}
