import re
import secrets
import hashlib
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from ..config import GOOGLE_CLIENT_ID, FRONTEND_URL, ADMIN_USERNAMES
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
from ..services.wechat_service import (
    WechatMiniProgramAuthError,
    WechatMiniProgramConfigError,
    exchange_code_for_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Login lockout (in-memory) ---
_LOCKOUT_MAX = 5
_LOCKOUT_WINDOW = 900  # 15 minutes
_login_fails: dict[str, list[float]] = {}


def _check_lockout(key: str):
    attempts = _login_fails.get(key, [])
    cutoff = time.monotonic() - _LOCKOUT_WINDOW
    attempts = [t for t in attempts if t > cutoff]
    _login_fails[key] = attempts
    if len(attempts) >= _LOCKOUT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
        )


def _record_failure(key: str):
    _login_fails.setdefault(key, []).append(time.monotonic())


def _clear_failures(key: str):
    _login_fails.pop(key, None)


@router.get("/config")
async def auth_config():
    return {"google_client_id": GOOGLE_CLIENT_ID}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister):
    check_rate_limit(f"register:{body.username}", max_requests=5, window_seconds=60)

    async with get_db() as db:
        if await db.fetchval("SELECT id FROM users WHERE username = $1", body.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        if body.student_id:
            if await db.fetchval("SELECT id FROM users WHERE student_id = $1", body.student_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Student ID already registered",
                )

        safe = sanitize_dict(
            {"username": body.username, "nickname": body.nickname, "student_id": body.student_id},
            "username", "nickname", "student_id",
        )

        now = datetime.now(timezone.utc)
        row = await db.fetchrow(
            """INSERT INTO users (username, password_hash, nickname, student_id, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            safe["username"], hash_password(body.password), safe["nickname"], safe["student_id"], now, now,
        )
        user_id = row["id"]

    return UserOut(
        id=user_id,
        username=safe["username"],
        nickname=safe["nickname"],
        student_id=safe["student_id"],
        created_at=now.isoformat(),
        email=None,
        oauth_provider=None,
    )


@router.post("/login", response_model=Token)
async def login(body: UserLogin):
    check_rate_limit(f"login:{body.username}", max_requests=5, window_seconds=60)
    _check_lockout(f"login:{body.username}")

    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT id, username, password_hash, email_verified FROM users WHERE username = $1",
            body.username,
        )

    if not row or not verify_password(body.password, row["password_hash"]):
        _record_failure(f"login:{body.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if not row["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        )

    _clear_failures(f"login:{body.username}")

    # Auto-promote configured admin users on login
    if ADMIN_USERNAMES and body.username in ADMIN_USERNAMES:
        async with get_db() as db:
            await db.execute(
                "UPDATE users SET identity = 'admin' WHERE id = $1 AND identity != 'admin'",
                row["id"],
            )

    token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
    refresh = await create_refresh_token(row["id"])
    return Token(access_token=token, refresh_token=refresh)


@router.get("/me", response_model=UserOut)
async def get_me(user: dict = Depends(get_current_user)):
    async with get_db() as db:
        row = await db.fetchrow(
            """SELECT id, username, nickname, student_id, avatar_url, bio, identity,
                      email, oauth_provider, created_at
               FROM users WHERE id = $1""",
            user["id"],
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return UserOut(
        id=row["id"],
        username=row["username"],
        nickname=row["nickname"],
        student_id=row["student_id"],
        avatar_url=row["avatar_url"],
        bio=row["bio"] or "",
        identity=row["identity"],
        created_at=created_at,
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

    async with get_db() as db:
        # 1. Match by OAuth identity
        row = await db.fetchrow(
            "SELECT id, username FROM users WHERE oauth_provider = 'google' AND oauth_id = $1",
            google_sub,
        )
        if row:
            token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
            refresh = await create_refresh_token(row["id"])
            return Token(access_token=token, refresh_token=refresh)

        # 2. Match by email → link OAuth
        if google_email:
            row = await db.fetchrow("SELECT id, username FROM users WHERE email = $1", google_email)
            if row:
                await db.execute(
                    "UPDATE users SET oauth_provider = 'google', oauth_id = $1 WHERE id = $2",
                    google_sub, row["id"],
                )
                token = create_access_token({"sub": str(row["id"]), "username": row["username"]})
                refresh = await create_refresh_token(row["id"])
                return Token(access_token=token, refresh_token=refresh)

        # 3. Auto-create new user
        base_name = re.sub(r'[^a-zA-Z0-9_]', '', google_email.split("@")[0])[:20] if google_email else "user"
        username = f"{base_name}_{secrets.token_hex(3)}"
        nickname = idinfo.get("name", base_name)[:30]
        now = datetime.now(timezone.utc)

        new_row = await db.fetchrow(
            """INSERT INTO users (username, password_hash, nickname, email, oauth_provider, oauth_id, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'google', $5, $6, $7) RETURNING id""",
            username, OAUTH_NO_PASSWORD, sanitize(nickname), google_email, google_sub, now, now,
        )
        user_id = new_row["id"]

    token = create_access_token({"sub": str(user_id), "username": username})
    refresh = await create_refresh_token(user_id)
    return Token(access_token=token, refresh_token=refresh)


async def _generate_unique_wechat_username(db, openid: str) -> str:
    """Generate a unique 'wx_<openid8>' username. Must be called within the
    caller's `async with get_db() as db:` block — `db` is the live connection."""
    base_name = f"wx_{openid[:8]}"
    username = base_name
    while True:
        if not await db.fetchval("SELECT 1 FROM users WHERE username = $1", username):
            return username
        username = f"{base_name}_{secrets.token_hex(2)}"


# --- WeChat Mini Program ---

@router.post("/wechat/miniprogram", response_model=Token)
async def wechat_miniprogram_login(body: dict, request: Request):
    check_rate_limit(
        f"wechat:{request.client.host if request.client else 'unknown'}",
        max_requests=10, window_seconds=60,
    )

    code = str(body.get("code") or "").strip()
    nickname = str(body.get("nickname") or "").strip()
    avatar_url = str(body.get("avatar_url") or "").strip() or None

    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code")

    try:
        session = await exchange_code_for_session(code)
    except WechatMiniProgramConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except WechatMiniProgramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    safe_nickname = sanitize(nickname)[:30] if nickname else None

    async with get_db() as db:
        # 1. Match by WeChat openid
        row = await db.fetchrow(
            "SELECT id, username FROM users WHERE oauth_provider = 'wechat_miniprogram' AND oauth_id = $1",
            session.openid,
        )

        if row:
            # 2. Update nickname/avatar if provided
            updates = {}
            if safe_nickname:
                updates["nickname"] = safe_nickname
            if avatar_url:
                updates["avatar_url"] = avatar_url
            if updates:
                updates["updated_at"] = datetime.now(timezone.utc)
                set_clause = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(updates.keys()))
                await db.execute(
                    f"UPDATE users SET {set_clause} WHERE id = ${len(updates) + 1}",
                    *list(updates.values()), row["id"],
                )
            user_id = row["id"]
            username = row["username"]
        else:
            # 3. Auto-create new user
            username = await _generate_unique_wechat_username(db, session.openid)
            display_name = safe_nickname or f"微信用户{secrets.randbelow(9000) + 1000}"
            now = datetime.now(timezone.utc)
            new_row = await db.fetchrow(
                """INSERT INTO users (username, password_hash, nickname, avatar_url,
                                      oauth_provider, oauth_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, 'wechat_miniprogram', $5, $6, $7) RETURNING id""",
                username, OAUTH_NO_PASSWORD, display_name, avatar_url,
                session.openid, now, now,
            )
            user_id = new_row["id"]

    token = create_access_token({"sub": str(user_id), "username": username})
    refresh = await create_refresh_token(user_id)
    return Token(access_token=token, refresh_token=refresh)


# --- Email Auth ---

@router.post("/email/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def email_register(body: EmailRegister):
    check_rate_limit(f"register:{body.email}", max_requests=5, window_seconds=60)

    async with get_db() as db:
        if await db.fetchval("SELECT id FROM users WHERE email = $1", body.email):
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

        # Auto-generate username from email prefix
        base_name = re.sub(r'[^a-zA-Z0-9_]', '', body.email.split("@")[0])[:20]
        username = f"{base_name}_{secrets.token_hex(3)}"

        safe_nick = sanitize(body.nickname)
        now = datetime.now(timezone.utc)

        new_row = await db.fetchrow(
            """INSERT INTO users (username, password_hash, nickname, email, student_id, email_verified, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, FALSE, $6, $7) RETURNING id""",
            username, hash_password(body.password), safe_nick, body.email, body.student_id, now, now,
        )
        user_id = new_row["id"]

        # Send verification email (non-blocking — SMTP may not be configured)
        verify_token = await _create_email_token(user_id, "email_verify", ttl_hours=24, conn=db)
        verify_url = f"{FRONTEND_URL}/#/verify-email?token={verify_token}"
        await send_verification_email(body.email, verify_url)

    return UserOut(
        id=user_id,
        username=username,
        nickname=safe_nick,
        student_id=body.student_id,
        created_at=now.isoformat(),
        email=body.email,
        oauth_provider=None,
    )


@router.post("/email/login", response_model=Token)
async def email_login(body: EmailLogin):
    check_rate_limit(f"login:{body.email}", max_requests=5, window_seconds=60)
    _check_lockout(f"login:{body.email}")

    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT id, username, password_hash, email, email_verified FROM users WHERE email = $1",
            body.email,
        )

    if not row:
        _record_failure(f"login:{body.email}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if is_oauth_only(row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account uses Google login. Please sign in with Google.")

    if not verify_password(body.password, row["password_hash"]):
        _record_failure(f"login:{body.email}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not row["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
            headers={"X-User-Email": row["email"]},
        )

    _clear_failures(f"login:{body.email}")
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

    async with get_db() as db:
        row = await db.fetchrow("SELECT username FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    new_access = create_access_token({"sub": str(user_id), "username": row["username"]})
    new_refresh = await rotate_refresh_token(raw, user_id)
    return Token(access_token=new_access, refresh_token=new_refresh)


# --- Password Reset ---

async def _create_email_token(user_id: int, token_type: str, ttl_hours: int, conn=None) -> str:
    raw = secrets.token_hex(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    async def _insert(db):
        await db.execute(
            "INSERT INTO email_tokens (user_id, token_hash, token_type, expires_at) VALUES ($1, $2, $3, $4)",
            user_id, token_hash, token_type, expires,
        )

    if conn:
        await _insert(conn)
    else:
        async with get_db() as db:
            await _insert(db)
    return raw


async def _consume_email_token(raw: str, token_type: str, conn=None) -> int | None:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    async def _do(db):
        async with db.transaction():
            row = await db.fetchrow(
                "SELECT user_id, expires_at FROM email_tokens WHERE token_hash = $1 AND token_type = $2",
                token_hash, token_type,
            )
            if not row:
                return None
            expires = row["expires_at"]
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            await db.execute("DELETE FROM email_tokens WHERE token_hash = $1", token_hash)
            if expires < datetime.now(timezone.utc):
                return None
            return row["user_id"]

    if conn:
        return await _do(conn)
    else:
        async with get_db() as db:
            return await _do(db)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPassword):
    check_rate_limit(f"forgot:{body.email}", max_requests=3, window_seconds=300)

    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT id, username, password_hash FROM users WHERE email = $1", body.email,
        )
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

    async with get_db() as db:
        async with db.transaction():
            user_id = await _consume_email_token(body.token, "password_reset", conn=db)
            if user_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

            await db.execute(
                "UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3",
                hash_password(body.new_password), datetime.now(timezone.utc), user_id,
            )
            # Invalidate all refresh tokens for security
            await db.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)

    return {"message": "Password has been reset successfully."}


# --- Email Verification ---

@router.post("/verify-email")
async def verify_email(body: VerifyEmail):
    async with get_db() as db:
        user_id = await _consume_email_token(body.token, "email_verify", conn=db)
        if user_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification token")

        await db.execute(
            "UPDATE users SET email_verified = TRUE WHERE id = $1", user_id,
        )
    return {"message": "Email verified successfully."}


@router.post("/resend-verification")
async def resend_verification(body: ForgotPassword):
    check_rate_limit(f"resend:{body.email}", max_requests=3, window_seconds=300)

    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT id, email_verified FROM users WHERE email = $1", body.email,
        )
    if not row or row["email_verified"]:
        return {"message": "If that email needs verification, a new link has been sent."}

    token = await _create_email_token(row["id"], "email_verify", ttl_hours=24)
    verify_url = f"{FRONTEND_URL}/#/verify-email?token={token}"
    await send_verification_email(body.email, verify_url)
    return {"message": "If that email needs verification, a new link has been sent."}
