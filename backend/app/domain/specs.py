"""지표·조업 스펙 레지스트리 — 스펙 수치(밴드)의 유일한 선언 지점.

`MetricSpec.id`는 heats.parquet의 평탄 컬럼명이자 KPI 트렌드 행의 키이며,
`GET /api/meta/specs`로 프론트에 그대로 노출된다. 지표 추가/밴드 조정은
이 파일의 선언 수정만으로 완결되어야 한다 — 380/410/1590 같은 수치를
repository·service·route·프론트 어디에도 하드코딩하지 말 것.

domain 계층이므로 다른 계층에 의존하지 않는다.
"""
from collections.abc import Mapping
from dataclasses import dataclass

#: 스펙 밴드 판정 시 경계값은 정상으로 취급한다 ([lo, hi] 폐구간).


@dataclass(frozen=True)
class MetricSpec:
    """단일 지표의 표시 규약 + 조업 스펙 밴드.

    lo/hi가 모두 None이면 밴드 없음(트렌드 선택용 지표로만 사용).
    """

    id: str
    label_ko: str
    unit: str
    decimals: int
    lo: float | None = None
    hi: float | None = None

    @property
    def has_band(self) -> bool:
        return self.lo is not None or self.hi is not None

    def is_within(self, value: float) -> bool:
        """값이 밴드 내(경계 포함)인지. 밴드가 없으면 항상 True."""
        if self.lo is not None and value < self.lo:
            return False
        if self.hi is not None and value > self.hi:
            return False
        return True


#: 지표 선언 (순서 = API 응답 순서 = 프론트 표시 순서)
SPEC_REGISTRY: list[MetricSpec] = [
    MetricSpec("kpi_energy_kwh_per_t", "전력원단위", "kWh/t", 1, 380.0, 410.0),
    MetricSpec("kpi_o2_nm3_per_t", "산소원단위", "Nm³/t", 1),
    MetricSpec("kpi_carbon_kg_per_t", "탄소원단위", "kg/t", 1),
    MetricSpec("kpi_power_on_min", "Power-on Time (POT)", "min", 1, 33.0, 40.0),
    MetricSpec("kpi_tap_to_tap_min", "Tap-to-Tap", "min", 1),
    MetricSpec("kpi_tap_weight_t", "출강량", "t", 1, 148.0, 153.0),
    MetricSpec("kpi_yield_pct", "수율", "%", 1),
    MetricSpec("eop_tap_temp_c", "출강 온도", "°C", 0, 1590.0, 1620.0),
    MetricSpec("eop_comp_c", "종점 C", "%", 3, 0.03, 0.10),
    MetricSpec("eop_comp_p", "종점 P", "%", 3, 0.010, 0.030),
    MetricSpec("charge_total_t", "총 장입량", "t", 1, 155.0, 165.0),
]

_SPECS_BY_ID: dict[str, MetricSpec] = {s.id: s for s in SPEC_REGISTRY}
if len(_SPECS_BY_ID) != len(SPEC_REGISTRY):
    raise ValueError("중복 지표 id가 선언됨")


def get(spec_id: str) -> MetricSpec | None:
    """id로 지표 조회 (미등록이면 None)."""
    return _SPECS_BY_ID.get(spec_id)


def ids() -> list[str]:
    """선언 순서대로의 지표 id 목록."""
    return [s.id for s in SPEC_REGISTRY]


def banded() -> list[MetricSpec]:
    """스펙 밴드가 선언된 지표만."""
    return [s for s in SPEC_REGISTRY if s.has_band]


def _as_float(value: object) -> float | None:
    """결측(None/NaN/비수치)을 None으로 정규화."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN 제외


def is_out_of_spec(row: Mapping[str, object]) -> bool:
    """heat 한 행(평탄 dict)이 스펙 이탈인지 판정.

    밴드가 선언된 지표 중 하나라도 [lo, hi] 밖이면 이탈(경계값은 정상).
    결측·미존재 컬럼은 판정에서 제외한다.
    """
    for spec in banded():
        value = _as_float(row.get(spec.id))
        if value is None:
            continue
        if not spec.is_within(value):
            return True
    return False


@dataclass(frozen=True)
class SummaryCardDef:
    """KPI 요약 카드 선언. agg/column이 집계 방식을 결정한다.

    agg: "count"(heat 수) | "sum" | "mean" | "out_of_spec_count"
    column: 집계 대상 컬럼 (count/out_of_spec_count는 None)
    spec_id: 값 판정에 사용할 SPEC_REGISTRY id (없으면 None)
    """

    id: str
    label_ko: str
    unit: str
    decimals: int
    agg: str
    column: str | None = None
    spec_id: str | None = None


#: 요약 카드 선언 (순서 = API 응답 순서 = 프론트 표시 순서)
SUMMARY_CARDS: list[SummaryCardDef] = [
    SummaryCardDef("heat_count", "Heat 수", "heat", 0, "count"),
    SummaryCardDef("production_t", "생산량 합", "t", 0, "sum", "kpi_tap_weight_t"),
    SummaryCardDef(
        "avg_energy_kwh_per_t", "평균 전력원단위", "kWh/t", 1,
        "mean", "kpi_energy_kwh_per_t", "kpi_energy_kwh_per_t",
    ),
    SummaryCardDef(
        "avg_o2_nm3_per_t", "평균 산소원단위", "Nm³/t", 1, "mean", "kpi_o2_nm3_per_t"
    ),
    SummaryCardDef(
        "avg_power_on_min", "평균 Power-on Time", "min", 1,
        "mean", "kpi_power_on_min", "kpi_power_on_min",
    ),
    SummaryCardDef(
        "avg_tap_to_tap_min", "평균 Tap-to-Tap", "min", 1, "mean", "kpi_tap_to_tap_min"
    ),
    SummaryCardDef("avg_yield_pct", "평균 수율", "%", 1, "mean", "kpi_yield_pct"),
    SummaryCardDef(
        "out_of_spec_count", "스펙 이탈 Heat 수", "heat", 0, "out_of_spec_count"
    ),
]
