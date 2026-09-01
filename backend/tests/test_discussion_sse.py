"""SSE 프레이밍/하트비트 테스트.

LLM은 실호출하지 않는다(비용) — provider를 대체한 가짜 서비스로 프레임만 검증한다.
"""
import asyncio
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.deps import get_discussion_service
from app.api.routes import discussion as discussion_route
from app.llm import options
from app.llm.base import StreamEvent, StreamEventType
from app.main import app
from app.services.discussion_service import DiscussionRequest


class _SlowService:
    """첫 이벤트까지 지연이 있는 provider를 흉내낸다 (reasoning 구간 재현)."""

    def __init__(self, delay_s: float):
        self._delay_s = delay_s
        self.seen: list[DiscussionRequest] = []

    async def stream(self, req) -> AsyncIterator[StreamEvent]:
        self.seen.append(req)
        await asyncio.sleep(self._delay_s)
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, text="안녕")
        yield StreamEvent(type=StreamEventType.DONE)


def _post_body() -> dict:
    return {"messages": [{"role": "user", "content": "테스트"}]}


def test_heartbeat_frames_precede_first_event(monkeypatch):
    monkeypatch.setattr(discussion_route, "HEARTBEAT_INTERVAL_S", 0.05)
    app.dependency_overrides[get_discussion_service] = lambda: _SlowService(0.3)
    try:
        with TestClient(app) as client:
            body = client.post("/api/discussion", json=_post_body()).text
    finally:
        app.dependency_overrides.pop(get_discussion_service, None)

    assert ": ping\n\n" in body
    # 하트비트는 첫 data: 프레임보다 먼저 나온다
    assert body.index(": ping") < body.index("data:")
    # data: 프레임 형식·순서는 기존과 동일
    data_lines = [ln for ln in body.splitlines() if ln.startswith("data: ")]
    assert len(data_lines) == 2
    assert '"type":"text_delta"' in data_lines[0]
    assert '"type":"done"' in data_lines[1]


def test_no_heartbeat_when_events_are_prompt(monkeypatch):
    monkeypatch.setattr(discussion_route, "HEARTBEAT_INTERVAL_S", 5.0)
    app.dependency_overrides[get_discussion_service] = lambda: _SlowService(0.0)
    try:
        with TestClient(app) as client:
            body = client.post("/api/discussion", json=_post_body()).text
    finally:
        app.dependency_overrides.pop(get_discussion_service, None)

    assert ": ping" not in body
    assert body.count("data: ") == 2


# -- 요청 단위 모델/effort 오버라이드 ---------------------------------------


def _post_with_overrides(model, effort) -> DiscussionRequest:
    """요청을 보내고 서비스가 실제로 받은 DiscussionRequest를 돌려준다."""
    service = _SlowService(0.0)
    app.dependency_overrides[get_discussion_service] = lambda: service
    body = _post_body()
    body["model"] = model
    body["reasoning_effort"] = effort
    try:
        with TestClient(app) as client:
            assert client.post("/api/discussion", json=body).status_code == 200
    finally:
        app.dependency_overrides.pop(get_discussion_service, None)
    assert len(service.seen) == 1
    return service.seen[0]


def test_discussion_request_parses_overrides():
    req = _post_with_overrides("gpt-5", "high")
    assert req.model == "gpt-5"
    assert req.reasoning_effort == "high"


def test_discussion_request_overrides_optional():
    service = _SlowService(0.0)
    app.dependency_overrides[get_discussion_service] = lambda: service
    try:
        with TestClient(app) as client:
            assert client.post("/api/discussion", json=_post_body()).status_code == 200
    finally:
        app.dependency_overrides.pop(get_discussion_service, None)
    assert service.seen[0].model is None
    assert service.seen[0].reasoning_effort is None


def test_invalid_overrides_are_accepted_and_fall_back():
    # 목록 밖 값이어도 400이 아니라 200 — 폴백은 provider 계층 책임
    req = _post_with_overrides("gpt-4o-mystery", "ultra")
    assert req.model == "gpt-4o-mystery"
    assert options.resolve_model(req.model, "gpt-5-mini") == "gpt-5-mini"
    assert options.resolve_effort(req.reasoning_effort, "low") == "low"


def test_resolve_helpers():
    assert options.resolve_model("gpt-5-nano", "gpt-5-mini") == "gpt-5-nano"
    assert options.resolve_model(None, "gpt-5-mini") == "gpt-5-mini"
    assert options.resolve_effort("minimal", "low") == "minimal"
    assert options.resolve_effort(None, "low") == "low"
    assert options.resolve_effort("", "low") == "low"
