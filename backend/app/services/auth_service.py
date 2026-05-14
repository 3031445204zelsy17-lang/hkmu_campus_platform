import hashlib
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
    db = await get_db()
    cur = await db.execute("SELECT id, username FROM users WHERE id = ?", (uid,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id": row["id"], "username": row["username"]}


async def create_refresh_token(user_id: int) -> str:
    import secrets as _secrets
    raw = _secrets.token_hex(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    db = await get_db()
    await db.execute(
        "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, token_hash, expires.isoformat()),
    )
    await db.commit()
    return raw


async def verify_refresh_token(raw: str) -> int:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db = await get_db()
    cur = await db.execute(
        "SELECT user_id, expires_at FROM refresh_tokens WHERE token_hash = ?",
        (token_hash,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    expires = datetime.fromisoformat(row["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        await db.execute("DELETE FROM refresh_tokens WHERE token_hash = ?", (token_hash,))
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    return row["user_id"]


async def rotate_refresh_token(raw: str, user_id: int) -> str:
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db = await get_db()
    await db.execute("DELETE FROM refresh_tokens WHERE token_hash = ?", (token_hash,))
    await db.commit()
    return await create_refresh_token(user_id)
