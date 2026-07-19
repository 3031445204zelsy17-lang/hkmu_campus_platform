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
from PIL import Image, ImageOps, UnidentifiedImageError

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

# ── Image pipeline config (Phase 2) ───────────────────────────────
# Per-module longest-side target sizes (small, large). Each upload produces
# one object per size at a versioned path ``{base}@{size}.{ext}`` so the
# client can derive a 2x URL for srcset and pick the right payload for the
# viewport/DPR. Avatars stay small (nav/comment/profile); feed images cap at
# 640 default + 1280 retina.
_MODULE_SIZES = {
    "avatars": (96, 192),
    "posts": (640, 1280),
    "lostfound": (640, 1280),
    "news": (640, 1280),
    "courses": (640, 1280),
}
_DEFAULT_SIZES = (640, 1280)

# Which variant label is returned as the canonical ``url`` (what <img src>
# loads by default). Feed-friendly so the default load is already small; the
# 2x variant is reached via srcset. Avatars default to the larger size so a
# profile header (up to ~96px, 2x = 192) stays sharp without srcset.
_MAIN_LABEL = {"avatars": "192"}
_MAIN_DEFAULT = "640"


# ── Public helpers ────────────────────────────────────────────────

def validate_image(content_type: str, size: int) -> str | None:
    """Return an error string if invalid, or None if OK."""
    if content_type not in ALLOWED_MIME:
        return f"Unsupported file type: {content_type}"
    if size > MAX_FILE_SIZE:
        return f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)"
    return None


async def read_bounded(file) -> bytes:
    """Read an UploadFile, capping memory at ``MAX_FILE_SIZE + 1`` bytes (Codex
    [5][15] — unbounded whole-file read).

    The previous ``await file.read()`` loaded the *entire* upload into memory
    before any size check, so a client could stream gigabytes and OOM the worker
    (the size limit was only enforced after the bytes were already in RAM). Read
    at most ``MAX_FILE_SIZE + 1``; if that much comes back the file is too large
    → raises ValueError (caller maps to 413). Otherwise returns the full
    (validly-sized) file bytes.
    """
    data = await file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        raise ValueError(f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)")
    return data


def _storage_path(
    module: str, user_id: int, content_type: str, filename: str | None = None
) -> str:
    """Build the object key inside the uploads bucket.

    Default: ``{module}/{user_id}/{uuid}.{ext}`` — a fresh object per upload,
    correct for multi-image modules (posts / lostfound / news) where each file
    is a distinct asset. Pass ``filename`` (no extension) to get a STABLE key
    ``{module}/{user_id}/{filename}.{ext}`` so a re-upload overwrites the same
    object instead of orphaning the previous one — used for avatars (Codex
    [20][24]). If ``filename`` already carries an extension it is used as-is.
    """
    ext = _EXT_MAP.get(content_type, ".bin")
    if filename is None:
        name = f"{uuid.uuid4().hex}{ext}"
    elif os.path.splitext(filename)[1]:
        name = filename
    else:
        name = f"{filename}{ext}"
    return f"{module}/{user_id}/{name}"


# ── Image processing (Phase 2) ────────────────────────────────────

def _resize_to_fit(img: Image.Image, max_dim: int) -> Image.Image:
    """Return a copy resized so the longest side == ``max_dim``. Downscale
    only — never enlarge (a 400px image requested at 640 stays 400px; we still
    transcode it to strip metadata + recompress)."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img.copy()
    scale = max_dim / max(w, h)
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def process_image(raw: bytes, content_type: str, module: str):
    """Process an uploaded image into display-sized variants.

    Per target size: apply EXIF orientation (``ImageOps.exif_transpose``),
    resize (downscale only), and recompress. Transcoding inherently strips
    EXIF/GPS/camera metadata (we never pass ``exif=`` to save). Opaque images
    → JPEG ``quality=80, optimize=True``; images with an alpha channel → PNG
    to preserve transparency.

    Returns a list of ``(label, bytes, content_type)`` ordered small → large,
    or ``None`` to signal "keep the original as-is" — used for GIFs (collapsing
    to the first frame would silently break animation) and for anything Pillow
    fails to decode, so image processing can never break an otherwise-valid
    upload (the caller falls back to storing the original bytes).
    """
    if content_type == "image/gif":
        return None
    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # rotate per EXIF, drop orientation tag
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    except Exception:  # never let a Pillow quirk break the upload
        log.warning("image processing failed, keeping original", exc_info=True)
        return None

    has_alpha = (
        img.mode in ("RGBA", "LA")
        or (img.mode == "P" and "transparency" in img.info)
    )
    out_ct = "image/png" if has_alpha else "image/jpeg"

    variants = []
    for size in _MODULE_SIZES.get(module, _DEFAULT_SIZES):
        v = _resize_to_fit(img, size)
        buf = BytesIO()
        if has_alpha:
            if v.mode != "RGBA":
                v = v.convert("RGBA")
            v.save(buf, format="PNG", optimize=True)
        else:
            if v.mode != "RGB":
                v = v.convert("RGB")
            v.save(buf, format="JPEG", quality=80, optimize=True)
        variants.append((str(size), buf.getvalue(), out_ct))
    return variants


async def _upload_blob(storage_path: str, file_bytes: bytes, content_type: str) -> str:
    """PUT one object to Supabase Storage, return its public URL."""
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
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"


async def upload_to_supabase(
    file_bytes: bytes,
    content_type: str,
    module: str,
    user_id: int,
    *,
    filename: str | None = None,
) -> str:
    """Upload *file_bytes* to Supabase Storage and return the public URL.

    Path convention: ``uploads/{module}/{user_id}/{name}.{ext}`` where ``name``
    is a fresh UUID by default, or a stable ``filename`` (avatars) so re-uploads
    overwrite in place instead of accumulating orphaned objects.

    Stores bytes verbatim — no resizing/recompression. Callers that want the
    multi-size image pipeline should use ``upload_image_variants`` instead.
    """
    storage_path = _storage_path(module, user_id, content_type, filename)
    return await _upload_blob(storage_path, file_bytes, content_type)


async def upload_image_variants(
    raw: bytes,
    content_type: str,
    module: str,
    user_id: int,
    *,
    filename: str | None = None,
) -> dict:
    """Process + upload all display variants of an image.

    Returns ``{"url": <main url>, "variants": {label: url}}``. ``url`` is the
    canonical URL to store in DB / hand to ``<img src>``; ``variants`` maps each
    size label to its public URL so a client can build srcset explicitly.

    Falls back to a single verbatim upload (empty ``variants``) for GIFs or
    anything Pillow can't process, preserving the old single-URL contract so
    callers keep working.

    Versioned paths ``{base}@{label}.{ext}`` mean a re-upload with the same
    stable key overwrites the same per-size object (no orphan), and the 2x URL
    is derivable client-side by swapping the label (``@640`` → ``@1280``).
    """
    variants = process_image(raw, content_type, module)
    if not variants:
        url = await upload_to_supabase(raw, content_type, module, user_id, filename=filename)
        return {"url": url, "variants": {}}

    base = _storage_path(module, user_id, content_type, filename)
    root, _ = os.path.splitext(base)

    out = {}
    for label, vbytes, vct in variants:
        ext = ".png" if vct == "image/png" else ".jpg"
        out[label] = await _upload_blob(f"{root}@{label}{ext}", vbytes, vct)

    main_label = _MAIN_LABEL.get(module, _MAIN_DEFAULT)
    main_url = out.get(main_label) or out[max(out, key=int)]
    return {"url": main_url, "variants": out}


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
