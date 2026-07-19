"""Phase 2 image pipeline — pins ``process_image`` behaviour.

The upload/avatar HTTP path talks to real Supabase Storage and isn't exercised
here (same boundary as test_upload_bounded / test_avatar_storage, which unit-
test the helpers). Instead these tests drive ``process_image`` directly: the
EXIF-orient / metadata-strip / multi-size / format / fail-safe guarantees that
make new uploads small and privacy-safe. Needs Pillow (now in requirements.txt).
"""
import io

import pytest
from PIL import Image

from backend.app.services import storage_service as ss
from backend.app.services.storage_service import process_image


def _jpeg(w, h, orientation=None, make=None):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = ((x * 255) // w, (y * 255) // h, 100)
    exif = img.getexif()
    if orientation:
        exif[0x0112] = orientation  # Orientation
    if make:
        exif[0x010f] = make  # Make — stands in for camera metadata / GPS
    buf = io.BytesIO()
    kw = {"exif": exif.tobytes()} if (orientation or make) else {}
    img.save(buf, format="JPEG", quality=95, **kw)
    return buf.getvalue()


def test_posts_module_produces_two_variants_within_size_budget():
    variants = process_image(_jpeg(2000, 1500), "image/jpeg", "posts")
    labels = [lbl for lbl, _, _ in variants]
    assert labels == ["640", "1280"]
    for label, vbytes, vct in variants:
        v = Image.open(io.BytesIO(vbytes))
        assert max(v.size) <= int(label)
        assert vct == "image/jpeg"
        assert len(vbytes) < 150 * 1024  # feed image budget


def test_exif_orientation_applied_and_metadata_stripped():
    # Orientation 6 = 90° CW: a 2000x1500 landscape is logically portrait after rotation.
    raw = _jpeg(2000, 1500, orientation=6, make="TestCamera")
    in_exif = Image.open(io.BytesIO(raw)).getexif()
    assert in_exif.get(0x010f) == "TestCamera"

    variants = process_image(raw, "image/jpeg", "posts")
    v640 = Image.open(io.BytesIO(variants[0][1]))
    # Transposed to portrait then fit to 640 longest side → (480, 640).
    assert v640.size == (480, 640)
    out_exif = v640.getexif()
    assert 0x0112 not in out_exif  # orientation tag gone
    assert out_exif.get(0x010f) is None  # camera metadata stripped (GPS too — transcoded)


def test_transparent_png_stays_png_with_alpha():
    png = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    px = png.load()
    for x in range(800):
        for y in range(400):
            px[x, y] = (255, 0, 0, 255)
    buf = io.BytesIO()
    png.save(buf, format="PNG")

    variants = process_image(buf.getvalue(), "image/png", "posts")
    for _, vbytes, vct in variants:
        v = Image.open(io.BytesIO(vbytes))
        assert vct == "image/png"
        assert v.mode == "RGBA"  # transparency preserved, not flattened to JPEG


def test_gif_kept_as_original():
    """GIF returns None so the caller keeps the original — we don't silently
    collapse animation to a static first frame."""
    g = Image.new("P", (100, 100))
    buf = io.BytesIO()
    g.save(buf, format="GIF")
    assert process_image(buf.getvalue(), "image/gif", "posts") is None


def test_avatars_module_uses_small_sizes_under_30kb():
    variants = process_image(_jpeg(1000, 1000), "image/jpeg", "avatars")
    labels = [lbl for lbl, _, _ in variants]
    assert labels == ["96", "192"]
    assert ss._MAIN_LABEL["avatars"] == "192"
    v192 = Image.open(io.BytesIO(variants[1][1]))
    assert max(v192.size) <= 192
    assert len(variants[1][1]) < 30 * 1024  # avatar budget


def test_does_not_upscale_small_input():
    variants = process_image(_jpeg(400, 300), "image/jpeg", "posts")
    v640 = Image.open(io.BytesIO(variants[0][1]))
    assert v640.size == (400, 300)  # requested 640 but input smaller → kept as-is


def test_corrupt_input_falls_back_to_original():
    """A Pillow decode failure must never break the upload — return None so the
    caller stores the original bytes verbatim."""
    assert process_image(b"not an image", "image/jpeg", "posts") is None
    assert process_image(b"", "image/jpeg", "posts") is None


def test_opaque_webp_normalized_to_jpeg():
    webp = Image.new("RGB", (1600, 1200), (50, 150, 200))
    buf = io.BytesIO()
    webp.save(buf, format="WEBP", quality=90)
    variants = process_image(buf.getvalue(), "image/webp", "posts")
    assert [vct for _, _, vct in variants] == ["image/jpeg", "image/jpeg"]
