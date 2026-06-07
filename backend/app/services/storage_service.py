"""
Generic image upload service backed by Supabase Storage.

Upload flow:
  1. Client sends multipart/form-data to POST /api/v1/upload
  2. Backend validates file (type + size), generates unique path
  3. File is uploaded to Supabase Storage bucket via REST API
  4. Public URL is returned to the client

Other modules (lostfound, posts, avatars, …) simply pass the returned URL
when creating / updating their own records.
"""

import os
import uuid
import logging
from io import BytesIO

import httpx

from ..config import SUPABASE_URL, SUPABASE_SERVICE_KEY

log = logging.getLogger("storage")

# ── Config ────────────────────────────────────────────────────────

BUCKET = "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Extension map for generating file names
_EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


# ── Public helpers ────────────────────────────────────────────────

def validate_image(content_type: str, size: int) -> str | None:
    """Return an error string if invalid, or None if OK."""
    if content_type not in ALLOWED_MIME:
        return f"Unsupported file type: {content_type}"
    if size > MAX_FILE_SIZE:
        return f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)"
    return None


async def upload_to_supabase(
    file_bytes: bytes,
    content_type: str,
    module: str,
    user_id: int,
) -> str:
    """Upload *file_bytes* to Supabase Storage and return the public URL.

    Path convention: ``uploads/{module}/{user_id}/{uuid}.{ext}``
    """
    ext = _EXT_MAP.get(content_type, ".bin")
    filename = f"{uuid.uuid4().hex}{ext}"
    storage_path = f"{module}/{user_id}/{filename}"

    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            content=file_bytes,
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "apikey": SUPABASE_SERVICE_KEY,
                "Content-Type": content_type,
            },
        )

    if resp.status_code not in (200, 201):
        log.error("Supabase upload failed: %s %s", resp.status_code, resp.text)
        raise RuntimeError(f"Upload failed: {resp.status_code}")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"
    return public_url


async def delete_from_supabase(public_url: str) -> bool:
    """Best-effort delete. Returns True on success."""
    try:
        # Extract path after bucket name
        prefix = f"/storage/v1/object/public/{BUCKET}/"
        idx = public_url.find(prefix)
        if idx == -1:
            return False
        storage_path = public_url[idx + len(prefix):]

        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                url,
                headers={
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "apikey": SUPABASE_SERVICE_KEY,
                },
            )
        return resp.status_code in (200, 204)
    except Exception:
        log.warning("Failed to delete storage object", exc_info=True)
        return False
