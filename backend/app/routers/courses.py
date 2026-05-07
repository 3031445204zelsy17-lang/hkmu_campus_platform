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
    db = await get_db()
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list = []

    if year is not None:
        conditions.append("year = ?")
        params.append(year)
    if semester:
        conditions.append("semester = ?")
        params.append(semester)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(name LIKE ? OR code LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur = await db.execute(f"SELECT COUNT(*) AS cnt FROM courses {where}", params)
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        f"""SELECT * FROM courses {where}
            ORDER BY year, semester, code
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    rows = await cur.fetchall()
    items = [_course_row_to_out(r).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.get("/{course_id}", response_model=CourseOut)
async def get_course(course_id: str):
    db = await get_db()
    cur = await db.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return _course_row_to_out(row)


# ── User progress ────────────────────────────────────────────────────────────

@router.get("/progress/me", response_model=list[UserCourseOut])
async def get_my_progress(user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute(
        "SELECT course_id, status, updated_at FROM user_courses WHERE user_id = ?",
        (user["id"],),
    )
    rows = await cur.fetchall()
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
    db = await get_db()

    # Verify course exists
    cur = await db.execute("SELECT id FROM courses WHERE id = ?", (body.course_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO user_courses (user_id, course_id, status, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, course_id) DO UPDATE SET
               status = excluded.status,
               updated_at = excluded.updated_at""",
        (user["id"], body.course_id, body.status, now),
    )
    await db.commit()

    return UserCourseOut(course_id=body.course_id, status=body.status, updated_at=now)


@router.post("/progress/batch", response_model=list[UserCourseOut])
async def batch_upsert_progress(
    body: BatchProgressUpdate,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    results = []

    for item in body.items:
        cur = await db.execute("SELECT id FROM courses WHERE id = ?", (item.course_id,))
        if not await cur.fetchone():
            continue

        await db.execute(
            """INSERT INTO user_courses (user_id, course_id, status, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, course_id) DO UPDATE SET
                   status = excluded.status,
                   updated_at = excluded.updated_at""",
            (user["id"], item.course_id, item.status, now),
        )
        results.append(UserCourseOut(course_id=item.course_id, status=item.status, updated_at=now))

    await db.commit()
    return results


@router.delete("/progress/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_progress(
    course_id: str,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    await db.execute(
        "DELETE FROM user_courses WHERE user_id = ? AND course_id = ?",
        (user["id"], course_id),
    )
    await db.commit()


# ── Course reviews ───────────────────────────────────────────────────────────

@router.get("/{course_id}/reviews", response_model=PaginatedResponse)
async def list_reviews(
    course_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    db = await get_db()
    cur = await db.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    offset = (page - 1) * page_size

    cur = await db.execute(
        "SELECT COUNT(*) AS cnt FROM course_reviews WHERE course_id = ?",
        (course_id,),
    )
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        """SELECT cr.*, u.nickname AS author_nickname
           FROM course_reviews cr
           JOIN users u ON u.id = cr.author_id
           WHERE cr.course_id = ?
           ORDER BY cr.created_at DESC
           LIMIT ? OFFSET ?""",
        (course_id, page_size, offset),
    )
    rows = await cur.fetchall()
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
    db = await get_db()
    cur = await db.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    # One review per user per course
    cur = await db.execute(
        "SELECT id FROM course_reviews WHERE course_id = ? AND author_id = ?",
        (course_id, user["id"]),
    )
    if await cur.fetchone():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You have already reviewed this course",
        )

    now = datetime.now(timezone.utc).isoformat()
    safe_content = sanitize(body.content)

    cur = await db.execute(
        """INSERT INTO course_reviews (course_id, author_id, rating, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (course_id, user["id"], body.rating, safe_content, now),
    )
    await db.commit()

    review_id = cur.lastrowid
    cur = await db.execute(
        """SELECT cr.*, u.nickname AS author_nickname
           FROM course_reviews cr
           JOIN users u ON u.id = cr.author_id
           WHERE cr.id = ?""",
        (review_id,),
    )
    r = await cur.fetchone()
    return _review_row_to_out(r)


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_review(
    review_id: int,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute(
        "SELECT author_id FROM course_reviews WHERE id = ?",
        (review_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    if row["author_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your review")

    await db.execute("DELETE FROM course_reviews WHERE id = ?", (review_id,))
    await db.commit()
