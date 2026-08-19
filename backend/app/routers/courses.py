import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from ..database import get_db
from ..models import (
    CourseOut, UserCourseUpdate, UserCourseOut,
    CourseReviewCreate, CourseReviewOut, PaginatedResponse,
    REVIEW_TAGS,
    CourseTagAggregate, CourseReviewTagsOut, CourseReviewStatsOut,
    GECourseInfoOut,
)
from ..data.programmes import (
    PROGRAMMES, DEFAULT_PROGRAMME_CODE, get_programme, DISCONTINUED_CODES,
)
from ..data.ge_courses import (
    GE_FIELD_ORDER, PROGRAMME_GE_FIELDS, ge_courses_for, ge_course_by_id,
)
from ..data.ge_catalog_enrichment import GE_SCHOOL_NAMES
from ..services.cache import TTLCache
from ..services.content_security import audit_user_text, SCENE_COMMENT
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



# T27 排课台: 单课学年覆盖(upsert)。planned_* 优先于 courses 表默认值。
class ScheduleUpdate(BaseModel):
    course_id: str
    planned_year: int = Field(ge=1, le=4)
    planned_semester: str = Field(pattern=r"^(autumn|spring|summer)$")


class ScheduleEntryOut(BaseModel):
    course_id: str
    planned_year: int
    planned_semester: str
    updated_at: str | None = None

from ..services.auth_service import get_current_user

router = APIRouter(prefix="/courses", tags=["courses"])

# 可选鉴权(标签云 voted 标记):未带 token/过期 → None,不 401(同 posts.py 范式)
_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def _get_optional_user(token: str | None = Depends(_optional_oauth2)) -> dict | None:
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


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
    discontinued: bool = False


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
    # offering terms in the current guide window (2026 Autumn → 2027 Summer);
    # [] = not offered in the window. Parsed from the GE Selection Guide PDF.
    terms: list[str] = []
    # 官方目录富化(小字段;description/school_name 只走详情 GET /{id} 的 ge 子
    # 对象,列表不带长文本)。level=官方「程度」1000|2000,moi=english|chinese|bilingual。
    credits: int = 3
    level: int = 0
    moi: str = ""
    excluded: list[str] = []


class GEListOut(BaseModel):
    programme_code: str | None = None
    own_fields: list[str] = Field(default_factory=list)
    field_order: list[str] = Field(default_factory=list)
    courses: list[GECourseOut]


class GERankTagOut(BaseModel):
    tag: str
    count: int


class GERankItemOut(BaseModel):
    id: str
    code: str
    name_en: str
    name_zh: str
    field: str
    score: float  # (给分+收获+(5-工作量))/3, 1-5, 越高越值得修
    review_count: int  # 该课全部评论数(含老 5 星)
    teaching_avg: float
    workload_avg: float
    gain_avg: float
    top_tags: list[GERankTagOut] = Field(default_factory=list)


class GERankingOut(BaseModel):
    programme_code: str | None = None
    total: int = 0
    items: list[GERankItemOut] = Field(default_factory=list)


class GEGuideStepOut(BaseModel):
    key: str  # stable i18n key — 前端按 key 映射三语，缺失时回退 title/detail(zh)
    title: str
    detail: str


class GEGuideOut(BaseModel):
    select_url: str  # MyHKMU portal login (复制链接用)
    pdf_url: str     # 官方 GE Courses Selection Guide PDF
    pdf_updated: str
    tutorial_steps: list[GEGuideStepOut]


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


def _ge_info_for(course_id: str) -> GECourseInfoOut | None:
    """官方 GE 目录信息(纯常量 join,不碰 DB);非 GE 课返回 None。

    学院缩写按目录打印名反查——官方文件内课码第5字母与「所屬學院」栏偶有出入
    (GEN 1510NCF/2501NEF 印 S&T),展示以目录为准。"""
    src = ge_course_by_id(course_id)
    if not src:
        return None
    printed = src.get("school_name", "")
    school = src.get("school", "")
    for abbr, names in GE_SCHOOL_NAMES.items():
        if printed in {names["pdf_verbatim"][0], names["pdf_verbatim"][1],
                       names["en"], names["zh"]}:
            school = abbr
            break
    return GECourseInfoOut(
        field=src["field"],
        level=src.get("level", 0),
        moi=src.get("moi", ""),
        terms=src.get("terms", []),
        excluded=src.get("excluded", []),
        description=src.get("description", ""),
        school=school,
        school_name=printed,
    )


def _review_row_to_out(row, author_tags: list[str] | None = None) -> CourseReviewOut:
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return CourseReviewOut(
        id=row["id"],
        course_id=row["course_id"],
        author_id=row["author_id"],
        rating=row["rating"],
        rating_teaching=row["rating_teaching"] if "rating_teaching" in row.keys() else None,
        rating_workload=row["rating_workload"] if "rating_workload" in row.keys() else None,
        rating_gain=row["rating_gain"] if "rating_gain" in row.keys() else None,
        content=row["content"],
        helpful_count=row["helpful_count"],
        created_at=created_at,
        author_nickname=row["author_nickname"],
        tags=author_tags or [],
    )


_REVIEW_COLS = """cr.id, cr.course_id, cr.author_id, cr.rating,
    cr.rating_teaching, cr.rating_workload, cr.rating_gain, cr.content,
    cr.helpful_count, cr.created_at,
    u.nickname AS author_nickname"""


# ── Course listing & detail ──────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse)
async def list_courses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),  # le 50→500: GE 灌表后 courses 表 114 门，planner _loadCourses 需 page_size=200 一次拉全（le=50 会 422 返空 → "我的课程"空）。reviews 端点 le=50 不动（50/页合理）
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

    - credit pool (pool:"credits", programme_rules electives): satisfied
      purely by earned >= min_credits — any course combination counts, which
      is how "N credit-units from the elective table (or 150-course STEAM
      menu)" is actually specified in the PDFs.
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
    if cat.get("pool") == "credits":
        return earned >= required
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
            discontinued=r["programme_code"] in DISCONTINUED_CODES,
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

    Returns the full official GE catalog (89 courses: 73 offered this AY +
    16 not offered, terms=[]), each flagged ``blocked`` if it falls in the
    given programme's own 'field of study' — the student may not take GE
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


@router.get("/ge/ranking", response_model=GERankingOut)
async def ge_ranking(programme_code: str | None = None):
    """GE 评分榜(T18):三维简单平均 (给分+收获+(5-工作量))/3,降序。

    进榜条件:课程不属本专业禁选领域(blocked 过滤)且三维均分齐全 —
    老 5 星-only 或缺维度的课不产生分数(前端退回领域视图,T20)。
    附每课前 3 个避坑标签计数。公开无鉴权。
    """
    pool = [c for c in ge_courses_for(programme_code) if not c["blocked"]]
    ids = [c["id"] for c in pool]
    stats: dict = {}
    tags: dict[str, list] = {}
    if ids:
        async with get_db() as db:
            stat_rows = await db.fetch(
                """SELECT course_id,
                          COUNT(*) AS cnt,
                          AVG(rating_teaching) AS teaching_avg,
                          AVG(rating_workload) AS workload_avg,
                          AVG(rating_gain) AS gain_avg
                   FROM course_reviews WHERE course_id = ANY($1)
                   GROUP BY course_id""",
                ids,
            )
            stats = {r["course_id"]: r for r in stat_rows}
            tag_rows = await db.fetch(
                """SELECT course_id, tag, COUNT(*) AS cnt FROM course_review_tags
                   WHERE course_id = ANY($1) GROUP BY course_id, tag""",
                ids,
            )
            for tr in tag_rows:
                tags.setdefault(tr["course_id"], []).append((tr["tag"], tr["cnt"]))

    items = []
    for c in pool:
        s = stats.get(c["id"])
        if not s or s["teaching_avg"] is None or s["workload_avg"] is None or s["gain_avg"] is None:
            continue
        t, w, g = (float(s["teaching_avg"]), float(s["workload_avg"]), float(s["gain_avg"]))
        top = sorted(tags.get(c["id"], []), key=lambda x: -x[1])[:3]
        items.append(GERankItemOut(
            id=c["id"], code=c["code"], name_en=c["name_en"], name_zh=c["name_zh"],
            field=c["field"],
            score=round((t + g + (5 - w)) / 3, 1),
            review_count=s["cnt"],
            teaching_avg=round(t, 1), workload_avg=round(w, 1), gain_avg=round(g, 1),
            top_tags=[GERankTagOut(tag=tg, count=cn) for tg, cn in top],
        ))
    items.sort(key=lambda i: (-i.score, i.code))
    return GERankingOut(programme_code=programme_code, total=len(items), items=items)


# T22: GE 选课官方教程配置。纯静态(无 DB、无图片)——PDF 转图整条链已砍,
# 教程目的=学会流程,4 步够。步骤 3 的"本专业领域"高亮由前端结合 /ge 的
# own_fields 动态渲染(后端不知道用户专业,不掺和)。URL 均实测可达:
# myhkmu 302 登录跳转、PDF 206(2026-08-13 验证)。
_GE_GUIDE = GEGuideOut(
    select_url="https://myhkmu.hkmu.edu.hk/",
    pdf_url=(
        "https://www.hkmu.edu.hk/REG/reg_ftae/GE/"
        "General%20Education%20Courses%20Selection%20Guide_3cru.pdf"
    ),
    pdf_updated="2026-08-07",  # PDF 自述的 last updated,换版时同步改
    tutorial_steps=[
        GEGuideStepOut(
            key="pick_two",
            title="选 2 门通识 · 6 学分",
            detail="每门 3 学分。在本应用「选课程」里点选，即可加入毕业规划。",
        ),
        GEGuideStepOut(
            key="different_fields",
            title="两门必须来自不同领域",
            detail="field of study 须互异，同领域选 2 门只算 1 门。例：创意艺术 + 健康科学 ✓",
        ),
        GEGuideStepOut(
            key="avoid_own_field",
            title="避开你的专业领域",
            detail="本专业所属领域的 GE 官方禁选，选课器里已自动置灰并标「禁选」。",
        ),
        GEGuideStepOut(
            key="enrol",
            title="去 MyHKMU 正式注册",
            detail="登录 MyHKMU → 点你的专业 → Classes & Enrolment → Enrolment - UG → "
                   "Class Search 搜课号(如 GEN1001ABF)→ 提交后到 My Class Schedule 确认。",
        ),
    ],
)


@router.get("/ge/guide", response_model=GEGuideOut)
async def ge_guide():
    """GE 选课教程配置(T22):select_url + pdf_url + 4 步文案。公开无鉴权。"""
    return _GE_GUIDE


@router.get("/{course_id}", response_model=CourseOut)
async def get_course(course_id: str):
    async with get_db() as db:
        row = await db.fetchrow(
            "SELECT * FROM courses WHERE id = $1", course_id,
        )
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
        out = _course_row_to_out(row)
    # GE 课挂官方目录信息(纯常量 join,不查库);非 GE 保持 ge=None
    out.ge = _ge_info_for(course_id)
    return out


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


@router.get("/progress/schedule", response_model=list[ScheduleEntryOut])
async def get_schedule(user: dict = Depends(get_current_user)):
    """T27 排课台: 当前用户全部学年覆盖行。空列表 = 全按课程默认安排。"""
    async with get_db() as db:
        rows = await db.fetch(
            """SELECT course_id, planned_year, planned_semester, updated_at
               FROM user_course_schedule WHERE user_id = $1
               ORDER BY course_id""",
            user["id"],
        )
        return [
            ScheduleEntryOut(
                course_id=r["course_id"],
                planned_year=r["planned_year"],
                planned_semester=r["planned_semester"],
                updated_at=r["updated_at"].isoformat() if isinstance(r["updated_at"], datetime) else r["updated_at"],
            )
            for r in rows
        ]


@router.put("/progress/schedule", response_model=ScheduleEntryOut)
async def upsert_schedule(
    body: ScheduleUpdate,
    user: dict = Depends(get_current_user),
):
    """T27 排课台: upsert 单课学年覆盖(planned_* 优先于 courses 表默认)。"""
    async with get_db() as db:
        exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", body.course_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

        now = datetime.now(timezone.utc)
        await db.execute(
            """INSERT INTO user_course_schedule (user_id, course_id, planned_year, planned_semester, updated_at)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT(user_id, course_id) DO UPDATE SET
                   planned_year = excluded.planned_year,
                   planned_semester = excluded.planned_semester,
                   updated_at = excluded.updated_at""",
            user["id"], body.course_id, body.planned_year, body.planned_semester, now,
        )

    return ScheduleEntryOut(
        course_id=body.course_id,
        planned_year=body.planned_year,
        planned_semester=body.planned_semester,
        updated_at=now.isoformat(),
    )


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
        # T14: 作者标签票一次批量取(避免逐行 N+1)
        tag_map: dict[int, list[str]] = {}
        author_ids = [r["author_id"] for r in rows]
        if author_ids:
            tag_rows = await db.fetch(
                """SELECT user_id, tag FROM course_review_tags
                   WHERE course_id = $1 AND user_id = ANY($2)""",
                course_id, author_ids,
            )
            for tr in tag_rows:
                tag_map.setdefault(tr["user_id"], []).append(tr["tag"])
        items = [
            _review_row_to_out(r, tag_map.get(r["author_id"])).model_dump()
            for r in rows
        ]

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

        # UGC text gate(版本修改指引 3.2「任意发布场景生效」):课评正文
        # 是公开展示的用户文本,与帖子/评论同标准审核。
        await audit_user_text(user, body.content, SCENE_COMMENT)

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
            """INSERT INTO course_reviews
                   (course_id, author_id, rating, rating_teaching,
                    rating_workload, rating_gain, content, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            course_id, user["id"], body.rating,
            body.rating_teaching, body.rating_workload, body.rating_gain,
            safe_content, now,
        )
        review_id = row["id"]

        # T14: 作者标签随评论落票(重复投过幂等跳过)
        for tag in body.tags:
            await db.execute(
                """INSERT INTO course_review_tags (course_id, user_id, tag)
                   VALUES ($1, $2, $3) ON CONFLICT DO NOTHING""",
                course_id, user["id"], tag,
            )

        author_tags = [tr["tag"] for tr in await db.fetch(
            "SELECT tag FROM course_review_tags WHERE course_id = $1 AND user_id = $2",
            course_id, user["id"],
        )]
        r = await db.fetchrow(
            f"""SELECT {_REVIEW_COLS}
                FROM course_reviews cr
                JOIN users u ON u.id = cr.author_id
                WHERE cr.id = $1""",
            review_id,
        )
        return _review_row_to_out(r, author_tags)


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


# ── 避坑标签投票 + 三维统计(T14) ──────────────────────────────────────────────

def _require_valid_tag(tag: str) -> None:
    if tag not in REVIEW_TAGS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown tag: {tag}",
        )


async def _require_course(db, course_id: str) -> None:
    exists = await db.fetchrow("SELECT id FROM courses WHERE id = $1", course_id)
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")


@router.get("/{course_id}/review-tags", response_model=CourseReviewTagsOut)
async def list_review_tags(
    course_id: str,
    user: dict | None = Depends(_get_optional_user),
):
    """标签云聚合(计数倒序)+ 当前查看者 voted 标记;未登录只看计数。"""
    async with get_db() as db:
        await _require_course(db, course_id)
        rows = await db.fetch(
            """SELECT tag, COUNT(*) AS cnt FROM course_review_tags
               WHERE course_id = $1 GROUP BY tag ORDER BY cnt DESC, tag""",
            course_id,
        )
        voted: set[str] = set()
        if user:
            voted = {
                r["tag"] for r in await db.fetch(
                    """SELECT tag FROM course_review_tags
                       WHERE course_id = $1 AND user_id = $2""",
                    course_id, user["id"],
                )
            }
    return CourseReviewTagsOut(
        course_id=course_id,
        total_votes=sum(r["cnt"] for r in rows),
        tags=[
            CourseTagAggregate(tag=r["tag"], count=r["cnt"], voted=r["tag"] in voted)
            for r in rows
        ],
    )


@router.post("/{course_id}/review-tags/{tag}", status_code=status.HTTP_201_CREATED)
async def vote_review_tag(
    course_id: str,
    tag: str,
    user: dict = Depends(get_current_user),
):
    _require_valid_tag(tag)
    async with get_db() as db:
        await _require_course(db, course_id)
        # 一人一票:重复投幂等
        await db.execute(
            """INSERT INTO course_review_tags (course_id, user_id, tag)
               VALUES ($1, $2, $3) ON CONFLICT DO NOTHING""",
            course_id, user["id"], tag,
        )
    return {"ok": True, "tag": tag}


@router.delete(
    "/{course_id}/review-tags/{tag}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unvote_review_tag(
    course_id: str,
    tag: str,
    user: dict = Depends(get_current_user),
):
    _require_valid_tag(tag)
    async with get_db() as db:
        await db.execute(
            """DELETE FROM course_review_tags
               WHERE course_id = $1 AND user_id = $2 AND tag = $3""",
            course_id, user["id"], tag,
        )


def _avg1(v) -> float | None:
    return None if v is None else round(float(v), 1)


@router.get("/{course_id}/review-stats", response_model=CourseReviewStatsOut)
async def review_stats(course_id: str):
    """三维均分 + 老 5 星均分;无数据的维度为 None(T15 头部直接判空降级)。"""
    async with get_db() as db:
        await _require_course(db, course_id)
        row = await db.fetchrow(
            """SELECT COUNT(*) AS cnt,
                      AVG(rating) AS rating_avg,
                      AVG(rating_teaching) AS teaching_avg,
                      AVG(rating_workload) AS workload_avg,
                      AVG(rating_gain) AS gain_avg
               FROM course_reviews WHERE course_id = $1""",
            course_id,
        )
    return CourseReviewStatsOut(
        course_id=course_id,
        review_count=row["cnt"],
        rating_avg=_avg1(row["rating_avg"]),
        teaching_avg=_avg1(row["teaching_avg"]),
        workload_avg=_avg1(row["workload_avg"]),
        gain_avg=_avg1(row["gain_avg"]),
    )
