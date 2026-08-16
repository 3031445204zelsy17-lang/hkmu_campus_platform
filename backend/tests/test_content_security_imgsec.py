"""版本修改指引 3.2 整改回归:图片 img_sec_check + 全场景文本闸门。

微信 5月26日版本修改指引(拒绝情形 3.2)点名【头像】功能缺内容安全,
要求内容安全 API「可在小程序内任意发布的场景生效」。本文件锁定:

  - audit_user_image 决策表:errcode 0 放行 / 87014 → 400 / 其他 errcode
    或服务异常 → 503(fail-closed)/ 无法解码 → 400 / 非微信用户 skip /
    kill switch 直通
  - check_thumbnail:任意可解码图 → ≤750×1334 JPEG;垃圾字节 → None
  - 端点接线:头像 /users/me/avatar、昵称简介 PUT /users/me、课评
    POST /courses/{id}/reviews、私信 POST /messages/{id}、反馈 POST
    /feedback —— 微信用户发违规内容 → 400 且 check 确被调用
    (帖子/评论/失物/新闻评论的接线由 test_content_security_fr1 锁定)
"""
import io
import uuid

import pytest
from fastapi import HTTPException
from PIL import Image

from backend.app.database import get_db


async def _make_wechat_user(make_user, label):
    """复用 fr1 的手法:注册用户后翻成微信小程序用户(带 openid)。"""
    suffix = uuid.uuid4().hex[:8]
    uid, token = await make_user(f"{label}_{suffix}")
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET oauth_provider='wechat_miniprogram', "
            "oauth_id=$1 WHERE id=$2",
            f"OPENID_{suffix}", uid,
        )
    return uid, token


def _png_bytes(w=800, h=1600):
    """生成一张超过 img_sec_check 尺寸上限的 PNG,验证 check_thumbnail 缩放。"""
    img = Image.new("RGB", (w, h), color=(200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── check_thumbnail ──────────────────────────────────────────────────

def test_check_thumbnail_scales_and_transcodes():
    from backend.app.services.storage_service import check_thumbnail

    out = check_thumbnail(_png_bytes(800, 1600))
    assert out, "decodable PNG must produce a check thumbnail"
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert max(img.size) <= 1334, f"must fit 750x1334 box, got {img.size}"
    assert len(out) < 1024 * 1024, "thumbnail must stay under the 1 MB API cap"


def test_check_thumbnail_garbage_returns_none():
    from backend.app.services.storage_service import check_thumbnail

    assert check_thumbnail(b"not an image at all") is None


# ── audit_user_image 决策表(单元) ────────────────────────────────────

def _wx_user():
    return {"id": 1, "oauth_provider": "wechat_miniprogram", "oauth_id": "OPENID_x"}


async def test_audit_image_pass(monkeypatch):
    from backend.app.services import content_security as cs

    async def fake_check(b):
        return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(cs, "check_image", fake_check)
    await cs.audit_user_image(_wx_user(), _png_bytes(50, 50))  # no raise = allow


async def test_audit_image_risky_400(monkeypatch):
    from backend.app.services import content_security as cs

    async def fake_check(b):
        return {"errcode": 87014, "errmsg": "content is risky"}

    monkeypatch.setattr(cs, "check_image", fake_check)
    with pytest.raises(HTTPException) as ei:
        await cs.audit_user_image(_wx_user(), _png_bytes(50, 50))
    assert ei.value.status_code == 400
    assert "违规" in str(ei.value.detail)


async def test_audit_image_other_errcode_503(monkeypatch):
    from backend.app.services import content_security as cs

    async def fake_check(b):
        return {"errcode": 40001, "errmsg": "invalid credential"}

    monkeypatch.setattr(cs, "check_image", fake_check)
    with pytest.raises(HTTPException) as ei:
        await cs.audit_user_image(_wx_user(), _png_bytes(50, 50))
    assert ei.value.status_code == 503


async def test_audit_image_transport_503(monkeypatch):
    from backend.app.services import content_security as cs

    async def boom(b):
        raise cs.WechatContentSecurityError("no network")

    monkeypatch.setattr(cs, "check_image", boom)
    with pytest.raises(HTTPException) as ei:
        await cs.audit_user_image(_wx_user(), _png_bytes(50, 50))
    assert ei.value.status_code == 503


async def test_audit_image_undecodable_400():
    from backend.app.services import content_security as cs

    with pytest.raises(HTTPException) as ei:
        await cs.audit_user_image(_wx_user(), b"\x00garbage\xff")
    assert ei.value.status_code == 400


async def test_audit_image_non_wechat_skips(monkeypatch):
    from backend.app.services import content_security as cs

    calls = {"n": 0}

    async def fake_check(b):
        calls["n"] += 1
        return {"errcode": 0}

    monkeypatch.setattr(cs, "check_image", fake_check)
    await cs.audit_user_image({"id": 2, "oauth_provider": "email", "oauth_id": None}, _png_bytes(10, 10))
    assert calls["n"] == 0, "non-WeChat users skip the image gate (FR1c deferred)"


async def test_audit_image_kill_switch(monkeypatch):
    from backend.app.services import content_security as cs

    calls = {"n": 0}

    async def fake_check(b):
        calls["n"] += 1
        return {"errcode": 0}

    monkeypatch.setattr(cs, "check_image", fake_check)
    monkeypatch.setattr(cs, "ENABLE_CONTENT_MODERATION", False)
    await cs.audit_user_image(_wx_user(), b"\x00garbage")  # 甚至不过解码
    assert calls["n"] == 0


# ── 端点接线 ─────────────────────────────────────────────────────────

async def test_avatar_risky_image_rejected(client, make_user, monkeypatch):
    """微信用户传违规头像 → 400(img_sec_check 被真正调用,不落 Storage)。"""
    _uid, token = await _make_wechat_user(make_user, "wxav")
    from backend.app.services import content_security as cs

    calls = {"n": 0}

    async def fake_check(b):
        calls["n"] += 1
        return {"errcode": 87014, "errmsg": "content is risky"}

    monkeypatch.setattr(cs, "check_image", fake_check)

    res = await client.post(
        "/api/v1/users/me/avatar",
        files={"file": ("avatar.png", _png_bytes(60, 60), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    assert calls["n"] == 1, "img_sec_check must be reached for avatar uploads"


async def test_nickname_risky_rejected(client, make_user, monkeypatch):
    _uid, token = await _make_wechat_user(make_user, "wxnk")
    from backend.app.services import content_security as cs

    calls = {"n": 0}

    async def fake_check(openid, content, scene):
        calls["n"] += 1
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(cs, "check_text", fake_check)

    res = await client.put(
        "/api/v1/users/me",
        json={"nickname": "spammy risky name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    assert calls["n"] == 1


async def test_bio_risky_rejected(client, make_user, monkeypatch):
    _uid, token = await _make_wechat_user(make_user, "wxbio")
    from backend.app.services import content_security as cs

    async def fake_check(openid, content, scene):
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(cs, "check_text", fake_check)
    res = await client.put(
        "/api/v1/users/me",
        json={"bio": "违规简介"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text


async def test_dm_risky_rejected(client, make_user, monkeypatch):
    _p_uid, _p_token = await make_user(f"wxpartner_{uuid.uuid4().hex[:6]}")
    _uid, token = await _make_wechat_user(make_user, "wxdm")
    from backend.app.services import content_security as cs

    calls = {"n": 0}

    async def fake_check(openid, content, scene):
        calls["n"] += 1
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(cs, "check_text", fake_check)

    res = await client.post(
        f"/api/v1/messages/{_p_uid}",
        json={"content": "risky dm text"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
    assert calls["n"] == 1


async def test_review_risky_rejected(client, make_user, monkeypatch):
    cid = f"T32{uuid.uuid4().hex[:8].upper()}"
    async with get_db() as db:
        await db.execute(
            """INSERT INTO courses (id, code, name, credits, category, year, semester)
               VALUES ($1, $1, 'T32 Test Course', 3, 'core', 1, 'autumn')""",
            cid,
        )
    try:
        _uid, token = await _make_wechat_user(make_user, "wxrv")
        from backend.app.services import content_security as cs

        async def fake_check(openid, content, scene):
            return {"errcode": 0, "result": {"suggest": "risky"}}

        monkeypatch.setattr(cs, "check_text", fake_check)
        res = await client.post(
            f"/api/v1/courses/{cid}/reviews",
            json={"rating": 5, "content": "risky review"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400, res.text
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM course_reviews WHERE course_id = $1", cid)
            await db.execute("DELETE FROM courses WHERE id = $1", cid)


async def test_feedback_risky_rejected(client, make_user, monkeypatch):
    _uid, token = await _make_wechat_user(make_user, "wxfb")
    from backend.app.services import content_security as cs

    async def fake_check(openid, content, scene):
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(cs, "check_text", fake_check)
    res = await client.post(
        "/api/v1/feedback",
        json={"rating": 5, "content": f"risky feedback {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400, res.text
