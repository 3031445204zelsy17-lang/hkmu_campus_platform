import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status

from ..database import get_db
from ..models import UserOut, UserUpdate
from ..services.auth_service import get_current_user
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_UPLOAD_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "assets", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_USER_COLS = """id, username, nickname, student_id, avatar_url, bio, identity,
    created_at::TEXT AS created_at, email, oauth_provider"""


def _user_out(row, include_email: bool = True) -> UserOut:
    """Convert an asyncpg Record to UserOut."""
    kw = dict(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=row["created_at"],
    )
    if include_email:
        kw["email"] = row["email"]
        kw["oauth_provider"] = row["oauth_provider"]
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

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
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
    now = datetime.now(timezone.utc).isoformat()

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
