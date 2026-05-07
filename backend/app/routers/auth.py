import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_db
from ..models import UserRegister, UserLogin, Token, UserOut
from ..services.auth_service import (
    hash_password, verify_password, create_access_token, get_current_user,
)
from ..services.sanitizer import sanitize_dict

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-memory rate limiter: {username: [timestamps]}
_login_attempts: dict[str, list[float]] = {}
_RATE_LIMIT = 5  # max attempts
_RATE_WINDOW = 60  # seconds


def _check_rate_limit(username: str):
    now = time.time()
    attempts = _login_attempts.get(username, [])
    attempts = [t for t in attempts if now - t < _RATE_WINDOW]
    _login_attempts[username] = attempts
    if len(attempts) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    attempts.append(now)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister):
    db = await get_db()

    cur = await db.execute("SELECT id FROM users WHERE username = ?", (body.username,))
    if await cur.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    if body.student_id:
        cur = await db.execute("SELECT id FROM users WHERE student_id = ?", (body.student_id,))
        if await cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student ID already registered",
            )

    safe = sanitize_dict(
        {"username": body.username, "nickname": body.nickname, "student_id": body.student_id},
        "username", "nickname", "student_id",
    )

    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        """INSERT INTO users (username, password_hash, nickname, student_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (safe["username"], hash_password(body.password), safe["nickname"], safe["student_id"], now, now),
    )
    await db.commit()

    user_id = cur.lastrowid
    return UserOut(
        id=user_id,
        username=safe["username"],
        nickname=safe["nickname"],
        student_id=safe["student_id"],
        created_at=now,
    )


@router.post("/login", response_model=Token)
async def login(body: UserLogin):
    _check_rate_limit(body.username)

    db = await get_db()
    cur = await db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (body.username,),
    )
    row = await cur.fetchone()

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    row = await cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

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
