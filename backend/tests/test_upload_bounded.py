"""[5][15] Upload bounded-read regression.

Both upload paths (``POST /upload`` and ``POST /users/me/avatar``) previously did
``raw = await file.read()`` — loading the *entire* upload into memory before any
size check. A client streaming gigabytes could OOM the worker (the MAX_FILE_SIZE
guard only ran after the bytes were already in RAM). ``read_bounded`` reads at
most ``MAX_FILE_SIZE + 1`` bytes and raises if the file is bigger, so memory is
bounded regardless of upload size. These tests pin that helper.
"""
import pytest

import backend.app.services.storage_service as ss


class _FakeUpload:
    """Mimics the only surface read_bounded touches: ``await read(n)`` that
    returns up to n bytes and advances."""

    def __init__(self, data: bytes):
        self._buf = data

    async def read(self, n: int = -1) -> bytes:
        if n == -1:
            out, self._buf = self._buf, b""
        else:
            out, self._buf = self._buf[:n], self._buf[n:]
        return out


async def test_rejects_oversize(monkeypatch):
    monkeypatch.setattr(ss, "MAX_FILE_SIZE", 100)
    with pytest.raises(ValueError, match="File too large"):
        await ss.read_bounded(_FakeUpload(b"x" * 5000))


async def test_accepts_within_limit(monkeypatch):
    monkeypatch.setattr(ss, "MAX_FILE_SIZE", 100)
    data = await ss.read_bounded(_FakeUpload(b"x" * 50))
    assert data == b"x" * 50


async def test_memory_is_bounded_not_whole_file(monkeypatch):
    """The whole point: even a multi-MB upload only pulls MAX+1 bytes into RAM,
    not the entire file. (Old code read it all before checking size.)"""
    monkeypatch.setattr(ss, "MAX_FILE_SIZE", 100)
    f = _FakeUpload(b"x" * 5000)
    with pytest.raises(ValueError):
        await ss.read_bounded(f)
    # only MAX+1 = 101 bytes drained; the remaining ~4900 untouched
    assert len(f._buf) == 5000 - 101


async def test_boundary_exactly_max_is_accepted(monkeypatch):
    monkeypatch.setattr(ss, "MAX_FILE_SIZE", 100)
    data = await ss.read_bounded(_FakeUpload(b"x" * 100))  # exactly the cap
    assert len(data) == 100
