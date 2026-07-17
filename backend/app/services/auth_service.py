import hashlib
import time
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from ..config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from ..database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

OAUTH_NO_PASSWORD = "!oauth_no_password"


def is_oauth_only(password_hash: str) -> bool:
    return password_hash == OAUTH_NO_PASSWORD


def is_hkmu_email(email: str) -> bool:
    """HKMU faculty (@hkmu.edu.hk) or student (@live.hkmu.edu.hk) email."""
    if not email:
        return False
    lowered = email.lower()
    return lowered.endswith("@hkmu.edu.hk") or lowered.endswith("@live.hkmu.edu.hk")


def derive_student_id(email: str) -> str | None:
    """HKMU student email s1234567@live.hkmu.edu.hk -> student_id 1234567 (strip leading s)."""
    if not email:
        return None
    local = email.split("@")[0]
    if len(local) >= 2 and local[0].lower() == "s" and local[1:].isdigit():
        return local[1:]
    return None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    uid = int(user_id)
    async with get_db() as db:
        row = await db.fetchrow("SELECT id, username FROM users WHERE id = $1", uid)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id": row["id"], "username": row["username"]}


async def create_refresh_token(user_id: int, conn=None) -> str:
    import secrets as _secrets
    raw = _secrets.token_hex(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    async def _insert(db):
        await db.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
            user_id, token_hash, expires,
        )

    if conn:
        await _insert(conn)
    else:
        async with get_db() as db:
            await _insert(db)
    return raw


def access_token_expired(exp) -> bool:
    """True when a JWT ``exp`` claim (epoch seconds, as set by
    ``create_access_token``) is in the past.

    The WebSocket receive loop ([2]) uses this to tear down long-lived sockets
    whose access token has expired mid-connection: a socket opened at login can
    stay open for hours, but the access token inside it expires in
    ``ACCESS_TOKEN_EXPIRE_MINUTES``. Without this re-check the socket keeps
    accepting chat/mark_read frames after expiry. Access tokens are stateless
    JWTs with no revocation list, so re-checking the already-verified ``exp`` on
    each inbound frame is sufficient. A missing / non-numeric ``exp`` is treated
    as "not expired" (matches jose, which only enforces ``exp`` when present).
    """
    return isinstance(exp, (int, float)) and time.time() >= exp


async def rotate_refresh_token(raw: str) -> tuple[int, str] | None:
    """Atomically rotate a refresh token.

    DELETE...RETURNING + expiry check + mint successor, all in one transaction.
    This replaces the old verify-then-rotate flow (a SELECT in
    ``verify_refresh_token`` followed by a separate DELETE here) which had a
    TOCTOU window: two concurrent ``/auth/refresh`` calls with the *same*
    refresh token both passed verification and both rotated, so a stolen token
    stayed usable after the legitimate client had already rotated it.

    Making verification and invalidation a single atomic step closes that
    window — the row is deleted the instant it is read, so a racing caller
    finds nothing to RETURN and fails. Returns ``(user_id, new_raw_token)`` on
    success, or ``None`` if the token is invalid, already used, or expired.
    """
    if not raw:
        return None
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        async with db.transaction():
            row = await db.fetchrow(
                "DELETE FROM refresh_tokens WHERE token_hash = $1 "
                "RETURNING user_id, expires_at",
                token_hash,
            )
            if not row:
                return None
            expires = row["expires_at"]
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                return None
            new_raw = await create_refresh_token(row["user_id"], conn=db)
            return row["user_id"], new_raw


async def revoke_refresh_token(raw: str) -> bool:
    """Delete the refresh-token row matching ``raw``.

    Idempotent — returns True if a row was deleted, False if the token was
    already absent (or empty). Mirrors the hash + DELETE pattern used by
    ``verify_refresh_token`` / ``rotate_refresh_token``; no blacklist needed
    since refresh tokens are DB rows, not stateless JWTs.
    """
    if not raw:
        return False
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    async with get_db() as db:
        row = await db.fetchrow(
            "DELETE FROM refresh_tokens WHERE token_hash = $1 RETURNING user_id",
            token_hash,
        )
    return row is not None
