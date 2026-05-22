from fastapi import APIRouter, Depends, HTTPException, status

from ..models import PushSubscriptionIn
from ..services.auth_service import get_current_user
from ..services.push_service import (
    get_vapid_public_key,
    save_subscription,
    remove_subscription,
)

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-key")
async def vapid_key():
    key = get_vapid_public_key()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Push not configured")
    return {"public_key": key}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(
    body: PushSubscriptionIn,
    user: dict = Depends(get_current_user),
):
    sub = body.subscription
    if not sub.get("endpoint") or not sub.get("keys", {}).get("p256dh"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid subscription")
    await save_subscription(user["id"], sub)
    return {"status": "ok"}


@router.post("/unsubscribe")
async def unsubscribe(
    body: PushSubscriptionIn,
    user: dict = Depends(get_current_user),
):
    endpoint = body.subscription.get("endpoint", "")
    if endpoint:
        await remove_subscription(user["id"], endpoint)
    return {"status": "ok"}
