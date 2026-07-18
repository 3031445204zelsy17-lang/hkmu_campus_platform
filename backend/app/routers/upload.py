"""
Generic image upload endpoint.

POST /api/v1/upload?module=<module_name>

Accepts multipart/form-data with a single ``file`` field.
Returns ``{"url": "<public_url>"}`` on success.

Any authenticated module can use this — just pass the ``module`` query param
(e.g. ``lostfound``, ``posts``, ``avatars``, ``news``) so files are organised
by folder in the storage bucket.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status

from ..services.auth_service import get_current_user
from ..services.storage_service import validate_image, upload_to_supabase, read_bounded

router = APIRouter(prefix="/upload", tags=["upload"])

_VALID_MODULES = {"lostfound", "posts", "avatars", "news", "courses"}


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    module: str = Query("lostfound", pattern=r"^[a-z_]+$"),
    user: dict = Depends(get_current_user),
):
    # Validate module name
    if module not in _VALID_MODULES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid module. Allowed: {', '.join(sorted(_VALID_MODULES))}",
        )

    # Read file bytes with a BOUNDED read (Codex [5][15]) — never load an
    # unbounded upload into memory. 413 if it exceeds the cap.
    try:
        raw = await read_bounded(file)
    except ValueError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    content_type = file.content_type or "application/octet-stream"

    err = validate_image(content_type, len(raw))
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)

    url = await upload_to_supabase(raw, content_type, module, user["id"])
    return {"url": url}
