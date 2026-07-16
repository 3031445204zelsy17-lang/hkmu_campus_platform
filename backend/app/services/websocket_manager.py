import json
from fastapi import WebSocket


class ConnectionManager:
    """Tracks each user's WebSocket connections — multi-device / multi-tab safe.

    A user maps to a SET of sockets, so opening a second tab no longer evicts
    the first. disconnect() removes ONE specific socket (by instance), so when
    a stale tab closes it cannot drop a newer tab's connection. send_to_user()
    fans out to every live socket of that user.
    """

    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = {}

    def connect(self, user_id: int, ws: WebSocket) -> None:
        self._connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        """Remove a single socket. Drops the user entry once the set is empty."""
        conns = self._connections.get(user_id)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            del self._connections[user_id]

    async def send_to_user(self, user_id: int, data: dict) -> None:
        """Deliver to every live socket of the user; prunes dead ones."""
        conns = self._connections.get(user_id)
        if not conns:
            return
        dead: list[WebSocket] = []
        for ws in list(conns):  # snapshot — set may mutate via disconnect below
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_unread_count(self, user_id: int, count: int) -> None:
        await self.send_to_user(user_id, {"type": "unread_count", "count": count})

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))


manager = ConnectionManager()
