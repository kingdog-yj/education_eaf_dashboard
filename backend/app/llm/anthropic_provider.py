"""Claude 구현 (향후 전환 예정 — 스텁).

전환 시 구현 가이드:
- anthropic SDK의 messages.stream 사용, 서버측 web_search tool 활성화
- DiscussionTool → Claude tool 스키마 변환 (name/description/input_schema)
- 스트림 이벤트를 StreamEvent로 정규화 (OpenAIProvider와 동일 계약)
- .env: ANTHROPIC_API_KEY 설정 + LLM_PROVIDER=anthropic 변경으로 활성화
"""
from collections.abc import AsyncIterator

from app.config import Settings
from app.llm.base import ChatMessage, LLMProvider, StreamEvent


class AnthropicProvider(LLMProvider):
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않음")
        self._settings = settings

    async def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError("Claude 전환 시 구현 (SPEC.md §8)")
        yield  # AsyncIterator 시그니처 유지용
