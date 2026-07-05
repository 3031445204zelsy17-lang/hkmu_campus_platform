from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_db
from ..models import FeedbackCreate, FeedbackOut
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),
):
    """Lightweight in-app feedback.

    Auth required: ties feedback to a user for follow-up and anti-spam.
    Content is stored as-is; render with textContent (not innerHTML) if surfaced.
    """
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="content required")

    contact = payload.contact.strip() if payload.contact else None

    async with get_db() as db:
        row = await db.fetchrow(
            """INSERT INTO feedback (user_id, rating, content, contact)
               VALUES ($1, $2, $3, $4)
               RETURNING id, rating, content, contact, created_at""",
            user["id"], payload.rating, content, contact,
        )

    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    return FeedbackOut(
        id=row["id"],
        rating=row["rating"],
        content=row["content"],
        contact=row["contact"],
        created_at=created_at,
    )
