"""Claude Agent SDK 실호출 스모크 — 수동 실행 전용 (pytest에 포함하지 않는다).

실행:
    cd backend && ../.venv/Scripts/python.exe scripts/smoke_claude_agent.py quick
    cd backend && ../.venv/Scripts/python.exe scripts/smoke_claude_agent.py deep

성공 조건:
    quick — text_delta 1건 이상 + done으로 종료
    deep  — 위 조건 + tool_call 1건 이상
→ exit 0, 아니면 1.

자격증명/환경변수 값은 어떤 경우에도 출력하지 않는다. 본문은 앞 120자만 표시한다.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import modes  # noqa: E402
from app.llm.base import ChatMessage, StreamEventType, create_provider  # noqa: E402
from app.llm.context_builder import ContextBuilder  # noqa: E402

PREVIEW_CHARS = 120

PROMPTS = {
    "quick": "전기로 조업에서 용락(meltdown) 판단이 왜 중요한지 두 문장으로 답하라.",
    "deep": (
        "heat A171400의 active_power 평균값을 실제 데이터에서 직접 확인해서 답하라. "
        "데이터는 data/dummy 아래 parquet이다."
    ),
}


async def run(mode_id: str) -> int:
    spec = modes.resolve_mode(mode_id)
    # 컨텍스트는 주입하지 않는다(스모크는 provider 경로만 확인).
    system = ContextBuilder().build_system_prompt(None, spec)
    provider = create_provider()

    seq: list[str] = []
    tool_calls: list[str] = []
    text = ""
    started = time.perf_counter()
    ttfb: float | None = None

    async for event in provider.stream_chat(
        system,
        [ChatMessage(role="user", content=PROMPTS[mode_id])],
        mode=spec.id,
    ):
        if not seq or seq[-1] != event.type.value:
            seq.append(event.type.value)
        if event.type == StreamEventType.TEXT_DELTA:
            if ttfb is None:
                ttfb = time.perf_counter() - started
            text += event.text
        elif event.type == StreamEventType.TOOL_CALL:
            tool_calls.append(event.tool_name)
            print(f"[tool_call] {event.tool_name}")
        elif event.type == StreamEventType.TOOL_RESULT:
            print(f"[tool_result] {event.tool_name}")
        elif event.type == StreamEventType.CITATION:
            print(f"[citation] {event.url}")
        elif event.type == StreamEventType.ERROR:
            print(f"[error] {event.text}")

    elapsed = time.perf_counter() - started
    print(f"mode: {spec.id} ({spec.model})")
    print("event sequence:", " -> ".join(seq))
    print(f"tool_calls: {tool_calls}")
    print("TTFB(s):", f"{ttfb:.2f}" if ttfb is not None else "n/a")
    print(f"elapsed(s): {elapsed:.2f}")
    print(f"text chars: {len(text)}")
    print(f"text[:{PREVIEW_CHARS}]:", text[:PREVIEW_CHARS])

    ok = "text_delta" in seq and seq[-1] == "done"
    if spec.id == "deep":
        ok = ok and len(tool_calls) >= 1
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    mode_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode_id not in PROMPTS:
        print(f"usage: {Path(__file__).name} {'|'.join(PROMPTS)}")
        return 2
    return asyncio.run(run(mode_id))


if __name__ == "__main__":
    raise SystemExit(main())
