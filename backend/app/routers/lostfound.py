from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import (
    LostFoundCreate, LostFoundUpdate, LostFoundOut, PaginatedResponse,
)
from ..services.auth_service import get_current_user
from ..services.rate_limiter import check_rate_limit
from ..services.sanitizer import sanitize

router = APIRouter(prefix="/lostfound", tags=["lostfound"])

_LF_COLS = """lf.id, lf.author_id, lf.title, lf.description, lf.item_type,
    lf.category, lf.location, lf.image_url, lf.status,
    lf.created_at,
    u.nickname AS author_nickname"""


def _row_to_out(r) -> LostFoundOut:
    created_at = r["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return LostFoundOut(
        id=r["id"], author_id=r["author_id"], title=r["title"],
        description=r["description"], item_type=r["item_type"],
        category=r["category"], location=r["location"],
        image_url=r["image_url"], status=r["status"],
        created_at=created_at, author_nickname=r["author_nickname"],
    )


@router.get("", response_model=PaginatedResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    item_type: str | None = Query(None, pattern=r"^(lost|found)$"),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(active|resolved)$"),
    category: str | None = None,
):
    offset = (page - 1) * page_size

    conditions = []
    params: list = []
    n = 1

    if item_type:
        conditions.append(f"item_type = ${n}")
        params.append(item_type)
        n += 1
    if status_filter:
        conditions.append(f"status = ${n}")
        params.append(status_filter)
        n += 1
    if category:
        conditions.append(f"category = ${n}")
        params.append(category)
        n += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_db() as db:
        total = (await db.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM lostfound {where}", *params,
        ))["cnt"]

        rows = await db.fetch(
            f"""SELECT {_LF_COLS}
                FROM lostfound lf
                JOIN users u ON u.id = lf.author_id
                {where}
                ORDER BY lf.created_at DESC
                LIMIT ${n} OFFSET ${n+1}""",
            *params, page_size, offset,
        )
        items = [_row_to_out(r).model_dump() for r in rows]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.get("/{item_id}", response_model=LostFoundOut)
async def get_item(item_id: int):
    async with get_db() as db:
        r = await db.fetchrow(
            f"""SELECT {_LF_COLS}
                FROM lostfound lf
                JOIN users u ON u.id = lf.author_id
                WHERE lf.id = $1""",
            item_id,
        )
        if not r:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        return _row_to_out(r)


@router.post("", response_model=LostFoundOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: LostFoundCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"lostfound:{user['id']}", max_requests=10, window_seconds=60)
    now = datetime.now(timezone.utc)

    async with get_db() as db:
        row = await db.fetchrow(
            """INSERT INTO lostfound (author_id, title, description, item_type, category, location, image_url, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               RETURNING id""",
            user["id"], sanitize(body.title), sanitize(body.description), body.item_type,
            body.category, body.location, body.image_url, now,
        )
        item_id = row["id"]

        r = await db.fetchrow(
            f"""SELECT {_LF_COLS}
                FROM lostfound lf JOIN users u ON u.id = lf.author_id
                WHERE lf.id = $1""",
            item_id,
        )
        return _row_to_out(r)


@router.put("/{item_id}", response_model=LostFoundOut)
async def update_item(
    item_id: int,
    body: LostFoundUpdate,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        existing = await db.fetchrow("SELECT author_id FROM lostfound WHERE id = $1", item_id)
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        if existing["author_id"] != user["id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your item")

        updates = {}
        if body.title is not None:
            updates["title"] = sanitize(body.title)
        if body.description is not None:
            updates["description"] = sanitize(body.description)
        if body.status is not None:
            updates["status"] = body.status

        if not updates:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

        set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(updates.keys()))
        where_n = len(updates) + 1
        await db.execute(
            f"UPDATE lostfound SET {set_clause} WHERE id = ${where_n}",
            *list(updates.values()), item_id,
        )

        r = await db.fetchrow(
            f"""SELECT {_LF_COLS}
                FROM lostfound lf JOIN users u ON u.id = lf.author_id
                WHERE lf.id = $1""",
            item_id,
        )
        return _row_to_out(r)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    user: dict = Depends(get_current_user),
):
    async with get_db() as db:
        row = await db.fetchrow("SELECT author_id FROM lostfound WHERE id = $1", item_id)
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
        if row["author_id"] != user["id"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your item")

        await db.execute("DELETE FROM lostfound WHERE id = $1", item_id)
