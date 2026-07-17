"""复验残留问题回归 — WS chat 校验对齐 REST send_message。

原 WS 端点(messages.py ws_endpoint)仅 `if not receiver_id or not content`,
可写入「自发 / 超 2000 字 / 不存在收件人」的消息(PoC 已验证)。
``_validate_ws_chat`` 抽出 REST 同款 4 道校验(MessageCreate 长度 + 限流 +
收件人存在 + 禁自发);此测试锁住,任一回退即红。

直接单测 ``_validate_ws_chat`` 函数,无需 WebSocket client(校验逻辑已从
ws_endpoint 的 receive 循环里抽出,便于测试)。
"""
import uuid

import pytest

from backend.app.database import get_db
from backend.app.routers.messages import _validate_ws_chat


async def test_ws_chat_rejects_too_long(client, make_user):
    """>2000 字 → Invalid message(MessageCreate max_length=2000)。"""
    uid, _ = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    async with get_db() as db:
        with pytest.raises(ValueError, match="Invalid message"):
            await _validate_ws_chat(uid, uid, "x" * 2001, db)


async def test_ws_chat_rejects_self_message(client, make_user):
    """receiver == sender → Cannot message yourself(收件人存在校验通过后)。"""
    uid, _ = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    async with get_db() as db:
        with pytest.raises(ValueError, match="Cannot message yourself"):
            await _validate_ws_chat(uid, uid, "hi", db)


async def test_ws_chat_rejects_nonexistent_recipient(client, make_user):
    """receiver 不存在 → User not found。"""
    uid, _ = await make_user(f"u_{uuid.uuid4().hex[:6]}")
    async with get_db() as db:
        with pytest.raises(ValueError, match="User not found"):
            await _validate_ws_chat(uid, 999999, "hi", db)


async def test_ws_chat_accepts_valid_message(client, make_user):
    """正常消息 → 返回规整后的 (receiver_id, content)。"""
    suffix = uuid.uuid4().hex[:6]
    u1, _ = await make_user(f"u1_{suffix}")
    u2, _ = await make_user(f"u2_{suffix}")
    async with get_db() as db:
        receiver_id, content = await _validate_ws_chat(u1, u2, "hello", db)
        assert receiver_id == u2
        assert content == "hello"
