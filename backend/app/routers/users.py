import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status

from ..config import FRONTEND_URL
from ..database import get_db
from ..models import UserOut, UserUpdate, BindEmail
from ..services.auth_service import get_current_user, is_hkmu_email
from ..services.email_service import send_verification_email
from ..services.rate_limiter import check_rate_limit
from ..services.sanitizer import sanitize
from .auth import _create_email_token

router = APIRouter(prefix="/users", tags=["users"])


async def _require_admin(user: dict) -> None:
    """Raise 403 if the current user is not an admin."""
    async with get_db() as db:
        row = await db.fetchrow("SELECT identity FROM users WHERE id = $1", user["id"])
    if not row or row["identity"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")

ALLOWED_UPLOAD_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "assets", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_USER_COLS = """id, username, nickname, student_id, avatar_url, bio, identity,
    created_at, email, oauth_provider, programme_code"""


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
    return UserOut(**kw)


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


@router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: dict = Depends(get_current_user),
):
    updates = {}
    if body.nickname is not None:
        updates["nickname"] = sanitize(body.nickname)
    if body.bio is not None:
        updates["bio"] = sanitize(body.bio)
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
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Must be an image file")

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:  # 2MB limit
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image too large (max 2MB)")

    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    if ext.lower() not in ALLOWED_UPLOAD_EXT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File type not allowed")
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    avatar_url = f"/assets/uploads/{filename}"
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


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    async with get_db() as db:
        row = await db.fetchrow(
            f"SELECT {_USER_COLS} FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return _user_out(row)


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
