from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import NewsCreate, NewsOut, NewsCommentCreate, NewsCommentOut, PaginatedResponse
from ..services.auth_service import get_current_user
from ..services.rate_limiter import check_rate_limit
from ..services.sanitizer import sanitize
from ..services.content_security import audit_user_text, SCENE_COMMENT

router = APIRouter(prefix="/news", tags=["news"])

_NEWS_COLS = """id, author_id, title, summary, image_url, category,
    source_url, published_at, comments_count, lang"""

_COMMENT_COLS = """nc.id, nc.news_id, nc.author_id, nc.content,
    nc.created_at,
    u.nickname AS author_nickname, u.avatar_url AS author_avatar"""


async def _is_admin(user_id: int) -> bool:
    async with get_db() as db:
        row = await db.fetchrow("SELECT identity FROM users WHERE id = $1", user_id)
    return row is not None and row["identity"] == "admin"


@router.get("", response_model=PaginatedResponse)
async def list_news(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    category: str | None = None,
    lang: str | None = None,
):
    offset = (page - 1) * page_size

    conditions = []
    params: list = []
    n = 1

    # Filter by language. Defaults to zh-hant (Phase 6a ships Traditional only;
    # the ?lang param is the hook for the deferred trilingual rollout — see
    # progress.json phase6b_news_trilingual). Guarantees callers without ?lang
    # never see mixed or duplicate rows across languages.
    conditions.append(f"lang = ${n}")
    params.append(lang if lang else "zh-hant")
    n += 1

    if category:
        conditions.append(f"category = ${n}")
        params.append(category)
        n += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        total = (await db.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM news {where}", *params,
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT {_NEWS_COLS} FROM news {where}
                ORDER BY published_at DESC
                LIMIT ${n} OFFSET ${n+1}""",
            *params, page_size, offset,
        )
        items = [
            NewsOut(
                id=r["id"],
                author_id=r["author_id"],
                title=r["title"],
                summary=r["summary"],
                image_url=r["image_url"],
                category=r["category"],
                source_url=r["source_url"],
                published_at=r["published_at"].isoformat() if isinstance(r["published_at"], datetime) else r["published_at"],
                comments_count=r["comments_count"] if "comments_count" in r.keys() else 0,
                lang=r["lang"],
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

    now = datetime.now(timezone.utc)

    async with get_db() as db:
        row = await db.fetchrow(
            """INSERT INTO news (author_id, title, summary, image_url, category, source_url, published_at, lang)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            user["id"], sanitize(body.title), body.summary, body.image_url,
            body.category, sanitize(body.source_url), now,
            body.lang if body.lang else "zh-hant",
        )
        news_id = row["id"]

        r = await db.fetchrow(
            f"SELECT {_NEWS_COLS} FROM news WHERE id = $1", news_id,
        )
        published_at = r["published_at"]
        if isinstance(published_at, datetime):
            published_at = published_at.isoformat()
        return NewsOut(
            id=r["id"], author_id=r["author_id"], title=r["title"], summary=r["summary"],
            image_url=r["image_url"], category=r["category"],
            source_url=r["source_url"], published_at=published_at,
            comments_count=r["comments_count"], lang=r["lang"],
        )


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(
    news_id: int,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        row = await db.fetchrow("SELECT author_id FROM news WHERE id = $1", news_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

    is_admin = await _is_admin(user["id"])
    if row["author_id"] != user["id"] and not is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your news")

    async with get_db() as db:
        await db.execute("DELETE FROM news WHERE id = $1", news_id)


# ── News Comments ────────────────────────────────────────────────────────────

@router.get("/{news_id}/comments", response_model=PaginatedResponse)
async def list_news_comments(
    news_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    offset = (page - 1) * page_size

    async with get_db() as db:
        exists = await db.fetchrow("SELECT id FROM news WHERE id = $1", news_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

        total = (await db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM news_comments WHERE news_id = $1", news_id,
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT {_COMMENT_COLS}
                FROM news_comments nc
                JOIN users u ON u.id = nc.author_id
                WHERE nc.news_id = $1
                ORDER BY nc.created_at ASC
                LIMIT $2 OFFSET $3""",
            news_id, page_size, offset,
        )
        items = [
            NewsCommentOut(
                id=r["id"],
                news_id=r["news_id"],
                author_id=r["author_id"],
                content=r["content"],
                created_at=r["created_at"].isoformat() if isinstance(r["created_at"], datetime) else r["created_at"],
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

    safe_content = sanitize(body.content)
    await audit_user_text(user, body.content, SCENE_COMMENT)
    now = datetime.now(timezone.utc)

    async with get_db() as db:
        async with db.transaction():
            exists = await db.fetchrow("SELECT id FROM news WHERE id = $1", news_id)
            if not exists:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "News not found")

            row = await db.fetchrow(
                """INSERT INTO news_comments (news_id, author_id, content, created_at)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id""",
                news_id, user["id"], safe_content, now,
            )
            comment_id = row["id"]

            await db.execute(
                "UPDATE news SET comments_count = comments_count + 1 WHERE id = $1",
                news_id,
            )

            r = await db.fetchrow(
                f"""SELECT {_COMMENT_COLS}
                    FROM news_comments nc
                    JOIN users u ON u.id = nc.author_id
                    WHERE nc.id = $1""",
                comment_id,
            )
            created_at = r["created_at"]
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()
            return NewsCommentOut(
                id=r["id"],
                news_id=r["news_id"],
                author_id=r["author_id"],
                content=r["content"],
                created_at=created_at,
                author_nickname=r["author_nickname"],
                author_avatar=r["author_avatar"],
            )
