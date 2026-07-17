"""[13] SECRET_KEY fail-closed + [6] reset-password per-IP rate-limit 回归。

[13]: 空/default SECRET_KEY 必须拒绝启动(否则任何人可伪造 JWT 冒充账号)。
[6]: reset-password 按 client IP 分桶——原常量 key "reset-password" 让任意 5 请求
     耗尽整个 worker 的全局预算,阻断所有用户重置密码。
"""
import uuid

import pytest

from backend.app.main import _validate_secret_key


def test_secret_key_rejects_default():
    """[13] default SECRET_KEY → 拒绝启动。"""
    with pytest.raises(RuntimeError):
        _validate_secret_key("change-me-in-production")


def test_secret_key_rejects_empty():
    """[13] 空 SECRET_KEY → 拒绝启动(漏配 / SECRET_KEY=)。"""
    with pytest.raises(RuntimeError):
        _validate_secret_key("")


def test_secret_key_accepts_strong():
    """[13] 强随机 SECRET_KEY → 通过(不 raise)。"""
    _validate_secret_key("a" * 64)


async def test_reset_password_rate_limit_is_per_ip(client):
    """[6] reset-password 按 IP 分桶:同 IP 5 次后 429,异 IP 独立不受影响。"""
    suffix = uuid.uuid4().hex[:6]
    ip_a = f"10.{suffix}.1"
    ip_b = f"10.{suffix}.2"
    body = {"token": "any-token", "new_password": "Test1234!"}

    # IP A 前 5 次:rate-limit 通过(token 无效→400,但 rate-limit 在前会计数)
    for i in range(5):
        r = await client.post(
            "/api/v1/auth/reset-password", json=body,
            headers={"x-forwarded-for": ip_a},
        )
        assert r.status_code != 429, f"IP A 第{i+1}次不应 429, got {r.status_code}"
    # IP A 第 6 次 → 429(per-IP 桶满)
    r = await client.post(
        "/api/v1/auth/reset-password", json=body,
        headers={"x-forwarded-for": ip_a},
    )
    assert r.status_code == 429, f"IP A 第6次应 429, got {r.status_code}"
    # IP B 第 1 次 → 非 429(独立桶,证明已非常量全局 key)
    r = await client.post(
        "/api/v1/auth/reset-password", json=body,
        headers={"x-forwarded-for": ip_b},
    )
    assert r.status_code != 429, f"IP B 不应被 IP A 耗尽影响, got {r.status_code}"
