"""LLM provider 추상화. provider 교체는 .env의 LLM_PROVIDER로 완결한다.

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
    """모든 provider는 (1) 모드별 도구/모델 구성, (2) StreamEvent 정규화를 책임진다."""

    @abstractmethod
    def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
        mode: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """mode는 채팅 모드 id(선택지는 llm/modes.py).

        누락/목록 밖 값이면 기본 모드로 조용히 폴백한다(에러 아님).
        """
        ...


def create_provider() -> LLMProvider:
    """LLM_PROVIDER 설정에 따른 구현체 factory."""
    from app.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "claude_agent":
        from app.llm.claude_agent_provider import ClaudeAgentProvider

        return ClaudeAgentProvider(settings)
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {settings.llm_provider}")
