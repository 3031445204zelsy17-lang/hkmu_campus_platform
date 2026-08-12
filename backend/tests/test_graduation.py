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
