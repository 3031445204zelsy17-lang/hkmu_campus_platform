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
