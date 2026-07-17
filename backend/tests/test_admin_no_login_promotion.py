"""[4] admin 提权修复回归 — login 不再因 username 自动 promote。

原 auth.py login 时 ``if body.username in ADMIN_USERNAMES`` → ``UPDATE identity='admin'``,
让任何人注册一个 ADMIN_USERNAMES 条目后登录即 admin(username squatting → 提权)。
修复后 promotion 只在启动(init_db)发生,优先用不可变的 ADMIN_USER_IDS。
"""


async def test_login_does_not_promote_via_username(client, make_user, monkeypatch):
    """[4] 即使 username 在 ADMIN_USERNAMES,login 也不 promote(消除抢注→admin)。"""
    import uuid
    from backend.app.database import get_db

    # 模拟抢注:把将要注册的 username 注入 ADMIN_USERNAMES(修复前这里会触发 promote)
    spoof = f"spoof_admin_{uuid.uuid4().hex[:6]}"
    monkeypatch.setattr("backend.app.routers.auth.ADMIN_USERNAMES", [spoof])
    uid, _ = await make_user(spoof)

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": spoof, "password": "Test12345!"},
    )
    assert login.status_code == 200, login.text

    # login 后 identity 必须不是 admin —— 修复前会 promote 成 admin
    async with get_db() as db:
        row = await db.fetchrow("SELECT identity FROM users WHERE id=$1", uid)
    assert row["identity"] != "admin", (
        "login 不应因 username 自动 promote([4] 抢注→admin); "
        "promotion 只该在启动时由 ADMIN_USER_IDS 发生"
    )
