"""课程数据覆盖率断言(选课数据修复 · 批次 0,验收标准.md)。

基准数字依据 docs/ops/选课选课/advice_sheets/复核报告-2026-08-19.md(独立复核:
双引擎 × 三锚点收敛 + 人眼逐字段核对,数字已双验,本测试不重推导):
  GE 目录全集 = 89 | 本学年开课 = 73 | 缺 16 门全部不开课(批次 1 才进池,terms=[])

官方码集全部取自 docs/ops/选课选课/advice_sheets/verify/ 下双引擎产物(入库,CI 可读):
  ge_sets/ge_pypdf/ge_poppler.json  GE 目录(锚点:TOC 点线 + 正文 Credit-units: 英文
    标签 54 + 學分: 中文标签 35;poppler 与 pypdf 逐码一致)
  ge_offered.json  本学年开课集(token 级提取,双引擎同收;Remarks 互斥引用码隔离)
  elec_catalog.json  UG 选修目录(锚点:TOC 页尾行 + 正文条目作用域;双引擎逐码一致)
重跑提取:python3 docs/ops/选课选课/advice_sheets/verify/
  {ge_catalog_check,ge_guide_check,elec_catalog_check}.py

选修目录三个数(旧单方结论 477/106/205)已于 2026-08-19 双引擎重数推翻:
  目录 477→451(477 是朴素全文正则,把 Prerequisites/不可兼修的引用码当课收,实测
  朴素去重 479;BUS1003/1004BEF 等只有引用没有条目)| 全库缺 106→5 | 长尾 205→210。

幻影码防线:GEN1064BCF/1078BCF/2078BEF 只存在于其他课的「Excluded Combination /
不可兼修」引用里,无正文条目、无 TOC 行(复核报告第一节)。除直接排除外,还锁死
「朴素正则恰好比 89 多出这 3 个」——锚点解析若退化成朴素扫描,立即红。

批次 1(2026-08-19)已施工:缺 16 门带 terms=[] 进池,池 73→89;GEN1012ACF/
2013SEF terms 已修为 spring;A&SS 15 专业 school 已换伍絜宜新名;seed_courses
CREDIT_FIXES 裁定 16 门学分(15 门三方一致 + NURS1313NCF 人工裁 6)。相关断言
均已翻转并加批次 1 锁定测试。
"""
import ast
import json
import re
from pathlib import Path

from backend.app.data.ge_courses import GE_COURSES
from backend.app.data.programmes import PROGRAMMES
from backend.app.data.programme_rules import PROGRAMME_RULES

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "docs/ops/选课选课/advice_sheets/verify"

# ── 基准字面量(来源:复核报告-2026-08-19.md,双验) ─────────────────────────
OFFICIAL_GE_N = 89          # 目录全集(双引擎三锚收敛)
OFFERED_GE_N = 73           # 本学年开课(指南三轮 33+34+11,跨轮重复 5)
# 缺课工作单 = 目录 89 − 开课 73,全部本学年不开课;批次 1 以 terms=[] 进池
MISSING_16 = frozenset({
    "GEN1000SEF", "GEN1005ACF", "GEN1013ACF", "GEN1021AEF", "GEN1025AEF",
    "GEN1028ACF", "GEN1500SEF", "GEN1501NEF", "GEN1504NEF", "GEN2002AEF",
    "GEN2013AEF", "GEN2014ABF", "GEN2015ACF", "GEN2019ABF", "GEN2045ECF",
    "GEN2502NEF",
})
# Excluded Combination 引用码(幻影):真课 1064BEF/1078BEF/2078BCF 的变体后缀
PHANTOM_GE = frozenset({"GEN1064BCF", "GEN1078BCF", "GEN2078BEF"})

ELECTIVE_CATALOG_N = 451    # 双引擎双锚重数(旧 477 为朴素正则污染值)
# 有正文条目但官方 TOC 没行的 4 门(PDF 官方自身漏行,人工核过原文)
ELECTIVE_TOC_OMISSIONS = frozenset({"PSYC3001AEF", "PTH3256ECF", "SCI3101SEF", "SCI3102SEF"})
# 选修目录里全库(catalogue 表 ∪ 可规划课程宇宙)都没有的 —— 批次 5 导入工作单。
# 2026-08-19 批次 2 前 = 5 门;批次 2 补池把其中 3 门经官方 advice sheet 提前
# 带进可规划宇宙(COUN1001AEF→BSSCHPWSJ core、TRAN3603ABF/TRAN4654ABF→
# BAHLTJ elective),缺口缩到 2。
_NOT_IN_WHOLE_DB = frozenset({"DRAM1000ECF", "DRAM4244ECF"})
_BATCH2_BROUGHT_IN = frozenset({"COUN1001AEF", "TRAN3603ABF", "TRAN4654ABF"})
NOT_IN_WHOLE_DB_NOW = _NOT_IN_WHOLE_DB | _BATCH2_BROUGHT_IN  # 兼容旧引用,= 批次2前全量5门

# ── 选修白名单(显式列出,逐门注明理由)─────────────────────────────────────
# 规则 elective 类目里不在官方选修目录的课 = 白名单全体;两类划分可被
# test_whitelist_reason_tags_verifiable 机器复核(catalogue 类必须真在 skill.md,
# rules-only 类必须不在)。批次 5 逐门定性后此清单应收缩。
WHITELIST_CATALOGUE = frozenset({
    # 理由:官方 catalogue(skill.md,生产 catalogue 表之源)有完整条目;属专业
    # advice sheet 选修菜单自设的置换选项,UG 选修目录(3cr 版)不收录。163 门。
    "ACT3020BEF", "ACT4015BEF", "AMVE1003AEF", "AMVE2003AEF", "AMVE2004AEF", "AMVE3007ABF",
    "AMVE3008ABF", "AMVE4004AEF", "AMVE4005AEF", "AMVE4009ABF", "AMVE4010ABF", "ASM3057BEF",
    "ASM3058BEF", "ASM4028BEF", "ASM4057BEF", "ASM4078BEF", "BIOL3002SEF", "BIOL3015SEF",
    "BIOL3051SEF", "BIOL4012SEF", "BIOL4013SEF", "BUS3092BEF", "BUS3098BEF", "BUS4038BEF",
    "BUS4098BEF", "CAMD4003ABF", "CAMD4004ABF", "CAMD4005AEF", "CAMD4006AEF", "CAMD4007AEF",
    "CCA1004ACF", "CCA1005ABF", "CCA3009ABF", "CCA3010ACF", "CCA4003ACF", "CCA4004ACF",
    "CCA4006ACF", "CCA4007ACF", "CGV4013BEF", "CHEM4006SEF", "CHIN4006ACF", "CHIN4007ACF",
    "CHIN4008ACF", "CHIN4243ECF", "CHIN4244ECF", "CHIN4400ECF", "CHIN4401ECF", "CM4001SEF",
    "CM4002SEF", "COMP4210SEF", "COMP4600SEF", "COMP4630SEF", "DRAM3259ECF", "ECON3007AEF",
    "ECON3009AEF", "ECON4002AEF", "EDU4405ECF", "EDU4480ECF", "ELEC3004SEF", "ELEC3650SEF",
    "ELEC4200SEF", "ELEC4380SEF", "ENGG2021SEF", "ENGG3007SEF", "ENGG4004SEF", "ENGG4005SEF",
    "ENGG4006SEF", "ENGG4007SEF", "ENGG4008SEF", "ENGG4021SEF", "ENGG4022SEF", "ENGL3021AEF",
    "ENGL3026AEF", "ENGL3330EEF", "ENGL4001AEF", "ENGL4002AEF", "ENGL4003AEF", "ENGL4025AEF",
    "ENGL4042AEF", "ENGL4139EEF", "ENGL4420EEF", "ENGL4430EEF", "ENVR4007SEF", "ENVR4042SEF",
    "ENVR4043SEF", "FIN3075BEF", "FIN3085BEF", "FIN4088BEF", "FIN4091BEF", "FINT4052BEF",
    "GCST4001AEF", "GCST4002AEF", "GCST4005AEF", "GCST4006AEF", "HPM3002BEF", "HPM4098BEF",
    "IB4096BEF", "IB4097BEF", "IDDA4004AEF", "IDDA4005AEF", "LANG3366EEF", "LANG4501AEF",
    "LANG4502AEF", "LANG4534AEF", "MGT4044BEF", "MKT2050BEF", "MKT4022BEF", "MKT4062BEF",
    "MKT4077BEF", "MKT4083BEF", "MLS4011SEF", "NMIE4202AEF", "NURS1512NEF", "NURS1513NEF",
    "NURS1515NEF", "NURS1516NEF", "NURS1517NEF", "NURS1518NEF", "POLS3003AEF", "POLS4001AEF",
    "PSYC3007AEF", "PSYC4001AEF", "PSYC4007AEF", "PSYC4010AEF", "RFM3002BEF", "RFM4098BEF",
    "SCI3064SEF", "SCI4000SEF", "SCI4004SEF", "SCI4064SEF", "SCI4065SEF", "SCI4066SEF",
    "SCM3073BEF", "SCM4072BEF", "SOCI4001AEF", "SOCI4007AEF", "SOCI4008AEF", "SOCI4009AEF",
    "SOSC4001AEF", "SPM3017BEF", "SPM3059BEF", "SPM4036BEF", "ST4020SEF", "STAT2001AEF",
    "TC3011SEF", "TC3031SEF", "TC3032SEF", "TC3041SEF", "TC3042SEF", "TC3065SEF",
    "TC3080SEF", "TC4009SEF", "TC4015SEF", "TC4075SEF", "TRAN3254ACF", "TRAN3268ACF",
    "TRAN3603ACF", "TRAN4602ABF", "TRAN4654ACF", "TRM3002BEF", "TRM3010BEF", "TRM3013BEF",
    "TRM4098BEF",
})
WHITELIST_RULES_ONLY = frozenset({
    # 理由:仅来自 programme-requirements PDF 抓取的规则(T31/T32),catalogue 表
    # 也没有 —— 可信度更低,批次 5 定性时的重点。47 门。
    "ASM3028BEF", "ASM4048BEF", "ASM4058BEF", "BIOL4001SEF", "BIOL4002SEF", "CHIN4245ECF",
    "COMP2002SEF", "COMP2008SEF", "COMP2009SEF", "COMP3012SEF", "COMP3013SEF", "COMP3020SEF",
    "COMP3021SEF", "COMP3051SEF", "COMP3062SEF", "COMP3063SEF", "COMP3080SEF", "COMP3081SEF",
    "COMP3082SEF", "COMP3090SEF", "COMP4013SEF", "COMP4092SEF", "ECON4001AEF", "EDU1150ECF",
    "ELEC2001SEF", "ELEC2003SEF", "ELEC2041SEF", "ELEC3006SEF", "ELEC3015SEF", "ELEC3037SEF",
    "ELEC3038SEF", "ELEC3047SEF", "ELEC3063SEF", "ELEC4021SEF", "ELEC4025SEF", "ENGG3023SEF",
    "ENGL4004AEF", "GCST3005AEF", "IT2090SEF", "LAW3000BEF", "LAW4000BEF", "NMIE4003AEF",
    "PTH1902ACF", "SOCI4006AEF", "STAT2051SEF", "TC3019SEF", "TC4063SEF",
})
# 批次 2(2026-08-19)advice-sheet 补池带入:仅出现在官方 Course Advice Sheet
# 横版选修菜单页(无表头,final_recalc2 后扫捕获;my_pipeline 丢行故无 type/学分行),
# skill.md 与 Requirements PDF 均无条目。2 门。依据:复核报告第三节
# 「差 = STAMJ 菜单页的 CHEM2035SEF、IT1020SEF」同源菜单页;IT1020SEF 已在
# DSAI 手工表不重复列。
WHITELIST_ADVICE_SHEET = frozenset({
    "CHEM2035SEF",  # BSCHSTAMJ Y3 / BASCHTICJ 选修菜单
    "SCI4090SEF",   # BSCHSTEMJ 选修菜单
})


def _load(name):
    with open(VERIFY / name, encoding="utf-8") as f:
        return json.load(f)


def _head(xs, n=12):
    xs = sorted(xs)
    more = f" …(共{len(xs)}门)" if len(xs) > n else ""
    return "[" + ", ".join(xs[:n]) + more + "]"


def _pool_ids():
    return {c["code"].replace(" ", "") for c in GE_COURSES}


def _elective_pool():
    """选修池 = PROGRAMME_RULES 各专业 elective 类目(pool='credits')课并集。"""
    pool = set()
    for e in PROGRAMME_RULES.values():
        for cat, v in e["categories"].items():
            if cat == "elective":
                pool.update(v.get("courses", []))
    return pool


def _skill_md_codes():
    """catalogue 表的静态之源:skill.md 里的 3cr 课码(4位数字+3字母)。"""
    codes = set()
    for ln in (REPO / "docs/ops/选课选课/skill.md").read_text(encoding="utf-8").splitlines():
        m = re.search(r"\[代码:\s*([A-Z]{2,5})\s+(\d{4}[A-Z]{3})\]", ln)
        if m:
            codes.add(m.group(1) + m.group(2))
    return codes


def _seed_ids():
    """seed_courses.py 顶层 COURSES(DSAI 手工表)的课码;只 ast 解析不执行。"""
    tree = ast.parse((REPO / "scripts/seed_courses.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "COURSES":
            return {c["id"] for c in ast.literal_eval(node.value)}
    return set()


# ── GE:目录 89(双引擎 × 三锚点) ──────────────────────────────────────────
def test_ge_catalog_89_dual_engine_three_anchor():
    pp, po, gs = _load("ge_pypdf.json"), _load("ge_poppler.json"), _load("ge_sets.json")
    a, b = set(pp["toc"]), set(po["toc"])
    assert a == b, (
        f"GE 目录双引擎不一致:poppler {len(a)} 门 vs pypdf {len(b)} 门,"
        f"差集 {_head(a ^ b)};对账:verify/ge_catalog_check.py"
    )
    assert len(a) == OFFICIAL_GE_N, (
        f"GE 目录全集应为 {OFFICIAL_GE_N},实得 {len(a)}。"
        "基准依据复核报告第一节(双引擎三锚收敛,已双验),重跑 verify/ge_catalog_check.py 对账"
    )
    anchors = set(gs["en"]) | set(gs["zh"])   # 正文英文标签 54 + 中文标签 35
    assert anchors == a, (
        f"三锚点不收敛:TOC {len(a)} vs 正文标签 {len(anchors)},"
        f"差集 {_head(a ^ anchors)};对账:verify/ge_catalog_check.py"
    )


def test_phantom_reference_codes_excluded():
    """幻影码防线:互斥引用码不得混入目录/池;朴素正则恰好多出这 3 个(锁死失败模式)。"""
    official = set(_load("ge_sets.json")["toc"])
    hit = PHANTOM_GE & official
    assert not hit, f"官方目录混入 Excluded 引用码(幻影):{_head(hit)};对账:复核报告第一节"
    hit = PHANTOM_GE & _pool_ids()
    assert not hit, f"GE 池混入幻影码 {_head(hit)} —— 会向用户注入不存在的课"
    raw = (VERIFY / "ge_catalog_raw.txt").read_text(encoding="utf-8")
    naive = {m.group(0).replace(" ", "") for m in re.finditer(r"GEN\s*\d{4}[A-Z]{3}", raw)}
    extra = naive - official
    assert naive != official and extra == PHANTOM_GE, (
        f"朴素全文正则应得 92 门且恰好多出幻影 3 码(旧结论 92 的来源),"
        f"实得 {len(naive)} 门、多出 {_head(extra)}。该检查锁死『锚点解析退化成朴素扫描』"
        "这一失败模式;若原文结构变化,先人眼复核再改基准"
    )


# ── GE:本学年开课 73(指南) ──────────────────────────────────────────────
def test_ge_offered_73_dual_engine():
    d = _load("ge_offered.json")
    po, py = d["poppler"], d["pypdf"]
    assert po == py, (
        f"开课集双引擎不一致:{ {k: sorted(set(po[k]) ^ set(py[k])) for k in po if set(po[k]) != set(py[k])} };"
        "对账:verify/ge_guide_check.py"
    )
    expect = {"2026 Autumn": 33, "2027 Spring": 34, "2027 Summer": 11}
    got = {k: len(v) for k, v in po.items()}
    assert got == expect, f"三轮门数应为 {expect}(复核报告人眼基准),实得 {got}"
    offered = set(d["all"])
    assert len(offered) == OFFERED_GE_N, f"开课去重应为 {OFFERED_GE_N},实得 {len(offered)}"
    assert "GEN2045ECF" not in offered, (
        "GEN2045ECF 是春表 Remarks 里的互斥引用(幻影),不得计为开课;对账:复核报告第一节"
    )
    assert "GEN1144ECF" in set(po["2027 Spring"]), (
        "GEN1144ECF 是春表真行(GEN 前缀被折行,逐行配前缀的解析器必丢);对账:复核报告第二节"
    )


def test_ge_pool_equals_offered_plus_missing16():
    """批次 1 后:池 = 本学年开课 73 + 不开课 16 = 目录全集 89(复核报告第一节)。"""
    pool, offered = _pool_ids(), set(_load("ge_offered.json")["all"])
    assert pool == offered | MISSING_16, (
        f"GE 池({len(pool)})≠开课集∪缺课 16(={len(offered | MISSING_16)}):"
        f"池多 {_head(pool - offered - MISSING_16)} | 池缺 {_head((offered | MISSING_16) - pool)};"
        "对账:backend/app/data/ge_courses.py vs verify/ge_offered.json + MISSING_16"
    )
    assert len(pool) == OFFICIAL_GE_N == 89, (
        f"GE 池应为 {OFFICIAL_GE_N}(73 开课 + 16 不开),实得 {len(pool)};"
        "对账:复核报告第一节(批次 1 验收标准)"
    )


def test_ge_missing16_in_pool_with_empty_terms():
    """批次 1 后:目录−开课 = 缺 16 门工作单,且全部已带 terms=[] 进池。"""
    official = set(_load("ge_sets.json")["toc"])
    offered = set(_load("ge_offered.json")["all"])
    diff = official - offered
    assert diff == MISSING_16, (
        f"缺课工作单应为 16 门,实得 {len(diff)} 门:"
        f"新增 {_head(diff - MISSING_16)} | 消失 {_head(MISSING_16 - diff)}。"
        "对账:复核报告第一节"
    )
    pool = _pool_ids()
    absent = MISSING_16 - pool
    assert not absent, (
        f"缺课 16 门应全部进池(批次 1),池缺 {_head(absent)};"
        "对账:backend/app/data/ge_courses.py vs MISSING_16"
    )
    wrongly_offered = {
        c["code"].replace(" ", ""): c["terms"]
        for c in GE_COURSES
        if c["code"].replace(" ", "") in MISSING_16 and c["terms"]
    }
    assert not wrongly_offered, (
        f"缺课 16 门本学年一律不开课(terms=[]),却带学期:{wrongly_offered};"
        "尤其 GEN2045ECF 是春表 Remarks 互斥引用,不得给学期(复核报告第一节)"
    )


def test_ge_pool_terms_match_guide():
    """批次 1 后:terms 空集门=缺课 16 门(合法);池内其余课与指南轮次零出入。"""
    empty = {c["code"].replace(" ", "") for c in GE_COURSES if not c["terms"]}
    assert empty == MISSING_16, (
        f"terms 空集门应为缺课 16 门,实得 {len(empty)} 门,多出 {_head(empty - MISSING_16)};"
        "空门=开课学期回退或新缺课混入;对账:verify/ge_offered.json(指南三轮)"
    )
    guide_terms = {}
    for term, codes in _load("ge_offered.json")["poppler"].items():
        t = term.split()[1].lower()
        for c in codes:
            guide_terms.setdefault(c, set()).add(t)
    mismatch = {
        c["code"].replace(" ", ""): (sorted(c["terms"]), sorted(guide_terms.get(c["code"].replace(" ", ""), set())))
        for c in GE_COURSES
        if set(c["terms"]) != guide_terms.get(c["code"].replace(" ", ""), set())
    }
    assert not mismatch, (
        f"池 terms 与指南轮次有出入 {len(mismatch)} 门(1012ACF/2013SEF 已于批次 1 修为 spring):"
        f"{dict(list(mismatch.items())[:8])};对账:复核报告第二节 + verify/ge_offered.json"
    )


# ── 选修:目录 451(双引擎 × 双锚)+ 池 ⊆ 目录 ∪ 白名单 ────────────────────
def test_elective_catalog_451_dual_engine():
    d = _load("elec_catalog.json")
    body_po, body_py = set(d["poppler_body"]), set(d["pypdf_body"])
    assert body_po == body_py, (
        f"选修目录双引擎不一致:poppler {len(body_po)} vs pypdf {len(body_py)},"
        f"差集 {_head(body_po ^ body_py)};对账:verify/elec_catalog_check.py"
    )
    assert len(body_po) == ELECTIVE_CATALOG_N, (
        f"选修目录应为 {ELECTIVE_CATALOG_N} 门(2026-08-19 双引擎重数,"
        f"旧 477 为朴素正则污染值),实得 {len(body_po)};对账:verify/elec_catalog_check.py"
    )
    toc_po = set(d["poppler_toc"])
    assert not (toc_po - body_po), (
        f"TOC 行有码而无正文条目(幻影嫌疑):{_head(toc_po - body_po)};"
        "Prerequisites/不可兼修引用码不点线、抢不到条目标签;对账:verify/elec_catalog_check.py"
    )
    assert body_po - toc_po == ELECTIVE_TOC_OMISSIONS, (
        f"官方 TOC 漏行集合变化:应恰好 {sorted(ELECTIVE_TOC_OMISSIONS)},"
        f"实得 {_head(body_po - toc_po)}(有正文条目+Credit-units,人工核过原文)"
    )


def test_elective_pool_subset_of_catalog_or_whitelist():
    catalog = set(_load("elec_catalog.json")["poppler_body"])
    pool = _elective_pool()
    outside = pool - catalog
    whitelist = WHITELIST_CATALOGUE | WHITELIST_RULES_ONLY | WHITELIST_ADVICE_SHEET
    assert outside == whitelist, (
        f"选修池 {len(pool)} 门中目录外 {len(outside)} 门 ≠ 白名单 {len(whitelist)} 门:"
        f"新落目录外 {_head(outside - whitelist)}(逐门定性后补白名单并注明理由)"
        f" | 白名单已陈旧 {_head(whitelist - outside)}(移出清单或已入目录,应删)"
    )
    assert pool <= catalog | whitelist, "选修池 ⊆ 官方选修目录 ∪ 白名单 必须成立"


def test_whitelist_reason_tags_verifiable():
    """白名单两类划分机器复核:catalogue 类必须真在 skill.md,rules-only 类必须不在。"""
    skill = _skill_md_codes()
    leaked = WHITELIST_CATALOGUE - skill
    assert not leaked, (
        f"catalogue 类白名单里 {len(leaked)} 门其实不在 skill.md,"
        f"应挪到 rules-only 类:{_head(leaked)}"
    )
    crossed = WHITELIST_RULES_ONLY & skill
    assert not crossed, (
        f"rules-only 类白名单里 {len(crossed)} 门其实在 skill.md,"
        f"应挪到 catalogue 类:{_head(crossed)}"
    )


def test_elective_catalog_gap_in_db_locked():
    """选修目录−全库(catalogue 表 ∪ 可规划宇宙)= 2 门,批次 5 的导入工作单。

    批次 2(2026-08-19)补池前 = 5 门;补池把 COUN1001AEF/TRAN3603ABF/
    TRAN4654ABF 经官方 advice sheet 带进 POOL_ADDITIONS → 可规划宇宙,缺口 5→2。
    批次 2 带入的 3 门必须有映射/补池落点(防静默漂移回 5)。"""
    catalog = set(_load("elec_catalog.json")["poppler_body"])
    seed = _seed_ids()
    assert seed, "seed_courses.py 顶层 COURSES 解析失败(变量被改名?)——修这里别绕过"
    plannable = _pool_ids() | seed
    for e in PROGRAMME_RULES.values():
        for v in e["categories"].values():
            plannable.update(v.get("courses", []))
    from backend.app.data.programme_year_map import POOL_ADDITIONS
    for cats in POOL_ADDITIONS.values():
        for cs in cats.values():
            plannable.update(cs)
    whole_db = plannable | _skill_md_codes()
    gap = catalog - whole_db
    assert gap == _NOT_IN_WHOLE_DB, (
        f"选修目录全库缺口应为 {len(_NOT_IN_WHOLE_DB)} 门(批次 2 后),"
        f"实得 {len(gap)} 门 {_head(gap)};批次 5 按 _NOT_IN_WHOLE_DB 导入;"
        "对账:verify/elec_coverage.json"
    )
    for c in _BATCH2_BROUGHT_IN:
        assert c in plannable, f"{c} 应已被批次 2 补池带入(检查 POOL_ADDITIONS)"


# ── 批次 1:学院更名 + 学分裁定 + results/ 禁用 ─────────────────────────────
AASS_NEW_NAME = "Wu Jieh Yee School of Arts and Social Sciences"
AASS_OLD_NAME = "School of Arts and Social Sciences"


def test_aass_programmes_renamed():
    """A&SS 专业 school = 伍絜宜新名(2026-09-01 更名,与 GE_SCHOOL_NAMES 口径
    一致);旧名仅允许存在于 PDF verbatim 锁定处(GE_SCHOOL_NAMES.pdf_verbatim、
    skill.md 官方导出),不得再作任何专业的 school 值。
    批次 1 时 15 个;批次 3(2026-08-19)+BSSCHWSJ 实体 → 16;批次 4 再 +WSJ
    五 Stream 实体(BSSCHWSJ-AGS 等,programme_rules_extra.py)→ 21。"""
    aass = {c for c, p in PROGRAMMES.items() if "Arts and Social" in (p.get("school") or "")}
    assert len(aass) == 21, f"A&SS 专业应为 21 个(批次4 +五 Stream),实得 {len(aass)}:{sorted(aass)}"
    stale = sorted(c for c in aass if PROGRAMMES[c].get("school") == AASS_OLD_NAME)
    assert not stale, (
        f"A&SS 专业仍挂旧名:{stale};应换 {AASS_NEW_NAME!r}"
        "(含 BSSCHPJ 别名副本);对账:批次 1 验收标准 + GE_SCHOOL_NAMES"
    )
    assert all(PROGRAMMES[c]["school"] == AASS_NEW_NAME for c in aass)


# 复核报告第五节表(16 门;NURS1313NCF 官方源矛盾,2026-08-19 人工裁定取 yr 表 6)
REPORT_CREDIT_FIXES = {
    "TC4019SEF": 3, "TC4026SEF": 3, "CHIN3004ACF": 3, "CHIN4243ECF": 3,
    "CHIN4383ECF": 3, "COMP4570SEF": 6, "TC4094SEF": 12, "CHIN4009ACF": 6,
    "CAMD2000AEF": 3, "CCA4002ACF": 3, "IDDA2001AEF": 3, "TRM3013BEF": 3,
    "SCI4063SEF": 3, "ASM4057BEF": 9, "SPM4098BEF": 9, "NURS1313NCF": 6,
}


def _credit_fixes():
    """seed_courses.py 顶层 CREDIT_FIXES(只 ast 解析不执行——免 import 副作用,
    也免同秒 mtime 的 stale pycache 陷阱,与 _seed_ids 同款)。"""
    tree = ast.parse((REPO / "scripts" / "seed_courses.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "CREDIT_FIXES":
            return ast.literal_eval(node.value)
    return None


def test_seed_credit_fixes_match_report():
    """seed_courses.CREDIT_FIXES == 复核报告第五节 16 门裁定值(NURS1313NCF 人工
    裁 6);除 NURS 外每门与 RCC 一致(三方投票的机器复核)。"""
    from backend.app.data.programme_rules import RULE_COURSE_CREDITS
    fixes = _credit_fixes()
    assert fixes, "seed_courses.py 顶层 CREDIT_FIXES 解析失败(变量被改名?)——修这里别绕过"
    assert fixes == REPORT_CREDIT_FIXES, (
        f"CREDIT_FIXES 与复核报告第五节不符:"
        f"多 {sorted(set(fixes) - set(REPORT_CREDIT_FIXES))} | "
        f"少 {sorted(set(REPORT_CREDIT_FIXES) - set(fixes))} | "
        f"值异 { {k: (fixes.get(k), v) for k, v in REPORT_CREDIT_FIXES.items() if fixes.get(k) != v} };"
        "对账:复核报告-2026-08-19.md 第五节"
    )
    # 三方一致性:除 NURS1313NCF(官方源自相矛盾,人工裁)外,裁定值应与 RCC 相等
    rcc = {}
    for prog, cats in RULE_COURSE_CREDITS.items():
        for cat, courses in cats.items():
            for cid, cr in courses.items():
                rcc.setdefault(cid, set()).add(cr)
    bad = {
        cid: (cr, rcc.get(cid))
        for cid, cr in fixes.items()
        if cid != "NURS1313NCF" and rcc.get(cid) != {cr}
    }
    assert not bad, (
        f"裁定值与 RCC 不一致(复核报告:15 门 yr=RCC=叶标题尾数 三方一致):{bad};"
        "若 RCC 改版须先重验再动 CREDIT_FIXES"
    )


def test_results_dir_not_referenced():
    """results/(丢行解析器旧产物,2026-08-19 复核推翻)禁用:代码与 CI 配置零引用。
    任何断言/施工清单只允许引用 verify/ 下的双引擎产物。"""
    hits = []
    guard = REPO / "backend/tests/test_course_data_coverage.py"  # 本测试自身豁免
    for pattern in ("backend/**/*.py", "scripts/**/*.py", ".github/**/*.yml",
                    "frontend/**/*.js", "miniprogram/**/*.js"):
        for f in REPO.glob(pattern):
            if f.is_file() and f != guard and "advice_sheets/results" in f.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(f.relative_to(REPO)))
    assert not hits, (
        f"以下文件引用了已禁用的 advice_sheets/results 旧产物:{hits};"
        "可信数据在 advice_sheets/verify/(双引擎);对账:results/README.md"
    )
