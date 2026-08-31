"""OpenAI 실호출 스모크 — 수동 실행 전용 (pytest에 포함하지 않는다; 비용 발생).

실행:
    cd backend && ../.venv/Scripts/python.exe scripts/smoke_openai.py

성공 조건: text_delta 이벤트 1건 이상 + done으로 종료 → exit 0.
API 키는 어떤 경우에도 출력하지 않는다. 응답 본문은 앞 80자만 표시한다.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.base import ChatMessage, StreamEventType, create_provider  # noqa: E402

SYSTEM = "당신은 전기로(EAF) 제강 공정 전문가다. 한국어로 간결하게 답한다."
USER = "전기로 조업에서 용락(meltdown)을 한 문장으로 정의하라. 검색 없이 답하라."
PREVIEW_CHARS = 80


async def main() -> int:
    provider = create_provider()
    seq: list[str] = []
    text = ""
    async for event in provider.stream_chat(SYSTEM, [ChatMessage(role="user", content=USER)]):
        if not seq or seq[-1] != event.type.value:
            seq.append(event.type.value)
        if event.type == StreamEventType.TEXT_DELTA:
            text += event.text
        elif event.type == StreamEventType.ERROR:
            print(f"[error] {event.text}")
        elif event.type == StreamEventType.CITATION:
            print(f"[citation] {event.url}")
        elif event.type in (StreamEventType.TOOL_CALL, StreamEventType.TOOL_RESULT):
            print(f"[{event.type.value}] {event.tool_name}")

    print("event sequence:", " -> ".join(seq))
    print(f"text chars: {len(text)}")
    print("text[:80]:", text[:PREVIEW_CHARS])

    ok = "text_delta" in seq and seq[-1] == "done"
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
