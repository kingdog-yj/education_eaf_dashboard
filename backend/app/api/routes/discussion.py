"""Discussion 채팅 — POST 요청에 SSE 형식으로 StreamEvent를 스트리밍한다.

reasoning 모델은 첫 토큰까지 수십 초가 걸릴 수 있어(무이벤트 구간) 유휴 연결이
프록시나 클라이언트에서 끊길 수 있다. 이를 막기 위해 이벤트가 없는 동안
SSE 주석 프레임(": ping")을 주기적으로 내보낸다. 주석 프레임은 SSE 규격상
데이터가 아니므로 프론트 파서(data: 외 라인 무시)와 호환되며,
StreamEvent 스키마·`data:` 프레임 형식은 변경되지 않는다.
"""
import asyncio
import contextlib

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_discussion_service
from app.llm.base import StreamEvent, StreamEventType
from app.services.discussion_service import DiscussionRequest, DiscussionService

router = APIRouter(prefix="/api/discussion", tags=["discussion"])

#: 무이벤트 구간에서 연결 생존 신호를 보내는 주기(초)
HEARTBEAT_INTERVAL_S = 15.0
#: SSE 주석 프레임 (데이터 아님 — 클라이언트 파서는 무시한다)
HEARTBEAT_FRAME = ": ping\n\n"


@router.post("")
async def discussion(
    req: DiscussionRequest,
    service: DiscussionService = Depends(get_discussion_service),
):
    async def sse():
        # provider 스트림을 별도 태스크로 소비한다. wait_for로 제너레이터의
        # __anext__를 직접 취소하면 스트림이 깨지므로 큐를 사이에 둔다.
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        failure: list[BaseException] = []

        async def produce() -> None:
            try:
                async for event in service.stream(req):
                    await queue.put(event)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 — 스트림 종료 신호로 전환
                failure.append(exc)
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    yield HEARTBEAT_FRAME       # 이벤트 없음 → 연결 유지
                    continue
                if event is None:
                    break
                yield f"data: {event.model_dump_json()}\n\n"

            if failure:
                error = StreamEvent(
                    type=StreamEventType.ERROR, text="응답 스트림이 중단되었습니다."
                )
                yield f"data: {error.model_dump_json()}\n\n"
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
