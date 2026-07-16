"""B — WebSocket ConnectionManager multi-device regression tests (security roadmap B).

Pure unit tests, no DB / no network. Locks the fix in PR #25: a user maps to a
SET of sockets, so closing one tab no longer evicts another, and a dead socket
is pruned without dropping live ones. If someone reverts `_connections` to a
single-socket dict these tests go red.

Run: pytest backend/tests/test_websocket_manager.py -q
"""
import asyncio

from backend.app.services.websocket_manager import ConnectionManager


class FakeWS:
    """Minimal stand-in for fastapi.WebSocket — only send_json is exercised."""

    def __init__(self, name: str = "ws", *, fail: bool = False):
        self.name = name
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        if self.fail:
            raise RuntimeError("simulated dead socket")
        self.sent.append(data)

    def __repr__(self) -> str:
        return f"<FakeWS {self.name}>"


def test_multi_device_both_online():
    """Two tabs of the same user coexist (the core multi-device invariant)."""
    m = ConnectionManager()
    tab1, tab2 = FakeWS("tab1"), FakeWS("tab2")
    m.connect(1, tab1)
    m.connect(1, tab2)
    assert m.is_online(1)
    assert len(m._connections[1]) == 2


def test_disconnect_old_tab_keeps_new_tab():
    """B's headline fix: closing the OLD tab must NOT drop the NEW tab.

    The pre-fix single-socket dict disconnected the user entirely on any close.
    """
    m = ConnectionManager()
    old_tab, new_tab = FakeWS("old"), FakeWS("new")
    m.connect(1, old_tab)
    m.connect(1, new_tab)
    m.disconnect(1, old_tab)  # stale tab closes
    assert m.is_online(1), "newer tab must survive the older tab closing"
    assert new_tab in m._connections[1]
    assert old_tab not in m._connections[1]


def test_disconnect_last_clears_entry():
    m = ConnectionManager()
    ws = FakeWS("only")
    m.connect(1, ws)
    m.disconnect(1, ws)
    assert not m.is_online(1)
    assert 1 not in m._connections


def test_disconnect_unknown_user_is_noop():
    m = ConnectionManager()
    m.disconnect(999, FakeWS())  # never connected — must not raise
    assert not m.is_online(999)


def test_disconnect_unrelated_socket_keeps_connected_one():
    """Disconnecting a socket instance that isn't tracked leaves the real one."""
    m = ConnectionManager()
    real = FakeWS("real")
    m.connect(1, real)
    m.disconnect(1, FakeWS("not-the-same-instance"))
    assert m.is_online(1)
    assert real in m._connections[1]


def test_send_to_user_fans_out_to_all_sockets():
    m = ConnectionManager()
    a, b = FakeWS("a"), FakeWS("b")
    m.connect(1, a)
    m.connect(1, b)
    asyncio.run(m.send_to_user(1, {"type": "msg", "v": 1}))
    assert a.sent == [{"type": "msg", "v": 1}]
    assert b.sent == [{"type": "msg", "v": 1}]


def test_send_to_user_prunes_dead_keeps_live():
    """A dead socket (send_json raises) is pruned, and must not kill the live one.

    Pre-fix behaviour could drop the user's only remaining connection when
    pruning. send_to_user must isolate failures per socket.
    """
    m = ConnectionManager()
    live, dead = FakeWS("live"), FakeWS("dead", fail=True)
    m.connect(1, live)
    m.connect(1, dead)
    asyncio.run(m.send_to_user(1, {"x": 1}))
    assert live.sent == [{"x": 1}]  # live socket still received
    assert m.is_online(1)
    assert live in m._connections[1]
    assert dead not in m._connections[1]  # dead pruned


def test_send_to_user_unknown_user_is_noop():
    m = ConnectionManager()
    asyncio.run(m.send_to_user(999, {"x": 1}))  # must not raise


def test_users_are_isolated():
    m = ConnectionManager()
    ua, ub = FakeWS("userA"), FakeWS("userB")
    m.connect(1, ua)
    m.connect(2, ub)
    asyncio.run(m.send_to_user(1, {"to": "A"}))
    assert ua.sent == [{"to": "A"}]
    assert ub.sent == []  # user B's socket did not receive user A's message
