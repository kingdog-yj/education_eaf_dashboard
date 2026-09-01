"""채팅 모드 선언 — 모델/도구/턴 수의 유일한 선언 지점.

`GET /api/meta/chat_modes`의 응답, 요청 `mode` 값 검증, provider의
ClaudeAgentOptions 구성, 프론트 모드 세그먼트가 모두 이 선언을 참조한다.
모델 id·도구 목록·턴 수를 라우트·서비스·프론트에 흩어 하드코딩하지 말 것
(CLAUDE.md 선언 중심 확장 원칙 — 모드 추가는 여기 한 줄).

llm 계층 선언이므로 config/서비스에 의존하지 않는다.
"""
from dataclasses import dataclass

#: 심화 모드가 실행할 수 있는 유일한 파이썬 인터프리터(프로젝트 루트 기준 상대 경로).
#: Bash 허용 패턴과 시스템 프롬프트 지침 문구가 모두 이 상수를 참조한다.
VENV_PYTHON = ".venv/Scripts/python.exe"
#: 같은 경로의 Windows 역슬래시 표기 (모델이 어느 쪽으로 써도 승인되도록).
_VENV_PYTHON_WIN = VENV_PYTHON.replace("/", "\\")


@dataclass(frozen=True)
class ChatModeSpec:
    """채팅 모드 1개. id는 API/프론트가 주고받는 값, label_ko/description_ko는 UI 표시용."""

    id: str
    label_ko: str
    description_ko: str
    model: str
    #: 사전 승인 도구(패턴 지원: "Bash(cmd *)"). permission_mode="dontAsk"와 함께
    #: 목록 밖 도구·명령은 프롬프트 없이 즉시 거부된다.
    allowed_tools: tuple[str, ...]
    #: 컨텍스트에서 제거할 도구. ("*",)는 모든 도구 정의를 제거한다.
    disallowed_tools: tuple[str, ...]
    max_turns: int
    #: True면 thinking={"type": "disabled"}를 전달, False면 SDK 기본값 유지.
    thinking_disabled: bool


#: 선택 가능한 모드 (순서 = UI 표시 순서)
CHAT_MODES: list[ChatModeSpec] = [
    ChatModeSpec(
        id="quick",
        label_ko="빠른 대화",
        description_ko="수 초 안에 답합니다. 일반 질문이나 화면 내용의 간단한 확인에 적합합니다.",
        model="claude-haiku-4-5",
        allowed_tools=(),
        disallowed_tools=("*",),
        max_turns=1,
        thinking_disabled=True,
    ),
    ChatModeSpec(
        id="deep",
        label_ko="심화 분석",
        description_ko="데이터와 문서를 직접 확인하며 답합니다. 정확하지만 수 분까지 걸릴 수 있습니다.",
        model="claude-opus-5",
        allowed_tools=(
            "Read",
            "Grep",
            "Glob",
            "WebSearch",
            "WebFetch",
            # 파이썬 실행만 허용 — 경로 구분자 두 표기를 모두 승인한다(Windows).
            f"Bash({VENV_PYTHON} *)",
            f"Bash({_VENV_PYTHON_WIN} *)",
        ),
        disallowed_tools=("Write", "Edit", "NotebookEdit", "Task", "TodoWrite"),
        max_turns=25,
        thinking_disabled=False,
    ),
]

DEFAULT_MODE_ID = "quick"

_BY_ID = {m.id: m for m in CHAT_MODES}


def resolve_mode(mode_id: str | None) -> ChatModeSpec:
    """요청 mode를 검증해 반환. 누락/목록 밖 값이면 기본 모드로 폴백(에러 아님)."""
    return _BY_ID.get(mode_id or "", _BY_ID[DEFAULT_MODE_ID])


def as_dicts() -> list[dict]:
    """API 직렬화 형태 (UI가 필요로 하는 필드만)."""
    return [
        {"id": m.id, "label_ko": m.label_ko, "description_ko": m.description_ko}
        for m in CHAT_MODES
    ]
