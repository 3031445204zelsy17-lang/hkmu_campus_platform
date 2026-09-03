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
import hashlib
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
    # comment images render inline and small — tighter caps than feed images
    # keep the Supabase free-tier storage budget sustainable
    "comments": (360, 640),
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
_MAIN_LABEL = {"avatars": "192", "comments": "360"}
_MAIN_DEFAULT = "640"

# Pipeline version embedded in avatar paths so a processing change (resize /
# quality / format) rotates to a new path segment (v1 → v2) instead of serving
# stale bytes at the same URL. Combined with a content hash, an avatar URL is
# fully immutable: same URL → same bytes, forever.
_PIPELINE_VERSION = "v1"

# Long cache (1 year) for IMMUTABLE-URL uploads only — uuid-keyed feed images
# (posts/lostfound/news) and versioned-hash avatars. MUST co-apply with an
# immutable path: never set long cache on an overwritable stable path, or a
# re-upload would serve stale bytes from the CDN. Empirically verified:
# multipart upload with this cacheControl makes the public URL GET return
# `public, max-age=31536000` + cf-cache HIT (HEAD ignores cacheControl, but
# image display uses GET). See memory cachecontrol-supabase-controllable.
_IMMUTABLE_CACHE = "31536000"


def _content_hash(b: bytes) -> str:
    """Short content-addressed hash (sha256[:16]) for immutable avatar paths."""
    return hashlib.sha256(b).hexdigest()[:16]


# ── Public helpers ────────────────────────────────────────────────

def validate_image(content_type: str, size: int) -> str | None:
    """Return an error string if invalid, or None if OK."""
    if content_type not in ALLOWED_MIME:
        return f"Unsupported file type: {content_type}"
    if size > MAX_FILE_SIZE:
        return f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)"
    return None


def is_module_image_url(url: str | None) -> bool:
    """True iff ``url`` points inside our own uploads bucket.

    The ONLY way to create such URLs is POST /upload, which runs the
    img_sec_check gate before storing — so accepting bucket URLs exclusively
    (comment image_url etc.) keeps moderation the single attachment path and
    blocks foreign/arbitrary image URLs that were never scanned.
    """
    return isinstance(url, str) and url.startswith(
        f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/"
    )


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


# WeChat img_sec_check accepts PNG/JPEG/BMP ≤1 MB and ≤750×1334 — uploads here
# can be webp/gif and up to 10 MB, so moderation runs on a transcoded thumbnail
# of the ORIGINAL pixels (a 750px JPEG q85 is comfortably under 1 MB).
_IMG_CHECK_BOX = (750, 1334)


def check_thumbnail(raw: bytes) -> bytes | None:
    """Build a WeChat img_sec_check-ready JPEG from any Pillow-decodable upload.

    EXIF-oriented, downscaled to fit 750×1334, RGB JPEG. GIF → first frame
    (Pillow's default seek(0)). Returns None when Pillow cannot decode the
    bytes — the caller decides; with ``validate_image`` passed this is rare.
    """
    try:
        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail(_IMG_CHECK_BOX)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception:  # mirror process_image: never let a Pillow quirk break flow
        log.warning("check_thumbnail failed to decode upload", exc_info=True)
        return None


def _storage_path(
    module: str, user_id: int, content_type: str, filename: str | None = None
) -> str:
    """Build the object key inside the uploads bucket.

    Default: ``{module}/{user_id}/{uuid}.{ext}`` — a fresh, immutable object per
    upload, correct for multi-image modules (posts / lostfound / news) where each
    file is a distinct asset. ``filename`` (stable key) is retained for legacy
    callers but **avatars no longer use it**: ``upload_image_variants`` builds a
    versioned content-hash path ``avatars/{uid}/{v1}/{hash}@{label}.{ext}`` so a
    re-upload never overwrites (new content → new hash → new URL; same content →
    same URL, idempotent). If ``filename`` carries an extension it is used as-is.
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


async def _upload_blob(
    storage_path: str, file_bytes: bytes, content_type: str, *, cache_control: str | None = None
) -> str:
    """POST one object to Supabase Storage, return its public URL.

    When ``cache_control`` is given (immutable-URL uploads), the object is
    uploaded as multipart with ``cacheControl`` as a form field — the only
    mechanism empirically confirmed to make the public URL's GET honor the
    header (raw-body POST without it → Supabase defaults to ``no-cache``).
    """
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        if cache_control:
            resp = await client.post(
                url,
                headers=headers,
                files={"file": (os.path.basename(storage_path), file_bytes, content_type)},
                data={"cacheControl": cache_control},
            )
        else:
            resp = await client.post(
                url,
                content=file_bytes,
                headers={**headers, "Content-Type": content_type},
            )
    if resp.status_code not in (200, 201):
        # Supabase returns HTTP 400 with body {"statusCode":"409","error":"Duplicate"}
        # when the key already exists (default POST refuses overwrite; no x-upsert).
        # For immutable content-addressed paths (avatar versioned-hash) the existing
        # object IS the identical content — the path encodes the hash — so reuse it
        # and never overwrite. (uuid-keyed feed paths never collide.) This honors
        # "禁止覆盖旧头像对象": a re-upload of identical bytes reuses, never overwrites.
        body = resp.text
        is_duplicate = resp.status_code in (400, 409) and "Duplicate" in body
        if is_duplicate:
            log.info("storage object exists, reuse (no overwrite): %s", storage_path)
        else:
            log.error("Supabase upload failed: %s %s", resp.status_code, body)
            raise RuntimeError(f"Upload failed: {resp.status_code}")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"


async def verify_public_url(url: str) -> bool:
    """HEAD the public URL; True only if the object is live (200). Used to
    confirm an upload is reachable before pointing a DB row at it."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.head(url)
        return resp.status_code == 200
    except Exception:
        log.warning("public URL verify failed: %s", url, exc_info=True)
        return False


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

    Long cache is set ONLY for the default immutable (uuid) path; a stable
    ``filename`` path stays no-cache because a stable path is overwritable and
    long cache + overwrite would serve stale bytes (long cache must co-apply
    with an immutable URL).
    """
    storage_path = _storage_path(module, user_id, content_type, filename)
    cache_control = None if filename else _IMMUTABLE_CACHE
    return await _upload_blob(storage_path, file_bytes, content_type, cache_control=cache_control)


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

    Paths are IMMUTABLE so a long cache (``_IMMUTABLE_CACHE``) is safe:
      - posts/lostfound/news/courses: ``{module}/{uid}/{uuid}@{label}.{ext}``
        (fresh uuid per upload; ``filename`` ignored).
      - avatars: ``avatars/{uid}/{_PIPELINE_VERSION}/{content_hash}@{label}.{ext}``
        — content-hash of the main variant + pipeline version segment means a
        re-upload NEVER overwrites (new content → new hash → new URL; identical
        content → same URL, idempotent). Same URL → same bytes, forever.
    The 2x URL stays derivable client-side by swapping the label (``@640`` → ``@1280``).
    """
    variants = process_image(raw, content_type, module)
    if not variants:
        # GIF / unprocessable → verbatim. Avatars: versioned content-hash path
        # (immutable). Others: uuid path via upload_to_supabase.
        if module == "avatars":
            chash = _content_hash(raw)
            ext = _EXT_MAP.get(content_type, ".bin")
            sp = f"avatars/{user_id}/{_PIPELINE_VERSION}/{chash}{ext}"
            url = await _upload_blob(sp, raw, content_type, cache_control=_IMMUTABLE_CACHE)
        else:
            url = await upload_to_supabase(raw, content_type, module, user_id, filename=filename)
        return {"url": url, "variants": {}}

    # Variant path base — immutable either way.
    if module == "avatars":
        main_label = _MAIN_LABEL["avatars"]
        main_bytes = next((vb for lb, vb, _ in variants if lb == main_label), variants[-1][1])
        chash = _content_hash(main_bytes)
        root = f"avatars/{user_id}/{_PIPELINE_VERSION}/{chash}"
    else:
        base = _storage_path(module, user_id, content_type, filename)
        root, _ = os.path.splitext(base)

    out = {}
    for label, vbytes, vct in variants:
        ext = ".png" if vct == "image/png" else ".jpg"
        out[label] = await _upload_blob(
            f"{root}@{label}{ext}", vbytes, vct, cache_control=_IMMUTABLE_CACHE
        )

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
