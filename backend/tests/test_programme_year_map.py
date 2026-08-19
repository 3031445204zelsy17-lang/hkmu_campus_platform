"""per-专业年份映射 · 批次 2 断言(验收标准.md 批次 2)。

架构要求(复核报告第四节):courses 表全局单一年份列被 per-(专业, 课) 映射
取代 —— 映射按当前专业解析,全局 course.year 降级为回退值;用户 schedule
覆盖仍然最高优先(前端三层链:schedule > 专业映射 > 全局列)。

本文件两段:
  · 2a 架构段(数据无关):空映射 = 纯回退不改既有行为;别名归一;补池并入幂等。
  · 2b 数据段(灌数后生效):155 硬错位闭环 / BBAHMGTJ Y1 ≥4 项 / UNI3002BEW
    撞车解决 / GIP 补池 0 学分 / 课名回填。数据源锁定 verify/ 产物(入库);
    results/ 旧 JSON 被 CI 断言禁止引用。
"""
import json
from pathlib import Path

import pytest

from backend.app.data import programmes as programmes_mod
from backend.app.data import programme_year_map as pym
from backend.app.data.programmes import PROGRAMMES, PROGRAMME_ALIASES

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "docs/ops/选课选课/advice_sheets/verify"

HAS_MAP_DATA = bool(pym.PROGRAMME_YEAR_MAP)


# ── 2a 架构:映射 → 载荷管线(数据无关,monkeypatch 桩验证)──────────────────

def test_payload_fields_exist_and_empty_map_is_pure_fallback():
    """空映射时 ProgrammeOut.placements/ge_slots = 空 → 前端回退全局 year。"""
    from backend.app.routers import courses
    out = courses._programme_to_out("BSCHDSAIJ", PROGRAMMES["BSCHDSAIJ"])
    assert out.placements == {} and out.ge_slots == []
    dumped = out.model_dump()
    assert dumped["placements"] == {} and dumped["ge_slots"] == []


def test_placements_resolved_per_programme_and_alias(monkeypatch):
    """映射按当前专业取;别名码(BAPHBMJ1)归一到主码,不重复灌数据。"""
    from backend.app.routers import courses
    stub_map = {"BAPHBMJ": {"XYZ1001AEF": {"year": 2, "term": "spring"}}}
    stub_slots = {"BAPHBMJ": [{"year": 1, "term": "autumn"}]}
    monkeypatch.setattr(courses, "PROGRAMME_YEAR_MAP", stub_map)
    monkeypatch.setattr(courses, "PROGRAMME_GE_SLOTS", stub_slots)

    main = courses._programme_to_out("BAPHBMJ", PROGRAMMES["BAPHBMJ"])
    assert main.placements == stub_map["BAPHBMJ"]
    assert main.ge_slots == stub_slots["BAPHBMJ"]

    alias = courses._programme_to_out("BAPHBMJ1", PROGRAMMES["BAPHBMJ1"])
    assert alias.placements == stub_map["BAPHBMJ"], "别名码必须共享主码映射"
    assert alias.ge_slots == stub_slots["BAPHBMJ"]

    other = courses._programme_to_out("BSCHDSAIJ", PROGRAMMES["BSCHDSAIJ"])
    assert other.placements == {}, "映射不得跨专业外溢(批次 2 根修的撞车病)"


def test_pool_additions_merge_idempotent():
    """补池并入:目标类目追加、幂等(重跑不重复);未知/coming_soon 专业跳过。"""
    prog = PROGRAMMES["BAHCAMDJ"]  # 不在 23 个补池专业里,桶干净
    core = prog["categories"]["core"]["courses"]
    base_n = len(core)
    additions = {"BAHCAMDJ": {"core": ["TEST0001AEF"]},
                 "NOSUCHPROG": {"core": ["TEST0002AEF"]}}
    try:
        programmes_mod._apply_pool_additions(additions)
        programmes_mod._apply_pool_additions(additions)  # 幂等:二次并入零增量
        assert core[base_n:] == ["TEST0001AEF"]
        assert "NOSUCHPROG" not in PROGRAMMES, "未知专业码不得被静默建桶"
    finally:
        del core[base_n:]


def test_year_map_module_shape():
    """生成模块五个导出齐全;映射键落在 PROGRAMMES、值形状合法。"""
    for attr in ("PROGRAMME_YEAR_MAP", "PROGRAMME_GE_SLOTS",
                 "COURSE_NAME_BACKFILL", "POOL_ADDITIONS", "ADDITION_CREDITS"):
        assert hasattr(pym, attr), f"programme_year_map 缺导出 {attr}"
    for prog, entries in pym.PROGRAMME_YEAR_MAP.items():
        assert prog in PROGRAMMES or prog in PROGRAMME_ALIASES, \
            f"映射键 {prog} 不在 PROGRAMMES(生成器 join 坏了?)"
        for course, pl in entries.items():
            assert set(pl) == {"year", "term"}, f"{prog}/{course} 形状坏:{pl}"
            assert 1 <= pl["year"] <= 4
            assert pl["term"] in ("autumn", "spring", "summer")


# ── 2b 数据:以下断言在映射灌数(生成器产物)后生效 ──────────────────────────

def _final_result2() -> dict:
    return json.loads((VERIFY / "final_result2.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(not HAS_MAP_DATA, reason="批次 2b 未灌数(空骨架阶段)")
class TestBatch2bData:
    def test_hard_mismatch_closure(self):
        """155 硬错位闭环:hard 清单每条的映射年份必须落在官方年集内。
        豁免:该课在 my_rows 无任何行(解析盲区,回退全局列)——当前仅
        BASCHRAEJ/COMP2083SEF 一条;新增豁免必须在验收记录里说明依据。"""
        hard = _final_result2()["hard"]
        allowed_missing = {("BASCHRAEJ", "COMP2083SEF")}
        misses = []
        for p, c, _my, official in hard:
            got = pym.PROGRAMME_YEAR_MAP.get(p, {}).get(c)
            if got is None:
                if (p, c) not in allowed_missing:
                    misses.append((p, c, "无映射", official))
            elif got["year"] not in official:
                misses.append((p, c, got["year"], official))
        assert not misses, f"硬错位未闭环 {len(misses)} 条(前 10):{misses[:10]}"

    def test_uni3002_collision_resolved(self):
        """旗舰撞车案:UNI3002BEW 在 DSAI=Y4、其他多数专业=Y3,同一映射并存。"""
        assert pym.PROGRAMME_YEAR_MAP["BSCHDSAIJ"]["UNI3002BEW"]["year"] == 4
        years = {p: e["UNI3002BEW"]["year"] for p, e in pym.PROGRAMME_YEAR_MAP.items()
                 if "UNI3002BEW" in e}
        assert len(years) >= 10, f"UNI3002BEW 覆盖专业过少:{len(years)}"
        assert sum(1 for y in years.values() if y != 4) >= 8, \
            "外溢撞车未解决:除 DSAI 外应有大量专业拿到非 4 年官方值"

    def test_bbahmgtj_y1_payload(self):
        """商院抽查:BBAHMGTJ Y1 载荷 ≥4 项(BUS2000+UNI+GIP+GE 占位,对照官方 Yr1 表)。"""
        ym = pym.PROGRAMME_YEAR_MAP["BBAHMGTJ"]
        assert ym["BUS2000BEF"] == {"year": 1, "term": "autumn"}
        assert ym["UNI1012ABW"]["year"] == 1
        assert ym["GIP100BEF"] == {"year": 1, "term": "autumn"}
        assert {"year": 1, "term": "autumn"} in pym.PROGRAMME_GE_SLOTS["BBAHMGTJ"]

    def test_pool_additions_in_programmes(self):
        """78 缺课进池:GIP 挂 BBA core;0 学分;毕业计算不崩(_compute_graduation 冒烟)。"""
        core = PROGRAMMES["BBAHMGTJ"]["categories"]["core"]["courses"]
        for gip in ("GIP100BEF", "GIP200BEF", "GIP300BEF", "GIP400BEF"):
            assert gip in core, f"{gip} 未进 BBAHMGTJ core"
            assert pym.ADDITION_CREDITS[gip] == 0
        # 毕业计算冒烟:补池课 0 学分参与下,progress 全空也不崩
        from backend.app.routers.courses import _compute_graduation
        prog = PROGRAMMES["BBAHMGTJ"]
        rows = {}
        for cat in prog["categories"].values():
            for cid in cat.get("courses", []):
                rows[cid] = {"id": cid, "code": cid, "name": cid, "credits": 3,
                             "prerequisites": "[]"}
        for cid, cr in pym.ADDITION_CREDITS.items():
            rows[cid] = {"id": cid, "code": cid, "name": cid,
                         "credits": cr, "prerequisites": "[]"}
        cats, _earned, _recs, _all = _compute_graduation(prog, rows, {})
        assert cats, "毕业计算在 0 学分补池课上崩溃"

    def test_course_name_backfill_flagship(self):
        """课名回填:BUS2000BEF = Integrated Business Foundation(官方标题列)。"""
        assert pym.COURSE_NAME_BACKFILL.get("BUS2000BEF") == \
            "Integrated Business Foundation"

    def test_additions_match_missing_78(self):
        """补池总量 = 复核清单 missing 78 课次 / 23 专业(机器对账)。"""
        missing = _final_result2()["missing"]
        total = sum(len(cs) for cats in pym.POOL_ADDITIONS.values()
                    for cs in cats.values())
        expect = sum(len(v) for v in missing.values())
        assert total == expect == 78, f"补池 {total} ≠ 清单 {expect}"
        assert len(pym.POOL_ADDITIONS) == len(missing) == 23
