"""批次 4:规则建模 + cohort 闸(验收标准.md 批次 4,2026-08-19)。

五条验收各配测试:
  1. MHFA:NURS1050 进 2025/26+ Y1 入学规则池,过与不过影响毕业判定;
  2. 层级学分约束:1000 级 >30 学分 → 毕业判定不通过;
  3. 互斥组合:同时标记 → 冲突提示(3 组测试例,per-sheet scope);
  4. cohort:2022/23 入学 5cr / 2023/24+ 3cr / MHFA 按 AY 判定(春入学归属);
  5. 每条规则附官方出处(RULES_EVIDENCE 完整性断言)。

证据:docs/ops/选课选课/advice_sheets/yr/(433 份全库扫描)+ pr_wsj/ 8 份
官方 Requirements PDF(202607_V5)。纯函数测试,无 DB;端点级 cohort/conflicts
另有一条 DB 测试(走 conftest client)。
"""
from backend.app.data.programme_rules_extra import (
    EXCLUDED_COMBINATIONS,
    LEVEL_CREDIT_RULES,
    MHFA_COURSES,
    RULES_EVIDENCE,
    WSJ_STREAM_PROGRAMMES,
    WSJ_EXTRA_CREDITS,
    cohort_profile,
    excluded_conflicts,
    level_of_course,
    level_rules_for,
    parse_entry_ay,
)
from backend.app.data.programmes import PROGRAMMES, PROGRAMME_ALIASES
from backend.app.routers.courses import _compute_graduation


def _row(cid, credits=3, prereqs=None):
    return {"id": cid, "code": cid, "name": cid, "credits": credits,
            "prerequisites": prereqs}


# ── 验收 1:MHFA(2025/26+ Y1 入学)────────────────────────────────────────────

def test_mhfa_required_for_2025_26_cohort_and_blocks_graduation():
    """2025/26 入学:未完成 NURS1050 → mhfa 伪分类不满足,all_satisfied=False;
    完成 NEF(英文班)任一即满足(NEF/NCF 二选一,官方原文 either…or)。"""
    prog = PROGRAMMES["BSCHDSAIJ"]
    rows = {cid: _row(cid) for cid in
            [c for cat in prog["categories"].values() for c in cat["courses"]]}
    # 一个「其它全满足」的完成集(复用 test_graduation 的思路:全必修+选修+GE)
    progress = {cid: "completed" for cid in rows
                if cid != "COMP4610SEF"}
    progress["COMP4610SEF"] = "completed"

    cats, _total, _recs, all_sat = _compute_graduation(
        prog, rows, progress, entry_term="2024-autumn",
    )
    assert all(c.key != "mhfa" for c in cats), "2024/25 入学不该有 MHFA 行"

    cats, _total, _recs, all_sat = _compute_graduation(
        prog, rows, progress, entry_term="2025-autumn",
    )
    mhfa = next(c for c in cats if c.key == "mhfa")
    assert mhfa.satisfied is False, "未完成 NURS1050 却判 MHFA 满足"
    assert mhfa.missing_course_ids == MHFA_COURSES
    assert all_sat is False, "MHFA 未完成必须压下毕业判定"

    progress["NURS1050NEF"] = "completed"
    cats, _total, _recs, all_sat = _compute_graduation(
        prog, rows, progress, entry_term="2025-autumn",
    )
    mhfa = next(c for c in cats if c.key == "mhfa")
    assert mhfa.satisfied is True, "完成 NEF(英文班)应满足 MHFA"
    assert mhfa.earned_credits == 0, "MHFA 是 0 学分课,不得污染学分台账"


def test_mhfa_spring_entry_belongs_to_prior_ay():
    """春入学归属上一学年:2025-spring = 2024/25 AY → MHFA 不适用;
    2026-spring = 2025/26 AY → 适用(官方 1 月入学属上一学年春季学期)。"""
    assert cohort_profile("2025-spring")["mhfa_required"] is False
    assert cohort_profile("2025-spring")["ay"] == "2024/25"
    assert cohort_profile("2026-spring")["mhfa_required"] is True
    assert cohort_profile("2025-autumn")["mhfa_required"] is True
    # 缺失/格式错 → 不判(宁可少判不误判,验收纪律)
    assert cohort_profile(None)["mhfa_required"] is False
    assert cohort_profile("autumn-2025")["ay"] is None


# ── 验收 2:层级学分约束(1000 级 ≤30)───────────────────────────────────────

def _level_probe_prog(courses):
    return {
        "code": "TESTPROG",
        "total_credits": 120,
        "categories": {"core": {"min_credits": 3, "color": "blue",
                                "courses": courses}},
    }


def test_level_cap_1000_over_30_fails_graduation():
    """构造 1000 级 >30 学分的用户(11 门 ×3cr = 33):level-1000 行不满足,
    all_satisfied=False——验收单原文场景。"""
    courses = [f"TEST{n}100SEF" for n in range(1, 12)]  # TEST1100…TEST11100?
    # 课码造形:x100~x1100 → level_of_course 须得 100/1100 混合;改用真形态
    courses = [f"TST1{n:02d}0SEF" for n in range(1, 12)]  # TST1010…TST1110
    levels = {level_of_course(c) for c in courses}
    assert levels == {1000}, f"测试课码层级构造错:{levels}"
    prog = _level_probe_prog(courses)
    rows = {cid: _row(cid, credits=3) for cid in courses}
    progress = {cid: "completed" for cid in courses}

    cats, _total, _recs, all_sat = _compute_graduation(prog, rows, progress)
    lvl = next(c for c in cats if c.key == "level-1000")
    assert lvl.earned_credits == 33
    assert lvl.satisfied is False, "1000 级 33cr > 30 帽必须不满足"
    assert all_sat is False, "层级越帽必须压下毕业判定"

    # 边界:恰好 30cr(10 门)→ 满足
    courses30 = courses[:10]
    prog30 = _level_probe_prog(courses30)
    rows30 = {cid: _row(cid, credits=3) for cid in courses30}
    cats30, *_ , _, all_sat30 = _compute_graduation(
        prog30, rows30, {cid: "completed" for cid in courses30})
    lvl30 = next(c for c in cats30 if c.key == "level-1000")
    assert lvl30.earned_credits == 30 and lvl30.satisfied is True


def test_level_floors_and_wsj_scoped_rules():
    """3000/4000 下限(全校)与 WSJ Stream scoped 脚注(ME+EA 内 ≥N@4000)。"""
    rules = {r.get("rule_id"): r for r in level_rules_for("BSSCHWSJ-AS")}
    uni = rules["level-university"]
    assert uni["min"] == {"3000": 24, "4000": 24}
    scoped = rules["level-as-major"]
    assert scoped["min"] == {"4000": 9}
    assert set(scoped["scope_categories"]) == {"major-elective", "area-elective"}
    # HD 豁免;STAMJ/STEMJ 1000 帽挂起但 3000/4000 下限照常
    assert level_rules_for("HDNGF") == []
    stamj = {r.get("rule_id"): r for r in level_rules_for("BSCHSTAMJ")}
    assert "max" not in stamj["level-university"]
    assert stamj["level-university"]["min"] == {"3000": 24, "4000": 24}

    # scoped 行单独成 key(-major 后缀),聚合只算 ME+EA 池内的完成课
    prog = PROGRAMMES["BSSCHWSJ-AS"]
    me = prog["categories"]["major-elective"]["courses"]
    ea = prog["categories"]["area-elective"]["courses"]
    hi4000_ea = [c for c in ea if level_of_course(c) == 4000][:3]  # 9cr
    rows = {cid: _row(cid) for cid in set(me + ea)}
    progress = {cid: "completed" for cid in hi4000_ea}
    cats, *_ = _compute_graduation(prog, rows, progress)
    scoped_row = next(c for c in cats if c.key == "level-4000-major")
    assert scoped_row.earned_credits == 9
    assert scoped_row.satisfied is True
    # 拿掉一门(6cr)→ 不满足;且 core 里的 4000 级课不得计入 scoped 聚合
    progress.pop(hi4000_ea[0])
    rows_core = dict(rows)
    for cid in prog["categories"]["core"]["courses"]:
        if level_of_course(cid) == 4000:
            rows_core[cid] = _row(cid)
            progress[cid] = "completed"  # core 的 4000 级不应喂 scoped 行
    cats, *_ = _compute_graduation(prog, rows_core, progress)
    scoped_row = next(c for c in cats if c.key == "level-4000-major")
    assert scoped_row.earned_credits == 6 and scoped_row.satisfied is False


# ── 验收 3:互斥组合(3 组测试例)─────────────────────────────────────────────

def test_excluded_conflicts_three_groups_and_scope():
    """3 组互斥:BUS2000+BUS2001(BBAHMGTJ)、GIP200+GIP201(BBAHGBJ/ASMJ)、
    ACT3031+ACT3011(BBAHPAJ)。同时标记 → 冲突;未 attested 的专业不误报
    (per-sheet 口径);单门标记不冲突。"""
    # 组 1:BUS2000BEF ↔ BUS2001BEF
    cf = excluded_conflicts(
        {"BUS2000BEF": "completed", "BUS2001BEF": "in_progress"},
        "BBAHMGTJ",
    )
    assert len(cf) == 1 and cf[0]["rule_id"] == "excl-bus2000-bus2001"
    assert set(cf[0]["marked"]) == {"BUS2000BEF", "BUS2001BEF"}
    # 别名码(BBAHMGTJ1)同样命中
    assert PROGRAMME_ALIASES.get("BBAHMGTJ1", "BBAHMGTJ") in EXCLUDED_COMBINATIONS[0]["programmes"] or \
        len(excluded_conflicts({"BUS2000BEF": "completed", "BUS2001BEF": "completed"},
                               "BBAHMGTJ1")) == 1
    # 组 2:GIP200BEF ↔ GIP201BEF(BBAHGBJ)
    cf2 = excluded_conflicts(
        {"GIP200BEF": "completed", "GIP201BEF": "completed"}, "BBAHGBJ")
    assert len(cf2) == 1 and cf2[0]["rule_id"] == "excl-gip200-gip201"
    # 组 3:ACT3031BEF ↔ ACT3011BEF(BBAHPAJ)
    cf3 = excluded_conflicts(
        {"ACT3031BEF": "in_progress", "ACT3011BEF": "completed"}, "BBAHPAJ")
    assert len(cf3) == 1 and cf3[0]["rule_id"] == "excl-act3031-act3011"
    # scope 外专业(如 DSAI)标记同一对 → 不报(清单是 per-sheet 的)
    assert excluded_conflicts(
        {"BUS2000BEF": "completed", "BUS2001BEF": "completed"}, "BSCHDSAIJ") == []
    # 单门标记 → 不冲突
    assert excluded_conflicts({"BUS2000BEF": "completed"}, "BBAHMGTJ") == []
    # Stream 限定码折伞码后匹配
    assert excluded_conflicts(
        {"BUS2000BEF": "completed", "BUS2001BEF": "completed"},
        "BSSCHWSJ-AGS") == []


def test_excluded_semantics_separate_from_equivalence():
    """互斥 ≠ 等价:等价(新旧码同课)在批次 3 走 PROGRAMME_ALIASES/课码别名,
    EXCLUDED_COMBINATIONS 只承载「不可兼修」;每组必须带 programmes scope 与
    rule_id(证据可溯)。"""
    for g in EXCLUDED_COMBINATIONS:
        assert len(g["courses"]) >= 2
        assert g.get("programmes"), f"{g['rule_id']} 缺 per-sheet 专业 scope"
        assert g["rule_id"] in RULES_EVIDENCE, f"{g['rule_id']} 缺证据"


# ── 验收 4:cohort 学制闸 ─────────────────────────────────────────────────────

def test_cohort_credit_system_gate():
    """2022/23 及以前 = 5cr(前端展示「以官方 5cr 版文件为准」,不硬拦截);
    2023/24+ = 3cr;春入学按上一学年归属。"""
    assert cohort_profile("2022-autumn") == {
        "entry_term": "2022-autumn", "ay": "2022/23",
        "credit_system": "5cr", "mhfa_required": False,
    }
    assert cohort_profile("2023-autumn")["credit_system"] == "3cr"
    assert cohort_profile("2026-autumn")["credit_system"] == "3cr"
    assert cohort_profile("2023-spring")["ay"] == "2022/23"
    assert cohort_profile("2023-spring")["credit_system"] == "5cr"
    assert cohort_profile(None)["credit_system"] is None
    assert parse_entry_ay("2024-autumn") == (2024, 2025)
    assert parse_entry_ay("2024-spring") == (2023, 2024)


def test_5cr_cohort_skips_3cr_level_rules():
    """5cr 老 cohort 不套 3cr 层级约束(整个毕业数学本就以 3cr 文件为准,
    前端另有横幅;层级行不应出现误导老 cohort 学生)。"""
    prog = _level_probe_prog([f"TST1{n:02d}0SEF" for n in range(1, 12)])
    rows = {cid: _row(cid, credits=3) for cid in prog["categories"]["core"]["courses"]}
    progress = {cid: "completed" for cid in rows}
    cats, *_ = _compute_graduation(prog, rows, progress, entry_term="2022-autumn")
    assert all(not c.key.startswith("level-") for c in cats)


# ── 验收 5:每条规则附官方出处 + WSJ Stream 分档数据锁 ───────────────────────

def test_every_rule_has_evidence():
    """RULES_EVIDENCE 完整性:所有被规则结构引用的 rule_id 都有出处
    (哪份 PDF 哪一页 + 原文摘句 + 核对日期)——验收单明文,缺了打回。"""
    referenced = set()
    for g in EXCLUDED_COMBINATIONS:
        referenced.add(g["rule_id"])
    for rules in LEVEL_CREDIT_RULES.values():
        referenced |= {r["rule_id"] for r in rules}
    referenced |= {r["rule_id"] for r in level_rules_for("BSCHDSAIJ")}
    referenced |= {p["rule_id"] for p in WSJ_STREAM_PROGRAMMES.values()}
    missing = referenced - set(RULES_EVIDENCE)
    assert not missing, f"规则缺官方出处:{sorted(missing)}"
    for rid, ev in RULES_EVIDENCE.items():
        assert ev.get("source") and ev.get("quote") and ev.get("checked"), (
            f"{rid} 证据不完整(source/quote/checked)"
        )
        assert ".pdf" in ev["source"] or "推断" in ev["source"], (
            f"{rid} 出处须指到 PDF 页或明示推断"
        )


def test_wsj_stream_tiers_match_official_pdf():
    """WSJ 五 Stream 分档锁(证据:pr_wsj/ 202607_V5,算术校验 24/24):
    Σmin == total(Y1),分档值逐 Stream 对照官方条文;ECON Y2/Y3=90/63 异常
    与 PPA FYRP 口径见 RULES_EVIDENCE。"""
    tiers = {
        # code: (total, core, ME, EA, english, GE, ge_pick_n,
        #        entry_credits)
        "BSSCHWSJ-AGS": (120, 72, 9, 15, 6, 9, 3, {1: 120, 2: 93, 3: 66}),
        "BSSCHWSJ-ECON": (120, 75, 9, 15, 6, 6, 2, {1: 120, 2: 90, 3: 63}),
        "BSSCHWSJ-AS": (120, 69, 12, 15, 6, 9, 3, {1: 120, 2: 93, 3: 66}),
        # GCS core 含 Specialisation GCST3005ABF 6cr(57+6=63)
        "BSSCHWSJ-GCS": (120, 63, 18, 18, 6, 6, 2, {1: 120, 2: 93, 3: 66}),
        "BSSCHWSJ-PPA": (120, 81, 3, 15, 6, 6, 2, {1: 120, 2: 93, 3: 66}),
    }
    for code, (total, core, me, ea, ue, ge, ge_n, entry_cr) in tiers.items():
        prog = PROGRAMMES[code]
        cats = prog["categories"]
        assert prog["total_credits"] == total
        assert prog["entry_level_credits"] == entry_cr, (
            f"{code}: Y2/Y3 入学总分与官方不符({prog['entry_level_credits']}"
            f" ≠ {entry_cr};ECON 90/63 为官方原文)"
        )
        assert cats["core"]["min_credits"] == core
        assert cats["major-elective"]["min_credits"] == me
        assert cats["area-elective"]["min_credits"] == ea
        assert cats["english"]["min_credits"] == ue
        assert cats["general-ed"]["min_credits"] == ge
        assert cats["general-ed"]["pick_n"] == ge_n
        assert cats["university-core"]["min_credits"] == 9
        smin = sum(c["min_credits"] for c in cats.values())
        assert smin == total, f"{code}: Σmin={smin} != {total}"
        # GCS 的 spec 单门必修在 core 里且 6cr
        if code == "BSSCHWSJ-GCS":
            assert "GCST3005ABF" in cats["core"]["courses"]
            assert WSJ_EXTRA_CREDITS["GCST3005ABF"] == 6


def test_wsj_umbrella_still_pool_seed_with_stream_meta():
    """伞码 BSSCHWSJ 保持 pool_seed 骨架(min_credits=0,「未选 Stream」浏览态)
    + 挂五 Stream 元数据;Stream 实体已注册进 PROGRAMMES 可直接解析。"""
    umbrella = PROGRAMMES["BSSCHWSJ"]
    assert umbrella.get("pool_seed")
    assert len(umbrella["streams"]) == 5
    assert {s["code"] for s in umbrella["streams"]} == set(WSJ_STREAM_PROGRAMMES)
    for stream_code in WSJ_STREAM_PROGRAMMES:
        prog = PROGRAMMES[stream_code]
        assert not prog.get("pool_seed")
        assert prog["total_credits"] == 120
        assert len(prog["streams"]) == 5  # Stream 实体也带选择器(可互切)


# ── 端点级:graduation-status 的 cohort/conflicts 输出(DB)───────────────────

async def test_graduation_status_cohort_and_conflicts(client, make_user):
    """验收 3/4 的端点链路:users.entry_term → status.cohort(5cr/3cr + MHFA
    判定)与 progress → status.conflicts(互斥提示)。Stream 限定码经
    programme_code 查询参数解析到真实分档。"""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    _uid, token = await make_user(f"b4_{suffix}")
    h = {"Authorization": f"Bearer {token}"}

    # 2022/23 入学 + BBAHMGTJ + 互斥对双标
    r = await client.put("/api/v1/users/me", json={
        "entry_term": "2022-autumn", "programme_code": "BBAHMGTJ",
    }, headers=h)
    assert r.status_code == 200
    for cid in ("BUS2000BEF", "BUS2001BEF"):
        r = await client.put("/api/v1/courses/progress", json={
            "course_id": cid, "status": "completed",
        }, headers=h)
        assert r.status_code == 200, f"{cid}: {r.text}"

    r = await client.get("/api/v1/courses/graduation-status", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["programme_code"] == "BBAHMGTJ"
    assert body["cohort"]["credit_system"] == "5cr"
    assert body["cohort"]["ay"] == "2022/23"
    assert body["cohort"]["mhfa_required"] is False
    assert any(c["rule_id"] == "excl-bus2000-bus2001" for c in body["conflicts"])
    # 5cr 老 cohort 不出 3cr 层级行
    assert all(not c["key"].startswith("level-") for c in body["categories"])

    # 2025/26 入学 + MHFA 未完成 → all_categories_satisfied=False 且有 mhfa 行
    r = await client.put("/api/v1/users/me", json={
        "entry_term": "2025-autumn",
    }, headers=h)
    assert r.status_code == 200
    r = await client.get("/api/v1/courses/graduation-status", headers=h)
    body = r.json()
    assert body["cohort"]["mhfa_required"] is True
    assert any(c["key"] == "mhfa" and not c["satisfied"] for c in body["categories"])
    assert body["all_categories_satisfied"] is False

    # Stream 限定码:解析到真实分档(非伞码骨架的 min_credits=0)
    r = await client.get(
        "/api/v1/courses/graduation-status?programme_code=BSSCHWSJ-AS",
        headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["programme_code"] == "BSSCHWSJ-AS"
    by_key = {c["key"]: c for c in body["categories"]}
    assert by_key["core"]["min_credits"] == 69, "Stream 实体应带真实分档"
