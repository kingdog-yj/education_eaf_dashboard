"""Discussion 오케스트레이션: 컨텍스트 렌더링 → provider 스트림 → SSE 이벤트.

대화 이력은 서버에 저장하지 않는다(휘발성) — 매 요청에 프론트가 전체 이력을 보낸다.
"""
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.llm.base import ChatMessage, LLMProvider, StreamEvent
from app.llm.context_builder import ContextBuilder, DashboardContext


class DiscussionRequest(BaseModel):
    messages: list[ChatMessage]            # 전체 대화 이력 (마지막이 이번 user 메시지)
    context: DashboardContext | None = None
    # 요청 단위 오버라이드 (선택지는 llm/options.py). null/누락이면 서버 기본값,
    # 목록 밖 값이면 provider가 조용히 기본값으로 폴백한다(400 아님).
    model: str | None = None
    reasoning_effort: str | None = None


class DiscussionService:
    def __init__(self, provider: LLMProvider, context_builder: ContextBuilder | None = None):
        self._provider = provider
        self._context_builder = context_builder or ContextBuilder()

    async def stream(self, req: DiscussionRequest) -> AsyncIterator[StreamEvent]:
        system = self._context_builder.build_system_prompt(req.context)
        async for event in self._provider.stream_chat(
            system,
            req.messages,
            model=req.model,
            reasoning_effort=req.reasoning_effort,
        ):
            yield event
