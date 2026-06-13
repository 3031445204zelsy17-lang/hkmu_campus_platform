# Profile Tag Recommendations Prototype

This folder saves the code idea for adding categorized social tags to the user
profile page and recommending classmates by shared tags.

It is intentionally stored under `additional items/` so it does not affect the
main application until the team decides to integrate it.

## Goal

Allow users to choose tags by category on their profile:

- Interests
- Current courses
- Looking for

Then recommend classmates by comparing shared tags:

```text
same current course = 3 points
same partner type   = 2 points
same interest       = 1 point
```

## Files

- `backend-users-recommendations.py` - FastAPI model/router snippet for tag storage and recommendations
- `profile-tag-selector.js` - frontend profile UI snippet for categorized tag selection and recommendation cards
- `profile-tag-selector.css` - styles for tag picker and recommendations

## Suggested Real Integration Points

- `backend/app/models.py`
- `backend/app/routers/users.py`
- `frontend/js/pages/profile.js`
- `frontend/css/profile.css`

## Suggested API

```text
GET /api/v1/users/recommendations/me?limit=6
```

The API should return users with `match_score` and `matched_tags` so the profile
page can explain why each person was recommended.
