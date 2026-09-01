"""채팅에서 선택 가능한 모델/reasoning 강도 옵션 — 유일한 선언 지점.

`GET /api/meta/llm`의 응답, 요청 오버라이드 값 검증, 프론트 셀렉트 박스가
모두 이 선언을 참조한다. 모델 id 문자열을 라우트·서비스·프론트에 흩어
하드코딩하지 말 것 (CLAUDE.md 선언 중심 확장 원칙 — 모델 추가는 여기 한 줄).

llm 계층 선언이므로 config/서비스에 의존하지 않는다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMOption:
    """선택지 1개. id는 provider에 그대로 전달되는 값, label_ko는 UI 표시용."""

    id: str
    label_ko: str


#: 선택 가능한 모델 (순서 = UI 표시 순서)
LLM_MODEL_OPTIONS: list[LLMOption] = [
    LLMOption("gpt-5-mini", "GPT-5 mini (빠름)"),
    LLMOption("gpt-5", "GPT-5 (심층)"),
    LLMOption("gpt-5-nano", "GPT-5 nano (최속)"),
]

#: 선택 가능한 reasoning 강도 (순서 = UI 표시 순서)
EFFORT_OPTIONS: list[LLMOption] = [
    LLMOption("minimal", "최소"),
    LLMOption("low", "낮음"),
    LLMOption("medium", "중간"),
    LLMOption("high", "높음"),
]

#: 내장 웹 검색 tool과 함께 쓸 수 없는 reasoning 강도.
#: OpenAI Responses API 제약 — minimal 강도로 web_search를 함께 보내면 400:
#:   "The following tools cannot be used with reasoning.effort 'minimal': web_search"
#: 해당 강도의 요청에서는 web_search만 빼고 호출한다(데이터 조회 function tool은 유지).
#: 제약이 풀리거나 다른 강도로 확대되면 이 선언만 수정한다.
EFFORTS_WITHOUT_WEB_SEARCH: frozenset[str] = frozenset({"minimal"})


def supports_web_search(effort_id: str | None) -> bool:
    """해당 reasoning 강도에서 내장 웹 검색 tool을 함께 보낼 수 있는지."""
    return effort_id not in EFFORTS_WITHOUT_WEB_SEARCH


#: 응답 상세도(OpenAI Responses API의 text.verbosity) 유효값.
#: 모델이 말하는 양을 직접 조절한다 — 문체 계약(context_builder.PERSONA)의
#: "간결·두괄식" 지침을 파라미터 차원에서 보강한다.
VERBOSITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")


def is_valid_verbosity(verbosity: str | None) -> bool:
    return verbosity in VERBOSITY_LEVELS


_MODEL_IDS = {o.id for o in LLM_MODEL_OPTIONS}
_EFFORT_IDS = {o.id for o in EFFORT_OPTIONS}


def is_valid_model(model_id: str | None) -> bool:
    return model_id in _MODEL_IDS


def is_valid_effort(effort_id: str | None) -> bool:
    return effort_id in _EFFORT_IDS


def resolve_model(requested: str | None, fallback: str) -> str:
    """요청 오버라이드를 검증해 반환. 목록에 없으면 기본값으로 폴백(에러 아님)."""
    return requested if is_valid_model(requested) else fallback


def resolve_effort(requested: str | None, fallback: str) -> str:
    """요청 오버라이드를 검증해 반환. 목록에 없으면 기본값으로 폴백(에러 아님).

    반환이 빈 문자열이면 provider는 reasoning 파라미터를 보내지 않는다.
    """
    return requested if is_valid_effort(requested) else fallback


def as_dicts(options: list[LLMOption]) -> list[dict]:
    """API 직렬화 형태."""
    return [{"id": o.id, "label_ko": o.label_ko} for o in options]
