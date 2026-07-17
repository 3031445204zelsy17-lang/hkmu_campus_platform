"""A① — /users/{user_id} permission regression (security roadmap A, PR #24).

GET /api/v1/users/{id} must (1) require auth and (2) return ONLY UserPublicOut
fields — never email / student_id / invite_code / oauth / programme_code.
Reverting the auth gate (added in A) or the UserPublicOut response_model makes
these red. The invite_code check specifically guards the force-friend vector A
closed (another user's invite_code could be redeemed via /users/me/friends).
"""
import uuid

from backend.app.models import UserPublicOut

# A response that leaks any field outside this set fails the test.
_PUBLIC_FIELDS = set(UserPublicOut.model_fields.keys())
_SENSITIVE = ("email", "student_id", "invite_code", "oauth_provider", "programme_code", "hkmu_verified")


async def test_get_user_requires_auth(client):
    r = await client.get("/api/v1/users/12345")
    assert r.status_code == 401


async def test_get_user_returns_only_public_fields(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _a_id, a_token = await make_user(f"alice_{suffix}")
    b_id, _ = await make_user(f"bob_{suffix}")

    r = await client.get(
        f"/api/v1/users/{b_id}",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert set(body.keys()) <= _PUBLIC_FIELDS, f"unexpected fields leaked: {set(body) - _PUBLIC_FIELDS}"
    for secret in _SENSITIVE:
        assert secret not in body, f"{secret} leaked in public user view"
    assert body["id"] == b_id
    assert body["username"] == f"bob_{suffix}"


async def _make_user_with_secrets(make_user, label):
    """注册一个用户并塞满敏感字段(programme/student/email/oauth/hkmu_verified +
    invite_code),用于证明这些字段不会经 UserPublicOut 泄露给其他用户。"""
    suffix = uuid.uuid4().hex[:6]
    uid, _ = await make_user(f"{label}_{suffix}")
    from backend.app.database import get_db

    async with get_db() as db:
        await db.execute(
            "UPDATE users SET programme_code=$1, student_id=$2, hkmu_verified=TRUE, "
            "email=$3, oauth_provider=$4, invite_code=$5 WHERE id=$6",
            "DSAI", f"S{suffix}999", f"{label}_{suffix}@hkmu.edu.hk", "google",
            f"INV{suffix}", uid,
        )
    return uid, f"{label}_{suffix}", f"INV{suffix}"


def _assert_only_public(body, context="", extra=()):
    """断言单个 user 视图只含 UserPublicOut 字段(+ extra 白名单,如
    SuggestOut.reason 这种非隐私的 i18n 信号),无敏感字段。"""
    leaked = set(body.keys()) - _PUBLIC_FIELDS - set(extra)
    assert not leaked, f"{context} 泄露字段: {leaked}"
    for secret in _SENSITIVE:
        assert secret not in body, f"{context} {secret} 泄露"


async def test_search_returns_only_public_fields(client, make_user):
    """[10] /users/search 不泄露 student_id/programme/email/oauth。"""
    tid, tname, _ = await _make_user_with_secrets(make_user, "target")
    _vid, vtoken = await make_user(f"viewer_{uuid.uuid4().hex[:6]}")
    r = await client.get(
        f"/api/v1/users/search?q={tname}",
        headers={"Authorization": f"Bearer {vtoken}"},
    )
    assert r.status_code == 200, r.text
    matched = [u for u in r.json() if u.get("id") == tid]
    assert matched, "search 应找到 target"
    _assert_only_public(matched[0], "search")


async def test_suggest_returns_only_public_fields(client, make_user):
    """[8] /users/suggest 不泄露(target 是 hkmu_verified peer)。"""
    tid, _, _ = await _make_user_with_secrets(make_user, "target")
    _vid, vtoken = await make_user(f"viewer_{uuid.uuid4().hex[:6]}")
    r = await client.get(
        "/api/v1/users/suggest?limit=50",
        headers={"Authorization": f"Bearer {vtoken}"},
    )
    assert r.status_code == 200, r.text
    matched = [u for u in r.json() if u.get("id") == tid]
    assert matched, "target(hkmu_verified) 应在 suggest"
    _assert_only_public(matched[0], "suggest", extra={"reason"})


async def test_friends_list_returns_only_public_fields(client, make_user):
    """[12] /users/me/friends 的 friend 不泄露。"""
    tid, _, _ = await _make_user_with_secrets(make_user, "target")
    vid, vtoken = await make_user(f"viewer_{uuid.uuid4().hex[:6]}")
    from backend.app.database import get_db

    async with get_db() as db:
        await db.execute(
            "INSERT INTO friendships (user_id, friend_id, status, source) VALUES "
            "($1,$2,'accepted','test'),($2,$1,'accepted','test') ON CONFLICT DO NOTHING",
            vid, tid,
        )
    r = await client.get(
        "/api/v1/users/me/friends",
        headers={"Authorization": f"Bearer {vtoken}"},
    )
    assert r.status_code == 200, r.text
    fr = [f for f in r.json() if f["friend"]["id"] == tid]
    assert fr, "target 应在好友列表"
    _assert_only_public(fr[0]["friend"], "friends.friend")


async def test_invite_redeem_does_not_leak_inviter(client, make_user):
    """[1] 兑换邀请码返回的 friend 不含 inviter 的 email/oauth/student_id。"""
    iid, _, code = await _make_user_with_secrets(make_user, "inviter")
    _vid, vtoken = await make_user(f"redeemer_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/users/me/friends",
        json={"invite_code": code},
        headers={"Authorization": f"Bearer {vtoken}"},
    )
    assert r.status_code == 200, r.text
    friend = r.json()["friend"]
    _assert_only_public(friend, "invite_redeem.friend")
