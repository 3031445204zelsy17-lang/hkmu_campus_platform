from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer

from ..database import get_db
from ..config import HOT_GRAVITY, HOT_SEED
from ..models import (
    PostCreate, PostUpdate, PostOut, QuotedPostOut,
    CommentCreate, CommentOut,
    PaginatedResponse,
)
from ..services.auth_service import get_current_user, oauth2_scheme
from ..services.rate_limiter import check_rate_limit
from ..services.content_security import audit_user_text, SCENE_FORUM, SCENE_COMMENT

_optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

router = APIRouter(prefix="/posts", tags=["posts"])


# ── Column selectors ────────────────────────────────────────────────────────

_POST_COLS = """p.id, p.author_id, p.title, p.content, p.category,
    p.likes_count, p.comments_count, p.parent_post_id, p.is_anonymous,
    p.image_url, p.created_at, p.updated_at"""

_COMMENT_COLS = """c.id, c.post_id, c.author_id, c.content,
    c.likes_count, c.created_at"""


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _batch_liked_set(post_ids: list[int], user_id: int) -> set[int]:
    if not post_ids:
        return set()
    async with get_db() as db:
        placeholders = ",".join(f"${i+2}" for i in range(len(post_ids)))
        rows = await db.fetch(
            f"SELECT post_id FROM post_likes WHERE user_id = $1 AND post_id IN ({placeholders})",
            user_id, *post_ids,
        )
        return {r["post_id"] for r in rows}


async def _is_admin(user_id: int) -> bool:
    async with get_db() as db:
        row = await db.fetchrow("SELECT identity FROM users WHERE id = $1", user_id)
        return row is not None and row["identity"] == "admin"


def _fmt_ts(val):
    """Convert a datetime or string to ISO format string."""
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def _post_row_to_out(row, liked_set: set[int] | None = None,
                     viewer_id: int | None = None, is_admin: bool = False) -> PostOut:
    quoted = None
    # Only build the quoted block if the parent post still exists. delete_post()
    # removes the parent but leaves the child's parent_post_id FK dangling, so the
    # LEFT JOIN yields NULL parent fields → QuotedPostOut(title/id are required)
    # would raise a 500. parent_id is non-NULL only when the LEFT JOIN matched a
    # live parent row, so guard on it.
    if row["parent_post_id"] and row["parent_id"]:
        # Hide the quoted (parent) post's author when that post is anonymous,
        # unless the viewer is an admin — mirrors the main post's anon visibility.
        parent_anon = bool(row["parent_is_anonymous"]) if "parent_is_anonymous" in row.keys() else False
        show_parent_author = (not parent_anon) or is_admin
        quoted = QuotedPostOut(
            id=row["parent_id"],
            author_nickname=(row["parent_author"] if show_parent_author and "parent_author" in row.keys() else None),
            title=row["parent_title"],
            content_preview=(row["parent_content"] or "")[:150],
            created_at=_fmt_ts(row["parent_created"]) if "parent_created" in row.keys() else None,
        )
    is_anon = bool(row["is_anonymous"]) if "is_anonymous" in row.keys() else False
    show_author = True
    if is_anon:
        show_author = is_admin or (viewer_id is not None and row["author_id"] == viewer_id)
    return PostOut(
        id=row["id"],
        author_id=row["author_id"] if show_author else None,
        title=row["title"],
        content=row["content"],
        category=row["category"],
        likes_count=row["likes_count"],
        comments_count=row["comments_count"],
        created_at=_fmt_ts(row["created_at"]),
        updated_at=_fmt_ts(row["updated_at"]),
        author_nickname=row["author_nickname"] if show_author else None,
        author_avatar=row["avatar_url"] if show_author else None,
        is_liked=row["id"] in liked_set if liked_set else False,
        parent_post_id=row["parent_post_id"],
        quoted_post=quoted,
        is_anonymous=is_anon,
        image_url=row["image_url"] if "image_url" in row.keys() else None,
    )


# ── Posts CRUD ───────────────────────────────────────────────────────────────

async def _get_optional_user(token: str | None = Depends(_optional_oauth2)) -> dict | None:
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
    async with get_db() as db:
        offset = (page - 1) * page_size

        # ── build filter conditions (reusable for total & data queries) ──
        def _filter(start_n: int):
            conds, params, n = [], [], start_n
            if category:
                conds.append(f"p.category = ${n}"); params.append(category); n += 1
            if search:
                conds.append(f"(p.title LIKE ${n} OR p.content LIKE ${n+1})")
                params.extend([f"%{search}%"] * 2); n += 2
            where = ("WHERE " + " AND ".join(conds)) if conds else ""
            return where, params, n

        # ── total count ──
        where, fparams, _ = _filter(start_n=1)
        total = (await db.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM posts p {where}", *fparams
        ))["cnt"]

        # ── data query ──
        dparams: list = []
        dn = 1
        if sort == "hot":
            hot_seed_n = dn; dparams.append(HOT_SEED); dn += 1
            hot_gravity_n = dn; dparams.append(HOT_GRAVITY); dn += 1
        where2, fp2, dn = _filter(start_n=dn)
        dparams.extend(fp2)

        limit_n = dn; dparams.append(page_size); dn += 1
        offset_n = dn; dparams.append(offset)

        if sort == "hot":
            order = (
                "(LN(GREATEST(1, p.likes_count + p.comments_count * 2))"
                f" + ${hot_seed_n} - (EXTRACT(EPOCH FROM (NOW() - p.created_at)) / 3600) / ${hot_gravity_n})"
                " DESC, p.created_at DESC"
            )
        else:
            order = "p.created_at DESC"

        rows = await db.fetch(
            f"""SELECT {_POST_COLS}, u.nickname AS author_nickname, u.avatar_url,
                   pp.id AS parent_id, pp.title AS parent_title,
                   pp.content AS parent_content, pp.created_at AS parent_created,
                   pu.nickname AS parent_author,
                   pp.is_anonymous AS parent_is_anonymous
                FROM posts p
                JOIN users u ON u.id = p.author_id
                LEFT JOIN posts pp ON pp.id = p.parent_post_id
                LEFT JOIN users pu ON pu.id = pp.author_id
                {where2}
                ORDER BY {order}
                LIMIT ${limit_n} OFFSET ${offset_n}""",
            *dparams,
        )

        # batch like check (1 query instead of N)
        liked_set: set[int] = set()
        viewer_id = user["id"] if user else None
        is_admin_flag = await _is_admin(viewer_id) if viewer_id else False
        if user and rows:
            liked_set = await _batch_liked_set([r["id"] for r in rows], user["id"])

        items = [_post_row_to_out(r, liked_set, viewer_id=viewer_id, is_admin=is_admin_flag).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: int, user: dict | None = Depends(_get_optional_user)):
    async with get_db() as db:
        row = await db.fetchrow(
            f"""SELECT {_POST_COLS}, u.nickname AS author_nickname, u.avatar_url,
                   pp.id AS parent_id, pp.title AS parent_title,
                   pp.content AS parent_content, pp.created_at AS parent_created,
                   pu.nickname AS parent_author,
                   pp.is_anonymous AS parent_is_anonymous
               FROM posts p
               JOIN users u ON u.id = p.author_id
               LEFT JOIN posts pp ON pp.id = p.parent_post_id
               LEFT JOIN users pu ON pu.id = pp.author_id
               WHERE p.id = $1""",
            post_id,
        )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    viewer_id = user["id"] if user else None
    is_admin_flag = await _is_admin(viewer_id) if viewer_id else False
    return _post_row_to_out(row, set(), viewer_id=viewer_id, is_admin=is_admin_flag)


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(body: PostCreate, user: dict = Depends(get_current_user)):
    check_rate_limit(f"post:{user['id']}", max_requests=10, window_seconds=60)

    async with get_db() as db:
        if body.parent_post_id:
            exists = await db.fetchval("SELECT id FROM posts WHERE id = $1", body.parent_post_id)
            if not exists:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Original post not found")

        await audit_user_text(user, f"{body.title} {body.content}", SCENE_FORUM)
        now = datetime.now(timezone.utc)

        is_anonymous = body.is_anonymous
        if body.category == "treehole":
            is_anonymous = True

        new_row = await db.fetchrow(
            """INSERT INTO posts (author_id, title, content, category, parent_post_id, is_anonymous, image_url, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
            user["id"], body.title, body.content, body.category,
            body.parent_post_id, is_anonymous, body.image_url, now, now,
        )
        post_id = new_row["id"]

        row = await db.fetchrow(
            f"""SELECT {_POST_COLS}, u.nickname AS author_nickname, u.avatar_url,
                   pp.id AS parent_id, pp.title AS parent_title,
                   pp.content AS parent_content, pp.created_at AS parent_created,
                   pu.nickname AS parent_author,
                   pp.is_anonymous AS parent_is_anonymous
               FROM posts p
               JOIN users u ON u.id = p.author_id
               LEFT JOIN posts pp ON pp.id = p.parent_post_id
               LEFT JOIN users pu ON pu.id = pp.author_id
               WHERE p.id = $1""",
            post_id,
        )
        is_admin_flag = await _is_admin(user["id"])

    return _post_row_to_out(row, set(), viewer_id=user["id"], is_admin=is_admin_flag)


@router.put("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    body: PostUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        existing = await db.fetchrow("SELECT author_id FROM posts WHERE id = $1", post_id)
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
        if existing["author_id"] != user["id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your post")

        # Moderation on edit — mirrors create_post so users can't bypass content
        # security by posting clean then editing in violations.
        if body.title is not None or body.content is not None:
            await audit_user_text(user, f"{body.title or ''} {body.content or ''}", SCENE_FORUM)

        updates = {}
        if body.title is not None:
            updates["title"] = body.title
        if body.content is not None:
            updates["content"] = body.content
        if body.category is not None:
            updates["category"] = body.category
        if not updates:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

        updates["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(updates.keys()))
        where_n = len(updates) + 1
        await db.execute(
            f"UPDATE posts SET {set_clause} WHERE id = ${where_n}",
            *list(updates.values()), post_id,
        )

        row = await db.fetchrow(
            f"""SELECT {_POST_COLS}, u.nickname AS author_nickname, u.avatar_url,
                   pp.id AS parent_id, pp.title AS parent_title,
                   pp.content AS parent_content, pp.created_at AS parent_created,
                   pu.nickname AS parent_author,
                   pp.is_anonymous AS parent_is_anonymous
               FROM posts p JOIN users u ON u.id = p.author_id
               LEFT JOIN posts pp ON pp.id = p.parent_post_id
               LEFT JOIN users pu ON pu.id = pp.author_id
               WHERE p.id = $1""",
            post_id,
        )
        is_admin_flag = await _is_admin(user["id"])

    return _post_row_to_out(row, set(), viewer_id=user["id"], is_admin=is_admin_flag)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, user: dict = Depends(get_current_user)):
    async with get_db() as db:
        row = await db.fetchrow("SELECT author_id FROM posts WHERE id = $1", post_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
        is_admin_flag = await _is_admin(user["id"])
        if row["author_id"] != user["id"] and not is_admin_flag:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your post")

        async with db.transaction():
            await db.execute("DELETE FROM post_likes WHERE post_id = $1", post_id)
            await db.execute("DELETE FROM comments WHERE post_id = $1", post_id)
            await db.execute("DELETE FROM posts WHERE id = $1", post_id)


# ── Likes ────────────────────────────────────────────────────────────────────

@router.post("/{post_id}/like", response_model=PostOut)
async def toggle_like(post_id: int, user: dict = Depends(get_current_user)):
    async with get_db() as db:
        exists = await db.fetchval("SELECT id FROM posts WHERE id = $1", post_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

        async with db.transaction():
            liked = await db.fetchrow(
                "SELECT 1 FROM post_likes WHERE user_id = $1 AND post_id = $2",
                user["id"], post_id,
            )
            already_liked = liked is not None

            if already_liked:
                await db.execute(
                    "DELETE FROM post_likes WHERE user_id = $1 AND post_id = $2",
                    user["id"], post_id,
                )
                await db.execute(
                    "UPDATE posts SET likes_count = likes_count - 1 WHERE id = $1",
                    post_id,
                )
            else:
                await db.execute(
                    "INSERT INTO post_likes (user_id, post_id) VALUES ($1, $2)",
                    user["id"], post_id,
                )
                await db.execute(
                    "UPDATE posts SET likes_count = likes_count + 1 WHERE id = $1",
                    post_id,
                )

        row = await db.fetchrow(
            f"""SELECT {_POST_COLS}, u.nickname AS author_nickname, u.avatar_url,
                   pp.id AS parent_id, pp.title AS parent_title,
                   pp.content AS parent_content, pp.created_at AS parent_created,
                   pu.nickname AS parent_author,
                   pp.is_anonymous AS parent_is_anonymous
               FROM posts p JOIN users u ON u.id = p.author_id
               LEFT JOIN posts pp ON pp.id = p.parent_post_id
               LEFT JOIN users pu ON pu.id = pp.author_id
               WHERE p.id = $1""",
            post_id,
        )
        now_liked = not already_liked
        is_admin_flag = await _is_admin(user["id"])

    return _post_row_to_out(row, {post_id} if now_liked else set(),
                            viewer_id=user["id"], is_admin=is_admin_flag)


# ── Comments ─────────────────────────────────────────────────────────────────

@router.get("/{post_id}/comments", response_model=PaginatedResponse)
async def list_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    async with get_db() as db:
        exists = await db.fetchval("SELECT id FROM posts WHERE id = $1", post_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

        offset = (page - 1) * page_size

        total = (await db.fetchrow(
            "SELECT COUNT(*) AS cnt FROM comments WHERE post_id = $1", post_id
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT {_COMMENT_COLS}, u.nickname AS author_nickname, u.avatar_url AS author_avatar
               FROM comments c
               JOIN users u ON u.id = c.author_id
               WHERE c.post_id = $1
               ORDER BY c.created_at ASC
               LIMIT $2 OFFSET $3""",
            post_id, page_size, offset,
        )

        items = [
            CommentOut(
                id=r["id"],
                post_id=r["post_id"],
                author_id=r["author_id"],
                content=r["content"],
                likes_count=r["likes_count"],
                created_at=_fmt_ts(r["created_at"]),
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

    async with get_db() as db:
        exists = await db.fetchval("SELECT id FROM posts WHERE id = $1", post_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")

        await audit_user_text(user, body.content, SCENE_COMMENT)
        now = datetime.now(timezone.utc)

        async with db.transaction():
            new_row = await db.fetchrow(
                """INSERT INTO comments (post_id, author_id, content, created_at)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                post_id, user["id"], body.content, now,
            )
            comment_id = new_row["id"]
            await db.execute(
                "UPDATE posts SET comments_count = comments_count + 1 WHERE id = $1",
                post_id,
            )

        r = await db.fetchrow(
            f"""SELECT {_COMMENT_COLS}, u.nickname AS author_nickname, u.avatar_url AS author_avatar
               FROM comments c
               JOIN users u ON u.id = c.author_id
               WHERE c.id = $1""",
            comment_id,
        )

    return CommentOut(
        id=r["id"],
        post_id=r["post_id"],
        author_id=r["author_id"],
        content=r["content"],
        likes_count=r["likes_count"],
        created_at=_fmt_ts(r["created_at"]),
        author_nickname=r["author_nickname"],
        author_avatar=r["author_avatar"],
    )
