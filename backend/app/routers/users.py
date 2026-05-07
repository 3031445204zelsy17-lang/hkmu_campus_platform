import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status

from ..database import get_db
from ..models import UserOut, UserUpdate
from ..services.auth_service import get_current_user
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/users", tags=["users"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "assets", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return UserOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=row["created_at"],
    )


@router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: dict = Depends(get_current_user),
):
    db = await get_db()

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
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await db.execute(
        f"UPDATE users SET {set_clause} WHERE id = ?",
        list(updates.values()) + [user["id"]],
    )
    await db.commit()

    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    row = await cur.fetchone()
    return UserOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=row["created_at"],
    )


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
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    avatar_url = f"/assets/uploads/{filename}"
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    await db.execute(
        "UPDATE users SET avatar_url = ?, updated_at = ? WHERE id = ?",
        (avatar_url, now, user["id"]),
    )
    await db.commit()

    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    row = await cur.fetchone()
    return UserOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=row["created_at"],
    )


@router.get("/search", response_model=list[UserOut])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM users WHERE (username LIKE ? OR nickname LIKE ?) AND id != ? LIMIT 20",
        (f"%{q}%", f"%{q}%", user["id"]),
    )
    rows = await cur.fetchall()
    return [
        UserOut(
            id=r["id"],
            username=r["username"],
            nickname=r["nickname"],
            student_id=r["student_id"],
            avatar_url=r["avatar_url"],
            bio=r["bio"] or "",
            identity=r["identity"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return UserOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=row["created_at"],
    )
