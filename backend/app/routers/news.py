from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import NewsCreate, NewsOut, PaginatedResponse
from ..services.auth_service import get_current_user
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/news", tags=["news"])


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
            title=r["title"],
            summary=r["summary"],
            image_url=r["image_url"],
            category=r["category"],
            source_url=r["source_url"],
            published_at=r["published_at"],
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
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO news (title, summary, image_url, category, source_url, published_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sanitize(body.title), body.summary, body.image_url, body.category,
         sanitize(body.source_url), now),
    )
    await db.commit()

    news_id = cur.lastrowid
    cur = await db.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    r = await cur.fetchone()
    return NewsOut(
        id=r["id"], title=r["title"], summary=r["summary"],
        image_url=r["image_url"], category=r["category"],
        source_url=r["source_url"], published_at=r["published_at"],
    )


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(
    news_id: int,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute("SELECT id FROM news WHERE id = ?", (news_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

    await db.execute("DELETE FROM news WHERE id = ?", (news_id,))
    await db.commit()
