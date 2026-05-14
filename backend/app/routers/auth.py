import re
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from ..config import GOOGLE_CLIENT_ID, FRONTEND_URL
from ..database import get_db
from ..models import (
    UserRegister, UserLogin, GoogleLogin, EmailRegister, EmailLogin,
    Token, UserOut, ForgotPassword, ResetPassword, VerifyEmail,
)
from ..services.auth_service import (
    hash_password, verify_password, create_access_token, get_current_user,
    create_refresh_token, verify_refresh_token, rotate_refresh_token,
    OAUTH_NO_PASSWORD, is_oauth_only,
)
from ..services.sanitizer import sanitize_dict, sanitize
from ..services.rate_limiter import check_rate_limit
from ..services.email_service import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
async def auth_config():
    return {"google_client_id": GOOGLE_CLIENT_ID}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister):
    check_rate_limit(f"register:{body.username}", max_requests=5, window_seconds=60)
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
    check_rate_limit(f"login:{body.username}", max_requests=5, window_seconds=60)

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
    refresh = await create_refresh_token(row["id"])
    return Token(access_token=token, refresh_token=refresh)


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
        token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
        refresh = await create_refresh_token(row["id"])
        return Token(access_token=token, refresh_token=refresh)

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
            token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
            refresh = await create_refresh_token(row["id"])
            return Token(access_token=token, refresh_token=refresh)

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

    token = create_access_token({"sub": str(user_id), "username": username})
    refresh = await create_refresh_token(user_id)
    return Token(access_token=token, refresh_token=refresh)


# --- Email Auth ---

@router.post("/email/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def email_register(body: EmailRegister):
    check_rate_limit(f"register:{body.email}", max_requests=5, window_seconds=60)
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
        """INSERT INTO users (username, password_hash, nickname, email, student_id, email_verified, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
        (username, hash_password(body.password), safe_nick, body.email, body.student_id, now, now),
    )
    await db.commit()

    user_id = cur.lastrowid
    # Send verification email (non-blocking — SMTP may not be configured)
    verify_token = await _create_email_token(user_id, "email_verify", ttl_hours=24)
    verify_url = f"{FRONTEND_URL}/#/verify-email?token={verify_token}"
    await send_verification_email(body.email, verify_url)

    return UserOut(
        id=user_id,
        username=username,
        nickname=safe_nick,
        student_id=body.student_id,
        created_at=now,
        email=body.email,
        oauth_provider=None,
    )


@router.post("/email/login", response_model=Token)
async def email_login(body: EmailLogin):
    check_rate_limit(f"login:{body.email}", max_requests=5, window_seconds=60)
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

    token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
    refresh = await create_refresh_token(row["id"])
    return Token(access_token=token, refresh_token=refresh)


# --- Refresh Token ---

@router.post("/refresh", response_model=Token)
async def refresh_access(body: dict):
    raw = body.get("refresh_token", "")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing refresh_token")
    user_id = await verify_refresh_token(raw)
    db = await get_db()
    cur = await db.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    new_access = create_access_token({"sub": str(user_id), "username": row["username"]})
    new_refresh = await rotate_refresh_token(raw, user_id)
    return Token(access_token=new_access, refresh_token=new_refresh)


# --- Password Reset ---

async def _create_email_token(user_id: int, token_type: str, ttl_hours: int) -> str:
    raw = secrets.token_hex(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    db = await get_db()
    await db.execute(
        "INSERT INTO email_tokens (user_id, token_hash, token_type, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, token_hash, token_type, expires.isoformat()),
    )
    await db.commit()
    return raw


async def _consume_email_token(raw: str, token_type: str) -> int | None:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db = await get_db()
    cur = await db.execute(
        "SELECT user_id, expires_at FROM email_tokens WHERE token_hash = ? AND token_type = ?",
        (token_hash, token_type),
    )
    row = await cur.fetchone()
    if not row:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    await db.execute("DELETE FROM email_tokens WHERE token_hash = ?", (token_hash,))
    await db.commit()
    if expires < datetime.now(timezone.utc):
        return None
    return row["user_id"]


@router.post("/forgot-password")
async def forgot_password(body: ForgotPassword):
    check_rate_limit(f"forgot:{body.email}", max_requests=3, window_seconds=300)
    db = await get_db()
    cur = await db.execute(
        "SELECT id, username, password_hash FROM users WHERE email = ?", (body.email,),
    )
    row = await cur.fetchone()
    # Always return success to avoid email enumeration
    if not row or is_oauth_only(row["password_hash"]):
        return {"message": "If that email is registered, a reset link has been sent."}

    token = await _create_email_token(row["id"], "password_reset", ttl_hours=1)
    reset_url = f"{FRONTEND_URL}/#/reset-password?token={token}"
    await send_password_reset_email(body.email, reset_url)
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(body: ResetPassword):
    check_rate_limit("reset-password", max_requests=5, window_seconds=60)
    user_id = await _consume_email_token(body.token, "password_reset")
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    db = await get_db()
    await db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(body.new_password), datetime.now(timezone.utc).isoformat(), user_id),
    )
    await db.commit()
    # Invalidate all refresh tokens for security
    await db.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
    await db.commit()
    return {"message": "Password has been reset successfully."}


# --- Email Verification ---

@router.post("/verify-email")
async def verify_email(body: VerifyEmail):
    user_id = await _consume_email_token(body.token, "email_verify")
    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

    db = await get_db()
    await db.execute(
        "UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,),
    )
    await db.commit()
    return {"message": "Email verified successfully."}


@router.post("/resend-verification")
async def resend_verification(body: ForgotPassword):
    check_rate_limit(f"resend:{body.email}", max_requests=3, window_seconds=300)
    db = await get_db()
    cur = await db.execute(
        "SELECT id, email_verified FROM users WHERE email = ?", (body.email,),
    )
    row = await cur.fetchone()
    if not row or row["email_verified"]:
        return {"message": "If that email needs verification, a new link has been sent."}

    token = await _create_email_token(row["id"], "email_verify", ttl_hours=24)
    verify_url = f"{FRONTEND_URL}/#/verify-email?token={token}"
    await send_verification_email(body.email, verify_url)
    return {"message": "If that email needs verification, a new link has been sent."}
