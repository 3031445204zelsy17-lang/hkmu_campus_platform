"""T14 课评三维 + 避坑标签投票回归。

覆盖:三维创建/老 5 星兼容/至少一维校验/标签白名单、列表带三维+作者标签、
标签投票-幂等-撤票-匿名视角、review-stats 均分。
课程行由测试自插(不依赖 seed),沿用 conftest 的 client/make_user
(asyncio_mode=auto,无需 marker)。
"""
import uuid

import pytest_asyncio

_S = uuid.uuid4().hex[:6]  # 每次运行独占用户名,防重跑 409

from backend.app.database import get_db


@pytest_asyncio.fixture
async def course_id(client):
    """插一门独占测试课程(随机后缀防撞),测试完删干净。"""
    cid = f"T14T{uuid.uuid4().hex[:8].upper()}"
    async with get_db() as db:
        await db.execute(
            """INSERT INTO courses (id, code, name, credits, category, year, semester)
               VALUES ($1, $1, 'T14 Test Course', 3, 'core', 1, 'autumn')""",
            cid,
        )
    yield cid
    async with get_db() as db:
        await db.execute("DELETE FROM course_review_tags WHERE course_id = $1", cid)
        await db.execute("DELETE FROM course_reviews WHERE course_id = $1", cid)
        await db.execute("DELETE FROM courses WHERE id = $1", cid)


async def test_review_3d_create_and_list(client, make_user, course_id):
    _, token = await make_user(f"t14x_t14a{_S}")
    h = {"Authorization": f"Bearer {token}"}

    # 纯三维 + 标签(含重复 → 去重)
    r = await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={
            "rating_teaching": 5, "rating_workload": 2, "rating_gain": 4,
            "content": "给分大方", "tags": ["generous_grading", "heavy_workload", "generous_grading"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rating_teaching"] == 5
    assert body["rating_workload"] == 2
    assert body["rating_gain"] == 4
    assert body["tags"] == ["generous_grading", "heavy_workload"]

    # 列表带三维 + 作者标签
    lst = await client.get(f"/api/v1/courses/{course_id}/reviews")
    assert lst.status_code == 200
    item = lst.json()["items"][0]
    assert item["rating_teaching"] == 5
    assert set(item["tags"]) == {"generous_grading", "heavy_workload"}


async def test_review_validation(client, make_user, course_id):
    _, token = await make_user(f"t14x_t14b{_S}")
    h = {"Authorization": f"Bearer {token}"}

    # 老 5 星单参兼容(rating only)
    r = await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating": 4, "content": "老格式"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 4
    assert r.json()["rating_teaching"] is None

    # 全空评分 → 422
    r = await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"content": "没评分"},
        headers=h,
    )
    assert r.status_code == 422

    # 未知标签 → 422
    r = await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating": 3, "content": "x", "tags": ["no_such_tag"]},
        headers=h,
    )
    assert r.status_code == 422

    # 同人同课重复评论 → 409
    r = await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating": 3, "content": "再来一条"},
        headers=h,
    )
    assert r.status_code == 409


async def test_tag_vote_flow(client, make_user, course_id):
    uid, token = await make_user(f"t14x_t14c{_S}")
    h = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/courses/{course_id}/review-tags"

    # 投票 → 201,重复投幂等
    assert (await client.post(f"{base}/high_gain", headers=h)).status_code == 201
    assert (await client.post(f"{base}/high_gain", headers=h)).status_code == 201
    assert (await client.post(f"{base}/open_book", headers=h)).status_code == 201

    # 登录视角:计数 + voted
    mine = await client.get(base, headers=h)
    assert mine.status_code == 200
    data = mine.json()
    assert data["total_votes"] == 2
    by_tag = {t["tag"]: t for t in data["tags"]}
    assert by_tag["high_gain"]["count"] == 1  # 重复投没有 +1
    assert by_tag["high_gain"]["voted"] is True

    # 匿名视角:voted 恒 False
    anon = await client.get(base)
    assert {t["tag"]: t["voted"] for t in anon.json()["tags"]} == {
        "high_gain": False, "open_book": False,
    }

    # 白名单外 → 422
    assert (await client.post(f"{base}/nope", headers=h)).status_code == 422

    # 撤票 → 计数回落
    assert (await client.delete(f"{base}/high_gain", headers=h)).status_code == 204
    after = (await client.get(base, headers=h)).json()
    assert {t["tag"] for t in after["tags"]} == {"open_book"}
    assert after["total_votes"] == 1


async def test_review_stats_averages(client, make_user, course_id):
    _, t1 = await make_user(f"t14x_t14d{_S}")
    _, t2 = await make_user(f"t14x_t14e{_S}")
    _, t3 = await make_user(f"t14x_t14f{_S}")

    # 三条:5/2/4(三维)、4(老5星)、3/4/3(三维)
    await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating_teaching": 5, "rating_workload": 2, "rating_gain": 4, "content": "a"},
        headers={"Authorization": f"Bearer {t1}"},
    )
    await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating": 4, "content": "b"},
        headers={"Authorization": f"Bearer {t2}"},
    )
    await client.post(
        f"/api/v1/courses/{course_id}/reviews",
        json={"rating_teaching": 3, "rating_workload": 4, "rating_gain": 3, "content": "c"},
        headers={"Authorization": f"Bearer {t3}"},
    )

    stats = await client.get(f"/api/v1/courses/{course_id}/review-stats")
    assert stats.status_code == 200
    s = stats.json()
    assert s["review_count"] == 3
    assert s["teaching_avg"] == 4.0   # (5+3)/2 — 老5星不进三维均值
    assert s["workload_avg"] == 3.0   # (2+4)/2
    assert s["gain_avg"] == 3.5       # (4+3)/2
    assert s["rating_avg"] == 4.0     # 只有一条老 5 星

    # 不存在的课程 → 404
    assert (await client.get("/api/v1/courses/NOPE9999/review-stats")).status_code == 404
