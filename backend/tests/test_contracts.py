"""대시보드 v1 API 계약 테스트 (docs/plans/dashboard-v1.md §3).

LLM 실호출은 비용 때문에 테스트하지 않는다 (scripts/smoke_openai.py로만 확인).
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.domain import specs
from app.domain.materials import ADDITION_MATERIALS, SCRAP_GRADES, STEEL_GROUPS
from app.domain.phases import HeatPhase
from app.main import app

client = TestClient(app)

EXPECTED_SPEC_IDS = [
    "kpi_energy_kwh_per_t",
    "kpi_o2_nm3_per_t",
    "kpi_carbon_kg_per_t",
    "kpi_power_on_min",
    "kpi_tap_to_tap_min",
    "kpi_tap_weight_t",
    "kpi_yield_pct",
    "eop_tap_temp_c",
    "eop_comp_c",
    "eop_comp_p",
    "charge_total_t",
]

EXPECTED_CARD_IDS = [
    "heat_count",
    "production_t",
    "avg_energy_kwh_per_t",
    "avg_o2_nm3_per_t",
    "avg_power_on_min",
    "avg_tap_to_tap_min",
    "avg_yield_pct",
    "out_of_spec_count",
]


def _first_heat_id() -> str | None:
    heats = client.get("/api/heats").json()
    return heats[0]["heat_id"] if heats else None


# -- C1 /api/meta/specs -----------------------------------------------------


def test_meta_specs_contract():
    resp = client.get("/api/meta/specs")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["id"] for s in body] == EXPECTED_SPEC_IDS
    for item in body:
        assert set(item) == {"id", "label_ko", "unit", "decimals", "lo", "hi"}

    energy = next(s for s in body if s["id"] == "kpi_energy_kwh_per_t")
    assert (energy["lo"], energy["hi"]) == (380.0, 410.0)
    assert energy["label_ko"] == "전력원단위"
    assert energy["decimals"] == 1

    # 밴드 없는 지표는 lo/hi가 null
    o2 = next(s for s in body if s["id"] == "kpi_o2_nm3_per_t")
    assert o2["lo"] is None and o2["hi"] is None


def test_is_out_of_spec_rules():
    # 경계값은 정상, 결측은 판정 제외
    assert not specs.is_out_of_spec({"kpi_energy_kwh_per_t": 380.0})
    assert not specs.is_out_of_spec({"kpi_energy_kwh_per_t": 410.0})
    assert specs.is_out_of_spec({"kpi_energy_kwh_per_t": 410.1})
    assert not specs.is_out_of_spec({"kpi_energy_kwh_per_t": None})
    assert not specs.is_out_of_spec({})
    # 밴드 없는 지표는 어떤 값이어도 이탈이 아님
    assert not specs.is_out_of_spec({"kpi_o2_nm3_per_t": 99999.0})


# -- C5 /api/meta/materials -------------------------------------------------


def test_meta_materials_contract():
    body = client.get("/api/meta/materials").json()
    assert set(body) == {"scrap_grades", "addition_materials", "steel_groups"}
    assert body["scrap_grades"] == SCRAP_GRADES
    assert body["addition_materials"] == ADDITION_MATERIALS
    assert body["steel_groups"] == STEEL_GROUPS


# -- C2 /api/kpi/summary ----------------------------------------------------


@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_kpi_summary_contract(period: str):
    resp = client.get(f"/api/kpi/summary?period={period}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "period",
        "bucket_start",
        "bucket_end",
        "prev_bucket_start",
        "cards",
    }
    assert body["period"] == period

    if not body["cards"]:                      # 데이터 없음 → 버킷 필드 null
        assert body["bucket_start"] is None
        return

    assert [c["id"] for c in body["cards"]] == EXPECTED_CARD_IDS
    for card in body["cards"]:
        assert set(card) == {
            "id", "label_ko", "unit", "decimals", "value", "prev_value", "spec_id"
        }
    by_id = {c["id"]: c for c in body["cards"]}
    assert by_id["avg_energy_kwh_per_t"]["spec_id"] == "kpi_energy_kwh_per_t"
    assert by_id["avg_power_on_min"]["spec_id"] == "kpi_power_on_min"
    assert by_id["heat_count"]["spec_id"] is None
    assert by_id["heat_count"]["value"] >= 1
    assert body["bucket_start"] < body["bucket_end"]
    assert body["prev_bucket_start"] < body["bucket_start"]


def test_kpi_summary_rejects_unknown_period():
    assert client.get("/api/kpi/summary?period=year").status_code == 422


# -- C3 /api/kpi/trend ------------------------------------------------------


def test_kpi_trend_row_keys():
    rows = client.get("/api/kpi/trend").json()
    assert isinstance(rows, list)
    if not rows:
        pytest.skip("더미데이터 미생성")
    row = rows[0]
    for key in ("heat_id", "date", "steel_group", "eop_tap_temp_c", "charge_total_t"):
        assert key in row
    assert any(k.startswith("kpi_") for k in row)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


# -- C4 /api/heats/{id}/phases ---------------------------------------------


def test_phases_contract():
    heat_id = _first_heat_id()
    if heat_id is None:
        pytest.skip("더미데이터 미생성")
    resp = client.get(f"/api/heats/{heat_id}/phases")
    assert resp.status_code == 200
    phases = resp.json()
    assert phases, "이벤트가 있으면 최소 1개 페이즈가 나와야 한다"

    valid = {p.value for p in HeatPhase}
    for item in phases:
        assert set(item) == {"phase", "label_ko", "start", "end"}
        assert item["phase"] in valid
        assert item["end"] > item["start"]      # 길이 0 이하 구간은 생략됨
    starts = [p["start"] for p in phases]
    assert starts == sorted(starts)


def test_phases_unknown_heat_404():
    assert client.get("/api/heats/__nope__/phases").status_code == 404


# -- C6 slag additions 키 ---------------------------------------------------


def test_slag_additions_keys_have_no_kg_suffix():
    heat_id = _first_heat_id()
    if heat_id is None:
        pytest.skip("더미데이터 미생성")
    additions = client.get(f"/api/heats/{heat_id}").json()["slag"]["additions_kg"]
    if not additions:
        pytest.skip("부재료 컬럼 없음")
    for key in additions:
        assert not key.endswith("_kg")
        assert key in ADDITION_MATERIALS


# -- C7 정적 서빙 -----------------------------------------------------------


def test_spa_fallback_serves_index():
    if not (get_settings().frontend_dist_dir / "index.html").is_file():
        pytest.skip("frontend/dist 미빌드")
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    # 클라이언트 라우트도 index.html로 fallback
    assert client.get("/trend").status_code == 200


def test_unknown_api_path_is_404_json():
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
