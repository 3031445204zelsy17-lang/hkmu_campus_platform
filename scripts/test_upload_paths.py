"""Unit tests for upload_image_variants path + cacheControl logic (mocks _upload_blob, no network).

Run: python3 scripts/test_upload_paths.py
Validates: avatar versioned content-hash path (immutable, no-overwrite), posts uuid
path, all variants get _IMMUTABLE_CACHE; content-addressed dedup (same content →
same URL, different content → different URL).
"""
import asyncio
import re
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.services import storage_service as ss  # noqa: E402
from PIL import Image  # noqa: E402


def _jpg(size=500, color=(12, 34, 56)):
    buf = BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="JPEG")
    return buf.getvalue()


async def _capture(raw, ct, module, uid):
    calls = []

    async def fake(storage_path, file_bytes, content_type, *, cache_control=None):
        calls.append({"path": storage_path, "ct": content_type, "cache": cache_control})
        return f"https://x.supabase.co/storage/v1/object/public/uploads/{storage_path}"

    ss._upload_blob = fake  # monkeypatch module-level reference
    result = await ss.upload_image_variants(raw, ct, module, uid)
    return result, calls


async def main():
    cases = {}
    raw = _jpg()

    # avatars: versioned content-hash path + long cache + main = @192
    r, calls = await _capture(raw, "image/jpeg", "avatars", 42)
    ok_path = all(c["path"].startswith("avatars/42/v1/") for c in calls)
    ok_cache = all(c["cache"] == ss._IMMUTABLE_CACHE for c in calls)
    ok_url = "@192.jpg" in r["url"] and "/avatars/42/v1/" in r["url"]
    cases["avatars 版本化哈希路径 + 长缓存 + main=@192"] = ok_path and ok_cache and ok_url
    cases["avatars hash=sha256[:16]"] = bool(re.search(r"/v1/[0-9a-f]{16}@", r["url"]))

    # posts: uuid base path + long cache
    r2, calls2 = await _capture(raw, "image/jpeg", "posts", 7)
    cases["posts uuid 路径 + 长缓存 + main=@640"] = (
        all(c["path"].startswith("posts/7/") for c in calls2)
        and all(c["cache"] == ss._IMMUTABLE_CACHE for c in calls2)
        and "@640.jpg" in r2["url"]
    )

    # content-addressed: different content → different URL (no overwrite)
    rA, _ = await _capture(_jpg(color=(1, 1, 1)), "image/jpeg", "avatars", 42)
    rB, _ = await _capture(_jpg(color=(2, 2, 2)), "image/jpeg", "avatars", 42)
    cases["不同内容→不同 URL(不覆盖)"] = rA["url"] != rB["url"]

    # content-addressed: same content → same URL (idempotent)
    rC, _ = await _capture(_jpg(color=(1, 1, 1)), "image/jpeg", "avatars", 42)
    cases["同内容→同 URL(幂等)"] = rA["url"] == rC["url"]

    passed = sum(cases.values())
    for name, ok in cases.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n{passed}/{len(cases)} passed")
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    asyncio.run(main())
