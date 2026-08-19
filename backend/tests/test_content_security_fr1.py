"""FR1 regression: get_current_user must carry oauth_provider/oauth_id so
audit_user_text can moderate WeChat users' UGC via msg_sec_check.

Root cause (this fix): get_current_user's SELECT only loaded id/username, so
the user dict had no openid and audit_user_text hit the "skip (no openid)"
branch for EVERY request — msg_sec_check was never actually called, R1 content
moderation was inert for all users since launch.

These tests pin the fix:
  - WeChat user posting risky text → 400 (msg_sec_check reached + rejected)
  - WeChat user posting clean text → 201 (check reached, suggest=pass)
  - Non-WeChat (web/email) user → check NOT called → 201 (skip branch intact)
The first case would have passed pre-fix only because check_text was never
reached; we now assert call count to lock the openid plumbing in.
"""
import uuid


async def _make_wechat_user(make_user, label):
    """Register a user, then flip it to a WeChat miniprogram user with an openid.

    Reuses make_user (register + verify email + login) so we get a valid token;
    the token is bound to user_id, and the patched oauth_* columns are read by
    the fixed get_current_user on the next request.
    """
    suffix = uuid.uuid4().hex[:8]
    uid, token = await make_user(f"{label}_{suffix}")
    openid = f"OPENID_{suffix}"

    from backend.app.database import get_db

    async with get_db() as db:
        await db.execute(
            "UPDATE users SET oauth_provider='wechat_miniprogram', "
            "oauth_id=$1 WHERE id=$2",
            openid, uid,
        )
    return uid, token


async def test_wechat_user_risky_post_rejected(client, make_user, monkeypatch):
    """WeChat user posting risky text → 400; msg_sec_check must be reached."""
    _uid, token = await _make_wechat_user(make_user, "wxauthor")

    from backend.app.services import content_security

    calls = {"n": 0}

    async def fake_check_text(openid, content, scene):
        calls["n"] += 1
        assert openid and openid.startswith("OPENID_"), "openid must reach msg_sec_check"
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(content_security, "check_text", fake_check_text)

    res = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "spammy risky text", "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert calls["n"] == 1, (
        "msg_sec_check must be called for WeChat user — if 0, the FR1 regression "
        "returned: get_current_user dropped openid again"
    )
    assert res.status_code == 400, res.text
    assert "违规" in res.json()["detail"]


async def test_wechat_user_clean_post_allowed(client, make_user, monkeypatch):
    """WeChat user posting clean text → 201 (check reached, suggest=pass)."""
    _uid, token = await _make_wechat_user(make_user, "wxpass")

    from backend.app.services import content_security

    async def fake_check_text(openid, content, scene):
        return {"errcode": 0, "result": {"suggest": "pass"}}

    monkeypatch.setattr(content_security, "check_text", fake_check_text)

    res = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "hello world", "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text


async def test_non_wechat_user_skips_check(client, make_user, monkeypatch):
    """Non-WeChat (web/email) user → audit_user_text skips; check NOT called; 201.

    Guards the skip branch: ordinary registered users have no openid so
    moderation is skipped (a local sensitive-word layer is the planned FR1c
    follow-up). This must keep working after the fix — pre-fix it "worked" only
    because NO user ever reached the check.
    """
    _uid, token = await make_user(f"webuser_{uuid.uuid4().hex[:8]}")

    from backend.app.services import content_security

    calls = {"n": 0}

    async def fake_check_text(openid, content, scene):
        calls["n"] += 1
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(content_security, "check_text", fake_check_text)

    # Fake returns risky, but a web user is skipped → allowed.
    res = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "anything goes", "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert calls["n"] == 0, "non-WeChat user must skip msg_sec_check"
    assert res.status_code == 201, res.text


# --- fail-closed: service anomalies must BLOCK (503), not degrade to allow ---

async def _post_as_wechat(client, make_user, monkeypatch, fake_check_text):
    """Shared harness: flip a user to WeChat, patch check_text, POST a draft."""
    _uid, token = await _make_wechat_user(make_user, "wx")
    from backend.app.services import content_security
    monkeypatch.setattr(content_security, "check_text", fake_check_text)
    return await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "some text", "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_wechat_user_review_post_rejected(client, make_user, monkeypatch):
    """suggest=review → 400 (保守拦截,与 risky 同语义,补覆盖)。"""
    async def fake(openid, content, scene):
        return {"errcode": 0, "result": {"suggest": "review"}}
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 400, res.text
    assert "违规" in res.json()["detail"]


async def test_wechat_user_transport_failure_blocked(client, make_user, monkeypatch):
    """msg_sec_check transport/token/timeout failure → 503, post blocked."""
    from backend.app.services import content_security

    async def fake(openid, content, scene):
        raise content_security.WechatContentSecurityError("timeout")
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 503, res.text
    assert "暂时不可用" in res.json()["detail"]


async def test_wechat_user_errcode_61010_blocked(client, make_user, monkeypatch):
    """61010 openid-expired → 503 (并入服务异常,不提示重登)。"""
    async def fake(openid, content, scene):
        return {"errcode": 61010, "errmsg": "openid expired"}
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 503, res.text


async def test_wechat_user_unknown_errcode_blocked(client, make_user, monkeypatch):
    """未知 errcode → 503(fail-closed,不放行)。"""
    async def fake(openid, content, scene):
        return {"errcode": -1, "errmsg": "unknown"}
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 503, res.text


async def test_wechat_user_missing_result_blocked(client, make_user, monkeypatch):
    """errcode=0 但缺 result → 503(只有显式 pass 才放行)。"""
    async def fake(openid, content, scene):
        return {"errcode": 0}
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 503, res.text


async def test_wechat_user_unknown_suggest_blocked(client, make_user, monkeypatch):
    """未知 suggest → 503(default-deny)。"""
    async def fake(openid, content, scene):
        return {"errcode": 0, "result": {"suggest": "weird"}}
    res = await _post_as_wechat(client, make_user, monkeypatch, fake)
    assert res.status_code == 503, res.text


# --- kill switch: ENABLE_CONTENT_MODERATION=false bypasses moderation entirely ---

async def test_moderation_disabled_bypasses_check(client, make_user, monkeypatch):
    """ENABLE_CONTENT_MODERATION=false → audit_user_text returns immediately;
    check_text NOT called; even a WeChat user's risky post is allowed (201).

    Temporary degradation path for when the moderation service is unreachable
    (e.g. Azure outbound IPs outside WeChat IP whitelist). Asserting check_text
    is never reached locks the kill switch in.
    """
    from backend.app.services import content_security

    monkeypatch.setattr(content_security, "ENABLE_CONTENT_MODERATION", False)
    _uid, token = await _make_wechat_user(make_user, "wxdisabled")

    calls = {"n": 0}

    async def fake_check_text(openid, content, scene):
        calls["n"] += 1
        return {"errcode": 0, "result": {"suggest": "risky"}}

    monkeypatch.setattr(content_security, "check_text", fake_check_text)

    res = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "would-be-risky text", "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert calls["n"] == 0, "moderation disabled → check_text must not be called"
    assert res.status_code == 201, res.text
