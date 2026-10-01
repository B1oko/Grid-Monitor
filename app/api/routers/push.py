from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import AppState, get_state
from app.api.schemas import PushSubscriptionIn, PushUnsubscribe
from app.services.notifier import Notification

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/public-key")
async def public_key(state: AppState = Depends(get_state)) -> dict[str, object]:
    return {
        "public_key": state.push.public_key,
        "subscriptions": await state.push.subscription_count(),
    }


@router.post("/subscribe", status_code=204)
async def subscribe(
    body: PushSubscriptionIn,
    request: Request,
    state: AppState = Depends(get_state),
) -> Response:
    await state.push.subscribe(
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)


@router.post("/unsubscribe", status_code=204)
async def unsubscribe(body: PushUnsubscribe, state: AppState = Depends(get_state)) -> Response:
    await state.push.unsubscribe(body.endpoint)
    return Response(status_code=204)


@router.post("/test")
async def send_test(state: AppState = Depends(get_state)) -> dict[str, int]:
    delivered = await state.push.send(
        Notification(
            title="Grid Monitor",
            body="Test notification: alerts will show up like this.",
            tag="test",
        )
    )
    return {"delivered": delivered}
