"""채팅 모드 선언(llm/modes.py) 계약 테스트.

모델명·도구 목록·턴 수는 여기와 modes.py에만 존재해야 한다(선언 중심 확장 원칙).
"""
from app.llm import modes


def _by_id(mode_id: str) -> modes.ChatModeSpec:
    return next(m for m in modes.CHAT_MODES if m.id == mode_id)


def test_mode_order_and_models():
    assert [m.id for m in modes.CHAT_MODES] == ["quick", "deep"]
    assert _by_id("quick").model == "claude-haiku-4-5"
    assert _by_id("deep").model == "claude-opus-5"
    assert modes.DEFAULT_MODE_ID == "quick"


def test_quick_has_no_tools():
    quick = _by_id("quick")
    assert quick.allowed_tools == ()
    assert quick.disallowed_tools == ("*",)
    assert quick.max_turns == 1
    assert quick.thinking_disabled is True


def test_deep_tool_allowlist():
    deep = _by_id("deep")
    for name in ("Read", "Grep", "Glob", "WebSearch", "WebFetch"):
        assert name in deep.allowed_tools
    # Bash는 .venv 파이썬 실행 패턴으로만 승인된다(슬래시/역슬래시 두 표기).
    assert f"Bash({modes.VENV_PYTHON} *)" in deep.allowed_tools
    assert f"Bash({modes.VENV_PYTHON.replace('/', chr(92))} *)" in deep.allowed_tools
    assert "Bash" not in deep.allowed_tools
    assert sum(t.startswith("Bash(") for t in deep.allowed_tools) == 2

    for name in ("Write", "Edit"):
        assert name in deep.disallowed_tools
    assert deep.max_turns == 25
    assert deep.thinking_disabled is False


def test_venv_python_constant():
    assert modes.VENV_PYTHON == ".venv/Scripts/python.exe"


def test_resolve_mode_fallback():
    assert modes.resolve_mode("deep").id == "deep"
    assert modes.resolve_mode(None).id == modes.DEFAULT_MODE_ID
    assert modes.resolve_mode("").id == modes.DEFAULT_MODE_ID
    assert modes.resolve_mode("turbo").id == modes.DEFAULT_MODE_ID


def test_as_dicts_shape():
    dicts = modes.as_dicts()
    assert [d["id"] for d in dicts] == ["quick", "deep"]
    for item in dicts:
        assert set(item) == {"id", "label_ko", "description_ko"}
        assert item["label_ko"] and item["description_ko"]
    assert dicts[0]["label_ko"] == "빠른 대화"
    assert dicts[1]["label_ko"] == "심화 분석"
