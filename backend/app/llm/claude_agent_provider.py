"""Claude Agent SDK 구현 — 매 요청 `query()` 1회(무상태 세션).

SDK의 부분 스트리밍 이벤트를 provider 중립 StreamEvent로 정규화한다.
알 수 없는 이벤트(thinking_delta, input_json_delta 등)는 무시한다 — SDK가
이벤트를 늘려도 스트림이 깨지지 않도록.

인증: SDK가 스폰하는 Claude Code CLI가 이 PC의 로그인 자격증명을 상속한다.
`settings.anthropic_api_key`가 설정된 경우에만 API 키 인증으로 전환된다.
자격증명은 어떤 경로로도 로그/이벤트에 실리지 않는다.

`claude_agent_sdk` 임포트는 레이어 격리를 위해 이 파일에만 존재해야 한다.
"""
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
)
from claude_agent_sdk.types import StreamEvent as SdkStreamEvent
from claude_agent_sdk.types import (
    SystemPromptFile,
    ToolResultBlock,
    UserMessage,
)

from app.config import PROJECT_ROOT, Settings
from app.llm import modes
from app.llm.base import ChatMessage, LLMProvider, StreamEvent, StreamEventType
from app.llm.modes import ChatModeSpec

#: 시스템 프롬프트는 CLI 인자로 전달된다. Windows의 명령행 길이 제한(~32K자)에
#: 걸리지 않도록, 이 길이를 넘으면 임시 파일 참조로 바꿔 전달한다.
SYSTEM_PROMPT_INLINE_LIMIT = 16_000

#: 오류 메시지 절단 길이 (스택/응답 원문이 그대로 프론트로 흐르지 않도록).
ERROR_MESSAGE_LIMIT = 300

#: 세션 트랜스크립트를 디스크(~/.claude/projects)에 남기지 않는다 — 무상태 서버 위생.
SKIP_HISTORY_ENV = "CLAUDE_CODE_SKIP_PROMPT_HISTORY"

#: 도구 시작으로 취급하는 content_block 타입 (server_tool_use = WebSearch 등).
_TOOL_USE_BLOCK_TYPES = frozenset({"tool_use", "server_tool_use"})

_ROLE_LABELS = {"user": "[사용자]", "assistant": "[어시스턴트]"}


# -- .env 접근 차단 (권한 계층) ----------------------------------------------
# 프로젝트 읽기는 의도적으로 비격리(작업 디렉토리 = 프로젝트 루트)이지만,
# 자격증명이 담긴 .env만은 프롬프트 지침이 아니라 권한 계층에서 물리적으로 막는다.
# 아래 상수가 차단 규칙의 유일한 선언 지점이다.
#
# 메커니즘: PreToolUse 훅.
#   `can_use_tool` 콜백은 allowed_tools에 통째로 승인된 도구(Read/Grep/Glob 등)에는
#   호출되지 않는다(SDK 0.2.149 `_get_can_use_tool_shadowed_warning` 참조 — "To gate
#   every tool call, use a PreToolUse hook"). 두 모드 공통으로 모든 도구 호출을
#   가로채야 하므로 PreToolUse 훅을 사용한다.

#: 정확히 이 파일명이면 차단 (디렉토리 위치 무관).
SENSITIVE_ENV_FILENAME = ".env"
#: `.env.local`, `.env.production` 등 파생 파일도 차단.
SENSITIVE_ENV_PREFIX = ".env."
#: 민감정보가 없는 예시 파일만 예외로 허용.
SENSITIVE_ENV_ALLOWED = frozenset({".env.example"})
#: 경로 인자로 취급하는 도구 입력 키 (resolve 후 파일명 비교).
SENSITIVE_PATH_KEYS = ("file_path", "path", "notebook_path", "file", "directory")
#: 패턴 인자로 취급하는 키 (문자열에 .env 토큰이 있으면 차단 — 보수적).
SENSITIVE_PATTERN_KEYS = ("pattern", "glob", "globs", "query")
#: 셸 명령은 문자열 전체를 토큰 검사한다(보수적 — .env.example 언급도 함께 거부됨).
SENSITIVE_COMMAND_KEYS = ("command",)

SENSITIVE_DENY_MESSAGE = "보안 정책: .env 파일 접근은 차단되어 있습니다."


def _is_sensitive_path(value: str) -> bool:
    """경로 문자열이 .env 계열 파일을 가리키는가.

    상대경로(`../.env`, `backend/../.env`)로 우회하지 못하도록 프로젝트 루트를
    기준으로 resolve한 뒤 파일명만 비교한다.
    """
    text = value.strip().strip("'\"")
    if not text:
        return False
    try:
        name = (PROJECT_ROOT / text).resolve().name
    except (OSError, ValueError):
        name = Path(text).name
    return _is_sensitive_name(name)


def _is_sensitive_name(name: str) -> bool:
    if name in SENSITIVE_ENV_ALLOWED:
        return False
    return name == SENSITIVE_ENV_FILENAME or name.startswith(SENSITIVE_ENV_PREFIX)


def _has_sensitive_token(value: str) -> bool:
    """패턴/명령 문자열에 .env 토큰이 있는가(허용 예시 파일 언급은 제외하지 않음)."""
    return SENSITIVE_ENV_FILENAME in value


def _env_guard_decision(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """차단해야 하면 거부 사유, 아니면 None. (훅에서 분리 — 단위 테스트 대상)"""
    if not isinstance(tool_input, dict):
        return None
    for key, value in tool_input.items():
        if not isinstance(value, str):
            continue
        if key in SENSITIVE_COMMAND_KEYS and _has_sensitive_token(value):
            return SENSITIVE_DENY_MESSAGE
        if key in SENSITIVE_PATTERN_KEYS and _has_sensitive_token(value):
            return SENSITIVE_DENY_MESSAGE
        if key in SENSITIVE_PATH_KEYS and _is_sensitive_path(value):
            return SENSITIVE_DENY_MESSAGE
    return None


async def _env_guard_hook(
    hook_input: dict, tool_use_id: str | None, context: object
) -> dict:
    """PreToolUse 훅 — .env 접근 시도를 실행 전에 거부한다."""
    reason = _env_guard_decision(
        hook_input.get("tool_name") or "", hook_input.get("tool_input") or {}
    )
    if reason is None:
        return {}                       # 결정 없음 → 기존 권한 정책으로 진행
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


class ClaudeAgentProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self._settings = settings

    async def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
        mode: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        spec = modes.resolve_mode(mode)
        try:
            prompt = _render_prompt(messages)
        except ValueError as exc:
            yield StreamEvent(type=StreamEventType.ERROR, text=str(exc))
            return

        options, temp_prompt_path = _build_options(system, spec, self._settings)
        try:
            async for event in _stream_events(prompt, options):
                yield event
        finally:
            _cleanup_temp(temp_prompt_path)


async def _stream_events(
    prompt: str, options: ClaudeAgentOptions
) -> AsyncIterator[StreamEvent]:
    """query() 스트림 → StreamEvent. 예외는 ERROR 이벤트로 흡수한다."""
    # tool_use_id → 도구명. TOOL_CALL을 낸 도구는 반드시 TOOL_RESULT로 닫는다.
    pending_tools: dict[str, str] = {}
    stream = query(prompt=prompt, options=options)
    try:
        async for message in stream:
            if isinstance(message, SdkStreamEvent):
                for event in _from_raw_event(message.event, pending_tools):
                    yield event
            elif isinstance(message, UserMessage):
                # 도구 실행 결과는 UserMessage의 ToolResultBlock으로 돌아온다.
                for event in _from_tool_results(message, pending_tools):
                    yield event
            elif isinstance(message, AssistantMessage):
                # 본문은 델타로만 방출한다 — 완결 메시지의 TextBlock을 다시 내면
                # 텍스트가 2배가 된다.
                continue
            elif isinstance(message, ResultMessage):
                # 결과가 관측되지 않은 도구는 여기서 닫는다. SDK 버전에 따라
                # ToolResultBlock이 스트림에 실려오지 않을 수 있어(서버 사이드
                # 도구 등) TOOL_CALL이 UI에서 영원히 "실행 중"으로 남는 것을 막는
                # 폴백이다. content_block_stop 시점 방출은 도구 실행 전이라
                # 의미가 어긋나므로 채택하지 않았다.
                for event in _flush_pending(pending_tools):
                    yield event
                if getattr(message, "subtype", "") == "error" or message.is_error:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        text=f"응답 생성에 실패했습니다: {_safe_message(message.result)}",
                    )
                    return
                yield StreamEvent(type=StreamEventType.DONE)
                return
            # 그 외 메시지(SystemMessage, TaskProgress 등)는 무시
    except Exception as exc:  # noqa: BLE001 — 스트림을 깨지 않고 오류로 종료
        yield StreamEvent(
            type=StreamEventType.ERROR,
            text=f"LLM 호출 실패: {_safe_message(exc)}",
        )
        return
    finally:
        # 클라이언트 중단(CancelledError) 포함 — SDK 제너레이터를 정리해
        # CLI 서브프로세스가 잔존하지 않게 한다.
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()


def _from_raw_event(
    event: dict, pending_tools: dict[str, str]
) -> list[StreamEvent]:
    """원시 API 스트림 이벤트 → StreamEvent (해당 없으면 빈 목록)."""
    etype = event.get("type")
    if etype == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            return [
                StreamEvent(
                    type=StreamEventType.TEXT_DELTA, text=delta.get("text") or ""
                )
            ]
        return []                      # thinking_delta / input_json_delta 등은 무시
    if etype == "content_block_start":
        block = event.get("content_block") or {}
        if block.get("type") in _TOOL_USE_BLOCK_TYPES:
            name = block.get("name") or ""
            block_id = block.get("id") or ""
            if block_id:
                pending_tools[block_id] = name
            return [StreamEvent(type=StreamEventType.TOOL_CALL, tool_name=name)]
    return []


def _from_tool_results(
    message: UserMessage, pending_tools: dict[str, str]
) -> list[StreamEvent]:
    content = message.content
    if not isinstance(content, list):
        return []
    events: list[StreamEvent] = []
    for block in content:
        if isinstance(block, ToolResultBlock):
            name = pending_tools.pop(block.tool_use_id, "")
            events.append(
                StreamEvent(type=StreamEventType.TOOL_RESULT, tool_name=name)
            )
    return events


def _flush_pending(pending_tools: dict[str, str]) -> list[StreamEvent]:
    events = [
        StreamEvent(type=StreamEventType.TOOL_RESULT, tool_name=name)
        for name in pending_tools.values()
    ]
    pending_tools.clear()
    return events


def _render_prompt(messages: list[ChatMessage]) -> str:
    """대화 이력을 단일 유저 프롬프트로 렌더링한다.

    이력은 서버에 저장하지 않으므로(휘발성), 매 요청 프론트가 보낸 전체 이력을
    "# 이전 대화 이력" 블록으로, 마지막 user 메시지를 "# 이번 질문"으로 붙인다.
    """
    if not messages:
        raise ValueError("질문 내용이 비어 있습니다.")

    history = messages[:-1]
    current = messages[-1]
    blocks: list[str] = []
    if history:
        lines = [
            f"{_ROLE_LABELS.get(m.role, m.role)} {m.content}" for m in history
        ]
        blocks.append("# 이전 대화 이력\n" + "\n".join(lines))
    blocks.append("# 이번 질문\n" + current.content)
    return "\n\n".join(blocks)


def _build_options(
    system: str, spec: ChatModeSpec, settings: Settings
) -> tuple[ClaudeAgentOptions, Path | None]:
    """모드 선언(llm/modes.py) → ClaudeAgentOptions.

    반환 두 번째 값은 시스템 프롬프트 임시 파일 경로(사용하지 않았으면 None) —
    호출자가 스트림 종료 후 삭제한다.
    """
    system_prompt, temp_path = _system_prompt_option(system)
    extra: dict = {}
    if spec.thinking_disabled:
        extra["thinking"] = {"type": "disabled"}

    options = ClaudeAgentOptions(
        model=spec.model,
        system_prompt=system_prompt,
        allowed_tools=list(spec.allowed_tools),
        disallowed_tools=list(spec.disallowed_tools),
        max_turns=spec.max_turns,
        cwd=PROJECT_ROOT,
        permission_mode="dontAsk",
        # 개발용 CLAUDE.md/설정이 채팅 페르소나를 오염시키지 않도록 차단한다.
        setting_sources=[],
        include_partial_messages=True,
        # .env 접근은 프롬프트 지침이 아니라 권한 계층에서 막는다(두 모드 공통).
        hooks={"PreToolUse": [HookMatcher(hooks=[_env_guard_hook])]},
        env=_build_env(settings),
        **extra,
    )
    return options, temp_path


def _build_env(settings: Settings) -> dict[str, str]:
    env = {SKIP_HISTORY_ENV: "1"}
    # 파일럿은 미설정 → CLI 로그인(구독) 자격증명 상속. 팀 배포 시 이 값만 채우면
    # API 키 인증으로 전환된다.
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
    return env


def _system_prompt_option(system: str) -> tuple[str | SystemPromptFile, Path | None]:
    """긴 시스템 프롬프트는 파일 참조로 전달한다(CLI 인자 길이 제한 회피)."""
    if len(system) <= SYSTEM_PROMPT_INLINE_LIMIT:
        return system, None
    fd, name = tempfile.mkstemp(prefix="eaf_system_prompt_", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(system)
    path = Path(name)
    return SystemPromptFile(type="file", path=str(path)), path


def _cleanup_temp(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _safe_message(exc: object) -> str:
    text = getattr(exc, "message", None) or str(exc or "")
    return str(text)[:ERROR_MESSAGE_LIMIT]
