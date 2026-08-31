"""시계열 태그 레지스트리 — 태그의 유일한 선언 지점.

태그 추가/삭제/샘플링 주기 변경은 이 파일의 선언 수정만으로 완결되어야 한다.
태그 id·주기를 다른 모듈에 하드코딩하지 말 것 (CLAUDE.md 설계 원칙).
"""
from dataclasses import dataclass, field
from enum import Enum


class TagGroup(str, Enum):
    ELECTRICAL = "electrical"  # 전력 계통
    CHEMICAL = "chemical"      # 화학에너지 계통
    THERMAL = "thermal"        # 온도/부생 계통
    # 확장 예약: MECHANICAL(전극 위치/기계 계통) — 필요 시 그룹 추가 후 태그 선언


@dataclass(frozen=True)
class TagDef:
    id: str
    group: TagGroup
    unit: str
    label_ko: str
    sample_period_s: float = 1.0   # 태그별 수집 주기 (기본 1초, 태그별 상이 가능)
    dev_profile: bool = True       # 개발 단계 최소 프로필 포함 여부 (로딩 시간 최소화)
    cumulative: bool = False       # 누적값 여부 (차트 축/다운샘플 방식 결정에 사용)


_TAGS: list[TagDef] = [
    # --- 전력 계통 ---
    TagDef("active_power", TagGroup.ELECTRICAL, "MW", "유효전력"),
    # 더미 단계 미생성 — active_power 적분으로 파생 가능
    TagDef(
        "energy_total", TagGroup.ELECTRICAL, "kWh", "누적 전력량",
        cumulative=True, dev_profile=False,
    ),
    TagDef("tap_position", TagGroup.ELECTRICAL, "-", "변압기 탭 위치", dev_profile=False),
    # --- 화학에너지 계통 ---
    TagDef("o2_lance_flow", TagGroup.CHEMICAL, "Nm3/h", "산소 랜싱 유량"),
    TagDef("carbon_inj_rate", TagGroup.CHEMICAL, "kg/min", "분탄 인젝션 속도"),
    # --- 온도/부생 계통 (더미 단계 미생성 — 데이터 소스 연결 시 dev_profile=True) ---
    TagDef("panel_temp", TagGroup.THERMAL, "degC", "수냉 패널 온도", dev_profile=False),
    TagDef("offgas_temp", TagGroup.THERMAL, "degC", "배가스 온도", dev_profile=False),
    # --- 확장 예약 (dev_profile=False로 선언 후 데이터 소스 연결 시 활성화) ---
    # TagDef("arc_stability", TagGroup.ELECTRICAL, "-", "아크 안정도 지표", dev_profile=False),
    # TagDef("o2_total", TagGroup.CHEMICAL, "Nm3", "누적 산소량", cumulative=True, dev_profile=False),
    # TagDef("burner_gas_flow", TagGroup.CHEMICAL, "Nm3/h", "버너 가스 유량", dev_profile=False),
    # TagDef("offgas_co", TagGroup.THERMAL, "%", "배가스 CO 농도", dev_profile=False),
]


class TagRegistry:
    def __init__(self, tags: list[TagDef]):
        self._by_id = {t.id: t for t in tags}
        if len(self._by_id) != len(tags):
            raise ValueError("중복 태그 id가 선언됨")

    def get(self, tag_id: str) -> TagDef:
        return self._by_id[tag_id]

    def all(self, dev_only: bool = True) -> list[TagDef]:
        return [t for t in self._by_id.values() if t.dev_profile or not dev_only]

    def by_group(self, group: TagGroup, dev_only: bool = True) -> list[TagDef]:
        return [t for t in self.all(dev_only) if t.group == group]

    def ids(self, dev_only: bool = True) -> list[str]:
        return [t.id for t in self.all(dev_only)]


TAG_REGISTRY = TagRegistry(_TAGS)
