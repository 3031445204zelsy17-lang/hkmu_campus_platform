"""Graduation calculation regression tests.

Pure-function tests of ``_compute_graduation`` / ``_category_satisfied`` — no
DB or HTTP client needed. Locks in the fixes for:
  - cross-category de-duplication (a shared course counted once in the total)
  - pick_n pools (need both course count AND credits)
  - required pools (every listed course completed, not just credits met)
  - the COMP4610SEF data bug (was in core AND project -> double counted)
  - recommendations skipped for already-satisfied categories
"""
from backend.app.data.programmes import PROGRAMMES
from backend.app.routers.courses import _category_satisfied, _compute_graduation
from backend.app.data.ge_courses import GE_COURSES, ge_courses_for
from backend.app.data.programme_rules_extra import level_rules_for


def _row(cid, credits=3, prereqs=None):
    """A minimal course row shaped like the DB dict _compute_graduation reads."""
    return {"id": cid, "code": cid, "name": cid, "credits": credits, "prerequisites": prereqs}


# --- _category_satisfied rules -------------------------------------------------

def test_satisfied_pickn_needs_both_count_and_credits():
    cat = {"min_credits": 12, "pick_n": 4, "courses": ["a", "b", "c", "d", "e", "f"]}
    assert not _category_satisfied(cat, earned=12, completed_count=3)  # credits ok, count short
    assert not _category_satisfied(cat, earned=9, completed_count=4)   # count ok, credits short
    assert _category_satisfied(cat, earned=12, completed_count=4)


def test_satisfied_required_pool_needs_all_completed():
    cat = {"min_credits": 9, "courses": ["a", "b", "c"]}  # no pick_n => required pool
    assert not _category_satisfied(cat, earned=9, completed_count=2)  # credits met, one missing
    assert _category_satisfied(cat, earned=9, completed_count=3)


def test_satisfied_empty_pool():
    assert _category_satisfied({"min_credits": 0, "courses": []}, 0, 0)
    assert not _category_satisfied({"min_credits": 3, "courses": []}, 0, 0)


# --- _compute_graduation: cross-category de-dup -------------------------------

def test_shared_course_not_double_counted():
    """A course listed in two categories counts once in the grand total,
    while each category still reports it within its own earned_credits."""
    prog = {
        "total_credits": 12,
        "categories": {
            "a": {"min_credits": 6, "color": "blue", "courses": ["SHARED", "x"]},
            "b": {"min_credits": 6, "color": "amber", "courses": ["SHARED"]},
        },
    }
    rows = {"SHARED": _row("SHARED", credits=6), "x": _row("x", credits=3)}
    progress = {"SHARED": "completed"}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    bykey = {c.key: c for c in cats}
    assert total == 6, f"shared course double-counted: total={total}"
    assert bykey["a"].earned_credits == 6   # within its own pool
    assert bykey["b"].earned_credits == 6   # within its own pool
    assert bykey["a"].missing_course_ids == ["x"]


# --- DSAI real-data regression -------------------------------------------------

def test_dsai_comp4610_only_in_project_not_core():
    """Regression for the COMP4610SEF data bug: it was listed in core AND
    project, so completing it yielded total=12 (double counted) and core.earned=6.
    After the fix it lives only in project -> total=6, core.earned=0."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    rows = {"COMP4610SEF": _row("COMP4610SEF", credits=6)}
    progress = {"COMP4610SEF": "completed"}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    bykey = {c.key: c for c in cats}
    assert total == 6, f"expected 6, got {total}"
    assert bykey["core"].earned_credits == 0
    assert "COMP4610SEF" not in bykey["core"].missing_course_ids  # not a core course anymore
    assert bykey["project"].earned_credits == 6
    assert bykey["project"].satisfied is True
    assert bykey["core"].satisfied is False
    assert all_sat is False
    # project is satisfied, so COMP4610SEF must not be recommended
    assert all(r.course_id != "COMP4610SEF" for r in recs)


def test_dsai_core_has_28_courses_no_comp4610():
    """Data invariant: COMP4610SEF removed from core (28 courses, 84 cr pool)."""
    core = PROGRAMMES["BSCHDSAIJ"]["categories"]["core"]
    assert "COMP4610SEF" not in core["courses"]
    assert len(core["courses"]) == 28


# --- pick_n elective: satisfied pool stops recommendations --------------------

def test_elective_pickn_satisfied_not_recommended():
    """Completing 3 electives (pick_n=3, 9 cr per PDF Table 2) satisfies the
    pool; the elective category must then contribute no recommendations."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    all_elec = prog["categories"]["elective"]["courses"]
    done = all_elec[:3]
    rows = {cid: _row(cid, credits=3) for cid in all_elec}
    progress = {cid: "completed" for cid in done}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    bykey = {c.key: c for c in cats}
    assert bykey["elective"].completed_count == 3
    assert bykey["elective"].satisfied is True
    assert all(r.category_key != "elective" for r in recs), \
        "elective still recommended despite being satisfied"


# --- GE dynamic pool (pool="ge"): field-diverse picks, own field blocked ------
# These use the REAL DSAI programme + real ge_courses_for() data, so they also
# guard the ge_courses.py / programmes.py wiring end-to-end.

def test_ge_pool_two_different_fields_satisfied():
    """Completing 2 GE courses from different fields satisfies general-ed
    (pick_n=2, 6cr) and the 6 credits count toward the grand total."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    ge = ge_courses_for("BSCHDSAIJ")
    picks, fields = [], set()
    for c in ge:
        if c["blocked"] or c["field"] in fields:
            continue
        picks.append(c); fields.add(c["field"])
        if len(picks) == 2:
            break
    assert len(picks) == 2, "test data needs >=2 unblocked GE fields"
    rows = {c["id"]: _row(c["id"], credits=3) for c in picks}
    progress = {c["id"]: "completed" for c in picks}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    ge_cat = {c.key: c for c in cats}["general-ed"]
    assert ge_cat.completed_count == 2
    assert ge_cat.earned_credits == 6
    assert ge_cat.satisfied is True
    assert total == 6  # GE credits reach the grand total (deduped)


def test_ge_pool_same_field_only_counts_one():
    """Two completed GE courses from the SAME field: the official 'distinct
    field' rule drops the second -> only 1 counts, pool stays unsatisfied."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    ge = ge_courses_for("BSCHDSAIJ")
    by_field = {}
    for c in ge:
        if not c["blocked"]:
            by_field.setdefault(c["field"], []).append(c)
    same = next((v for v in by_field.values() if len(v) >= 2), None)
    assert same, "test data needs a GE field with >=2 unblocked courses"
    picks = same[:2]
    rows = {c["id"]: _row(c["id"], credits=3) for c in picks}
    progress = {c["id"]: "completed" for c in picks}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    ge_cat = {c.key: c for c in cats}["general-ed"]
    assert ge_cat.completed_count == 1  # field dedup drops the 2nd
    assert ge_cat.earned_credits == 3
    assert ge_cat.satisfied is False  # needs 2 distinct fields, has 1


def test_ge_pool_own_field_blocked():
    """DSAI's own field is Mathematics & Statistics; a completed GE there is
    blocked and must not count toward earned credits or the grand total."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    ge = ge_courses_for("BSCHDSAIJ")
    blocked_pick = next(c for c in ge if c["blocked"])
    rows = {blocked_pick["id"]: _row(blocked_pick["id"], credits=3)}
    progress = {blocked_pick["id"]: "completed"}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    ge_cat = {c.key: c for c in cats}["general-ed"]
    assert ge_cat.completed_count == 0
    assert ge_cat.earned_credits == 0
    assert ge_cat.satisfied is False
    assert total == 0  # blocked course never reaches the grand total


def test_ge_pool_recommendations_avoid_used_and_blocked_fields():
    """With 1 GE completed, general-ed recommends a follow-up GE whose field
    is neither the already-used field nor a blocked (own-programme) field."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    ge = ge_courses_for("BSCHDSAIJ")
    first = next(c for c in ge if not c["blocked"])
    # In production graduation-status fetches ALL GE rows (all_ids splices them
    # in), so recommendations can read any candidate's credits; mirror that.
    rows = {c["id"]: _row(c["id"], credits=3) for c in ge}
    progress = {first["id"]: "completed"}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    ge_recs = [r for r in recs if r.category_key == "general-ed"]
    assert len(ge_recs) >= 1, "unsatisfied GE pool should recommend a course"
    used_field = first["field"]
    blocked_fields = {c["field"] for c in ge if c["blocked"]}
    for r in ge_recs:
        match = next((c for c in ge if c["id"] == r.course_id), None)
        assert match, f"recommended {r.course_id} is not in the GE pool"
        assert match["field"] != used_field, "recommended a same-field GE"
        assert match["field"] not in blocked_fields, "recommended a blocked GE"


# --- T35: credit pools, 54-programme rules, Testing field unification ----------

def test_satisfied_credits_pool():
    """pool:"credits" satisfies on earned credits alone — any combination.
    This is how PDF electives are specified ('N credit-units from Table X'),
    including the 150-course STEAM menus where counting courses is wrong."""
    cat = {"min_credits": 51, "courses": [f"c{i}" for i in range(150)],
           "pool": "credits"}
    assert _category_satisfied(cat, earned=51, completed_count=17)  # 17 × 3cr
    assert _category_satisfied(cat, earned=51, completed_count=9)   # 6cr mix
    assert not _category_satisfied(cat, earned=48, completed_count=16)
    assert not _category_satisfied(cat, earned=0, completed_count=0)


def test_all_programmes_category_sums_match_total():
    """Data invariant across all rule-complete programmes (1 hand-curated +
    54 generated): each category's min_credits sums exactly to the PDF's
    obtain-total. 批次 3 起排除 ``pool_seed`` 骨架实体(BSSCHWSJ:五 Stream
    分档互不相同,min_credits=0 不裁学分,毕业数学归批次 4;total_credits
    仍取官方 Y1 总分 120,由 test_guide_programme_coverage 锁定)。"""
    for code, prog in PROGRAMMES.items():
        if prog.get("pool_seed"):
            continue
        smin = sum(c["min_credits"] for c in prog["categories"].values())
        assert smin == prog["total_credits"], \
            f"{code}: Σmin={smin} != total={prog['total_credits']}"


def test_generated_ge_pool_has_pickn():
    """GE categories carry pick_n (=min/3): without it the empty-course GE
    pool can never satisfy (empty-pool branch requires min_credits == 0)."""
    for code, prog in PROGRAMMES.items():
        ge = prog["categories"].get("general-ed")
        if ge and ge.get("pool") == "ge":
            assert ge.get("pick_n", 0) >= 1, f"{code}: general-ed missing pick_n"


def _rule_rows(prog_code):
    """course rows for every rule course, credits as parsed from the PDF
    (RULE_COURSE_CREDITS); DSAI's hand-curated project is 6cr. 变体码别名
    (J1/F3 等复用主码规则的)查主码的解析学分——别名码本身不在 PDF 里。
    批次 4:WSJ Stream 实体回退 POOL_SEED_CREDITS(advice sheet 行值)与
    WSJ_EXTRA_CREDITS(GCST3005ABF=6)。"""
    from backend.app.data.programmes import PROGRAMME_ALIASES
    from backend.app.data.programme_rules import RULE_COURSE_CREDITS
    from backend.app.data.programme_year_map import POOL_SEED_CREDITS
    from backend.app.data.programme_rules_extra import WSJ_EXTRA_CREDITS
    main = PROGRAMME_ALIASES.get(prog_code, prog_code)
    parsed = RULE_COURSE_CREDITS.get(main, {})
    rows = {}
    for key, cat in PROGRAMMES[prog_code]["categories"].items():
        if cat.get("pool") == "ge":
            continue
        for cid in cat["courses"]:
            credits = parsed.get(key, {}).get(cid)
            if credits is None:
                credits = POOL_SEED_CREDITS.get(cid)
            if credits is None:
                credits = WSJ_EXTRA_CREDITS.get(cid)
            if credits is None:
                credits = 6 if cid == "COMP4610SEF" else 3
            rows[cid] = _row(cid, credits=credits)
    return rows


def _level_of(cid):
    from backend.app.data.programme_rules_extra import level_of_course
    return level_of_course(cid)


def test_every_programme_can_graduate():
    """End-to-end over ALL programmes (55 批次3 + 批次4 WSJ 五 Stream):complete
    every required course, enough elective credits (credit pool), and pick_n
    distinct-field unblocked GEs -> every category satisfied and all_satisfied
    must be True.

    批次 4 起毕业判定含全校层级约束(1000≤30 / 3000≥24 / 4000≥24)与 WSJ
    Stream 的 scoped 层级脚注——选课策略必须层级感知(和真实学生一样):
      * 学分池按层级降序填(优先喂 3000/4000 下限);
      * 1000 级预算耗尽时学分池跳过 1000 级候选、GE 优先选 2000 级;
      * 填完各池下限后若层级下限仍差,从学分池未选课里按层级补足。
    若某专业在该策略下仍无法满足(如必修池自身超帽),测试红 = 数据问题
    该挂起的挂起(见 _LEVEL_CAP_SUSPENDED)。"""
    for code, prog in PROGRAMMES.items():
        if prog.get("coming_soon"):
            continue
        rows = _rule_rows(code)
        progress = {}
        uni_rule = next(
            (r for r in level_rules_for(code) if not r.get("scope_categories")),
            {},
        )
        cap1000 = uni_rule.get("max", {}).get("1000")

        def _earned_at(level):
            return sum(
                rows[cid]["credits"]
                for cid in progress
                if _level_of(cid) == level
            )

        # ① 必修池(非学分池)全修(含 pick_n 池:官方表即全修)
        fixed1000 = 0
        for key, cat in prog["categories"].items():
            if cat.get("pool") in ("ge", "credits"):
                continue
            progress.update({cid: "completed" for cid in cat["courses"]})
            fixed1000 += sum(
                rows[cid]["credits"]
                for cid in cat["courses"] if _level_of(cid) == 1000
            )
        budget1000 = (cap1000 - fixed1000) if cap1000 is not None else 10**6

        # ② 学分池:层级降序填到 min,1000 级仅在预算内取
        pools = [(k, c) for k, c in prog["categories"].items()
                 if c.get("pool") == "credits"]
        for key, cat in pools:
            earned = 0
            for cid in sorted(cat["courses"],
                              key=lambda c: -_level_of(c)):
                if earned >= cat["min_credits"]:
                    break
                if cid in progress:
                    continue
                cr = rows[cid]["credits"]
                if _level_of(cid) == 1000 and cr > budget1000:
                    continue
                progress[cid] = "completed"
                earned += cr
                if _level_of(cid) == 1000:
                    budget1000 -= cr
            assert earned >= cat["min_credits"], (
                f"{code}: credit pool {key} 无法在不破 1000 帽的前提下填满"
                f"({earned}/{cat['min_credits']})——数据或帽子挂起需复核"
            )

        # ③ GE:预算紧时优先 2000 级(field 互异 + 非本专业领域不变)
        ge_cat = prog["categories"].get("general-ed")
        if ge_cat and ge_cat.get("pool") == "ge":
            need, fields = ge_cat.get("pick_n", 2), set()
            ge_sorted = sorted(
                (c for c in ge_courses_for(code) if not c["blocked"]),
                key=lambda c: _level_of(c["id"]),
            )
            for c in ge_sorted:
                if len(fields) >= need:
                    break
                if c["field"] in fields:
                    continue
                cr = 3
                if _level_of(c["id"]) == 1000 and cr > budget1000:
                    continue
                fields.add(c["field"])
                rows[c["id"]] = _row(c["id"], credits=cr)
                progress[c["id"]] = "completed"
                if _level_of(c["id"]) == 1000:
                    budget1000 -= cr
            assert len(fields) >= need, f"{code}: GE 领域候选不足"

        # ④ 层级下限补足:3000/4000(全校)差多少,从学分池未选课按层级补
        for level, floor in sorted(uni_rule.get("min", {}).items()):
            level = int(level)
            floor = int(floor)
            short = floor - _earned_at(level)
            if short <= 0:
                continue
            cands = sorted(
                (cid for _k, cat in pools for cid in cat["courses"]
                 if cid not in progress and _level_of(cid) == level),
                key=lambda c: -rows[c]["credits"],
            )
            for cid in cands:
                if short <= 0:
                    break
                progress[cid] = "completed"
                short -= rows[cid]["credits"]
            # scoped 脚注(WSJ ME+EA ≥N@4000)同法在其作用域池内补
            for rule in level_rules_for(code):
                scope = rule.get("scope_categories")
                if not scope:
                    continue
                for lv, fl in sorted(rule.get("min", {}).items()):
                    lv, fl = int(lv), int(fl)
                    scope_ids = {cid for k in scope
                                 for cid in prog["categories"][k]["courses"]}
                    got = sum(rows[c]["credits"] for c in progress
                              if c in scope_ids and _level_of(c) == lv)
                    short2 = fl - got
                    for cid in sorted(
                        (c for c in scope_ids
                         if c not in progress and _level_of(c) == lv),
                        key=lambda c: -rows[c]["credits"],
                    ):
                        if short2 <= 0:
                            break
                        progress[cid] = "completed"
                        short2 -= rows[cid]["credits"]

        cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
        unsat = [c.key for c in cats if not c.satisfied]
        assert not unsat, f"{code}: categories not satisfied: {unsat}"
        assert all_sat is True, f"{code}: all_satisfied=False despite full plan"


def test_school_folding_smoke():
    """T32 folding decisions locked in via representative programmes:
    NHS core = Theoretical + Clinical Practicum; BA core = core + strategy +
    concentration; ST-STEAM elective is a credit-pool menu; AS keeps its
    'elective courses in specific area' table."""
    nhgj = PROGRAMMES["BNHGJ"]["categories"]
    assert nhgj["core"]["min_credits"] == 130  # 104 theoretical + 26 clinical
    assert any(c.startswith("NURS") for c in nhgj["core"]["courses"])

    cg = PROGRAMMES["BBAHCGSJ"]["categories"]["core"]
    assert cg["min_credits"] == 99  # 60 core + 3 strategy + 36 concentration

    stam = PROGRAMMES["BSCHSTAMJ"]["categories"]["elective"]
    assert stam["pool"] == "credits" and len(stam["courses"]) > 100  # S/T/E/A/M menu

    camd = PROGRAMMES["BAHCAMDJ"]["categories"]["elective"]
    assert len(camd["courses"]) > 0  # AS 'in specific area' table matched


def test_ge_terms_data_integrity():
    """Offering terms parsed from the GE Selection Guide (2026-08 window):
    values must be a valid subset; ~71/73 courses offered, 5 multi-term."""
    valid = {"autumn", "spring", "summer"}
    for c in GE_COURSES:
        assert set(c.get("terms", [])) <= valid, f"{c['code']}: bad terms {c['terms']}"
    offered = [c for c in GE_COURSES if c["terms"]]
    assert len(offered) >= 60, f"only {len(offered)} GE courses offered?"
    assert sum(1 for c in GE_COURSES if len(c["terms"]) > 1) >= 3


def test_testing_field_blocked_for_testing_programmes():
    """The 'Testing & Certification' vs 'Testing and Certification' spelling
    split used to silently disable own-field blocking for 8 programmes.
    (Programmes whose own field is not a GE field at all — Construction,
    Aviation, Applied Drama… — legitimately block nothing; that's fine.)"""
    from backend.app.data.ge_courses import PROGRAMME_GE_FIELDS, GE_FIELD_ORDER
    assert "Testing and Certification" in GE_FIELD_ORDER
    for fields in PROGRAMME_GE_FIELDS.values():  # no '&' spelling may remain
        assert "Testing & Certification" not in fields
    for code in ("BSCHFTSJ", "BSCHATSJ", "BASCHTICJ", "BENGHBSEJ",
                 "BENGHCEJ", "BSCHMLSJ", "BSCHSTEMJ", "BSCHSTAMJ"):
        blocked = {c["code"] for c in ge_courses_for(code) if c["blocked"]}
        assert "GEN 2001SEF" in blocked, f"{code}: Testing GE not blocked"
    dcai_blocked = {c["code"] for c in ge_courses_for("BSCHDSAIJ") if c["blocked"]}
    assert "GEN 2001SEF" not in dcai_blocked  # not DSAI's field
