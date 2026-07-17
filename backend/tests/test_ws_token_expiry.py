"""[2] WebSocket access-token expiry regression.

ws_endpoint captures the JWT ``exp`` at connect time and re-checks it on every
inbound frame via ``access_token_expired``; once the access token has expired
mid-connection the socket is torn down (no chat / mark_read processed past
expiry). These tests lock the pure helper that drives that check — the WS loop
itself has no in-process client harness (see conftest), so the behaviour is
unit-tested at the function the loop calls each iteration.
"""
import time

from backend.app.services.auth_service import access_token_expired


async def test_expired_when_exp_in_past():
    assert access_token_expired(time.time() - 1) is True


async def test_not_expired_when_exp_in_future():
    assert access_token_expired(time.time() + 3600) is False


async def test_not_expired_when_exp_missing():
    """A token without exp never expires by JWT rules (jose only enforces exp
    when present); the helper must not force-close such sockets."""
    assert access_token_expired(None) is False


async def test_not_expired_when_exp_malformed():
    # a non-numeric exp never occurs in practice (jose enforces NumericDate),
    # but the helper must not crash on garbage — treat it as "not expired" so a
    # bad payload doesn't force-close a socket that jose already accepted.
    assert access_token_expired("not-a-number") is False
    assert access_token_expired([1, 2]) is False
