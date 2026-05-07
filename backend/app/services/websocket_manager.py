import json
from fastapi import WebSocket
from typing import Optional


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, WebSocket] = {}

    def connect(self, user_id: int, ws: WebSocket):
        self._connections[user_id] = ws

    def disconnect(self, user_id: int):
        self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, data: dict):
        ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self._connections.pop(user_id, None)

    async def broadcast_unread_count(self, user_id: int, count: int):
        await self.send_to_user(user_id, {"type": "unread_count", "count": count})

    def is_online(self, user_id: int) -> bool:
        return user_id in self._connections


manager = ConnectionManager()
