from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import NewsCreate, NewsOut, NewsCommentCreate, NewsCommentOut, PaginatedResponse
from ..services.auth_service import get_current_user
from ..services.rate_limiter import check_rate_limit
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/news", tags=["news"])


async def _is_admin(user_id: int) -> bool:
    db = await get_db()
    cur = await db.execute("SELECT identity FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    return row is not None and row["identity"] == "admin"


@router.get("", response_model=PaginatedResponse)
async def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    category: str | None = None,
):
    db = await get_db()
    offset = (page - 1) * page_size

    conditions = []
    params: list = []

    if category:
        conditions.append("category = ?")
        params.append(category)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur = await db.execute(f"SELECT COUNT(*) AS cnt FROM news {where}", params)
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        f"""SELECT * FROM news {where}
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    rows = await cur.fetchall()
    items = [
        NewsOut(
            id=r["id"],
            author_id=r["author_id"],
            title=r["title"],
            summary=r["summary"],
            image_url=r["image_url"],
            category=r["category"],
            source_url=r["source_url"],
            published_at=r["published_at"],
            comments_count=r["comments_count"] if "comments_count" in r.keys() else 0,
        ).model_dump()
        for r in rows
    ]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.post("", response_model=NewsOut, status_code=status.HTTP_201_CREATED)
async def create_news(
    body: NewsCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"news:{user['id']}", max_requests=10, window_seconds=60)
    if not await _is_admin(user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO news (author_id, title, summary, image_url, category, source_url, published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user["id"], sanitize(body.title), body.summary, body.image_url, body.category,
         sanitize(body.source_url), now),
    )
    await db.commit()

    news_id = cur.lastrowid
    cur = await db.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    r = await cur.fetchone()
    return NewsOut(
        id=r["id"], author_id=r["author_id"], title=r["title"], summary=r["summary"],
        image_url=r["image_url"], category=r["category"],
        source_url=r["source_url"], published_at=r["published_at"],
    )


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(
    news_id: int,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute("SELECT author_id FROM news WHERE id = ?", (news_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")
    is_admin = await _is_admin(user["id"])
    if row["author_id"] != user["id"] and not is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your news")

    await db.execute("DELETE FROM news WHERE id = ?", (news_id,))
    await db.commit()


# ── News Comments ────────────────────────────────────────────────────────────

@router.get("/{news_id}/comments", response_model=PaginatedResponse)
async def list_news_comments(
    news_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    db = await get_db()
    cur = await db.execute("SELECT id FROM news WHERE id = ?", (news_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

    offset = (page - 1) * page_size

    cur = await db.execute(
        "SELECT COUNT(*) AS cnt FROM news_comments WHERE news_id = ?", (news_id,)
    )
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        """SELECT nc.*, u.nickname AS author_nickname, u.avatar_url AS author_avatar
           FROM news_comments nc
           JOIN users u ON u.id = nc.author_id
           WHERE nc.news_id = ?
           ORDER BY nc.created_at ASC
           LIMIT ? OFFSET ?""",
        (news_id, page_size, offset),
    )
    rows = await cur.fetchall()

    items = [
        NewsCommentOut(
            id=r["id"],
            news_id=r["news_id"],
            author_id=r["author_id"],
            content=r["content"],
            created_at=r["created_at"],
            author_nickname=r["author_nickname"],
            author_avatar=r["author_avatar"],
        ).model_dump()
        for r in rows
    ]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.post(
    "/{news_id}/comments",
    response_model=NewsCommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_news_comment(
    news_id: int,
    body: NewsCommentCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"news_comment:{user['id']}", max_requests=15, window_seconds=60)
    db = await get_db()
    cur = await db.execute("SELECT id FROM news WHERE id = ?", (news_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

    safe_content = sanitize(body.content)
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO news_comments (news_id, author_id, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (news_id, user["id"], safe_content, now),
    )
    await db.execute(
        "UPDATE news SET comments_count = comments_count + 1 WHERE id = ?",
        (news_id,),
    )
    await db.commit()

    comment_id = cur.lastrowid
    cur = await db.execute(
        """SELECT nc.*, u.nickname AS author_nickname, u.avatar_url AS author_avatar
           FROM news_comments nc
           JOIN users u ON u.id = nc.author_id
           WHERE nc.id = ?""",
        (comment_id,),
    )
    r = await cur.fetchone()
    return NewsCommentOut(
        id=r["id"],
        news_id=r["news_id"],
        author_id=r["author_id"],
        content=r["content"],
        created_at=r["created_at"],
        author_nickname=r["author_nickname"],
        author_avatar=r["author_avatar"],
    )
