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


@router.get("", response_model=PaginatedResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    item_type: str | None = Query(None, pattern=r"^(lost|found)$"),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(active|resolved)$"),
    category: str | None = None,
):
    db = await get_db()
    offset = (page - 1) * page_size

    conditions = []
    params: list = []

    if item_type:
        conditions.append("item_type = ?")
        params.append(item_type)
    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)
    if category:
        conditions.append("category = ?")
        params.append(category)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur = await db.execute(f"SELECT COUNT(*) AS cnt FROM lostfound {where}", params)
    total = (await cur.fetchone())["cnt"]

    cur = await db.execute(
        f"""SELECT lf.*, u.nickname AS author_nickname
            FROM lostfound lf
            JOIN users u ON u.id = lf.author_id
            {where}
            ORDER BY lf.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    )
    rows = await cur.fetchall()
    items = [
        LostFoundOut(
            id=r["id"],
            author_id=r["author_id"],
            title=r["title"],
            description=r["description"],
            item_type=r["item_type"],
            category=r["category"],
            location=r["location"],
            image_url=r["image_url"],
            status=r["status"],
            created_at=r["created_at"],
            author_nickname=r["author_nickname"],
        ).model_dump()
        for r in rows
    ]

    return PaginatedResponse(
        items=items, total=total, page=page,
        page_size=page_size, has_next=(offset + page_size) < total,
    )


@router.get("/{item_id}", response_model=LostFoundOut)
async def get_item(item_id: int):
    db = await get_db()
    cur = await db.execute(
        """SELECT lf.*, u.nickname AS author_nickname
           FROM lostfound lf
           JOIN users u ON u.id = lf.author_id
           WHERE lf.id = ?""",
        (item_id,),
    )
    r = await cur.fetchone()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")

    return LostFoundOut(
        id=r["id"], author_id=r["author_id"], title=r["title"],
        description=r["description"], item_type=r["item_type"],
        category=r["category"], location=r["location"],
        image_url=r["image_url"], status=r["status"],
        created_at=r["created_at"], author_nickname=r["author_nickname"],
    )


@router.post("", response_model=LostFoundOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: LostFoundCreate,
    user: dict = Depends(get_current_user),
):
    check_rate_limit(f"lostfound:{user['id']}", max_requests=10, window_seconds=60)
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    cur = await db.execute(
        """INSERT INTO lostfound (author_id, title, description, item_type, category, location, image_url, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user["id"], sanitize(body.title), sanitize(body.description), body.item_type,
         body.category, body.location, body.image_url, now),
    )
    await db.commit()

    item_id = cur.lastrowid
    cur = await db.execute(
        """SELECT lf.*, u.nickname AS author_nickname
           FROM lostfound lf JOIN users u ON u.id = lf.author_id
           WHERE lf.id = ?""",
        (item_id,),
    )
    r = await cur.fetchone()
    return LostFoundOut(
        id=r["id"], author_id=r["author_id"], title=r["title"],
        description=r["description"], item_type=r["item_type"],
        category=r["category"], location=r["location"],
        image_url=r["image_url"], status=r["status"],
        created_at=r["created_at"], author_nickname=r["author_nickname"],
    )


@router.put("/{item_id}", response_model=LostFoundOut)
async def update_item(
    item_id: int,
    body: LostFoundUpdate,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute("SELECT author_id FROM lostfound WHERE id = ?", (item_id,))
    existing = await cur.fetchone()
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

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    await db.execute(
        f"UPDATE lostfound SET {set_clause} WHERE id = ?",
        list(updates.values()) + [item_id],
    )
    await db.commit()

    cur = await db.execute(
        """SELECT lf.*, u.nickname AS author_nickname
           FROM lostfound lf JOIN users u ON u.id = lf.author_id
           WHERE lf.id = ?""",
        (item_id,),
    )
    r = await cur.fetchone()
    return LostFoundOut(
        id=r["id"], author_id=r["author_id"], title=r["title"],
        description=r["description"], item_type=r["item_type"],
        category=r["category"], location=r["location"],
        image_url=r["image_url"], status=r["status"],
        created_at=r["created_at"], author_nickname=r["author_nickname"],
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    user: dict = Depends(get_current_user),
):
    db = await get_db()
    cur = await db.execute("SELECT author_id FROM lostfound WHERE id = ?", (item_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    if row["author_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your item")

    await db.execute("DELETE FROM lostfound WHERE id = ?", (item_id,))
    await db.commit()
