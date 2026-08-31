"""OpenAI 구현 (Responses API + 내장 web_search + DiscussionTool 브릿지).

스트리밍 이벤트를 provider 중립 StreamEvent로 정규화한다.
※ 스켈레톤: 이벤트 필드명은 최초 실동작 시 SDK 버전에 맞춰 검증 필요.
"""
import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import ChatMessage, LLMProvider, StreamEvent, StreamEventType
from app.llm.tools.base import ToolRegistry, create_default_tools

MAX_TOOL_ROUNDS = 8  # tool 호출 무한 루프 방지


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings, tools: ToolRegistry | None = None):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._tools = tools or create_default_tools()

    async def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        input_items: list[dict] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        openai_tools = [{"type": "web_search"}] + [
            self._to_openai_tool(t) for t in self._tools.all()
        ]

        previous_response_id: str | None = None
        for _ in range(MAX_TOOL_ROUNDS):
            stream = await self._client.responses.create(
                model=self._model,
                instructions=system,
                input=input_items,
                tools=openai_tools,
                stream=True,
                previous_response_id=previous_response_id,
            )

            pending_calls: list[dict] = []
            async for event in stream:
                etype = getattr(event, "type", "")
                if etype == "response.output_text.delta":
                    yield StreamEvent(type=StreamEventType.TEXT_DELTA, text=event.delta)
                elif etype == "response.output_text.annotation.added":
                    ann = getattr(event, "annotation", None)
                    if ann is not None:
                        yield StreamEvent(
                            type=StreamEventType.CITATION,
                            url=getattr(ann, "url", "") or "",
                            title=getattr(ann, "title", "") or "",
                        )
                elif etype == "response.output_item.done":
                    item = event.item
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
