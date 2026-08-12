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
from backend.app.data.ge_courses import ge_courses_for


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
    """Completing 4 electives (pick_n=4, 12 cr) satisfies the pool; the elective
    category must then contribute no recommendations."""
    prog = PROGRAMMES["BSCHDSAIJ"]
    all_elec = prog["categories"]["elective"]["courses"]
    done = all_elec[:4]
    rows = {cid: _row(cid, credits=3) for cid in all_elec}
    progress = {cid: "completed" for cid in done}
    cats, total, recs, all_sat = _compute_graduation(prog, rows, progress)
    bykey = {c.key: c for c in cats}
    assert bykey["elective"].completed_count == 4
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
