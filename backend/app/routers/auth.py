import time
import re
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from ..config import GOOGLE_CLIENT_ID
from ..database import get_db
from ..models import UserRegister, UserLogin, GoogleLogin, EmailRegister, EmailLogin, Token, UserOut
from ..services.auth_service import (
    hash_password, verify_password, create_access_token, get_current_user,
    OAUTH_NO_PASSWORD, is_oauth_only,
)
from ..services.sanitizer import sanitize_dict, sanitize

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
        email=None,
        oauth_provider=None,
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
        email=row["email"],
        oauth_provider=row["oauth_provider"],
    )


# --- Google OAuth ---

@router.post("/google", response_model=Token)
async def google_login(body: GoogleLogin):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token")

    google_sub = idinfo["sub"]
    google_email = idinfo.get("email", "")

    db = await get_db()

    # 1. Match by OAuth identity
    cur = await db.execute(
        "SELECT id, username FROM users WHERE oauth_provider = 'google' AND oauth_id = ?",
        (google_sub,),
    )
    row = await cur.fetchone()
    if row:
        return Token(access_token=create_access_token({"sub": str(row["id"]), "username": row["username"]}))

    # 2. Match by email → link OAuth
    if google_email:
        cur = await db.execute("SELECT id, username FROM users WHERE email = ?", (google_email,))
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET oauth_provider = 'google', oauth_id = ? WHERE id = ?",
                (google_sub, row["id"]),
            )
            await db.commit()
            return Token(access_token=create_access_token({"sub": str(row["id"]), "username": row["username"]}))

    # 3. Auto-create new user
    base_name = re.sub(r'[^a-zA-Z0-9_]', '', google_email.split("@")[0])[:20] if google_email else "user"
    username = f"{base_name}_{secrets.token_hex(3)}"
    nickname = idinfo.get("name", base_name)[:30]
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO users (username, password_hash, nickname, email, oauth_provider, oauth_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'google', ?, ?, ?)""",
        (username, OAUTH_NO_PASSWORD, sanitize(nickname), google_email, google_sub, now, now),
    )
    await db.commit()
    user_id = cur.lastrowid

    return Token(access_token=create_access_token({"sub": str(user_id), "username": username}))


# --- Email Auth ---

@router.post("/email/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def email_register(body: EmailRegister):
    db = await get_db()

    cur = await db.execute("SELECT id FROM users WHERE email = ?", (body.email,))
    if await cur.fetchone():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    # Auto-generate username from email prefix
    base_name = re.sub(r'[^a-zA-Z0-9_]', '', body.email.split("@")[0])[:20]
    username = f"{base_name}_{secrets.token_hex(3)}"

    safe_nick = sanitize(body.nickname)
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO users (username, password_hash, nickname, email, student_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (username, hash_password(body.password), safe_nick, body.email, body.student_id, now, now),
    )
    await db.commit()

    return UserOut(
        id=cur.lastrowid,
        username=username,
        nickname=safe_nick,
        student_id=body.student_id,
        created_at=now,
        email=body.email,
        oauth_provider=None,
    )


@router.post("/email/login", response_model=Token)
async def email_login(body: EmailLogin):
    db = await get_db()
    cur = await db.execute(
        "SELECT id, username, password_hash FROM users WHERE email = ?",
        (body.email,),
    )
    row = await cur.fetchone()

    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if is_oauth_only(row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account uses Google login. Please sign in with Google.")

    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    return Token(access_token=create_access_token({"sub": str(row["id"]), "username": row["username"]}))
