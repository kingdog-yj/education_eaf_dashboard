"""OpenAI 구현 (Responses API + 내장 web_search + DiscussionTool 브릿지).

스트리밍 이벤트를 provider 중립 StreamEvent로 정규화한다.
알 수 없는 이벤트 타입(reasoning 계열 등)은 무시한다 — SDK/모델 업데이트로
이벤트가 늘어도 스트림이 깨지지 않도록.
"""
import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import Settings
from app.llm import options
from app.llm.base import ChatMessage, LLMProvider, StreamEvent, StreamEventType
from app.llm.tools.base import ToolRegistry, create_default_tools

MAX_TOOL_ROUNDS = 8  # tool 호출 무한 루프 방지

#: Responses API 내장 웹 검색 tool 타입. SDK/모델 버전에 따라
#: "web_search" ↔ "web_search_preview"로 갈리므로 이 상수만 바꾸면 되게 한다.
WEB_SEARCH_TOOL_TYPE = "web_search"


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings, tools: ToolRegistry | None = None):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._tools = tools or create_default_tools()
        # 빈 값이면 reasoning 파라미터를 아예 보내지 않는다(SDK/모델 기본 유지).
        self._reasoning_effort = (settings.llm_reasoning_effort or "").strip()
        # 응답 상세도. 무효/빈 값이면 text 파라미터를 보내지 않는다.
        self._verbosity = (settings.llm_verbosity or "").strip()

    async def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        # 요청 단위 오버라이드 — 재기동 없이 메시지마다 모델/강도를 바꾼다.
        # 목록 밖 값은 조용히 기본값으로 폴백한다(400을 내지 않는다).
        active_model = options.resolve_model(model, self._model)
        active_effort = options.resolve_effort(reasoning_effort, self._reasoning_effort)

        # 대화 이력: role(user/assistant) 그대로 input 항목으로 전달한다.
        # Responses API는 멀티턴 이력을 이 형식으로 받는다(서버 저장 없이 매 요청 전송).
        input_items: list[dict] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        openai_tools = self._build_tools(active_effort)

        previous_response_id: str | None = None
        for _ in range(MAX_TOOL_ROUNDS):
            pending_calls: list[dict] = []
            extra: dict = self._build_extra_params(active_effort)
            try:
                stream = await self._client.responses.create(
                    model=active_model,
                    instructions=system,
                    input=input_items,
                    tools=openai_tools,
                    stream=True,
                    previous_response_id=previous_response_id,
                    **extra,
                )
                async for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "response.output_text.delta":
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA,
                            text=getattr(event, "delta", "") or "",
                        )
                    elif etype == "response.output_text.annotation.added":
                        citation = _annotation_to_citation(
                            getattr(event, "annotation", None)
                        )
                        if citation is not None:
                            yield citation
                    elif etype == "response.output_item.done":
                        item = getattr(event, "item", None)
                        if getattr(item, "type", "") == "function_call":
                            pending_calls.append(
                                {
                                    "call_id": item.call_id,
                                    "name": item.name,
                                    "arguments": item.arguments,
                                }
                            )
                    elif etype == "response.completed":
                        previous_response_id = event.response.id
                    elif etype == "error":
                        yield StreamEvent(
                            type=StreamEventType.ERROR,
                            text=f"LLM 스트림 오류: {_safe_message(event)}",
                        )
                        return
                    # 그 외 이벤트(reasoning/web_search 진행 상황 등)는 무시
            except Exception as exc:  # 네트워크/인증/모델 오류 → 스트림을 깨지 않고 종료
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    text=f"LLM 호출 실패: {_safe_message(exc)}",
                )
                return

            if not pending_calls:
                yield StreamEvent(type=StreamEventType.DONE)
                return

            # tool 실행 후 결과만 전달하고 previous_response_id로 대화를 이어간다
            input_items = []
            for call in pending_calls:
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL, tool_name=call["name"]
                )
                output = await self._run_tool(call["name"], call["arguments"])
                yield StreamEvent(
                    type=StreamEventType.TOOL_RESULT, tool_name=call["name"]
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": output,
                    }
                )

        yield StreamEvent(
            type=StreamEventType.ERROR, text="tool 호출 한도 초과 (MAX_TOOL_ROUNDS)"
        )

    def _build_extra_params(self, effort: str) -> dict:
        """responses.create의 선택 파라미터.

        값이 없거나 무효하면 키 자체를 넣지 않는다 → SDK/모델 기본 동작 유지.
        """
        extra: dict = {}
        if effort:
            extra["reasoning"] = {"effort": effort}
        if options.is_valid_verbosity(self._verbosity):
            extra["text"] = {"verbosity": self._verbosity}
        return extra

    def _build_tools(self, effort: str) -> list[dict]:
        """이번 요청에 보낼 tool 목록.

        일부 reasoning 강도(llm/options.EFFORTS_WITHOUT_WEB_SEARCH)는 내장
        web_search와 함께 쓸 수 없어 400이 난다 → 그 강도에서는 web_search만
        제외하고 데이터 조회 function tool은 그대로 유지한다.
        """
        tools: list[dict] = []
        if options.supports_web_search(effort):
            tools.append({"type": WEB_SEARCH_TOOL_TYPE})
        tools += [self._to_openai_tool(t) for t in self._tools.all()]
        return tools

    async def _run_tool(self, name: str, arguments_json: str) -> str:
        try:
            kwargs = json.loads(arguments_json or "{}")
            return await self._tools.get(name).run(**kwargs)
        except Exception as exc:  # tool 실패가 스트림 전체를 끊지 않도록
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @staticmethod
    def _to_openai_tool(tool) -> dict:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        }


def _field(obj: object, key: str) -> str:
    """pydantic 객체/dict 어느 쪽이어도 문자열 필드를 안전 추출."""
    value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return str(value) if value else ""


def _annotation_to_citation(ann: object) -> StreamEvent | None:
    """annotation(웹 검색 인용) → CITATION 이벤트. url이 없으면 무시."""
    if ann is None:
        return None
    url = _field(ann, "url")
    if not url:
        return None
    return StreamEvent(type=StreamEventType.CITATION, url=url, title=_field(ann, "title"))


def _safe_message(exc: object) -> str:
    """오류 요약 — API 키가 메시지에 실려 나가지 않도록 마스킹한다."""
    text = getattr(exc, "message", None) or str(exc)
    text = str(text)[:300]
    return _mask_secrets(text)


def _mask_secrets(text: str) -> str:
    out: list[str] = []
    for token in text.split():
        # OpenAI 키 형태(sk-...)는 어떤 경로로도 노출하지 않는다
        out.append("***" if token.strip("'\",") .startswith("sk-") else token)
    return " ".join(out)
