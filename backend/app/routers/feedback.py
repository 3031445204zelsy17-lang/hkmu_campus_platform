from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import (
    FEEDBACK_PER_HOUR, MAX_FEEDBACK_PER_USER, FEEDBACK_RETENTION_DAYS,
)
from ..database import get_db
from ..models import FeedbackCreate, FeedbackOut
from ..services.auth_service import get_current_user
from ..services.rate_limiter import check_rate_limit

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),
):
    """Lightweight in-app feedback.

    Auth required: ties feedback to a user for follow-up and anti-spam.
    Content is stored as-is; render with textContent (not innerHTML) if surfaced.

    Anti-abuse (Codex [16]): per-user rate (bursts) + per-user quota (lifetime
    count) + opportunistic retention (prune rows older than the window so the
    table can't grow unbounded). Without these any authenticated user could
    spam unlimited rows.
    """
    # Per-user rate — checked before any DB work (in-memory limiter).
    check_rate_limit(
        f"feedback:{user['id']}", max_requests=FEEDBACK_PER_HOUR, window_seconds=3600
    )

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="content required")

    contact = payload.contact.strip() if payload.contact else None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FEEDBACK_RETENTION_DAYS)

    async with get_db() as db:
        async with db.transaction():
            # Opportunistic retention: prune expired feedback (range delete on
            # idx_feedback_created — cheap; feedback is low-volume). Runs before
            # the quota count so expired feedback no longer counts against a
            # user's cap, letting them submit again after the window.
            await db.execute("DELETE FROM feedback WHERE created_at < $1", cutoff)

            count = await db.fetchval(
                "SELECT COUNT(*) FROM feedback WHERE user_id = $1", user["id"]
            )
            if count >= MAX_FEEDBACK_PER_USER:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Feedback limit reached. Please contact support if urgent.",
                )

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
