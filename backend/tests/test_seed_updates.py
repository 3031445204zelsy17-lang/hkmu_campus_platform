"""批次 5 seed 修复回归:补池学分存量行 UPDATE 层 + 裸码课名回填三位数码。

背景(坑 11/12,azure-deploy-method memory):seed 的 INSERT 全是 ON CONFLICT
DO NOTHING + existing_ids 跳过,prod 预存行(v1.11 REST 导入时代)永远绕过
INSERT 路径的学分/课名裁定,曾残留 9 门学分错(GIP100/101/200/300/400=0、
COUN4008=6、SOCI4004/SOSC2002/POLS4009=3)+ 裸码/Wingdings 脏名,靠手工
UPDATE 收掉。本测试预埋错值行,验证 apply_existing_row_fixes 的 UPDATE 层
真实命中 —— 把批次 1 的「预埋错值→亲测红」手工动作固化成 CI。

需要 DATABASE_URL(CI deploy workflow / 本地配方见 memory local-pytest-recipe)。
"""
import importlib.util
import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="需要 DATABASE_URL(CI/本地配方)"
)


def _seed_module():
    """importlib 加载 scripts/seed_courses.py(仅用其常量与修正层函数,不跑 seed)。"""
    spec = importlib.util.spec_from_file_location(
        "seed_courses_under_test", REPO / "scripts" / "seed_courses.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest_asyncio.fixture
async def conn(client):
    """client 先跑 init_db 建表;本 fixture 给 seed 修正层一条独立连接(同 loop)。"""
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        yield c
    finally:
        await c.close()


# 预埋错值行:id → (错学分, 脏名形态)。目标值在 ADDITION_CREDITS/
# POOL_SEED_CREDITS(学分)与 COURSE_NAME_BACKFILL(课名),全部官方 advice 行口径。
PUA = chr(0xF0A0)  # Wingdings 对勾(prod 脏名实测形态,私用区)
WRONG_ROWS = {
    "GIP100BEF": (3, "GIP100BEF"),    # 三位裸码·不空格(旧 [0-9]{4} 正则漏网形态)
    "GIP101BEF": (3, "GIP 101BEF"),   # 三位裸码·空格
    "GIP200BEF": (3, "GIP 200BEF"),
    "GIP201BEF": (3, "GIP 201BEF"),
    "GIP300BEF": (3, "GIP 300BEF"),
    "GIP400BEF": (3, "GIP 400BEF"),
    "COUN4008AEF": (3, "Practicum" + PUA),   # 官方 6;脏名混私用区字符
    "SOCI4004AEF": (6, "SOCI 4004AEF"),      # 四位裸码·空格(旧正则可命中,回归守卫)
    "SOSC2002AEF": (6, "SOSC 2002AEF"),
    "POLS4009AEF": (6, "POLS 4009AEF"),
}
# 真名行:学分错、名字是真名(非裸码)→ 学分必须被修,名字必须原样保留
REAL_NAME_KEEP = ("SOCI4004AEF", "A Real Catalogue Title")


async def _seed_wrong_rows(c, mod):
    for cid, (credits, name) in WRONG_ROWS.items():
        await c.execute(
            """INSERT INTO courses (id, code, name, credits, category, year,
                                    semester, prerequisites, description)
               VALUES ($1, $2, $3, $4, 'elective', 1, 'autumn', '[]', 'test')
               ON CONFLICT (id) DO UPDATE
               SET credits = EXCLUDED.credits, name = EXCLUDED.name""",
            cid, mod._spaced_code(cid), name, credits,
        )


async def test_spaced_code_handles_three_digit_codes():
    mod = _seed_module()
    assert mod._spaced_code("GIP100BEF") == "GIP 100BEF"   # 批次 5 修复点
    assert mod._spaced_code("GIP 101BEF") == "GIP 101BEF"
    assert mod._spaced_code("COMP1080SEF") == "COMP 1080SEF"  # 四位不回归


async def test_update_layer_hits_preexisting_wrong_rows(conn):
    """预埋 v1.11 时代错值行(绕过 INSERT 路径)→ 修正层必须命中:
    补池学分手工裁定的 10 门全对、裸码/PUA 脏名回填、真名不覆盖。"""
    mod = _seed_module()
    # 现场快照(测完恢复,不污染共享测试库)
    ids = list(WRONG_ROWS)
    before = {
        r["id"]: dict(r)
        for r in await conn.fetch(
            "SELECT id, name, credits FROM courses WHERE id = ANY($1::text[])", ids
        )
    }
    try:
        await _seed_wrong_rows(conn, mod)
        # SOCI4004AEF 用真名形态再验「不覆盖真名」
        await conn.execute(
            "UPDATE courses SET name = $1 WHERE id = $2", REAL_NAME_KEEP[1], REAL_NAME_KEEP[0]
        )
        counts = await mod.apply_existing_row_fixes(conn)

        targets = {**mod.ADDITION_CREDITS, **mod.POOL_SEED_CREDITS}
        rows = {
            r["id"]: dict(r)
            for r in await conn.fetch(
                "SELECT id, name, credits FROM courses WHERE id = ANY($1::text[])", ids
            )
        }
        # ① 10 门学分全部修到官方值(含 prod 手工收掉的 9 门 + GIP201BEF 同族 0)
        bad = {cid: (rows[cid]["credits"], targets[cid])
               for cid in ids if rows[cid]["credits"] != targets[cid]}
        assert not bad, f"补池学分 UPDATE 层漏修:{bad}(坑 12 的 prod 残留形态)"
        # ② 裸码(三位/四位、空格/不空格)与 PUA 脏名 → 官方标题回填
        unbackfilled = {
            cid: rows[cid]["name"]
            for cid in ids
            if cid != REAL_NAME_KEEP[0]
            and rows[cid]["name"] != mod.COURSE_NAME_BACKFILL.get(cid)
        }
        assert not unbackfilled, f"裸码/脏码课名回填漏命中:{unbackfilled}"
        # ③ 真名行:学分修了,名字原样(回填层只动裸码/脏码行)
        assert rows[REAL_NAME_KEEP[0]]["name"] == REAL_NAME_KEEP[1]
        # ④ 计数自证:本批至少修 10 学分 + 9 名字(SOCI4004AEF 是真名不算回填)
        assert counts["pool_credit_fixed"] >= len(WRONG_ROWS)
        assert counts["names_fixed"] >= len(WRONG_ROWS) - 1
    finally:
        for cid, row in before.items():
            await conn.execute(
                "UPDATE courses SET name = $1, credits = $2 WHERE id = $3",
                row["name"], row["credits"], cid,
            )
        gone = [cid for cid in ids if cid not in before]
        if gone:
            await conn.execute("DELETE FROM courses WHERE id = ANY($1::text[])", gone)


async def test_update_layer_idempotent_on_rerun(conn):
    """幂等:修正层跑第二遍,零命中(重跑 seed 可重现 prod 终态,不反复改写)。"""
    mod = _seed_module()
    ids = list(WRONG_ROWS)
    before = {
        r["id"]: dict(r)
        for r in await conn.fetch(
            "SELECT id, name, credits FROM courses WHERE id = ANY($1::text[])", ids
        )
    }
    try:
        await _seed_wrong_rows(conn, mod)
        await mod.apply_existing_row_fixes(conn)
        second = await mod.apply_existing_row_fixes(conn)
        assert second == {"names_fixed": 0, "pool_credit_fixed": 0, "credit_fixed": 0}, (
            f"第二遍应零命中(幂等),实得 {second}"
        )
    finally:
        for cid, row in before.items():
            await conn.execute(
                "UPDATE courses SET name = $1, credits = $2 WHERE id = $3",
                row["name"], row["credits"], cid,
            )
        gone = [cid for cid in ids if cid not in before]
        if gone:
            await conn.execute("DELETE FROM courses WHERE id = ANY($1::text[])", gone)
