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
