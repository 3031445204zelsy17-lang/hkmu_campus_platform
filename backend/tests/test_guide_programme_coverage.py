"""官方指南 57 专业码 · 批次 3 断言(验收标准.md 批次 3)。

锚点链:官方《Advice on Course Selection Guide (3-credit-unit system)》
(Last Update 13 August 2026)索引表「Academic Plan」列 = 57 码,与
advice_sheets/covers/ 57 份封面文件名一一对应。2026-08-19 双锚收敛验证
(会话内亲测):桌面指南 PDF pdftotext -layout 后逐表行取首 token
(形状 [A-Z]{4,9}([0-9]?F[0-9]|[0-9]{1,2})?),得 57 码、零重复、与封面
文件名零差。指南 PDF 本体不入库,covers/ 为 CI 稳定锚点;封面内文再证
在招码形态(BSSCHWSJ1/2/3、BSCHCOMPF3、BAPHBMJ1- HAPBMJ1-18 等)。

批次 3 施工(2026-08-19):
  * BSCHCOMPF3 → BSCHCOMPF 别名(计算 Y3 入学;年份映射批次 2 已灌);
  * BSSCHWSJ 实体(2023 秋起的社科五大 Stream 大类学位,课池由
    PROGRAMME_POOL_SEED 从官方 advice 行种入;毕业数学归批次 4);
  * seed_catalogue 伞码解析(BSSCHWSJ_SCHJ-AGS 等 8 段,顺带清除其课行
    被误挂 BFAHIDDAJ 的 291 行污染)+ 变体折叠(picker 单入口);
  * 7 个非指南码定性:5 个社科旧码 2023 秋并入 BSSCHWSJ Stream(挂停招标,
    admissions.hkmu.edu.hk/ug/programmes/ 总列表已无 + ss 学院 Streams 表
    逐一对应);BBAHWBJ = World Business,2026/27 招生面三锚均无、注册组
    Requirements PDF 202607_V1 → 非停招不挂标(疑 2027/28 新开);BAPHBMJ1
    = 在招变体(JUPAS JS9280,招生专属页在列)。
"""
import importlib.util
import json
import os
import re
from pathlib import Path

from backend.app.data.programmes import (
    DISCONTINUED_CODES,
    PROGRAMME_ALIASES,
    PROGRAMME_SERIES_HINTS,
    PROGRAMMES,
)
from backend.app.data.programme_year_map import PROGRAMME_POOL_SEED, PROGRAMME_YEAR_MAP

REPO = Path(__file__).resolve().parents[2]
AS = REPO / "docs/ops/选课选课/advice_sheets"

# 批次 3 定性结论(2026-08-19 官方招生页核查,详见 programmes.py 注释):
# 5 个社科旧码停招(并入 BSSCHWSJ 五大 Stream);BBAHWBJ 不招不挂标;
# BAPHBMJ1 在招变体。锁死防无声翻转。
DISCONTINUED_BATCH3 = frozenset({
    "BSSCHAGSJ", "BSSCHECJ", "BSSCHJ", "BSSCHGCSJ", "BSSCHPAJ",
})
NOT_DISCONTINUED_BATCH3 = frozenset({"BBAHWBJ", "BAPHBMJ1"})

_GUIDE_CODE_SHAPE = re.compile(r"[A-Z]{4,9}(?:[0-9]F[0-9]|[0-9]{1,2})?")


def _covers():
    return {f[:-4] for f in os.listdir(AS / "covers") if f.endswith(".pdf")}


def _guide_mains():
    """指南 57 码 → 变体折叠后的主码集(BSCHCOMPF3→BSCHCOMPF、BNHGJ1→BNHGJ…)。"""
    return {PROGRAMME_ALIASES.get(c, c) for c in _covers()}


def _catalogue_codes():
    """seed_catalogue 解析 skill.md 的目录码集(= picker 全集,折叠后)。

    importlib 按文件路径加载(python-dotenv 在 CI 依赖内;opencc 可选,
    模块自带兜底);复用生产解析器本体而非测试内重写折叠逻辑。
    """
    path = REPO / "scripts" / "seed_catalogue.py"
    spec = importlib.util.spec_from_file_location("_seed_catalogue_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    progs, order, _courses, failures = mod.parse_skill_md(
        str(REPO / "docs/ops/选课选课/skill.md"))
    assert not failures, f"skill.md 解析失败 {len(failures)} 行:{failures[:5]}"
    return set(order), progs


def _head(xs, n=10):
    xs = sorted(xs)
    more = f" …(共{len(xs)}个)" if len(xs) > n else ""
    return "[" + ", ".join(xs[:n]) + more + "]"


# ── 锚点:57 封面 = 指南索引(双锚已收敛,CI 锁定) ────────────────────────────
def test_covers_anchor_57():
    covers = _covers()
    assert len(covers) == 57, (
        f"covers/ 应为 57 份指南封面,实得 {len(covers)};对账:桌面指南 PDF 索引表"
        "(2026-08-19 双锚收敛记录,见本文件 docstring)"
    )
    bad = {c for c in covers if not _GUIDE_CODE_SHAPE.fullmatch(c)}
    assert not bad, f"封面文件名不符合专业码形状:{_head(bad)}"


# ── 零缺失:每个指南专业可规划(折叠后 ∈ PROGRAMMES 且非占位) ───────────────
def test_every_guide_programme_plannable():
    missing = sorted(c for c in _guide_mains() if c not in PROGRAMMES)
    assert not missing, (
        f"指南专业缺规划实体:{_head(missing)}(批次 3 已补 BSCHCOMPF3 别名与 "
        "BSSCHWSJ 实体;对账:backend/app/data/programmes.py)"
    )
    placeholder = sorted(
        c for c in _guide_mains()
        if PROGRAMMES[c].get("coming_soon")
    )
    assert not placeholder, f"指南专业不得是 coming_soon 占位:{_head(placeholder)}"


# ── picker 单入口:目录码集 = 指南 57 ∪ 停招码,零缺失零多余 ─────────────────
def test_picker_exactly_guide_plus_discontinued():
    picker, _progs = _catalogue_codes()
    guide = _guide_mains()
    missing = guide - picker
    assert not missing, (
        f"指南专业在 picker 缺入口:{_head(missing)};对账:scripts/seed_catalogue.py"
        "(伞码/变体折叠解析)+ 生产需重跑 seed_catalogue 灌表"
    )
    extra = picker - guide - DISCONTINUED_CODES
    assert not extra, (
        f"picker 出现非指南、非停招的多余入口:{_head(extra)};"
        "新码要么进指南锚点要么进停招集(定性依据见 programmes.py 注释)"
    )
    absent_disc = DISCONTINUED_CODES - picker
    assert not absent_disc, (
        f"停招码应在目录保留浏览(phase-out 存量学生),缺:{_head(absent_disc)};"
        "对账:scripts/seed_catalogue.py"
    )


def test_no_unfolded_variant_rows():
    """9 对 J 系双胞胎 + 2 个 F3 变体:变体码不得独立成行(单入口)。"""
    picker, _progs = _catalogue_codes()
    unfolded = sorted(picker & set(PROGRAMME_ALIASES))
    assert not unfolded, (
        f"变体码未被折叠成主码,重复入口:{_head(unfolded)};"
        "对账:seed_catalogue._PROG_RE 分支的 PROGRAMME_ALIASES 折叠"
    )
    series_leaked = sorted(
        c for codes in PROGRAMME_SERIES_HINTS.values() for c in codes if c in picker
    )
    assert not series_leaked, (
        f"伞形专业系列码不得独立成行:{_head(series_leaked)};"
        f"应并入主码(对账:PROGRAMME_SERIES_HINTS + seed_catalogue 伞码归一)"
    )


def test_umbrella_wsj_courses_rehomed():
    """BSSCHWSJ 伞码段独立成行,课行不再挂在 BFAHIDDAJ 名下(291 行污染清除)。"""
    picker, progs = _catalogue_codes()
    assert "BSSCHWSJ" in picker, "BSSCHWSJ 应为目录独立专业(伞码 8 段归一)"
    assert progs["BSSCHWSJ"]["course_count"] > 100, (
        f"BSSCHWSJ 目录课行应 >100(8 段专修合并),实得 {progs['BSSCHWSJ']['course_count']}"
    )
    idda = progs["BFAHIDDAJ"]["course_count"]
    assert idda < 150, (
        f"BFAHIDDAJ 课行 {idda} 仍含 WSJ 段污染(修复前 341,应回落 ~107);"
        "对账:seed_catalogue 伞码解析"
    )


# ── 批次 3 停招定性锁(官方招生页依据,见 programmes.py DISCONTINUED_CODES 注) ──
def test_batch3_discontinued_verdicts_locked():
    missing = DISCONTINUED_BATCH3 - DISCONTINUED_CODES
    assert not missing, (
        f"批次 3 定性停招码未挂标:{_head(missing)};"
        "依据:2023 秋并入 BSSCHWSJ 五大 Stream(admissions.hkmu.edu.hk/ug/programmes/ 无此行)"
    )
    wrongly = NOT_DISCONTINUED_BATCH3 & DISCONTINUED_CODES
    assert not wrongly, (
        f"不得挂停招标:{_head(wrongly)}——BBAHWBJ=2026/27 不招的新专业(非停招),"
        "BAPHBMJ1=在招变体(JUPAS JS9280);对账:programmes.py 批次 3 注释"
    )
    assert "BAPHBMJ1" in PROGRAMME_ALIASES, "BAPHBMJ1 定性=在招变体,应保持别名映射"
    assert "BSSCHWSJ" in PROGRAMME_SERIES_HINTS.get("BSSCHWSJ", []) or \
        PROGRAMME_SERIES_HINTS.get("BSSCHWSJ"), "BSSCHWSJ 系列码提示应在"


# ── 463 行官方课归属:WSJ 映射灌入 + BSCHCOMPF3 别名生效 ────────────────────
def test_bsschwsj_year_map_and_pool_seed():
    wsj_prog = PROGRAMMES["BSSCHWSJ"]
    # total_credits = 官方 Requirements PDF(202607_V5)Y1 入学「obtain 120
    # credit-units」;三 Stream 恒和(AGS 72+9+15+9+6+9 / AS 69+12+… / PPA 81+…)
    assert wsj_prog["total_credits"] == 120, (
        f"BSSCHWSJ total_credits 应为官方 120,实得 {wsj_prog['total_credits']};"
        "对账:3CRU_FTU_AS_BSSCHWSJ_SCHJ-AGS/AS/-SCHJ-PPA_202607_V5.pdf"
    )
    wsj = PROGRAMME_YEAR_MAP.get("BSSCHWSJ")
    assert wsj, "BSSCHWSJ 年份映射缺失(重跑 scripts/build_programme_year_map.py)"
    rows = json.loads((AS / "verify/my_rows.json").read_text(encoding="utf-8"))
    wsj_rows = [r for r in rows if r["plan"].startswith("BSSCHWSJ")]
    assert len(wsj_rows) == 463, (
        f"BSSCHWSJ1/2/3 官方行应为 463(复核报告声明 12),实得 {len(wsj_rows)}"
    )
    unhomed = sorted({r["code"] for r in wsj_rows if r.get("yr") is not None} - set(wsj))
    assert not unhomed, (
        f"WSJ 官方行课码未进映射:{_head(unhomed)};对账:build_programme_year_map"
        ".build_year_map(norm_plan 裸码回退)+ BSSCHWSJ 实体"
    )
    bad_years = {c: v["year"] for c, v in wsj.items() if v["year"] not in (1, 2, 3, 4)}
    assert not bad_years, f"WSJ 映射年份越界:{bad_years}"

    seed = PROGRAMME_POOL_SEED.get("BSSCHWSJ", {})
    seeded = {c for cs in seed.values() for c in cs}
    assert seeded == {r["code"] for r in wsj_rows if r.get("type")} , (
        "WSJ 课池种子应覆盖全部带 type 的官方行课码(58 门);"
        f"差:{_head(seeded ^ {r['code'] for r in wsj_rows if r.get('type')})}"
    )
    assert "UNI1002ABW" in seed.get("university-core", []), (
        "UNI 前缀码应归 university-core(advice 表把 University Core 行打 C)"
    )


def test_bschcompf3_alias_shares_main():
    assert PROGRAMME_ALIASES.get("BSCHCOMPF3") == "BSCHCOMPF", (
        "BSCHCOMPF3 应别名到 BSCHCOMPF(计算 Y3 入学,批次 3)"
    )
    alias, main = PROGRAMMES["BSCHCOMPF3"], PROGRAMMES["BSCHCOMPF"]
    assert alias["total_credits"] == main["total_credits"] == 63
    assert alias["categories"] == main["categories"], "别名实体必须共享主码规则"
    compf = PROGRAMME_YEAR_MAP.get("BSCHCOMPF", {})
    assert len(compf) == 17, (
        f"BSCHCOMPF 映射应含 advice 表 17 行(Y3/Y4),实得 {len(compf)}"
    )
