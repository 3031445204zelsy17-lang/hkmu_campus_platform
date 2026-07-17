import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from pydantic import ValidationError

from ..database import get_db
from ..models import MessageCreate, MessageOut, ConversationOut
from ..services.auth_service import get_current_user, decode_access_token, access_token_expired
from ..services.rate_limiter import check_rate_limit
from ..services.websocket_manager import manager

router = APIRouter(prefix="/messages", tags=["messages"])

PING_INTERVAL = 30


# --- REST endpoints ---


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: dict = Depends(get_current_user)):
    uid = user["id"]
    async with get_db() as db:
        rows = await db.fetch(
            """
            WITH latest AS (
                SELECT
                    CASE WHEN sender_id = $1 THEN receiver_id ELSE sender_id END AS partner_id,
                    MAX(id) AS max_id
                FROM messages
                WHERE sender_id = $2 OR receiver_id = $3
                GROUP BY partner_id
            ),
            unread AS (
                SELECT sender_id AS partner_id, COUNT(*) AS cnt
                FROM messages
                WHERE receiver_id = $4 AND is_read = FALSE
                GROUP BY sender_id
            )
            SELECT
                l.partner_id,
                u.nickname AS partner_nickname,
                u.avatar_url AS partner_avatar,
                m.content AS last_message,
                m.created_at AS last_time,
                COALESCE(ud.cnt, 0) AS unread_count
            FROM latest l
            JOIN users u ON u.id = l.partner_id
            JOIN messages m ON m.id = l.max_id
            LEFT JOIN unread ud ON ud.partner_id = l.partner_id
            ORDER BY m.created_at DESC, m.id DESC
            """,
            uid, uid, uid, uid,
        )
        return [
            ConversationOut(
                partner_id=r["partner_id"],
                partner_nickname=r["partner_nickname"],
                partner_avatar=r["partner_avatar"],
                last_message=r["last_message"],
                last_time=r["last_time"].isoformat() if isinstance(r["last_time"], datetime) else r["last_time"],
                unread_count=r["unread_count"],
            )
            for r in rows
        ]


@router.get("/history/{partner_id}", response_model=list[MessageOut])
async def get_history(
    partner_id: int,
    user: dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    offset = (page - 1) * page_size

    async with get_db() as db:
        async with db.transaction():
            # Verify partner exists
            exists = await db.fetchrow("SELECT id FROM users WHERE id = $1", partner_id)
            if not exists:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

            rows = await db.fetch(
                """
                SELECT id, sender_id, receiver_id, content, is_read,
                       created_at
                FROM messages
                WHERE (sender_id = $1 AND receiver_id = $2)
                   OR (sender_id = $3 AND receiver_id = $4)
                ORDER BY created_at DESC, id DESC
                LIMIT $5 OFFSET $6
                """,
                user["id"], partner_id, partner_id, user["id"],
                page_size, offset,
            )
            messages = [
                MessageOut(
                    id=r["id"],
                    sender_id=r["sender_id"],
                    receiver_id=r["receiver_id"],
                    content=r["content"],
                    is_read=bool(r["is_read"]),
                    created_at=r["created_at"].isoformat() if isinstance(r["created_at"], datetime) else r["created_at"],
                )
                for r in rows
            ]

            # Mark as read
            await db.execute(
                "UPDATE messages SET is_read = TRUE WHERE sender_id = $1 AND receiver_id = $2 AND is_read = FALSE",
                partner_id, user["id"],
            )

    return list(reversed(messages))


@router.post("/{partner_id}", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    partner_id: int,
    body: MessageCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"msg:{user['id']}", max_requests=30, window_seconds=60)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    async with get_db() as db:
        # Verify partner exists
        exists = await db.fetchrow("SELECT id FROM users WHERE id = $1", partner_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        if partner_id == user["id"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot message yourself")

        row = await db.fetchrow(
            """INSERT INTO messages (sender_id, receiver_id, content, created_at)
               VALUES ($1, $2, $3, $4)
               RETURNING id""",
            user["id"], partner_id, body.content, now,
        )
        msg_id = row["id"]

    msg_out = MessageOut(
        id=msg_id,
        sender_id=user["id"],
        receiver_id=partner_id,
        content=body.content,
        is_read=False,
        created_at=now_iso,
    )

    # Push via WebSocket if partner is online
    await manager.send_to_user(partner_id, {
        "type": "chat",
        "id": msg_id,
        "sender_id": user["id"],
        "receiver_id": partner_id,
        "content": body.content,
        "is_read": False,
        "created_at": now_iso,
    })

    # Also send back to sender for multi-tab sync
    await manager.send_to_user(user["id"], {
        "type": "chat",
        "id": msg_id,
        "sender_id": user["id"],
        "receiver_id": partner_id,
        "content": body.content,
        "is_read": False,
        "created_at": now_iso,
    })

    # Web Push notification if partner is offline
    if not manager.is_online(partner_id):
        from ..services.push_service import send_push_to_user
        await send_push_to_user(partner_id, {
            "type": "message",
            "title": f"{user.get('username', 'Someone')} sent you a message",
            "body": body.content[:100],
            "url": "/#/messages",
            "sender_id": user["id"],
        })

    return msg_out


@router.put("/read/{partner_id}")
async def mark_read(partner_id: int, user: dict = Depends(get_current_user)):
    async with get_db() as db:
        await db.execute(
            "UPDATE messages SET is_read = TRUE WHERE sender_id = $1 AND receiver_id = $2 AND is_read = FALSE",
            partner_id, user["id"],
        )
    return {"status": "ok"}


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM messages WHERE receiver_id = $1 AND is_read = FALSE",
            user["id"],
        )
    return {"count": row["cnt"]}


# --- WebSocket ---


async def _validate_ws_chat(user_id, receiver_id_raw, content, db):
    """校验 WS chat 消息,对齐 REST send_message(复验残留问题修复)。

    REST 端点靠 MessageCreate + check_rate_limit + 收件人存在 + 禁自发 4 道校验;
    WS 端点原仅 `if not receiver_id or not content`,可写入自发/超长/不存在收件人消息。
    返回规整后的 (receiver_id, content);任一校验不过抛 ValueError(detail)。
    """
    try:
        receiver_id = int(receiver_id_raw)
        content = MessageCreate(content=content).content  # min_length=1 / max_length=2000
    except (TypeError, ValueError, ValidationError):
        raise ValueError("Invalid message")
    try:
        check_rate_limit(f"msg:{user_id}", max_requests=30, window_seconds=60)
    except HTTPException:
        raise ValueError("Rate limit exceeded")
    partner = await db.fetchrow("SELECT id FROM users WHERE id = $1", receiver_id)
    if not partner:
        raise ValueError("User not found")
    if receiver_id == user_id:
        raise ValueError("Cannot message yourself")
    return receiver_id, content


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001)
        return

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        # [2] capture exp so the long-lived socket can be torn down once the
        # access token expires mid-connection. Access tokens are stateless JWTs
        # (no revocation list), so re-checking the already-verified exp on each
        # inbound frame is sufficient — see access_token_expired().
        exp = payload.get("exp")
    except Exception:
        await ws.close(code=4001)
        return

    await ws.accept()
    manager.connect(user_id, ws)

    try:
        # [9] short DB borrow for the initial unread count only — do NOT hold a
        # pool connection across the receive loop. The old code wrapped the
        # whole while-loop in `async with get_db()`, so every connected WS
        # client pinned a pool connection for the socket's entire lifetime
        # (hours); with DB_POOL_MAX=10 a mere 10 chat clients starved every
        # REST endpoint. Each op below now borrows for just its own statement(s).
        async with get_db() as db:
            row = await db.fetchrow(
                "SELECT COUNT(*) AS cnt FROM messages WHERE receiver_id = $1 AND is_read = FALSE",
                user_id,
            )
        await manager.send_to_user(user_id, {"type": "unread_count", "count": row["cnt"]})

        while True:
            # [2] gate every frame on a fresh expiry check. If the token has
            # expired, tell the client and close — no chat / mark_read is
            # processed past expiry. Idle sockets are torn down on the next
            # inbound frame; since [9] they hold no DB connection, so lingering
            # is just a small amount of server memory until then.
            if access_token_expired(exp):
                try:
                    await manager.send_to_user(user_id, {"type": "auth_expired"})
                    await ws.close(code=4001)
                except Exception:
                    pass
                break

            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await manager.send_to_user(user_id, {"type": "pong"})

            elif msg_type == "chat":
                try:
                    async with get_db() as db:
                        receiver_id, content = await _validate_ws_chat(
                            user_id, data.get("receiver_id"), data.get("content", "").strip(), db
                        )
                        now = datetime.now(timezone.utc)
                        now_iso = now.isoformat()
                        row = await db.fetchrow(
                            """INSERT INTO messages (sender_id, receiver_id, content, created_at)
                               VALUES ($1, $2, $3, $4)
                               RETURNING id""",
                            user_id, receiver_id, content, now,
                        )
                        msg_id = row["id"]
                except ValueError as exc:
                    await manager.send_to_user(user_id, {"type": "error", "detail": str(exc)})
                    continue

                chat_msg = {
                    "type": "chat",
                    "id": msg_id,
                    "sender_id": user_id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "is_read": False,
                    "created_at": now_iso,
                }
                await manager.send_to_user(receiver_id, chat_msg)
                await manager.send_to_user(user_id, chat_msg)

                # Web Push if receiver is offline — mirror REST send_message:
                # re-check is_online at push time, and borrow its own short
                # connection for the username lookup ([9] — never hold across WS).
                if not manager.is_online(receiver_id):
                    from ..services.push_service import send_push_to_user
                    async with get_db() as db:
                        sender_row = await db.fetchrow(
                            "SELECT username FROM users WHERE id = $1", user_id
                        )
                    sender_name = sender_row["username"] if sender_row else "Someone"
                    await send_push_to_user(receiver_id, {
                        "type": "message",
                        "title": f"{sender_name} sent you a message",
                        "body": content[:100],
                        "url": "/#/messages",
                        "sender_id": user_id,
                    })

            elif msg_type == "mark_read":
                partner_id = data.get("partner_id")
                if partner_id:
                    async with get_db() as db:
                        await db.execute(
                            "UPDATE messages SET is_read = TRUE WHERE sender_id = $1 AND receiver_id = $2 AND is_read = FALSE",
                            partner_id, user_id,
                        )

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)
