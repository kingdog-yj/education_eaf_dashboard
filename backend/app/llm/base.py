"""LLM provider 추상화. OpenAI(현재) ↔ Claude(향후) 전환은 .env의 LLM_PROVIDER로 완결.

프론트/서비스 계층은 provider 중립 타입(ChatMessage, StreamEvent)만 다룬다.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"      # 본문 토큰
    TOOL_CALL = "tool_call"        # tool 실행 시작 알림 (UI 표시용)
    TOOL_RESULT = "tool_result"    # tool 실행 완료 알림
    CITATION = "citation"          # 웹/학술 검색 출처
    DONE = "done"
    ERROR = "error"


class StreamEvent(BaseModel):
    type: StreamEventType
    text: str = ""                 # TEXT_DELTA: 토큰 / ERROR: 메시지
    tool_name: str = ""            # TOOL_CALL/TOOL_RESULT
    url: str = ""                  # CITATION
    title: str = ""                # CITATION


class LLMProvider(ABC):
    """모든 provider는 (1) 내장 웹 검색 활성화, (2) DiscussionTool 브릿지,
    (3) StreamEvent 정규화를 책임진다."""

    @abstractmethod
    def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]: ...


def create_provider() -> LLMProvider:
    """LLM_PROVIDER 설정에 따른 구현체 factory."""
    from app.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {settings.llm_provider}")
