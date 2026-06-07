import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import (
    CourseOut, UserCourseUpdate, UserCourseOut,
    CourseReviewCreate, CourseReviewOut, PaginatedResponse,
)
from pydantic import BaseModel


class BatchProgressUpdate(BaseModel):
    items: list[UserCourseUpdate]
from ..services.auth_service import get_current_user
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/courses", tags=["courses"])


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
    return CourseReviewOut(
        id=row["id"],
        course_id=row["course_id"],
        author_id=row["author_id"],
        rating=row["rating"],
        content=row["content"],
        helpful_count=row["helpful_count"],
        created_at=row["created_at"],
        author_nickname=row["author_nickname"],
    )


_REVIEW_COLS = """cr.id, cr.course_id, cr.author_id, cr.rating, cr.content,
    cr.helpful_count, cr.created_at::TEXT AS created_at,
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
            "SELECT course_id, status, updated_at::TEXT AS updated_at FROM user_courses WHERE user_id = $1",
            user["id"],
        )
        return [
            UserCourseOut(
                course_id=r["course_id"],
                status=r["status"],
                updated_at=r["updated_at"],
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

        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """INSERT INTO user_courses (user_id, course_id, status, updated_at)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT(user_id, course_id) DO UPDATE SET
                   status = excluded.status,
                   updated_at = excluded.updated_at""",
            user["id"], body.course_id, body.status, now,
        )

    return UserCourseOut(course_id=body.course_id, status=body.status, updated_at=now)


@router.post("/progress/batch", response_model=list[UserCourseOut])
async def batch_upsert_progress(
    body: BatchProgressUpdate,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc).isoformat()
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
                results.append(UserCourseOut(course_id=item.course_id, status=item.status, updated_at=now))

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
    now = datetime.now(timezone.utc).isoformat()
    safe_content = sanitize(body.content)

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
