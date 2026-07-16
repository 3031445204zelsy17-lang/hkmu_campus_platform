"""E — backend stores post text RAW (security roadmap E, PR #28).

Escaping is done only at the render layer (frontend textContent / escapeHtml).
The backend must store AND return user text verbatim — never html-escaped. If
someone re-adds html.escape / a sanitize step on the backend, the returned
content becomes ``&lt;script&gt;...`` and this test goes red. (Double-escaping
was the exact regression PR #28 removed.)

Web users (no openid) are skipped by audit_user_text, so a benign-but-spicy
string is accepted as-is — letting us assert byte-for-byte raw round-trip.
"""
import uuid


async def test_post_content_round_trips_raw_not_html_escaped(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"writer_{suffix}")

    raw = '<script>alert(1)</script> & "q" \'s\' <b>hi</b>'
    create = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": raw, "category": "chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201, create.text
    post_id = create.json()["id"]

    got = await client.get(f"/api/v1/posts/{post_id}")
    assert got.status_code == 200, got.text
    assert got.json()["content"] == raw, (
        "backend must return raw text; got html-escaped content (double-escape regression)"
    )
