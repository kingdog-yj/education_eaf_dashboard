"""heat 도메인 모델. 그룹별 서브모델로 분리 — 그룹 추가 시 모델 추가 + Heat에 필드 1개.

API 응답 스키마로도 그대로 사용한다 (domain은 다른 계층에 의존하지 않는다).
"""
from datetime import datetime

from pydantic import BaseModel, Field


class HeatEvents(BaseModel):
    """조업 주요 이벤트 시각. 페이즈 경계 산출의 근거."""
    power_on: datetime
    meltdown: datetime | None = None      # 용락 시점 (최중요 이벤트)
    tap_start: datetime | None = None
    tap_end: datetime | None = None


class HeatSummary(BaseModel):
    """목록/트렌드 조회용 경량 요약."""
    heat_id: str
    date: datetime
    shift: str = ""
    steel_group: str = ""                 # 조업 패턴 그룹 코드 (domain/materials.STEEL_GROUPS)
    events: HeatEvents
    tap_weight_t: float | None = None
    energy_kwh_per_t: float | None = None


class ChargeInfo(BaseModel):
    """스크랩 장입 상세."""
    baskets: list[dict[str, float]] = Field(
        default_factory=list,
        description="바스켓별 {스크랩 등급: 장입량(t)} — 등급 체계는 데이터 소스 정의를 따름",
    )
    total_charge_t: float = 0.0
    hot_heel_t: float = 0.0


class KpiInfo(BaseModel):
    """조업 결과 KPI."""
    energy_kwh_per_t: float | None = None      # 전력원단위
    o2_nm3_per_t: float | None = None          # 산소원단위
    carbon_kg_per_t: float | None = None       # 탄소원단위
    power_on_min: float | None = None
    tap_to_tap_min: float | None = None
    tap_weight_t: float | None = None
    yield_pct: float | None = None             # 용강 회수율


class EopInfo(BaseModel):
    """종점(end-point) 정보."""
    tap_temp_c: float | None = None            # 출강 온도 (~1600°C)
    composition_pct: dict[str, float] = Field(
        default_factory=dict, description="종점 성분 % (C, P, S, Mn, ...)"
    )


class SlagInfo(BaseModel):
    """슬래그 성분 및 부재료."""
    composition_pct: dict[str, float] = Field(
        default_factory=dict, description="슬래그 성분 % (FeO, CaO, SiO2, MgO, ...)"
    )
    basicity: float | None = None              # 염기도 CaO/SiO2
    additions_kg: dict[str, float] = Field(
        default_factory=dict, description="부재료 투입량 kg (lime, dolomite, ...)"
    )


class AdditionEvent(BaseModel):
    """부원료 투입 이벤트 (생석회/괴탄 등). 코드 체계는 domain/materials.ADDITION_MATERIALS."""
    ts: datetime
    material: str
    label_ko: str = ""
    amount_kg: float


class Heat(BaseModel):
    """한 heat의 정적 데이터 전체."""
    summary: HeatSummary
    charge: ChargeInfo = Field(default_factory=ChargeInfo)
    kpi: KpiInfo = Field(default_factory=KpiInfo)
    eop: EopInfo = Field(default_factory=EopInfo)
    slag: SlagInfo = Field(default_factory=SlagInfo)


class TimeseriesPoint(BaseModel):
    ts: datetime
    value: float


class TimeseriesSeries(BaseModel):
    tag_id: str
    unit: str
    points: list[TimeseriesPoint]


class HeatTimeseries(BaseModel):
    heat_id: str
    series: list[TimeseriesSeries]
    downsample_s: float | None = None   # 적용된 다운샘플 주기 (None = 원본)
