"""GET /courses/{id} 的 GE 官方信息富化(ge 子对象)。

纯函数部分无 DB;端点部分走 client fixture(需 DATABASE_URL 指向可达 Postgres,
同 test_ge_ranking 先例:给 GE code 补 courses 表行,id=去空格码)。
"""
import uuid

import pytest_asyncio

from backend.app.database import get_db
from backend.app.routers.courses import _ge_info_for

_S = uuid.uuid4().hex[:6]


def test_ge_info_pure_helper_fields():
    out = _ge_info_for("GEN1042ECF")
    assert out is not None
    assert out.level == 1000 and out.moi == "chinese"
    assert out.school == "E&L" and out.school_name == "教育及語文學院"
    assert out.terms == ["autumn", "spring"]


def test_ge_info_school_follows_catalog_print():
    """官方文件内部出入:GEN 1510NCF 课码字母是 N,但目录印「科技學院」——
    学院缩写按目录打印反查,展示以目录为准。"""
    out = _ge_info_for("GEN1510NCF")
    assert out.school == "S&T" and out.school_name == "科技學院"
    out2 = _ge_info_for("GEN2501NEF")
    assert out2.school == "S&T"


def test_ge_info_excluded_and_description():
    out = _ge_info_for("GEN2255ECF")
    assert out.level == 2000 and out.moi == "chinese"
    assert "PTH 3255ECF" in out.excluded
    assert out.description.startswith("本科旨在")


def test_ge_info_none_for_non_ge():
    assert _ge_info_for("COMP1080SEF") is None
    assert _ge_info_for("nosuch") is None


@pytest_asyncio.fixture
async def ge_course_rows(client):
    """补 courses 表行(ON CONFLICT 幂等;GE 行本就该在种子数据里,不删——
    同 test_ge_ranking 先例,XYZ0001 是无害的测试残留)。"""
    rows = [
        ("GEN2255ECF", "GEN 2255ECF"),
        ("GEN1100SEW", "GEN 1100SEW"),
        ("XYZ0001", "XYZ 0001"),
    ]
    async with get_db() as db:
        for cid, code in rows:
            await db.execute(
                """INSERT INTO courses (id, code, name, credits, category, year, semester)
                   VALUES ($1, $2, $3, 3, 'general-ed', 0, 'any')
                   ON CONFLICT (id) DO NOTHING""",
                cid, code, code,
            )
    yield rows


async def test_course_detail_endpoint_ge_block(client, ge_course_rows):
    r = await client.get("/api/v1/courses/GEN2255ECF")
    assert r.status_code == 200
    ge = r.json()["ge"]
    assert ge["level"] == 2000 and ge["moi"] == "chinese"
    assert ge["school_name"] == "教育及語文學院"
    assert "PTH 3255ECF" in ge["excluded"]
    assert ge["description"].startswith("本科旨在")
    assert set(ge["terms"]) <= {"autumn", "spring", "summer"}


async def test_course_detail_endpoint_non_ge_has_no_ge(client, ge_course_rows):
    r = await client.get("/api/v1/courses/XYZ0001")
    assert r.status_code == 200
    assert r.json()["ge"] is None


async def test_ge_list_endpoint_small_fields(client):
    """/courses/ge 列表带小字段但不含长文本(description 只走详情)。"""
    r = await client.get("/api/v1/courses/ge")
    assert r.status_code == 200
    courses = r.json()["courses"]
    assert courses, "GE 池不应为空"
    by_id = {c["code"]: c for c in courses}
    c = by_id["GEN 1042ECF"]
    assert c["credits"] == 3 and c["level"] == 1000 and c["moi"] == "chinese"
    assert c["excluded"] == []
    assert "description" not in c and "school_name" not in c
