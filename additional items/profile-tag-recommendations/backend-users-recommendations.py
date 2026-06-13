"""
Prototype backend snippet for profile social tags and recommendations.

Suggested integration files:
- backend/app/models.py
- backend/app/routers/users.py
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    student_id: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: str = ""
    identity: str = "student"
    interests: list[str] = []
    current_courses: list[str] = []
    partner_types: list[str] = []
    created_at: Optional[str] = None


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=30)
    bio: Optional[str] = Field(None, max_length=300)
    avatar_url: Optional[str] = None
    interests: Optional[list[str]] = None
    current_courses: Optional[list[str]] = None
    partner_types: Optional[list[str]] = None


class UserRecommendationOut(UserOut):
    match_score: int = 0
    matched_tags: dict[str, list[str]] = {}


router = APIRouter(prefix="/users", tags=["users"])


def parse_tags(value) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()][:12]


def clean_tags(values: list[str] | None, sanitize) -> str:
    if not values:
        return "[]"
    cleaned = []
    for value in values:
        safe = sanitize(str(value).strip())[:40]
        if safe and safe not in cleaned:
            cleaned.append(safe)
    return json.dumps(cleaned[:12])


def shared_tags(left: list[str], right: list[str]) -> list[str]:
    right_norm = {tag.lower(): tag for tag in right}
    matches = []
    for tag in left:
        key = tag.lower()
        if key in right_norm and right_norm[key] not in matches:
            matches.append(right_norm[key])
    return matches


def recommendation_from_rows(current, candidate, user_row_to_out) -> UserRecommendationOut | None:
    current_interests = parse_tags(current["interests"] if "interests" in current.keys() else None)
    current_courses = parse_tags(current["current_courses"] if "current_courses" in current.keys() else None)
    current_types = parse_tags(current["partner_types"] if "partner_types" in current.keys() else None)

    candidate_interests = parse_tags(candidate["interests"] if "interests" in candidate.keys() else None)
    candidate_courses = parse_tags(candidate["current_courses"] if "current_courses" in candidate.keys() else None)
    candidate_types = parse_tags(candidate["partner_types"] if "partner_types" in candidate.keys() else None)

    matched = {
        "interests": shared_tags(current_interests, candidate_interests),
        "current_courses": shared_tags(current_courses, candidate_courses),
        "partner_types": shared_tags(current_types, candidate_types),
    }
    score = len(matched["current_courses"]) * 3 + len(matched["partner_types"]) * 2 + len(matched["interests"])
    if score <= 0:
        return None

    base = user_row_to_out(candidate).model_dump()
    return UserRecommendationOut(**base, match_score=score, matched_tags=matched)


@router.get("/recommendations/me", response_model=list[UserRecommendationOut])
async def recommend_users(
    limit: int = Query(6, ge=1, le=20),
    user: dict = Depends(...),  # Replace with get_current_user.
):
    """
    Integration notes:
    - Replace Depends(...) with get_current_user.
    - Replace get_db/user_row_to_out with project helpers.
    - Store tag arrays as JSON text fields on users for an MVP.
    """
    db = await get_db()  # noqa: F821 - project helper
    cur = await db.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
    current = await cur.fetchone()
    if not current:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    cur = await db.execute(
        "SELECT * FROM users WHERE id != ? ORDER BY updated_at DESC, created_at DESC LIMIT 100",
        (user["id"],),
    )
    candidates = await cur.fetchall()

    recommendations = []
    for row in candidates:
        rec = recommendation_from_rows(current, row, user_row_to_out)  # noqa: F821 - project helper
        if rec:
            recommendations.append(rec)

    recommendations.sort(
        key=lambda item: (
            item.match_score,
            len(item.matched_tags.get("current_courses", [])),
            len(item.matched_tags.get("partner_types", [])),
        ),
        reverse=True,
    )
    return recommendations[:limit]
