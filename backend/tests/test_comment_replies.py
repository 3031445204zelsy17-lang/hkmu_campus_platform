"""Two-layer comment replies + comment images (community comments upgrade).

Covers the behaviours introduced with parent_id / reply_to_user_id / image_url
on comments:

  * replies nest under their top-level parent in list_comments (two-layer
    tree, replies carry reply_to_nickname for the "回复 @xxx" display)
  * replying to a REPLY hoists to the top-level thread while keeping the
    immediate target as reply_to (strict two layers, WeChat/微博 盖楼 style)
  * image_url must live in our own uploads bucket — POST /upload is the only
    creator of those URLs and always runs the img_sec_check gate, so a
    foreign URL (never scanned) must be rejected
  * content or image_url — at least one — is required (image-only allowed)
"""
import uuid

from backend.app.config import SUPABASE_URL
from backend.app.services.storage_service import BUCKET

_STORAGE_PREFIX = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _make_post(client, token):
    resp = await client.post(
        "/api/v1/posts",
        json={"title": "t", "content": "c", "category": "discussion"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _comment(client, token, post_id, **body):
    return await client.post(
        f"/api/v1/posts/{post_id}/comments", json=body, headers=_auth(token)
    )


async def test_reply_nests_under_top_level_parent(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"cmt_{suffix}")
    post_id = await _make_post(client, token)

    top = await _comment(client, token, post_id, content="top")
    assert top.status_code == 201, top.text
    top_id = top.json()["id"]

    reply = await _comment(client, token, post_id, content="reply", parent_id=top_id)
    assert reply.status_code == 201, reply.text
    body = reply.json()
    assert body["parent_id"] == top_id
    assert body["replies"] == []

    listing = await client.get(f"/api/v1/posts/{post_id}/comments")
    items = listing.json()["items"]
    assert len(items) == 1, "reply must be nested, not a second top-level row"
    assert items[0]["id"] == top_id
    assert [r["id"] for r in items[0]["replies"]] == [body["id"]]
    assert items[0]["replies"][0]["reply_to_nickname"] is not None
    # total counts top-level + replies (stays in sync with comments_count)
    assert listing.json()["total"] == 2


async def test_reply_to_reply_hoists_to_top_level_thread(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _u1, token1 = await make_user(f"cmta_{suffix}")
    # make_user registers nickname == username, so the reply_to_nickname
    # assertion below can check the plain username without another API hop
    _u2, token2 = await make_user(f"cmtb_{suffix}")
    post_id = await _make_post(client, token1)

    top = (await _comment(client, token1, post_id, content="top")).json()
    r1 = (await _comment(client, token2, post_id, content="r1", parent_id=top["id"])).json()
    assert r1["parent_id"] == top["id"]

    # replying to r1 → attaches to the TOP-LEVEL thread, reply_to = r1's author
    r2 = await _comment(client, token1, post_id, content="r2", parent_id=r1["id"])
    assert r2.status_code == 201, r2.text
    assert r2.json()["parent_id"] == top["id"], "reply-to-reply must hoist one layer up"
    assert r2.json()["reply_to_nickname"] == f"cmtb_{suffix}"

    listing = await client.get(f"/api/v1/posts/{post_id}/comments")
    items = listing.json()["items"]
    assert len(items) == 1
    assert len(items[0]["replies"]) == 2, "r1 and r2 are siblings under the thread"
    assert listing.json()["total"] == 3


async def test_reply_from_another_post_is_rejected(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"cmtp_{suffix}")
    post_a = await _make_post(client, token)
    post_b = await _make_post(client, token)
    top_a = (await _comment(client, token, post_a, content="on A")).json()

    cross = await _comment(client, token, post_b, content="cross", parent_id=top_a["id"])
    assert cross.status_code == 404, cross.text


async def test_comment_image_must_live_in_our_bucket(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"cmti_{suffix}")
    post_id = await _make_post(client, token)

    foreign = await _comment(
        client, token, post_id,
        content="x", image_url="https://evil.example.com/pixel.png",
    )
    assert foreign.status_code == 400, foreign.text

    ok = await _comment(
        client, token, post_id,
        image_url=f"{_STORAGE_PREFIX}comments/1/abc@360.jpg",
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["image_url"].startswith(_STORAGE_PREFIX)
    # image-only comment round-trips with empty text
    assert ok.json()["content"] == ""


async def test_comment_requires_content_or_image(client, make_user):
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"cmte_{suffix}")
    post_id = await _make_post(client, token)

    empty = await _comment(client, token, post_id, content="   ")
    assert empty.status_code == 400, empty.text

    blank = await _comment(client, token, post_id)
    assert blank.status_code == 400, blank.text
