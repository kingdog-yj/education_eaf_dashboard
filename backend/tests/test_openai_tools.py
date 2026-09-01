"""OpenAIProvider의 요청별 tool 목록 구성 검증 (LLM 실호출 없음).

배경: reasoning.effort "minimal"은 내장 web_search와 함께 보낼 수 없어
OpenAI가 400(invalid_request_error, param=tools)을 반환한다.
"""
from app.config import Settings
from app.llm import options
from app.llm.openai_provider import WEB_SEARCH_TOOL_TYPE, OpenAIProvider


def _provider(**overrides) -> OpenAIProvider:
    # 실호출은 하지 않는다 — 클라이언트 생성용 더미 키
    return OpenAIProvider(Settings(openai_api_key="test-key", **overrides))


def _types(tools: list[dict]) -> list[str]:
    return [t["type"] for t in tools]


def test_minimal_effort_excludes_web_search():
    tools = _provider()._build_tools("minimal")
    assert WEB_SEARCH_TOOL_TYPE not in _types(tools)
    # 데이터 조회 function tool은 그대로 유지되어야 한다
    assert all(t["type"] == "function" for t in tools)
    assert len(tools) == len(_provider()._tools.all())


def test_low_effort_includes_web_search():
    tools = _provider()._build_tools("low")
    assert _types(tools)[0] == WEB_SEARCH_TOOL_TYPE
    assert len(tools) == len(_provider()._tools.all()) + 1


def test_empty_effort_includes_web_search():
    # 강도 미지정(SDK 기본) 요청도 기존 동작 그대로 web_search 포함
    assert WEB_SEARCH_TOOL_TYPE in _types(_provider()._build_tools(""))


# -- verbosity 파라미터 구성 ------------------------------------------------


def test_valid_verbosity_is_sent():
    extra = _provider(llm_verbosity="medium")._build_extra_params("low")
    assert extra["text"] == {"verbosity": "medium"}
    assert extra["reasoning"] == {"effort": "low"}


def test_invalid_verbosity_is_omitted():
    extra = _provider(llm_verbosity="ultra-chatty")._build_extra_params("low")
    assert "text" not in extra          # 무효값 → 파라미터 자체 미전달
    assert extra["reasoning"] == {"effort": "low"}


def test_empty_verbosity_is_omitted():
    extra = _provider(llm_verbosity="")._build_extra_params("")
    assert extra == {}                  # 빈 값 → reasoning/text 모두 미전달


def test_verbosity_levels_declaration():
    assert options.VERBOSITY_LEVELS == ("low", "medium", "high")
    for level in options.VERBOSITY_LEVELS:
        assert options.is_valid_verbosity(level)
        assert _provider(llm_verbosity=level)._build_extra_params("")["text"] == {
            "verbosity": level
        }
    assert not options.is_valid_verbosity(None)


def test_incompatible_effort_declaration_is_single_source():
    assert "minimal" in options.EFFORTS_WITHOUT_WEB_SEARCH
    assert not options.supports_web_search("minimal")
    for effort in options.EFFORT_OPTIONS:
        expected = effort.id not in options.EFFORTS_WITHOUT_WEB_SEARCH
        assert options.supports_web_search(effort.id) is expected
        has_ws = WEB_SEARCH_TOOL_TYPE in _types(_provider()._build_tools(effort.id))
        assert has_ws is expected
