import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import (
    CourseOut, UserCourseUpdate, UserCourseOut,
    CourseReviewCreate, CourseReviewOut, PaginatedResponse,
)
from ..data.programmes import PROGRAMMES, DEFAULT_PROGRAMME_CODE, get_programme
from ..data.ge_courses import (
    GE_FIELD_ORDER, PROGRAMME_GE_FIELDS, ge_courses_for,
)
from ..services.cache import TTLCache
from pydantic import BaseModel, Field, field_validator

# Cap on a single batch progress update (Codex [25]) — without it a client could
# POST thousands of items and force a long transaction of N existence checks +
# N upserts. 100 is far above any legitimate planner sync.
_MAX_BATCH_PROGRESS = 100


class BatchProgressUpdate(BaseModel):
    items: list[UserCourseUpdate]

    @field_validator("items")
    @classmethod
    def _cap_and_dedup(cls, items: list[UserCourseUpdate]) -> list[UserCourseUpdate]:
        if len(items) > _MAX_BATCH_PROGRESS:
            raise ValueError(f"Too many items (max {_MAX_BATCH_PROGRESS})")
        # Dedup by course_id, last occurrence wins — mirrors the endpoint's
        # ON CONFLICT DO UPDATE so a repeated course_id doesn't double-work.
        seen: dict[str, UserCourseUpdate] = {}
        for item in items:
            seen[item.course_id] = item
        return list(seen.values())
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/courses", tags=["courses"])


# ── Programme catalogue & graduation response models ─────────────────────────
# Inline (like BatchProgressUpdate) to keep the change inside the courses module.

class ProgrammeCategoryOut(BaseModel):
    key: str
    min_credits: int
    color: str
    pick_n: int | None = None
    courses: list[str]


class ProgrammeOut(BaseModel):
    code: str
    name: dict[str, str]
    school: str
    total_credits: int
    coming_soon: bool = False
    categories: list[ProgrammeCategoryOut]
    template: dict = {}


class ProgrammeCatalogueOut(BaseModel):
    default_code: str
    programmes: list[ProgrammeOut]


# ── Course catalogue (read-only official course lists) ───────────────────────
# Distinct from the planning catalogue above: these come from HKMU's public
# Programme Requirements PDFs and have no term / prerequisite / per-category
# credit info, so they drive a browse-only view (no graduation math).

class CatalogueCourseOut(BaseModel):
    course_code: str
    display_name: str
    # Simplified-Chinese name for zh-CN viewers (OpenCC t2s of display_name for
    # the CJK courses; None for English-only courses → front end falls back to
    # display_name). Traditional/EN viewers always use display_name.
    name_zh_cn: str | None = None
    credits: int
    code_system: str
    official_group: str


class CatalogueBucketOut(BaseModel):
    key: str
    label_key: str
    order: int
    courses: list[CatalogueCourseOut]


class CatalogueProgrammeOut(BaseModel):
    programme_code: str
    programme_name: str
    name_zh_cn: str | None = None
    name_zh_tw: str | None = None
    school: str
    course_count: int
    has_full_planning: bool


class CatalogueSchoolGroupOut(BaseModel):
    school: str
    programmes: list[CatalogueProgrammeOut]


class CatalogueProgrammesResponse(BaseModel):
    default_programme_code: str
    schools: list[CatalogueSchoolGroupOut]


class CatalogueCoursesResponse(BaseModel):
    programme_code: str
    programme_name: str
    school: str
    has_full_planning: bool
    disclaimer_key: str
    buckets: list[CatalogueBucketOut]


class CategoryProgressOut(BaseModel):
    key: str
    min_credits: int
    earned_credits: int
    color: str
    pick_n: int | None = None
    completed_count: int
    total_courses: int
    satisfied: bool = False
    missing_course_ids: list[str] = Field(default_factory=list)


class RecommendedCourseOut(BaseModel):
    course_id: str
    code: str
    name: str
    credits: int
    category_key: str
    needed_credits: int


class GraduationStatusOut(BaseModel):
    programme_code: str
    coming_soon: bool
    total_credits: int
    earned_credits: int
    percent: float
    categories: list[CategoryProgressOut]
    recommendations: list[RecommendedCourseOut]
    all_categories_satisfied: bool = False


class GECourseOut(BaseModel):
    id: str  # courses-table PK (code w/o spaces); drives PUT /courses/progress
    code: str
    name_en: str
    name_zh: str
    field: str
    school: str
    blocked: bool = False  # in the student's own programme field → cannot take


class GEListOut(BaseModel):
    programme_code: str | None = None
    own_fields: list[str] = Field(default_factory=list)
    field_order: list[str] = Field(default_factory=list)
    courses: list[GECourseOut]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _course_row_to_out(row) -> CourseOut:
    return CourseOut(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        credits=row["credits"],
        category=row["category"],
        year=row["year"],
        semester=row["semester"],
        prerequisites=row["prerequisites"] or "[]",
        description=row["description"],
    )


def _review_row_to_out(row) -> CourseReviewOut:
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return CourseReviewOut(
        id=row["id"],
        course_id=row["course_id"],
        author_id=row["author_id"],
        rating=row["rating"],
        content=row["content"],
        helpful_count=row["helpful_count"],
        created_at=created_at,
        author_nickname=row["author_nickname"],
    )


_REVIEW_COLS = """cr.id, cr.course_id, cr.author_id, cr.rating, cr.content,
    cr.helpful_count, cr.created_at,
    u.nickname AS author_nickname"""


# ── Course listing & detail ──────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse)
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    year: int | None = None,
    semester: str | None = None,
    category: str | None = None,
    search: str | None = None,
):
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list = []
    n = 1

    if year is not None:
        conditions.append(f"year = ${n}")
        params.append(year)
        n += 1
    if semester:
        conditions.append(f"semester = ${n}")
        params.append(semester)
        n += 1
    if category:
        conditions.append(f"category = ${n}")
        params.append(category)
        n += 1
    if search:
        conditions.append(f"(name LIKE ${n} OR code LIKE ${n+1})")
        params.extend([f"%{search}%", f"%{search}%"])
        n += 2

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        total = (await db.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM courses {where}", *params,
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT * FROM courses {where}
                ORDER BY year, semester, code
                LIMIT ${n} OFFSET ${n+1}""",
            *params, page_size, offset,
        )
        items = [_course_row_to_out(r).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


# ── Programme catalogue & graduation status ──────────────────────────────────
# NOTE: these single-segment routes MUST be declared before ``GET /{course_id}``,
# otherwise ``programmes`` / ``graduation-status`` would be captured as a course_id.

def _programme_to_out(code: str, prog: dict) -> ProgrammeOut:
    cats = [
        ProgrammeCategoryOut(
            key=key,
            min_credits=cat.get("min_credits", 0),
            color=cat.get("color", "blue"),
            pick_n=cat.get("pick_n"),
            courses=list(cat.get("courses", [])),
        )
        for key, cat in prog.get("categories", {}).items()
    ]
    return ProgrammeOut(
        code=code,
        name=dict(prog.get("name", {})),
        school=prog.get("school", ""),
        total_credits=prog.get("total_credits", 0),
        coming_soon=prog.get("coming_soon", False),
        categories=cats,
        template=prog.get("template", {}),
    )


def _parse_prereqs(raw) -> list[str]:
    """prerequisites is a JSON text column, e.g. '["COMP1080SEF"]'."""
    try:
        parsed = json.loads(raw or "[]")
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (ValueError, TypeError):
        pass
    return []


def _category_satisfied(cat: dict, earned: int, completed_count: int) -> bool:
    """Whether a category's graduation requirement is met.

    - pick_n pool (electives): need >= pick_n courses AND >= min_credits
    - required pool (core/project/...): every listed course completed AND
      >= min_credits. With DSAI's current data the pool's own credit sum
      equals min_credits, so "all completed" and "credits met" coincide —
      but both are checked so a future pool larger than min_credits can't
      be satisfied by skipping a required course.
    - empty pool: satisfied iff no credits are required.
    """
    required = cat.get("min_credits", 0)
    pick_n = cat.get("pick_n")
    total = len(cat.get("courses", []))
    if pick_n is not None:
        return completed_count >= pick_n and earned >= required
    if total == 0:
        return required == 0
    return completed_count == total and earned >= required


def _compute_graduation(
    prog: dict, course_rows: dict, progress: dict
) -> tuple[list[CategoryProgressOut], int, list[RecommendedCourseOut], bool]:
    """Mirror of the web client's graduation math.

    course_rows: {course_id: {"id","code","name","credits","prerequisites"}}
    progress:    {course_id: status}
    Returns (categories, total_earned, recommendations, all_satisfied).

    total_earned is de-duplicated across categories: a completed course's
    credits count once even if (erroneously) listed in multiple categories,
    so the grand total never exceeds the student's real earned credits.
    Per-category earned_credits still reflect that category's own pool.
    """
    categories: list[CategoryProgressOut] = []
    recs: list[RecommendedCourseOut] = []
    completed_global: dict[str, int] = {}  # course_id -> credits (deduped)
    all_satisfied = True

    for key, cat in prog.get("categories", {}).items():
        required = cat.get("min_credits", 0)
        pick_n = cat.get("pick_n")
        is_ge = cat.get("pool") == "ge"
        course_ids = cat.get("courses", [])
        earned = 0
        completed_count = 0
        missing: list[str] = []
        used_fields: set[str] = set()  # GE: fields already counting toward earned
        ge_list: list[dict] = []

        if is_ge:
            # Dynamic GE pool — resolved from ge_courses_for() (field/blocked
            # metadata) joined with course_rows (credits). GEN001/GEN002 were
            # placeholders; real GE courses live in the courses table.
            ge_list = ge_courses_for(prog.get("code"))
            ge_meta = {c["id"]: {"field": c["field"], "blocked": c["blocked"]} for c in ge_list}
            for cid, meta in ge_meta.items():
                if progress.get(cid) != "completed" or meta["blocked"]:
                    continue
                # Official GE rule: each course must be from a DIFFERENT field.
                # A second completed GE in an already-counted field is ignored.
                if meta["field"] in used_fields:
                    continue
                used_fields.add(meta["field"])
                course = course_rows.get(cid)
                if course:
                    earned += course["credits"]
                    completed_global[cid] = course["credits"]
                completed_count += 1
        else:
            for cid in course_ids:
                course = course_rows.get(cid)
                if not course:
                    continue
                if progress.get(cid) == "completed":
                    earned += course["credits"]
                    completed_count += 1
                    completed_global[cid] = course["credits"]
                else:
                    missing.append(cid)

        satisfied = _category_satisfied(cat, earned, completed_count)
        if not satisfied:
            all_satisfied = False

        categories.append(CategoryProgressOut(
            key=key,
            min_credits=required,
            earned_credits=earned,
            color=cat.get("color", "blue"),
            pick_n=pick_n,
            completed_count=completed_count,
            total_courses=len(ge_list) if is_ge else len(course_ids),
            satisfied=satisfied,
            missing_course_ids=missing,
        ))

        # Recommend not-started courses only while the category is unsatisfied;
        # for a pick_n pool, cap at the remaining slot count.
        if not satisfied:
            deficit = max(0, pick_n - completed_count) if pick_n is not None else None
            recommended_here = 0
            # GE recommends unblocked, not-started courses whose field isn't
            # already earned (field diversity); required pools walk course_ids.
            if is_ge:
                cand_ids = [
                    c["id"] for c in ge_list
                    if not c["blocked"]
                    and progress.get(c["id"]) not in ("completed", "in_progress")
                    and c["field"] not in used_fields
                ]
            else:
                cand_ids = course_ids
            for cid in cand_ids:
                if len(recs) >= 3:
                    break
                if deficit is not None and recommended_here >= deficit:
                    break
                course = course_rows.get(cid)
                if not course:
                    continue
                if not is_ge:
                    if progress.get(cid) in ("completed", "in_progress"):
                        continue
                    prereqs = _parse_prereqs(course.get("prerequisites"))
                    if prereqs and not all(progress.get(p) == "completed" for p in prereqs):
                        continue
                recs.append(RecommendedCourseOut(
                    course_id=course["id"],
                    code=course["code"],
                    name=course["name"],
                    credits=course["credits"],
                    category_key=key,
                    needed_credits=max(0, required - earned),
                ))
                recommended_here += 1

    total_earned = sum(completed_global.values())
    return categories, total_earned, recs, all_satisfied


@router.get("/programmes", response_model=ProgrammeCatalogueOut)
async def list_programmes():
    """Programme catalogue — static reference data (public, no auth).

    Lets clients render the selector and per-programme requirements without a
    second call; graduation numbers come from /graduation-status.
    """
    programmes = [_programme_to_out(code, prog) for code, prog in PROGRAMMES.items()]
    return ProgrammeCatalogueOut(
        default_code=DEFAULT_PROGRAMME_CODE, programmes=programmes,
    )


# NOTE: these two /catalogue routes MUST stay before @router.get("/{course_id}")
# below — otherwise FastAPI captures "catalogue" as a course_id path param.
# Catalogue responses are static reference data seeded from HKMU's public PDFs
# (107 programmes / ~4700 courses) — read on every planner open, written only
# by a re-seed. Cache 10 min per instance so the hot path skips Postgres.
_CATALOGUE_CACHE = TTLCache(ttl_seconds=600, max_entries=128)
@router.get("/catalogue/programmes", response_model=CatalogueProgrammesResponse)
async def list_catalogue_programmes():
    """All programmes with an official course catalogue (public, no auth).

    Returns every HKMU programme extracted from the public Programme
    Requirements PDFs, grouped by school. ``has_full_planning`` marks the few
    programmes (currently DSAI) that additionally carry graduation-planning
    data via /programmes + /graduation-status.
    """
    cached = _CATALOGUE_CACHE.get("programmes")
    if cached is not None:
        return cached
    async with get_db() as db:
        rows = await db.fetch(
            """SELECT programme_code, programme_name, name_zh_cn, name_zh_tw,
                      school, course_count, has_full_planning
               FROM programmes_catalogue
               ORDER BY school_order, prog_order"""
        )
    schools: dict[str, CatalogueSchoolGroupOut] = {}
    for r in rows:
        grp = schools.setdefault(
            r["school"], CatalogueSchoolGroupOut(school=r["school"], programmes=[])
        )
        grp.programmes.append(CatalogueProgrammeOut(
            programme_code=r["programme_code"],
            programme_name=r["programme_name"],
            name_zh_cn=r["name_zh_cn"],
            name_zh_tw=r["name_zh_tw"],
            school=r["school"],
            course_count=r["course_count"],
            has_full_planning=r["has_full_planning"],
        ))
    resp = CatalogueProgrammesResponse(
        default_programme_code=DEFAULT_PROGRAMME_CODE,
        schools=list(schools.values()),
    )
    _CATALOGUE_CACHE.set("programmes", resp)
    return resp


@router.get("/catalogue", response_model=CatalogueCoursesResponse)
async def get_catalogue_courses(
    programme_code: str = Query(..., min_length=4, max_length=20),
):
    """Official course catalogue for one programme (public, no auth).

    Browse-only grouped course list sourced from HKMU's public PDFs — no
    term / prerequisite / graduation info. Clients must surface the disclaimer.
    """
    cache_key = f"courses:{programme_code}"
    cached = _CATALOGUE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    async with get_db() as db:
        prog = await db.fetchrow(
            """SELECT programme_code, programme_name, school, has_full_planning
               FROM programmes_catalogue WHERE programme_code = $1""",
            programme_code,
        )
        if not prog:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Programme not in catalogue")
        rows = await db.fetch(
            """SELECT course_code, display_name, name_zh_cn, credits, code_system,
                      official_group, canonical_bucket, bucket_order
               FROM course_catalogue WHERE programme_code = $1
               ORDER BY bucket_order, official_group, course_code_sort""",
            programme_code,
        )
    buckets: dict[str, CatalogueBucketOut] = {}
    # A course can appear under several official_groups in the source PDF (e.g.
    # "Core (Middle Level)" and "Core (Higher Level)") that collapse into the
    # same bucket — de-dup by course_code programme-wide so each course shows
    # once (first occurrence in bucket/group order wins). Avoids repeated cards
    # and WeChat wx:key="code" collisions.
    seen_codes: set[str] = set()
    for r in rows:
        code = r["course_code"]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        key = r["canonical_bucket"]
        b = buckets.get(key)
        if b is None:
            b = buckets[key] = CatalogueBucketOut(
                key=key,
                label_key=f"planner.catalogue.bucket_{key}",
                order=r["bucket_order"],
                courses=[],
            )
        b.courses.append(CatalogueCourseOut(
            course_code=r["course_code"],
            display_name=r["display_name"],
            name_zh_cn=r["name_zh_cn"],
            credits=r["credits"],
            code_system=r["code_system"],
            official_group=r["official_group"],
        ))
    resp = CatalogueCoursesResponse(
        programme_code=prog["programme_code"],
        programme_name=prog["programme_name"],
        school=prog["school"],
        has_full_planning=prog["has_full_planning"],
        disclaimer_key="planner.catalogue.disclaimer",
        buckets=sorted(buckets.values(), key=lambda b: b.order),
    )
    _CATALOGUE_CACHE.set(cache_key, resp)
    return resp


@router.get("/graduation-status", response_model=GraduationStatusOut)
async def get_graduation_status(
    programme_code: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Graduation progress + recommendations for the current user.

    Programme is resolved as: query param > user's saved programme_code > default.
    """
    async with get_db() as db:
        code = programme_code
        if not code:
            row = await db.fetchrow(
                "SELECT programme_code FROM users WHERE id = $1", user["id"],
            )
            code = row["programme_code"] if row else None
        prog = get_programme(code)
        resolved_code = prog["code"]
        coming_soon = prog.get("coming_soon", False)

        course_rows: dict = {}
        progress: dict = {}
        if not coming_soon:
            all_ids = [
                cid for cat in prog.get("categories", {}).values()
                for cid in cat.get("courses", [])
            ]
            # A pool="ge" category carries an empty courses list; splice in the
            # real GE ids so their rows (credits) get fetched for the calc.
            if any(c.get("pool") == "ge" for c in prog.get("categories", {}).values()):
                all_ids += [c["id"] for c in ge_courses_for(resolved_code)]
            if all_ids:
                rows = await db.fetch(
                    "SELECT id, code, name, credits, prerequisites "
                    "FROM courses WHERE id = ANY($1::text[])",
                    all_ids,
                )
                course_rows = {r["id"]: dict(r) for r in rows}

                prows = await db.fetch(
                    "SELECT course_id, status FROM user_courses WHERE user_id = $1",
                    user["id"],
                )
                progress = {r["course_id"]: r["status"] for r in prows}

    if coming_soon:
        return GraduationStatusOut(
            programme_code=resolved_code,
            coming_soon=True,
            total_credits=prog.get("total_credits", 0),
            earned_credits=0,
            percent=0.0,
            categories=[],
            recommendations=[],
        )

    categories, total_earned, recs, all_satisfied = _compute_graduation(prog, course_rows, progress)
    total_required = prog.get("total_credits", 0)
    pct = min(100.0, total_earned / total_required * 100) if total_required > 0 else 0.0

    return GraduationStatusOut(
        programme_code=resolved_code,
        coming_soon=False,
        total_credits=total_required,
        earned_credits=total_earned,
        percent=round(pct, 1),
        categories=categories,
        recommendations=recs,
        all_categories_satisfied=all_satisfied,
    )


@router.get("/ge", response_model=GEListOut)
async def list_ge_courses(programme_code: str | None = None):
    """General Education course pool (3-credit-unit, 2026/27 AY). Public.

    Returns every GE course on offer, each flagged ``blocked`` if it falls in
    the given programme's own 'field of study' — the student may not take GE
    from their own field. Group/field order follows the official guide.
    """
    own = PROGRAMME_GE_FIELDS.get(programme_code or "", [])
    courses = [GECourseOut(**c) for c in ge_courses_for(programme_code)]
    return GEListOut(
        programme_code=programme_code,
        own_fields=own,
        field_order=list(GE_FIELD_ORDER),
        courses=courses,
    )


@router.get("/{course_id}", response_model=CourseOut)
async def get_course(course_id: str):
    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT * FROM courses WHERE id = $1", course_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
        return _course_row_to_out(row)


# ── User progress ────────────────────────────────────────────────────────────

@router.get("/progress/me", response_model=list[UserCourseOut])
async def get_my_progress(user: dict = Depends(get_current_user)):
    async with get_db() as db:
        rows = await db.fetch(
            "SELECT course_id, status, updated_at FROM user_courses WHERE user_id = $1",
            user["id"],
        )
        return [
            UserCourseOut(
                course_id=r["course_id"],
                status=r["status"],
                updated_at=r["updated_at"].isoformat() if isinstance(r["updated_at"], datetime) else r["updated_at"],
            )
            for r in rows
        ]


@router.put("/progress", response_model=UserCourseOut)
async def upsert_progress(
    body: UserCourseUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        # Verify course exists
        exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", body.course_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

        now = datetime.now(timezone.utc)
        await db.execute(
            """INSERT INTO user_courses (user_id, course_id, status, updated_at)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT(user_id, course_id) DO UPDATE SET
                   status = excluded.status,
                   updated_at = excluded.updated_at""",
            user["id"], body.course_id, body.status, now,
        )

    return UserCourseOut(course_id=body.course_id, status=body.status, updated_at=now.isoformat())


@router.post("/progress/batch", response_model=list[UserCourseOut])
async def batch_upsert_progress(
    body: BatchProgressUpdate,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    results = []

    async with get_db() as db:
        async with db.transaction():
            for item in body.items:
                exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", item.course_id)
                if not exists:
                    continue

                await db.execute(
                    """INSERT INTO user_courses (user_id, course_id, status, updated_at)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT(user_id, course_id) DO UPDATE SET
                           status = excluded.status,
                           updated_at = excluded.updated_at""",
                    user["id"], item.course_id, item.status, now,
                )
                results.append(UserCourseOut(course_id=item.course_id, status=item.status, updated_at=now_iso))

    return results


@router.delete("/progress/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_progress(
    course_id: str,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        await db.execute(
            "DELETE FROM user_courses WHERE user_id = $1 AND course_id = $2",
            user["id"], course_id,
        )


# ── Course reviews ───────────────────────────────────────────────────────────

@router.get("/{course_id}/reviews", response_model=PaginatedResponse)
async def list_reviews(
    course_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    offset = (page - 1) * page_size

    async with get_db() as db:
        exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", course_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

        total = (await db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM course_reviews WHERE course_id = $1",
            course_id,
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT {_REVIEW_COLS}
                FROM course_reviews cr
                JOIN users u ON u.id = cr.author_id
                WHERE cr.course_id = $1
                ORDER BY cr.created_at DESC
                LIMIT $2 OFFSET $3""",
            course_id, page_size, offset,
        )
        items = [_review_row_to_out(r).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.post(
    "/{course_id}/reviews",
    response_model=CourseReviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    course_id: str,
    body: CourseReviewCreate,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    safe_content = body.content

    async with get_db() as db:
        exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", course_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

        # One review per user per course
        dup = await db.fetchrow(
            "SELECT id FROM course_reviews WHERE course_id = $1 AND author_id = $2",
            course_id, user["id"],
        )
        if dup:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You have already reviewed this course",
            )

        row = await db.fetchrow(
            """INSERT INTO course_reviews (course_id, author_id, rating, content, created_at)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id""",
            course_id, user["id"], body.rating, safe_content, now,
        )
        review_id = row["id"]

        r = await db.fetchrow(
            f"""SELECT {_REVIEW_COLS}
                FROM course_reviews cr
                JOIN users u ON u.id = cr.author_id
                WHERE cr.id = $1""",
            review_id,
        )
        return _review_row_to_out(r)


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_review(
    review_id: int,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT author_id FROM course_reviews WHERE id = $1",
            review_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
        if row["author_id"] != user["id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your review")

        await db.execute("DELETE FROM course_reviews WHERE id = $1", review_id)
