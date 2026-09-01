"""ClaudeAgentProvider 단위 테스트 — SDK를 실호출하지 않는다.

provider 모듈의 query를 가짜 async generator로 monkeypatch하여
스트림 정규화·프롬프트 렌더링·옵션 구성만 검증한다.
"""
from pathlib import Path

import pytest
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    UserMessage,
)
from claude_agent_sdk.types import StreamEvent as SdkStreamEvent

from app.config import PROJECT_ROOT, Settings
from app.llm import claude_agent_provider as prov
from app.llm import modes
from app.llm.base import ChatMessage, StreamEventType

_SESSION = "sess-1"


def _raw(event: dict) -> SdkStreamEvent:
    return SdkStreamEvent(uuid="u", session_id=_SESSION, event=event)


def _text_delta(text: str) -> SdkStreamEvent:
    return _raw({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


def _tool_start(name: str, block_id: str) -> SdkStreamEvent:
    return _raw(
        {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "id": block_id, "name": name},
        }
    )


def _result(subtype: str = "success") -> ResultMessage:
    return ResultMessage(
        subtype=subtype,
        duration_ms=1,
        duration_api_ms=1,
        is_error=(subtype == "error"),
        num_turns=1,
        session_id=_SESSION,
        result="ok",
    )


def _patch_query(monkeypatch, messages, recorder: dict | None = None):
    async def fake_query(prompt, options):
        if recorder is not None:
            recorder["prompt"] = prompt
            recorder["options"] = options
        for message in messages:
            yield message

    monkeypatch.setattr(prov, "query", fake_query)


def _provider() -> prov.ClaudeAgentProvider:
    return prov.ClaudeAgentProvider(Settings(anthropic_api_key=""))


async def _collect(provider, mode="quick", messages=None):
    msgs = messages if messages is not None else [ChatMessage(role="user", content="질문")]
    return [e async for e in provider.stream_chat("SYSTEM", msgs, mode=mode)]


# -- 스트림 정규화 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_text_delta_normalized(monkeypatch):
    _patch_query(monkeypatch, [_text_delta("안녕"), _text_delta("하세요"), _result()])
    events = await _collect(_provider())
    assert [e.type for e in events] == [
        StreamEventType.TEXT_DELTA,
        StreamEventType.TEXT_DELTA,
        StreamEventType.DONE,
    ]
    assert "".join(e.text for e in events) == "안녕하세요"


@pytest.mark.asyncio
async def test_tool_use_start_becomes_tool_call(monkeypatch):
    _patch_query(
        monkeypatch,
        [
            _tool_start("Read", "tu_1"),
            UserMessage(content=[ToolResultBlock(tool_use_id="tu_1", content="x")]),
            _text_delta("답"),
            _result(),
        ],
    )
    events = await _collect(_provider(), mode="deep")
    assert [e.type for e in events] == [
        StreamEventType.TOOL_CALL,
        StreamEventType.TOOL_RESULT,
        StreamEventType.TEXT_DELTA,
        StreamEventType.DONE,
    ]
    assert events[0].tool_name == "Read"
    assert events[1].tool_name == "Read"


@pytest.mark.asyncio
async def test_pending_tool_is_closed_before_done(monkeypatch):
    # ToolResultBlock이 관측되지 않아도 tool_call은 tool_result로 닫힌다.
    _patch_query(monkeypatch, [_tool_start("WebSearch", "tu_9"), _result()])
    events = await _collect(_provider(), mode="deep")
    assert [e.type for e in events] == [
        StreamEventType.TOOL_CALL,
        StreamEventType.TOOL_RESULT,
        StreamEventType.DONE,
    ]


@pytest.mark.asyncio
async def test_assistant_message_text_not_duplicated(monkeypatch):
    _patch_query(
        monkeypatch,
        [
            _text_delta("본문"),
            AssistantMessage(content=[TextBlock(text="본문")], model="claude-haiku-4-5"),
            _result(),
        ],
    )
    events = await _collect(_provider())
    texts = [e.text for e in events if e.type == StreamEventType.TEXT_DELTA]
    assert texts == ["본문"]


@pytest.mark.asyncio
async def test_unknown_events_are_ignored(monkeypatch):
    _patch_query(
        monkeypatch,
        [
            _raw({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "…"}}),
            _raw({"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}}),
            _raw({"type": "message_stop"}),
            _text_delta("끝"),
            _result(),
        ],
    )
    events = await _collect(_provider())
    assert [e.type for e in events] == [StreamEventType.TEXT_DELTA, StreamEventType.DONE]


@pytest.mark.asyncio
async def test_result_message_error_subtype(monkeypatch):
    _patch_query(monkeypatch, [_text_delta("x"), _result("error")])
    events = await _collect(_provider())
    assert events[-1].type == StreamEventType.ERROR
    assert events[-1].text


@pytest.mark.asyncio
async def test_query_exception_becomes_error_event(monkeypatch):
    async def boom(prompt, options):
        raise RuntimeError("CLI 스폰 실패")
        yield  # pragma: no cover

    monkeypatch.setattr(prov, "query", boom)
    events = await _collect(_provider())          # 예외가 전파되면 실패한다
    assert [e.type for e in events] == [StreamEventType.ERROR]
    assert "CLI 스폰 실패" in events[0].text


@pytest.mark.asyncio
async def test_empty_messages_yield_error(monkeypatch):
    _patch_query(monkeypatch, [_result()])
    events = await _collect(_provider(), messages=[])
    assert [e.type for e in events] == [StreamEventType.ERROR]


# -- 프롬프트 렌더링 ---------------------------------------------------------


def test_render_prompt_with_history():
    prompt = prov._render_prompt(
        [
            ChatMessage(role="user", content="첫 질문"),
            ChatMessage(role="assistant", content="첫 답변"),
            ChatMessage(role="user", content="이번 질문 내용"),
        ]
    )
    assert "# 이전 대화 이력" in prompt
    assert "[사용자] 첫 질문" in prompt
    assert "[어시스턴트] 첫 답변" in prompt
    assert prompt.endswith("# 이번 질문\n이번 질문 내용")
    assert "이번 질문 내용" not in prompt.split("# 이번 질문")[0]


def test_render_prompt_single_message_has_no_history_block():
    prompt = prov._render_prompt([ChatMessage(role="user", content="단일")])
    assert "# 이전 대화 이력" not in prompt
    assert prompt == "# 이번 질문\n단일"


def test_render_prompt_empty_raises():
    with pytest.raises(ValueError):
        prov._render_prompt([])


# -- 옵션 구성 ---------------------------------------------------------------


def _options(mode_id: str):
    options, temp = prov._build_options(
        "SYSTEM", modes.resolve_mode(mode_id), Settings(anthropic_api_key="")
    )
    assert temp is None
    return options


def test_build_options_quick():
    options = _options("quick")
    assert options.model == "claude-haiku-4-5"
    assert options.allowed_tools == []
    assert options.disallowed_tools == ["*"]
    assert options.max_turns == 1
    assert options.thinking == {"type": "disabled"}
    assert options.permission_mode == "dontAsk"
    assert options.setting_sources == []
    assert options.include_partial_messages is True
    assert options.system_prompt == "SYSTEM"
    assert options.env[prov.SKIP_HISTORY_ENV] == "1"
    assert "ANTHROPIC_API_KEY" not in options.env


def test_build_options_deep():
    options = _options("deep")
    assert options.model == "claude-opus-5"
    assert f"Bash({modes.VENV_PYTHON} *)" in options.allowed_tools
    assert "Write" in options.disallowed_tools
    assert options.max_turns == 25
    assert options.thinking is None            # SDK 기본값 유지
    assert options.permission_mode == "dontAsk"


def test_build_options_uses_api_key_when_configured():
    options, _ = prov._build_options(
        "SYSTEM", modes.resolve_mode("quick"), Settings(anthropic_api_key="test-key")
    )
    assert options.env["ANTHROPIC_API_KEY"] == "test-key"


def test_build_options_registers_env_guard_hook():
    for mode_id in ("quick", "deep"):
        options = _options(mode_id)
        matchers = options.hooks["PreToolUse"]
        assert any(prov._env_guard_hook in m.hooks for m in matchers)


# -- .env 접근 차단 (PreToolUse 훅 로직) --------------------------------------


@pytest.mark.parametrize(
    "tool_name,tool_input",
    [
        ("Read", {"file_path": ".env"}),
        ("Read", {"file_path": "backend/../.env"}),
        ("Read", {"file_path": str(PROJECT_ROOT / ".env")}),
        ("Read", {"file_path": ".env.local"}),
        ("Read", {"file_path": "C:/somewhere/else/.env"}),
        ("Grep", {"pattern": "KEY", "path": ".env"}),
        ("Grep", {"pattern": ".env"}),
        ("Glob", {"pattern": "**/.env"}),
        ("Bash", {"command": "cat .env"}),
        ("Bash", {"command": ".venv/Scripts/python.exe -c \"print(open('.env').read())\""}),
    ],
)
def test_env_guard_denies(tool_name, tool_input):
    assert prov._env_guard_decision(tool_name, tool_input) == prov.SENSITIVE_DENY_MESSAGE


@pytest.mark.parametrize(
    "tool_name,tool_input",
    [
        ("Read", {"file_path": ".env.example"}),
        ("Read", {"file_path": "DOMAIN_INFO.md"}),
        ("Read", {"file_path": str(PROJECT_ROOT / "SPEC.md")}),
        ("Grep", {"pattern": "active_power", "path": "backend/app"}),
        ("Glob", {"pattern": "data/dummy/**/*.parquet"}),
        ("Bash", {"command": ".venv/Scripts/python.exe -c \"import pandas\""}),
    ],
)
def test_env_guard_allows(tool_name, tool_input):
    assert prov._env_guard_decision(tool_name, tool_input) is None


@pytest.mark.asyncio
async def test_env_guard_hook_output_shape():
    denied = await prov._env_guard_hook(
        {"tool_name": "Read", "tool_input": {"file_path": ".env"}}, "tu_1", {}
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert denied["hookSpecificOutput"]["permissionDecisionReason"] == (
        prov.SENSITIVE_DENY_MESSAGE
    )
    allowed = await prov._env_guard_hook(
        {"tool_name": "Read", "tool_input": {"file_path": "SPEC.md"}}, "tu_2", {}
    )
    assert allowed == {}


# -- 시스템 프롬프트 길이 폴백 -----------------------------------------------


def test_short_system_prompt_stays_inline():
    value, path = prov._system_prompt_option("짧은 프롬프트")
    assert value == "짧은 프롬프트"
    assert path is None


def test_long_system_prompt_falls_back_to_file():
    long_prompt = "가" * (prov.SYSTEM_PROMPT_INLINE_LIMIT + 1)
    value, path = prov._system_prompt_option(long_prompt)
    try:
        assert isinstance(value, dict)
        assert value["type"] == "file"
        assert value["path"] == str(path)
        assert path is not None and Path(path).read_text(encoding="utf-8") == long_prompt
    finally:
        prov._cleanup_temp(path)
    assert not Path(path).exists()
