"""Discussion 채팅 — POST 요청에 SSE 형식으로 StreamEvent를 스트리밍한다."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_discussion_service
from app.services.discussion_service import DiscussionRequest, DiscussionService

router = APIRouter(prefix="/api/discussion", tags=["discussion"])


@router.post("")
async def discussion(
    req: DiscussionRequest,
    service: DiscussionService = Depends(get_discussion_service),
):
    async def sse():
        async for event in service.stream(req):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
