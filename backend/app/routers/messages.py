import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status

from ..database import get_db
from ..models import MessageCreate, MessageOut, ConversationOut
from ..services.auth_service import get_current_user, decode_access_token
from ..services.websocket_manager import manager

router = APIRouter(prefix="/messages", tags=["messages"])

PING_INTERVAL = 30


# --- REST endpoints ---


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute(
        """
        SELECT
            CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END AS partner_id,
            u.nickname AS partner_nickname,
            u.avatar_url AS partner_avatar,
            m.content AS last_message,
            m.created_at AS last_time,
            (
                SELECT COUNT(*) FROM messages m2
                WHERE m2.sender_id = (
                    CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
                ) AND m2.receiver_id = ? AND m2.is_read = 0
            ) AS unread_count
        FROM messages m
        JOIN users u ON u.id = CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END
        WHERE m.id = (
            SELECT MAX(m3.id) FROM messages m3
            WHERE (m3.sender_id = ? AND m3.receiver_id = u.id)
               OR (m3.sender_id = u.id AND m3.receiver_id = ?)
        )
        ORDER BY m.created_at DESC
        """,
        (user["id"], user["id"], user["id"], user["id"], user["id"], user["id"]),
    )
    rows = await cur.fetchall()
    return [
        ConversationOut(
            partner_id=r["partner_id"],
            partner_nickname=r["partner_nickname"],
            partner_avatar=r["partner_avatar"],
            last_message=r["last_message"],
            last_time=r["last_time"],
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
    db = await get_db()

    # Verify partner exists
    cur = await db.execute("SELECT id FROM users WHERE id = ?", (partner_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    offset = (page - 1) * page_size
    cur = await db.execute(
        """
        SELECT * FROM messages
        WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user["id"], partner_id, partner_id, user["id"], page_size, offset),
    )
    rows = await cur.fetchall()
    messages = [
        MessageOut(
            id=r["id"],
            sender_id=r["sender_id"],
            receiver_id=r["receiver_id"],
            content=r["content"],
            is_read=bool(r["is_read"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]

    # Mark as read
    await db.execute(
        "UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0",
        (partner_id, user["id"]),
    )
    await db.commit()

    return list(reversed(messages))


@router.post("/{partner_id}", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    partner_id: int,
    body: MessageCreate,
    user: dict = Depends(get_current_user),
):
    db = await get_db()

    # Verify partner exists
    cur = await db.execute("SELECT id FROM users WHERE id = ?", (partner_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if partner_id == user["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot message yourself")

    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "INSERT INTO messages (sender_id, receiver_id, content, created_at) VALUES (?, ?, ?, ?)",
        (user["id"], partner_id, body.content, now),
    )
    await db.commit()
    msg_id = cur.lastrowid

    msg_out = MessageOut(
        id=msg_id,
        sender_id=user["id"],
        receiver_id=partner_id,
        content=body.content,
        is_read=False,
        created_at=now,
    )

    # Push via WebSocket if partner is online
    await manager.send_to_user(partner_id, {
        "type": "chat",
        "id": msg_id,
        "sender_id": user["id"],
        "receiver_id": partner_id,
        "content": body.content,
        "is_read": False,
        "created_at": now,
    })

    # Also send back to sender for multi-tab sync
    await manager.send_to_user(user["id"], {
        "type": "chat",
        "id": msg_id,
        "sender_id": user["id"],
        "receiver_id": partner_id,
        "content": body.content,
        "is_read": False,
        "created_at": now,
    })

    return msg_out


@router.put("/read/{partner_id}")
async def mark_read(partner_id: int, user: dict = Depends(get_current_user)):
    db = await get_db()
    await db.execute(
        "UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0",
        (partner_id, user["id"]),
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE receiver_id = ? AND is_read = 0",
        (user["id"],),
    )
    row = await cur.fetchone()
    return {"count": row["cnt"]}


# --- WebSocket ---


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001)
        return

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception:
        await ws.close(code=4001)
        return

    await ws.accept()
    manager.connect(user_id, ws)

    # Send initial unread count
    db = await get_db()
    cur = await db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE receiver_id = ? AND is_read = 0",
        (user_id,),
    )
    row = await cur.fetchone()
    await manager.send_to_user(user_id, {"type": "unread_count", "count": row["cnt"]})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await manager.send_to_user(user_id, {"type": "pong"})

            elif msg_type == "chat":
                receiver_id = data.get("receiver_id")
                content = data.get("content", "").strip()
                if not receiver_id or not content:
                    await manager.send_to_user(user_id, {"type": "error", "detail": "Missing fields"})
                    continue

                now = datetime.now(timezone.utc).isoformat()
                cur = await db.execute(
                    "INSERT INTO messages (sender_id, receiver_id, content, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, receiver_id, content, now),
                )
                await db.commit()
                msg_id = cur.lastrowid

                chat_msg = {
                    "type": "chat",
                    "id": msg_id,
                    "sender_id": user_id,
                    "receiver_id": receiver_id,
                    "content": content,
                    "is_read": False,
                    "created_at": now,
                }
                await manager.send_to_user(receiver_id, chat_msg)
                await manager.send_to_user(user_id, chat_msg)

            elif msg_type == "mark_read":
                partner_id = data.get("partner_id")
                if partner_id:
                    await db.execute(
                        "UPDATE messages SET is_read = 1 WHERE sender_id = ? AND receiver_id = ? AND is_read = 0",
                        (partner_id, user_id),
                    )
                    await db.commit()

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id)
