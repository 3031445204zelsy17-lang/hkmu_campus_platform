"""UGC report (举报) — let a logged-in user flag illegal/abusive content for
admin review. FR4 compliance: a UGC platform must offer a report channel and a
way to act on it.

Scope (MVP): the miniprogram only wires `post` as a target, but the schema +
this router accept an extensible target_type enum (post / comment / lostfound /
news_comment / user) so adding more surfaces later is a frontend-only change.

Why report reason text is NOT run through WeChat msg_sec_check (unlike posts):
  1. The reason is admin-eyes-only (never rendered to other users), so the
     XSS / public-display moderation risk that justifies auditing posts does
     not apply here.
  2. Users frequently quote the offending content in their reason — running it
     through msg_sec_check would flag the REPORT itself as a violation and
     reject the report (the exact opposite of what we want).
  3. Once #57 (fail-closed) lands, a WeChat outage would 503 the audit call,
     which would BLOCK users from submitting reports. A report is a safety
     mechanism; it must stay available during a moderation outage.
So: store the reason verbatim, bound its length, and rely on rate + quota +
per-target dedup for anti-abuse.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import REPORT_PER_HOUR, MAX_REPORTS_PER_USER
from ..database import get_db
from ..models import ReportCreate, ReportOut, ReportStatusUpdate
from ..services.auth_service import get_current_user
from ..services.rate_limiter import check_rate_limit

router = APIRouter(prefix="/reports", tags=["reports"])


# Fixed enum keyed by the model-validated target_type → (table, pk column).
# target_type is constrained by ReportCreate's pattern, so the f-string table
# interpolation below is safe (no arbitrary user input reaches the SQL).
_TARGET_TABLE = {
    "post": ("posts", "id"),
    "comment": ("comments", "id"),
    "lostfound": ("lostfound", "id"),
    "news_comment": ("news_comments", "id"),
    "user": ("users", "id"),
}


def _require_admin(user: dict) -> None:
    """Raise 403 unless the current user is an admin. identity is already on the
    user dict (get_current_user selects it per request), so no extra DB hop —
    same philosophy as posts._is_admin."""
    if user.get("identity") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")


async def _assert_target_exists(db, target_type: str, target_id: int) -> None:
    """404 if the reported target no longer exists. Validates that reports
    always reference a real row (otherwise the report is meaningless and could
    be abused to enumerate deleted ids)."""
    table, col = _TARGET_TABLE[target_type]
    exists = await db.fetchval(f"SELECT 1 FROM {table} WHERE {col} = $1", target_id)
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{target_type} not found")


async def _target_label(db, target_type: str, target_id: int) -> str | None:
    """A short human label for the reported target (post title, comment snippet,
    user nickname, ...). Best-effort: returns None if the target was deleted
    between the report and the admin view. Used only by the admin list view."""
    try:
        if target_type == "post":
            return await db.fetchval("SELECT title FROM posts WHERE id = $1", target_id)
        if target_type == "lostfound":
            return await db.fetchval("SELECT title FROM lostfound WHERE id = $1", target_id)
        if target_type == "user":
            return await db.fetchval("SELECT nickname FROM users WHERE id = $1", target_id)
        if target_type == "comment":
            v = await db.fetchval("SELECT content FROM comments WHERE id = $1", target_id)
            return (v or "")[:50]
        if target_type == "news_comment":
            v = await db.fetchval("SELECT content FROM news_comments WHERE id = $1", target_id)
            return (v or "")[:50]
    except Exception:
        return None
    return None


def _report_out(row, target_label: str | None = None) -> ReportOut:
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return ReportOut(
        id=row["id"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        reason_code=row["reason_code"],
        detail=row["detail"],
        status=row["status"],
        created_at=created_at,
        reporter_nickname=row.get("reporter_nickname"),
        target_label=target_label,
    )


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def submit_report(
    payload: ReportCreate,
    user: dict = Depends(get_current_user),
):
    """Submit a report. Auth-required (ties reports to a user for anti-abuse).
    Dedup: the UNIQUE(reporter_id, target_type, target_id) constraint means one
    user can report each target at most once — a repeat returns 409. Rate +
    lifetime quota cap how many DISTINCT targets a single user can flag."""
    check_rate_limit(f"report:{user['id']}", max_requests=REPORT_PER_HOUR, window_seconds=3600)
    detail = (payload.detail or "").strip() or None

    async with get_db() as db:
        # Lifetime quota — bounds total rows a single user can generate.
        count = await db.fetchval(
            "SELECT COUNT(*) FROM reports WHERE reporter_id = $1", user["id"]
        )
        if count >= MAX_REPORTS_PER_USER:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Report limit reached. Contact support if urgent.",
            )

        await _assert_target_exists(db, payload.target_type, payload.target_id)

        # ON CONFLICT DO NOTHING + RETURNING: a conflict (already reported) yields
        # no row → we surface a 409. This is race-safe (the DB enforces dedup)
        # without needing a SELECT-then-INSERT.
        row = await db.fetchrow(
            """INSERT INTO reports (reporter_id, target_type, target_id, reason_code, detail)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (reporter_id, target_type, target_id) DO NOTHING
               RETURNING id, target_type, target_id, reason_code, detail, status, created_at""",
            user["id"], payload.target_type, payload.target_id, payload.reason_code, detail,
        )

    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already reported this.")
    return _report_out(row)


@router.get("/admin", response_model=list[ReportOut])
async def list_reports_admin(
    status_filter: str | None = Query(
        None, alias="status", pattern=r"^(open|resolved|dismissed)$"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """Admin: list reports newest-first, optionally filtered by status. Joins the
    reporter's nickname; resolves a short target label per row. target_label is
    fetched per-row (N+1) which is fine at admin-list volume (≤ page_size rows)."""
    _require_admin(user)
    offset = (page - 1) * page_size
    cols = """r.id, r.target_type, r.target_id, r.reason_code, r.detail,
              r.status, r.created_at, u.nickname AS reporter_nickname"""
    async with get_db() as db:
        if status_filter:
            rows = await db.fetch(
                f"""SELECT {cols}
                    FROM reports r LEFT JOIN users u ON u.id = r.reporter_id
                    WHERE r.status = $1
                    ORDER BY r.created_at DESC
                    LIMIT $2 OFFSET $3""",
                status_filter, page_size, offset,
            )
        else:
            rows = await db.fetch(
                f"""SELECT {cols}
                    FROM reports r LEFT JOIN users u ON u.id = r.reporter_id
                    ORDER BY r.created_at DESC
                    LIMIT $1 OFFSET $2""",
                page_size, offset,
            )
        return [_report_out(r, await _target_label(db, r["target_type"], r["target_id"]))
                for r in rows]


@router.put("/{report_id}")
async def update_report_status(
    report_id: int,
    body: ReportStatusUpdate,
    user: dict = Depends(get_current_user),
):
    """Admin: mark a report resolved or dismissed (closes the loop — the report
    channel is not just a write-only sink). Open→open is rejected by the model
    pattern; status only moves forward to a terminal state."""
    _require_admin(user)
    async with get_db() as db:
        result = await db.execute(
            "UPDATE reports SET status = $1 WHERE id = $2",
            body.status, report_id,
        )
        if result.endswith("0"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return {"message": f"Report {report_id} marked {body.status}"}
