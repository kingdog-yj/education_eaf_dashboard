"""스켈레톤 스모크 테스트: 앱 기동/라우트/레지스트리 무결성."""
from fastapi.testclient import TestClient

from app.domain.tags import TAG_REGISTRY
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_tags():
    tags = client.get("/api/meta/tags").json()
    assert len(tags) == len(TAG_REGISTRY.all())
    # dev 프로필은 더미 생성 3태그(전력/화학) — 온도 계통은 dev_profile=False
    assert {"electrical", "chemical"} == {t["group"] for t in tags}


def test_meta_phases():
    phases = [p["id"] for p in client.get("/api/meta/phases").json()]
    assert phases == ["bore_in", "expansion", "meltdown", "refining", "tapping"]


def test_heats_endpoints():
    # 더미데이터 유무와 무관하게 동작해야 한다 (미생성 시 빈 배열)
    resp = client.get("/api/heats")
    assert resp.status_code == 200
    heats = resp.json()
    assert isinstance(heats, list)
    if not heats:
        return

    heat_id = heats[0]["heat_id"]
    assert client.get(f"/api/heats/{heat_id}").status_code == 200
    assert client.get(f"/api/heats/{heat_id}/timeseries?tags=active_power").status_code == 200
    additions = client.get(f"/api/heats/{heat_id}/additions")
    assert additions.status_code == 200
    assert isinstance(additions.json(), list)
