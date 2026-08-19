"""T18 GE 评分榜回归。

覆盖:三维简单平均公式 (给分+收获+(5-工作量))/3、降序排序、
本专业禁选领域(blocked)不进榜、缺三维(老 5 星 only)不进榜、
top_tags 计数与排序。

评分榜只遍历静态 GE_COURSES 池(生产语义),所以测试必须用真实 GE code
(往 courses 表插对应行,courses.id = 去空格 code,对齐 ge_courses_for)。
选课:A=GEN 1022AEF(Area Studies,DSAI 可选)、B=GEN 2503NEF
(Mathematics & Statistics,DSAI 禁选)、C=GEN 2005ACF(Chinese Lang,可选)。
"""
import uuid

import pytest_asyncio

from backend.app.database import get_db
from backend.app.data.ge_courses import GE_COURSES

_S = uuid.uuid4().hex[:6]

# (去空格 id, code, field) — 取自 GE_COURSES 真实条目
A_ID, A_CODE, A_FIELD = "GEN1022AEF", "GEN 1022AEF", "Area Studies"
B_ID, B_CODE, B_FIELD = "GEN2503NEF", "GEN 2503NEF", "Mathematics & Statistics"
C_ID, C_CODE, C_FIELD = "GEN2005ACF", "GEN 2005ACF", "Chinese Language Studies & Literature"


@pytest_asyncio.fixture
async def ge_courses(client):
    """给三门真实 GE 课程补 courses 表行(FK 需要;已存在则跳过),测完删净评论。"""
    rows = [(A_ID, A_CODE), (B_ID, B_CODE), (C_ID, C_CODE)]
    async with get_db() as db:
        for cid, code in rows:
            await db.execute(
                """INSERT INTO courses (id, code, name, credits, category, year, semester)
                   VALUES ($1, $2, $3, 3, 'general-ed', 1, 'autumn')
                   ON CONFLICT (id) DO NOTHING""",
                cid, code, code,
            )
    yield {"a": A_ID, "b": B_ID, "c": C_ID}
    async with get_db() as db:
        for cid, _ in rows:
            await db.execute("DELETE FROM course_review_tags WHERE course_id = $1", cid)
            await db.execute("DELETE FROM course_reviews WHERE course_id = $1", cid)


async def test_ge_ranking_formula_order_and_blocked(client, make_user, ge_courses):
    _, t1 = await make_user(f"t18a_{_S}")
    _, t2 = await make_user(f"t18b_{_S}")
    _, t3 = await make_user(f"t18c_{_S}")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    h3 = {"Authorization": f"Bearer {t3}"}

    # A 两条三维:5/2/4 与 4/2/5 → 均分 t=4.5 w=2 g=4.5 → score=(4.5+4.5+3)/3=4.0
    await client.post(
        f"/api/v1/courses/{ge_courses['a']}/reviews",
        json={"rating_teaching": 5, "rating_workload": 2, "rating_gain": 4,
              "content": "a1", "tags": ["high_gain", "generous_grading"]},
        headers=h1,
    )
    await client.post(
        f"/api/v1/courses/{ge_courses['a']}/reviews",
        json={"rating_teaching": 4, "rating_workload": 2, "rating_gain": 5,
              "content": "a2", "tags": ["high_gain"]},
        headers=h2,
    )
    # B(DSAI 禁选领域)也打了分 → 不应进 DSAI 榜
    await client.post(
        f"/api/v1/courses/{ge_courses['b']}/reviews",
        json={"rating_teaching": 5, "rating_workload": 1, "rating_gain": 5, "content": "b"},
        headers=h1,
    )
    # C 只有老 5 星 → 无三维不进榜
    await client.post(
        f"/api/v1/courses/{ge_courses['c']}/reviews",
        json={"rating": 5, "content": "c"},
        headers=h3,
    )

    r = await client.get("/api/v1/courses/ge/ranking", params={"programme_code": "BSCHDSAIJ"})
    assert r.status_code == 200, r.text
    data = r.json()
    ids = [i["id"] for i in data["items"]]
    assert ge_courses["a"] in ids            # A 进榜
    assert ge_courses["b"] not in ids        # B:DSAI 禁选领域
    assert ge_courses["c"] not in ids        # C:缺三维
    item = next(i for i in data["items"] if i["id"] == ge_courses["a"])
    assert item["score"] == 4.0
    assert item["teaching_avg"] == 4.5
    assert item["workload_avg"] == 2.0
    assert item["gain_avg"] == 4.5
    assert item["review_count"] == 2
    # top_tags:high_gain(2) 在前、generous_grading(1) 在后
    assert [(t["tag"], t["count"]) for t in item["top_tags"]] == [
        ("high_gain", 2), ("generous_grading", 1),
    ]
    # 榜内降序
    scores = [i["score"] for i in data["items"]]
    assert scores == sorted(scores, reverse=True)

    # 换非数学禁选专业(ESGM 只禁 Environmental Studies)→ B 也进榜且 4.7 分最高
    r2 = await client.get("/api/v1/courses/ge/ranking", params={"programme_code": "BSCHESGMJ"})
    data2 = r2.json()
    ids2 = [i["id"] for i in data2["items"]]
    assert ge_courses["b"] in ids2
    top = data2["items"][0]
    if top["id"] == ge_courses["b"]:
        assert top["score"] == 4.7  # (5+5+(5-1))/3
    # C 依然不进(缺三维)


async def test_ge_ranking_cold_start_shape(client):
    """结构冒烟:无参数可调、空库不 500(冷启动 total 可为 0)。"""
    r = await client.get("/api/v1/courses/ge/ranking")
    assert r.status_code == 200
    body = r.json()
    assert {"programme_code", "total", "items"} <= set(body.keys())
