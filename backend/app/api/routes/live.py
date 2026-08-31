from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.deps import get_live_service
from app.services.live_service import LiveStreamService

router = APIRouter(tags=["live"])


@router.websocket("/api/live")
async def live_stream(
    ws: WebSocket,
    service: LiveStreamService = Depends(get_live_service),
):
    await ws.accept()
    try:
        async for message in service.stream():
            await ws.send_json(message)
    except WebSocketDisconnect:
        pass
