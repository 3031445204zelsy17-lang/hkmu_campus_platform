"""[20][24] Avatar orphan-storage regression.

Two defects on the avatar path:

1. Every avatar upload generated a fresh ``avatars/{uid}/{uuid}.ext`` object, so
   updating an avatar left the previous object in the bucket forever (orphan).
   ``delete_from_supabase`` existed but was never wired up.
2. No stable key, so even same-user re-uploads accumulated distinct objects.

Fix: avatars now use a STABLE key ``avatars/{uid}/{uid}.ext`` (same-ext re-upload
overwrites in place) and the previous avatar object is deleted after the new one
is live. These tests lock the path-building helper (stable vs uuid, ext
handling) — the upload/delete HTTP path hits real Supabase and isn't exercised
in CI.
"""
import re

from backend.app.services.storage_service import _storage_path


_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")


def test_default_path_is_uuid_per_upload():
    """Multi-image modules get a fresh object each upload (correct for posts/
    lostfound/news — each file is a distinct asset, not a replace)."""
    p = _storage_path("posts", 42, "image/jpeg")
    module, uid, filename = p.split("/")
    assert module == "posts"
    assert uid == "42"
    name, ext = filename.split(".")
    assert ext == "jpg"
    assert _UUID_HEX.match(name), name
    # a second call yields a DIFFERENT object (uuid varies)
    assert _storage_path("posts", 42, "image/jpeg") != p


def test_avatar_stable_key_overwrites_in_place():
    """Avatars pass filename=<uid> → stable key, so a re-upload returns the SAME
    path (Supabase PUT overwrites) — no orphan on same-ext update."""
    a = _storage_path("avatars", 7, "image/png", filename="7")
    b = _storage_path("avatars", 7, "image/png", filename="7")
    assert a == b == "avatars/7/7.png"


def test_stable_filename_appends_ext_from_content_type():
    assert _storage_path("avatars", 3, "image/webp", filename="3") == "avatars/3/3.webp"
    assert _storage_path("avatars", 3, "image/gif", filename="3") == "avatars/3/3.gif"


def test_stable_filename_with_own_ext_used_as_is():
    """If the caller passes a filename that already has an extension, use it
    verbatim (don't double-append)."""
    assert _storage_path("avatars", 3, "image/jpeg", filename="3.png") == "avatars/3/3.png"


def test_ext_change_yields_different_path_so_old_gets_deleted():
    """jpg→png changes the path — the caller (upload_avatar) sees prev != new
    and deletes the old object. Same-ext re-upload keeps the path (no delete)."""
    jpg = _storage_path("avatars", 9, "image/jpeg", filename="9")
    png = _storage_path("avatars", 9, "image/png", filename="9")
    assert jpg == "avatars/9/9.jpg"
    assert png == "avatars/9/9.png"
    assert jpg != png  # ext change → old object must be cleaned up by caller


def test_avatar_path_is_distinct_from_uuid_path():
    """A legacy UUID avatar and the new stable avatar differ → on first
    re-upload the legacy orphan is deleted by the caller."""
    legacy = _storage_path("avatars", 5, "image/jpeg")
    stable = _storage_path("avatars", 5, "image/jpeg", filename="5")
    assert legacy != stable
    assert stable == "avatars/5/5.jpg"
