from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from ..database import get_db
from ..models import (
    PostCreate, PostUpdate, PostOut,
    CommentCreate, CommentOut,
    PaginatedResponse,
)
from ..services.auth_service import get_current_user, oauth2_scheme
from ..services.rate_limiter import check_rate_limit
from ..services.sanitizer import sanitize_dict

router = APIRouter(prefix="/posts", tags=["posts"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _batch_liked_set(post_ids: list[int], user_id: int) -> set[int]:
    if not post_ids:
        return set()
    db = await get_db()
    placeholders = ",".join("?" * len(post_ids))
    cur = await db.execute(
        f"SELECT post_id FROM post_likes WHERE user_id = ? AND post_id IN ({placeholders})",
        [user_id] + post_ids,
    )
    return {r["post_id"] for r in await cur.fetchall()}


def _post_row_to_out(row, liked_set: set[int] | None = None) -> PostOut:
    return PostOut(
        id=row["id"],
        author_id=row["author_id"],
        title=row["title"],
        content=row["content"],
        category=row["category"],
        likes_count=row["likes_count"],
        comments_count=row["comments_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        author_nickname=row["author_nickname"],
        author_avatar=row["avatar_url"],
        is_liked=row["id"] in liked_set if liked_set else False,
    )


# ── Posts CRUD ───────────────────────────────────────────────────────────────

async def _get_optional_user(token: str | None = Depends(oauth2_scheme)) -> dict | None:
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


@router.get("", response_model=PaginatedResponse)
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    sort: str = Query("newest", pattern=r"^(newest|hot)$"),
    category: str | None = None,
    search: str | None = None,
    user: dict | None = Depends(_get_optional_user),
):
    db = await get_db()
    offset = (page - 1) * page_size

    conditions = []
    params: list = []
    if category:
        conditions.append("p.category = ?")
        params.append(category)
    if search:
        conditions.append("(p.title LIKE ? OR p.content LIKE ?)")
        params.extend([f"%{search}%"] * 2)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if sort == "hot":
        order = "p.likes_count DESC, p.created_at DESC"
    else:
        order = "p.created_at DESC"

    # total
    cur = await db.execute(
        f"SELECT COUNT(*) AS cnt FROM posts p {where}", params
    )
    total = (await cur.fetchone())["cnt"]

    # data
    cur = await db.execute(
        f"""SELECT p.*, u.nickname AS author_nickname, u.avatar_url
            FROM posts p
            JOIN users u ON u.id = p.author_id
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    rows = await cur.fetchall()

    # batch like check (1 query instead of N)
    liked_set: set[int] = set()
    if user and rows:
        liked_set = await _batch_liked_set([r["id"] for r in rows], user["id"])

    items = [_post_row_to_out(r, liked_set).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: int):
    db = await get_db()
    cur = await db.execute(
        """SELECT p.*, u.nickname AS author_nickname, u.avatar_url
           FROM posts p
           JOIN users u ON u.id = p.author_id
           WHERE p.id = ?""",
        (post_id,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return await _post_row_to_out(row, set())


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(body: PostCreate, user: dict = Depends(get_current_user)):
    check_rate_limit(f"post:{user['id']}", max_requests=10, window_seconds=60)
    db = await get_db()
    safe = sanitize_dict(
        {"title": body.title, "content": body.content, "category": body.category},
        "title", "content", "category",
    )
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO posts (author_id, title, content, category, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user["id"], safe["title"], safe["content"], safe["category"], now, now),
    )
    await db.commit()

    post_id = cur.lastrowid
    cur = await db.execute(
        """SELECT p.*, u.nickname AS author_nickname, u.avatar_url
           FROM posts p JOIN users u ON u.id = p.author_id
           WHERE p.id = ?""",
        (post_id,),
    )
    row = await cur.fetchone()
    return await _post_row_to_out(row, {post_id})


@router.put("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    body: PostUpdate,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
    existing = await cur.fetchone()
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if existing["author_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your post")

    updates = {}
    if body.title is not None:
        updates["title"] = sanitize(body.title)
    if body.content is not None:
        updates["content"] = sanitize(body.content)
    if body.category is not None:
        updates["category"] = sanitize(body.category)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await db.execute(
        f"UPDATE posts SET {set_clause} WHERE id = ?",
        list(updates.values()) + [post_id],
    )
    await db.commit()

    cur = await db.execute(
        """SELECT p.*, u.nickname AS author_nickname, u.avatar_url
           FROM posts p JOIN users u ON u.id = p.author_id
           WHERE p.id = ?""",
        (post_id,),
    )
    row = await cur.fetchone()
    return await _post_row_to_out(row, {post_id})


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute("SELECT author_id FROM posts WHERE id = ?", (post_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if row["author_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your post")

    await db.execute("DELETE FROM post_likes WHERE post_id = ?", (post_id,))
    await db.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
    await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    await db.commit()


# ── Likes ────────────────────────────────────────────────────────────────────

@router.post("/{post_id}/like", response_model=PostOut)
async def toggle_like(post_id: int, user: dict = Depends(get_current_user)):
    db = await get_db()
    cur = await db.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

    cur = await db.execute(
        "SELECT 1 FROM post_likes WHERE user_id = ? AND post_id = ?",
        (user["id"], post_id),
    )
    already_liked = await cur.fetchone() is not None

    if already_liked:
        await db.execute(
            "DELETE FROM post_likes WHERE user_id = ? AND post_id = ?",
            (user["id"], post_id),
        )
        await db.execute(
            "UPDATE posts SET likes_count = likes_count - 1 WHERE id = ?",
            (post_id,),
        )
    else:
        await db.execute(
            "INSERT INTO post_likes (user_id, post_id) VALUES (?, ?)",
            (user["id"], post_id),
        )
        await db.execute(
            "UPDATE posts SET likes_count = likes_count + 1 WHERE id = ?",
            (post_id,),
        )
    await db.commit()

    cur = await db.execute(
        """SELECT p.*, u.nickname AS author_nickname, u.avatar_url
           FROM posts p JOIN users u ON u.id = p.author_id
           WHERE p.id = ?""",
        (post_id,),
    )
    row = await cur.fetchone()
    now_liked = not already_liked
    return await _post_row_to_out(row, {post_id} if now_liked else set())


# ── Comments ─────────────────────────────────────────────────────────────────

@router.get("/{post_id}/comments", response_model=PaginatedResponse)
async def list_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    db = await get_db()
    cur = await db.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

    offset = (page - 1) * page_size

    cur = await db.execute(
        "SELECT COUNT(*) AS cnt FROM comments WHERE post_id = ?", (post_id,)
    )
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        """SELECT c.*, u.nickname AS author_nickname, u.avatar_url AS author_avatar
           FROM comments c
           JOIN users u ON u.id = c.author_id
           WHERE c.post_id = ?
           ORDER BY c.created_at ASC
           LIMIT ? OFFSET ?""",
        (post_id, page_size, offset),
    )
    rows = await cur.fetchall()

    items = [
        CommentOut(
            id=r["id"],
            post_id=r["post_id"],
            author_id=r["author_id"],
            content=r["content"],
            likes_count=r["likes_count"],
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
    "/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: int,
    body: CommentCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"comment:{user['id']}", max_requests=15, window_seconds=60)
    db = await get_db()
    cur = await db.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
    if not await cur.fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

    safe_content = sanitize(body.content)
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO comments (post_id, author_id, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (post_id, user["id"], safe_content, now),
    )
    await db.execute(
        "UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?",
        (post_id,),
    )
    await db.commit()

    comment_id = cur.lastrowid
    cur = await db.execute(
        """SELECT c.*, u.nickname AS author_nickname, u.avatar_url AS author_avatar
           FROM comments c
           JOIN users u ON u.id = c.author_id
           WHERE c.id = ?""",
        (comment_id,),
    )
    r = await cur.fetchone()
    return CommentOut(
        id=r["id"],
        post_id=r["post_id"],
        author_id=r["author_id"],
        content=r["content"],
        likes_count=r["likes_count"],
        created_at=r["created_at"],
        author_nickname=r["author_nickname"],
        author_avatar=r["author_avatar"],
    )


# used by update_post — import from sanitizer directly
from ..services.sanitizer import sanitize
