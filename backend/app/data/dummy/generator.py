"""EAF 더미데이터 생성기 (SPEC.md §4.4 / docs/plans/dummy-data-generation.md).

물리 모델 요약
--------------
- heat마다 강종 그룹(STEEL_GROUPS) → 장입량 → 목표 전력원단위 → 총 투입에너지 E를
  샘플링하고, 전력 프로필(램프 2~3단 → 용해기 평탄부 → 정련기 평탄부)로부터
  power-on time(POT)을 역산한다. POT가 조업 범위를 벗어나면 프로필을 재샘플한다.
- 1초 시계열은 계획 프로필 + 노이즈로 생성하고, **누적 전력(cumE)이 E에 도달한 시점을
  power_off로 확정**한다. 즉 KPI(전력원단위 등)는 전부 생성된 시계열의 적분에서 파생되며
  정적 데이터와 시계열이 항상 정합한다.
- 용락(ev_meltdown) = cumE가 f·E를 넘는 첫 시점. 이 시점을 경계로 아크 안정도(노이즈),
  전력 평탄부(P_melt→P_ref), 산소 유량 단계, 분탄 인젝션 개시가 모두 바뀐다(DOMAIN_INFO.md).

설계 규약
--------
- 수치 파라미터는 GeneratorConfig / 모듈 상단 선언 테이블(GROUP_PARAMS, *_BAND)에만 둔다.
- 태그 id·스크랩 등급·부원료·강종 그룹 코드는 domain(tags.py/materials.py)에서 가져온다.
- domain 외 계층에 의존하지 않는다(config는 CLI 진입점에서만 import).
- 재현성: numpy.random.default_rng(config.seed) 단일 rng로 순차 생성.

실행: `python -m app.data.dummy.generator` (backend/ 에서, 사용자 승인 후)
"""
import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.domain.materials import ADDITION_MATERIALS, SCRAP_GRADES, STEEL_GROUPS
from app.domain.phases import HeatPhase
from app.domain.tags import TAG_REGISTRY

# --- 코드 상수: 선언 지점(domain)에서 취득 -----------------------------------
# 스크랩 등급/부원료 코드는 materials 선언 순서를 그대로 따른다(등급 추가 시 여기서 실패 → 배합표 갱신).
GRADE_A, SHREDDER, TURNINGS, COMMON = SCRAP_GRADES
LIME, LUMP_CARBON = ADDITION_MATERIALS
# 태그 id는 레지스트리 조회로 취득 (미선언 태그면 KeyError로 즉시 실패)
TAG_ACTIVE_POWER = TAG_REGISTRY.get("active_power").id
TAG_O2_LANCE_FLOW = TAG_REGISTRY.get("o2_lance_flow").id
TAG_CARBON_INJ_RATE = TAG_REGISTRY.get("carbon_inj_rate").id

# --- 선언 테이블 -------------------------------------------------------------

OUTLIER_P = 0.025  # 변수별 이상치 발생 확률


@dataclass(frozen=True)
class OutlierBand:
    """정상 밴드 [lo, hi]와 이상치 밴드 [lo_out, lo) ∪ (hi, hi_out]."""
    lo: float
    hi: float
    lo_out: float
    hi_out: float
    p: float = OUTLIER_P


@dataclass(frozen=True)
class GroupParams:
    """강종 그룹별 조업 패턴. 키는 STEEL_GROUPS와 일치해야 한다."""
    share: float                              # 그룹 출현 비율
    energy_kwh_per_t: tuple[float, float]     # 목표 전력원단위 U(lo, hi)
    scrap_grade_a: tuple[float, float]        # A급 배합비 (평균, 표준편차)
    scrap_shredder: tuple[float, float]       # 슈레더 배합비 (평균, 표준편차)
    turnings_of_balance: tuple[float, float]  # 잔여 중 선반설 비율 (평균, 표준편차)
    eop_tap_temp_c: tuple[float, float]
    eop_comp_c: tuple[float, float]
    eop_comp_p: tuple[float, float]
    o2_refine_end: tuple[float, float]        # 정련 말기 산소 유량 Nm3/h


GROUP_PARAMS: dict[str, GroupParams] = {
    "high": GroupParams(
        share=0.25,
        energy_kwh_per_t=(388.0, 410.0),
        scrap_grade_a=(0.75, 0.03),
        scrap_shredder=(0.10, 0.02),
        turnings_of_balance=(0.40, 0.02),
        eop_tap_temp_c=(1600.0, 1620.0),
        eop_comp_c=(0.03, 0.06),
        eop_comp_p=(0.010, 0.018),
        o2_refine_end=(8000.0, 9000.0),
    ),
    "mid": GroupParams(
        share=0.55,
        energy_kwh_per_t=(382.0, 404.0),
        scrap_grade_a=(0.70, 0.03),
        scrap_shredder=(0.10, 0.02),
        turnings_of_balance=(0.50, 0.02),
        eop_tap_temp_c=(1595.0, 1615.0),
        eop_comp_c=(0.05, 0.08),
        eop_comp_p=(0.015, 0.025),
        o2_refine_end=(8500.0, 9500.0),
    ),
    "low": GroupParams(
        share=0.20,
        energy_kwh_per_t=(380.0, 398.0),
        scrap_grade_a=(0.62, 0.04),
        scrap_shredder=(0.12, 0.03),
        turnings_of_balance=(0.55, 0.02),
        eop_tap_temp_c=(1590.0, 1610.0),
        eop_comp_c=(0.06, 0.10),
        eop_comp_p=(0.020, 0.030),
        o2_refine_end=(9000.0, 10000.0),
    ),
}
assert set(GROUP_PARAMS) == set(STEEL_GROUPS), "GROUP_PARAMS 키는 STEEL_GROUPS와 일치해야 한다"

# 전역 밴드 (그룹 연동 변수는 정상값을 그룹 범위에서, 이상치만 아래 밴드에서 뽑는다)
CHARGE_BAND = OutlierBand(155.0, 165.0, 152.0, 169.0)
ENERGY_BAND = OutlierBand(380.0, 410.0, 372.0, 420.0)
TAP_WEIGHT_BAND = OutlierBand(148.0, 153.0, 146.0, 155.5)
TAP_TEMP_BAND = OutlierBand(1590.0, 1620.0, 1578.0, 1632.0)
COMP_C_BAND = OutlierBand(0.03, 0.10, 0.0285, 0.105)
COMP_P_BAND = OutlierBand(0.010, 0.030, 0.0095, 0.0315)

# 페이즈별 유효전력 노이즈 σ 범위 (MW) — 용락 전 아크 불안정 / 용락 후 안정 (DOMAIN_INFO.md)
POWER_SIGMA_MW: dict[HeatPhase, tuple[float, float]] = {
    HeatPhase.BORE_IN: (4.0, 6.0),
    HeatPhase.EXPANSION: (4.0, 6.0),
    HeatPhase.MELTDOWN: (1.5, 2.5),
    HeatPhase.REFINING: (1.5, 2.5),
}

# 근무조 경계 (시작 시각 hour, 코드) — power_on 시각으로 판정
SHIFTS: tuple[tuple[int, int, str], ...] = ((6, 14, "D"), (14, 22, "S"))
SHIFT_NIGHT = "N"

# heats.parquet 컬럼 계약 (순서 포함)
_SCRAP_COLUMNS = tuple(f"charge_scrap_{code}_t" for code in SCRAP_GRADES)
_SLAG_ADD_COLUMNS = tuple(f"slag_add_{code}_kg" for code in ADDITION_MATERIALS)
HEAT_COLUMNS: tuple[str, ...] = (
    "heat_id", "date", "shift", "steel_group",
    "ev_power_on", "ev_meltdown", "ev_tap_start", "ev_tap_end",
    "charge_total_t", "charge_hot_heel_t", *_SCRAP_COLUMNS,
    "kpi_energy_kwh_per_t", "kpi_o2_nm3_per_t", "kpi_carbon_kg_per_t",
    "kpi_power_on_min", "kpi_tap_to_tap_min", "kpi_tap_weight_t", "kpi_yield_pct",
    "eop_tap_temp_c", "eop_comp_c", "eop_comp_p", *_SLAG_ADD_COLUMNS,
)
ADDITION_COLUMNS: tuple[str, ...] = ("heat_id", "ts", "material", "amount_kg")
# 시각 컬럼은 naive datetime64[ns]로 고정 (Repository/프론트 계약)
DATETIME_DTYPE = "datetime64[ns]"
HEAT_DATETIME_COLUMNS: tuple[str, ...] = (
    "date", "ev_power_on", "ev_meltdown", "ev_tap_start", "ev_tap_end",
)

# 태그별 저장 소수 자리수
TAG_DECIMALS: dict[str, int] = {
    TAG_ACTIVE_POWER: 2,
    TAG_O2_LANCE_FLOW: 1,
    TAG_CARBON_INJ_RATE: 2,
}


@dataclass
class GeneratorConfig:
    """생성 파라미터 일체. 함수 본문에 수치를 흩어 두지 않는다."""

    # 규모/재현성
    n_heats: int = 500
    seed: int = 42
    start_date: datetime = datetime(2026, 8, 1, 6, 0)
    sample_period_s: float = 1.0

    # heat 번호 (일의 자리 0, 10씩 증가)
    heat_no_min: int = 100010
    heat_no_max: int = 899990
    heat_no_step: int = 10

    # 조업 시간
    pot_min_range: tuple[float, float] = (33.0, 40.0)       # power-on time 목표 범위
    pot_hard_min_range: tuple[float, float] = (31.0, 42.0)  # 이상치 heat 허용 한계
    idle_min_range: tuple[float, float] = (10.0, 20.0)      # power_off → 다음 power_on
    max_profile_attempts: int = 200

    # 전력 프로필
    meltdown_frac_range: tuple[float, float] = (0.70, 0.75)
    p_melt_mw_range: tuple[float, float] = (100.0, 110.0)
    p_ref_mw_range: tuple[float, float] = (90.0, 95.0)
    ramp_step1_mw: float = 2.0
    ramp_step1_s_range: tuple[float, float] = (30.0, 60.0)
    ramp_step2_mw_range: tuple[float, float] = (20.0, 40.0)
    ramp_step3_mw_range: tuple[float, float] = (60.0, 80.0)
    ramp_step_s_range: tuple[float, float] = (45.0, 90.0)
    ramp_3step_prob: float = 0.5
    power_max_mw: float = 118.0
    collapse_count_range: tuple[int, int] = (2, 5)          # 붕락(스크랩 무너짐) 이벤트 수
    collapse_dur_s_range: tuple[float, float] = (10.0, 30.0)
    collapse_drop_mw_range: tuple[float, float] = (15.0, 40.0)

    # 산소 랜싱
    o2_start_range: tuple[float, float] = (4000.0, 6000.0)
    o2_trigger_kwh_per_t_range: tuple[float, float] = (90.0, 110.0)  # 붕락 트리거
    o2_mid_level: float = 8000.0
    o2_mid_prob: float = 0.5
    o2_mid_dur_s_range: tuple[float, float] = (30.0, 90.0)
    o2_collapse_level: float = 10000.0
    o2_meltdown_level: float = 12800.0
    o2_refine_end_frac_range: tuple[float, float] = (0.90, 0.94)
    o2_rel_sigma: float = 0.02

    # 분탄 인젝션
    carbon_rate_kg_min: float = 40.0
    carbon_sigma: float = 1.5
    carbon_delay_s_range: tuple[float, float] = (30.0, 120.0)   # 용락 후 개시 지연
    carbon_pause_prob: float = 0.05
    carbon_pause_s_range: tuple[float, float] = (30.0, 90.0)

    # 장입/출강
    hot_heel_t_range: tuple[float, float] = (30.0, 40.0)
    tap_weight_target_t: float = 150.5        # 목표 출강량(heat size)
    yield_range: tuple[float, float] = (0.90, 0.955)       # 수율 평균 밴드
    yield_hard_range: tuple[float, float] = (0.88, 0.965)  # 수율 물리 한계(이상치 포함)
    yield_sd: float = 0.007
    tap_weight_resample: int = 50

    # 스케줄
    tap_start_delay_min_range: tuple[float, float] = (1.0, 3.0)
    tap_dur_min_range: tuple[float, float] = (3.0, 6.0)
    gap_min_range: tuple[float, float] = (2.0, 12.0)
    pause_every_heats_range: tuple[int, int] = (10, 20)        # 15±5 heat마다
    pause_min_range: tuple[float, float] = (30.0, 90.0)        # 정비/지연 휴지

    # 부원료
    lime_trigger_kwh_per_t_range: tuple[float, float] = (135.0, 165.0)
    lime_charge_kg: float = 1500.0
    lump_carbon_kg: float = 800.0
    lime_meltdown_kg: float = 1000.0
    lime_meltdown_delay_s_range: tuple[float, float] = (30.0, 120.0)
    addition_noise: float = 0.10
    addition_anomaly_p: float = 0.025
    addition_anomaly_dev_range: tuple[float, float] = (0.15, 0.25)
    lump_delay_s_range: tuple[float, float] = (0.0, 30.0)


@dataclass(frozen=True)
class _PowerProfile:
    """전력 계획 프로필 (POT 역산 대상)."""
    ramp: tuple[tuple[float, float], ...]   # (MW, 지속 s)
    p_melt_mw: float
    p_ref_mw: float
    meltdown_frac: float

    @property
    def ramp_s(self) -> float:
        return sum(d for _, d in self.ramp)

    @property
    def ramp_kwh(self) -> float:
        return sum(mw * d for mw, d in self.ramp) / 3.6


@dataclass
class _HeatPlan:
    """heat 단위 샘플링 결과(시계열 생성 입력)."""
    heat_id: str
    steel_group: str
    charge_total_t: float
    energy_kwh_per_t: float
    e_total_kwh: float
    profile: _PowerProfile
    collapses: tuple[tuple[float, float], ...]   # (전력 급락 폭 MW, 지속 s)
    pot_min_est: float


@dataclass
class _HeatTrace:
    """생성된 1초 시계열과 파생 이벤트 인덱스."""
    power: np.ndarray          # active_power (MW), 반올림 완료
    cum_kwh: np.ndarray        # 누적 전력량 (kWh)
    i_meltdown: int            # 용락 샘플 인덱스
    phases: dict[HeatPhase, tuple[int, int]]   # 페이즈 → [시작, 끝) 샘플 인덱스

    def span(self, phase: HeatPhase) -> tuple[int, int]:
        return self.phases[phase]


class DummyHeatGenerator:
    """페이즈 기반 EAF 더미데이터 생성기.

    생성 순서: heat 샘플링 → POT 역산 → 1초 시계열(전력→산소→분탄) →
    부원료 이벤트 → 시계열 적분에서 KPI 파생 → parquet 저장.
    """

    def __init__(
        self,
        config: GeneratorConfig,
        out_dir: Path,
        on_progress: Callable[[str], None] | None = None,
    ):
        self._config = config
        self._out_dir = Path(out_dir)
        self._rng = np.random.default_rng(config.seed)
        self._log = on_progress or (lambda _msg: None)

    # -- 공개 API ----------------------------------------------------------

    def generate(self) -> dict[str, object]:
        cfg = self._config
        builders = self._series_builders()
        assert set(builders) == set(TAG_REGISTRY.ids(dev_only=True)), (
            "생성 프로필과 TAG_REGISTRY dev 프로필이 불일치 — tags.py 선언을 먼저 맞출 것"
        )
        started = time.perf_counter()
        ts_dir = self._out_dir / "timeseries"
        ts_dir.mkdir(parents=True, exist_ok=True)

        heat_rows: list[dict] = []
        addition_rows: list[dict] = []
        power_on = cfg.start_date
        heat_no = int(self._rng.integers(
            cfg.heat_no_min // cfg.heat_no_step,
            cfg.heat_no_max // cfg.heat_no_step,
            endpoint=True,
        )) * cfg.heat_no_step
        heats_to_pause = self._draw_pause_interval()
        log_every = max(1, cfg.n_heats // 10)

        for i in range(cfg.n_heats):
            heat_id = f"A{heat_no + i * cfg.heat_no_step:06d}"
            plan = self._sample_plan(heat_id)
            trace = self._simulate_power(plan)
            series = {tag: builder(plan, trace) for tag, builder in builders.items()}
            series = {tag: np.round(v, TAG_DECIMALS[tag]) for tag, v in series.items()}

            n = len(trace.power)
            ts_index = pd.date_range(
                power_on, periods=n, freq=pd.Timedelta(seconds=cfg.sample_period_s)
            ).astype(DATETIME_DTYPE)
            additions = self._build_additions(plan, trace, ts_index)
            addition_rows.extend({"heat_id": heat_id, **a} for a in additions)
            self._write_timeseries(ts_dir / f"{heat_id}.parquet", ts_index, series)

            schedule = self._draw_schedule(power_on, ts_index[-1].to_pydatetime())
            heat_rows.append(
                self._build_heat_row(plan, trace, series, additions, schedule)
            )
            power_on = schedule["next_power_on"]

            heats_to_pause -= 1
            if heats_to_pause <= 0:   # 정비/지연에 의한 추가 휴지
                pause_min = self._rng.uniform(*cfg.pause_min_range)
                power_on += timedelta(seconds=round(pause_min * 60))
                heats_to_pause = self._draw_pause_interval()

            if (i + 1) % log_every == 0:
                self._log(f"  진행 {i + 1}/{cfg.n_heats} heat ({100 * (i + 1) // cfg.n_heats}%)")

        heats_df = pd.DataFrame(heat_rows, columns=list(HEAT_COLUMNS))
        heats_df[list(HEAT_DATETIME_COLUMNS)] = heats_df[
            list(HEAT_DATETIME_COLUMNS)
        ].astype(DATETIME_DTYPE)
        heats_df.to_parquet(self._out_dir / "heats.parquet", index=False)
        additions_df = pd.DataFrame(addition_rows, columns=list(ADDITION_COLUMNS))
        additions_df["ts"] = additions_df["ts"].astype(DATETIME_DTYPE)
        additions_df.to_parquet(self._out_dir / "additions.parquet", index=False)

        return {
            "heats": len(heats_df),
            "timeseries_files": cfg.n_heats,
            "addition_rows": len(additions_df),
            "elapsed_s": round(time.perf_counter() - started, 1),
            "period": (heats_df["date"].min(), heats_df["date"].max()),
        }

    # -- 태그별 시계열 빌더 매핑 -------------------------------------------

    def _series_builders(
        self,
    ) -> dict[str, Callable[[_HeatPlan, _HeatTrace], np.ndarray]]:
        """태그 id → 시계열 생성기. 키 집합 == TAG_REGISTRY dev 프로필."""
        return {
            TAG_ACTIVE_POWER: lambda _plan, trace: trace.power,
            TAG_O2_LANCE_FLOW: self._build_o2,
            TAG_CARBON_INJ_RATE: self._build_carbon,
        }

    # -- heat 샘플링 / POT 역산 --------------------------------------------

    def _sample_plan(self, heat_id: str) -> _HeatPlan:
        cfg, rng = self._config, self._rng
        group = str(rng.choice(
            list(GROUP_PARAMS), p=[g.share for g in GROUP_PARAMS.values()]
        ))
        params = GROUP_PARAMS[group]
        charge_t = self._sample_banded((CHARGE_BAND.lo, CHARGE_BAND.hi), CHARGE_BAND)
        energy_per_t = self._sample_banded(params.energy_kwh_per_t, ENERGY_BAND)
        e_total = charge_t * energy_per_t

        collapses = tuple(
            (rng.uniform(*cfg.collapse_drop_mw_range), rng.uniform(*cfg.collapse_dur_s_range))
            for _ in range(int(rng.integers(*cfg.collapse_count_range, endpoint=True)))
        )
        collapse_kwh = sum(mw * s for mw, s in collapses) / 3.6

        profile, pot_min = self._solve_profile(e_total, collapse_kwh)
        hard_lo, hard_hi = cfg.pot_hard_min_range
        if not hard_lo <= pot_min <= hard_hi:
            # 이상치(원단위·장입량 동시 극단)에서만 도달 — 한계 안으로 에너지를 되맞춘다
            bound = hard_lo + 0.5 if pot_min < hard_lo else hard_hi - 0.5
            e_total = self._energy_for_pot(profile, bound, collapse_kwh)
            energy_per_t = float(np.clip(e_total / charge_t, ENERGY_BAND.lo_out, ENERGY_BAND.hi_out))
            e_total = charge_t * energy_per_t
            pot_min = self._pot_minutes(profile, e_total, collapse_kwh)

        return _HeatPlan(
            heat_id=heat_id,
            steel_group=group,
            charge_total_t=charge_t,
            energy_kwh_per_t=energy_per_t,
            e_total_kwh=e_total,
            profile=profile,
            collapses=collapses,
            pot_min_est=pot_min,
        )

    def _draw_profile(self) -> _PowerProfile:
        cfg, rng = self._config, self._rng
        ramp: list[tuple[float, float]] = [
            (cfg.ramp_step1_mw, rng.uniform(*cfg.ramp_step1_s_range)),          # 천공(short arc)
            (rng.uniform(*cfg.ramp_step2_mw_range), rng.uniform(*cfg.ramp_step_s_range)),
        ]
        if rng.random() < cfg.ramp_3step_prob:
            ramp.append(
                (rng.uniform(*cfg.ramp_step3_mw_range), rng.uniform(*cfg.ramp_step_s_range))
            )
        return _PowerProfile(
            ramp=tuple(ramp),
            p_melt_mw=rng.uniform(*cfg.p_melt_mw_range),
            p_ref_mw=rng.uniform(*cfg.p_ref_mw_range),
            meltdown_frac=rng.uniform(*cfg.meltdown_frac_range),
        )

    @staticmethod
    def _pot_minutes(profile: _PowerProfile, e_total: float, collapse_kwh: float) -> float:
        """POT 역산: 램프 + 용해기 평탄부 + 정련기 평탄부 (붕락 급락분 포함)."""
        f = profile.meltdown_frac
        melt_min = (
            (f * e_total - profile.ramp_kwh + collapse_kwh) / (profile.p_melt_mw * 1000) * 60
        )
        ref_min = (1 - f) * e_total / (profile.p_ref_mw * 1000) * 60
        return profile.ramp_s / 60 + melt_min + ref_min

    @staticmethod
    def _energy_for_pot(profile: _PowerProfile, pot_min: float, collapse_kwh: float) -> float:
        """POT는 E에 대해 1차식이므로 목표 POT를 만드는 E를 직접 푼다."""
        f = profile.meltdown_frac
        const = (
            profile.ramp_s / 60
            + (collapse_kwh - profile.ramp_kwh) / (profile.p_melt_mw * 1000) * 60
        )
        slope = 60 * (f / (profile.p_melt_mw * 1000) + (1 - f) / (profile.p_ref_mw * 1000))
        return (pot_min - const) / slope

    def _solve_profile(
        self, e_total: float, collapse_kwh: float
    ) -> tuple[_PowerProfile, float]:
        lo, hi = self._config.pot_min_range
        best: tuple[float, _PowerProfile, float] | None = None
        for _ in range(self._config.max_profile_attempts):
            profile = self._draw_profile()
            pot = self._pot_minutes(profile, e_total, collapse_kwh)
            if lo <= pot <= hi:
                return profile, pot
            distance = min(abs(pot - lo), abs(pot - hi))
            if best is None or distance < best[0]:
                best = (distance, profile, pot)
        assert best is not None
        return best[1], best[2]

    # -- 시계열 ------------------------------------------------------------

    def _simulate_power(self, plan: _HeatPlan) -> _HeatTrace:
        """유효전력 시계열. cumE가 f·E / E에 도달하는 시점이 용락 / power_off."""
        cfg, rng = self._config, self._rng
        dt = cfg.sample_period_s
        profile = plan.profile
        f = profile.meltdown_frac

        # --- 용락 전 (BORE_IN + EXPANSION): 램프 → 용해기 평탄부 + 붕락 급락 ---
        pre_s = (
            profile.ramp_s
            + (f * plan.e_total_kwh - profile.ramp_kwh + sum(mw * s for mw, s in plan.collapses) / 3.6)
            / (profile.p_melt_mw * 1000) * 3600
        )
        n_pre = int(pre_s / dt) + int(600 / dt)
        base = np.full(n_pre, profile.p_melt_mw)
        cursor = 0
        bore_in_end = 0
        for idx, (mw, dur_s) in enumerate(profile.ramp):
            end = min(cursor + int(round(dur_s / dt)), n_pre)
            base[cursor:end] = mw
            if idx == 0:
                bore_in_end = end          # 1단(저전력 천공) 구간 = BORE_IN
            cursor = end
        self._apply_collapses(base, plan, cursor, int(pre_s / dt))

        sigma_pre = rng.uniform(*POWER_SIGMA_MW[HeatPhase.EXPANSION])
        # 저전력 램프 구간은 절대 편차가 작으므로 계획 전력 수준에 따라 σ를 축소한다
        sigma_arr = sigma_pre * np.sqrt(np.clip(base, 0.0, None) / profile.p_melt_mw)
        power_pre = np.clip(
            base + rng.normal(0.0, 1.0, n_pre) * sigma_arr, 0.0, cfg.power_max_mw
        )
        cum_pre = np.cumsum(power_pre) * dt / 3.6
        i_meltdown = int(np.searchsorted(cum_pre, f * plan.e_total_kwh))
        i_meltdown = min(i_meltdown, n_pre - 1)

        # --- 용락 후 (MELTDOWN + REFINING): 정련기 평탄부, 아크 안정 ---
        rest_kwh = plan.e_total_kwh - cum_pre[i_meltdown]
        n_post = int(rest_kwh * 3.6 / profile.p_ref_mw / dt * 1.3) + int(600 / dt)
        sigma_post = rng.uniform(*POWER_SIGMA_MW[HeatPhase.REFINING])
        power_post = np.clip(
            profile.p_ref_mw + rng.normal(0.0, sigma_post, n_post), 0.0, cfg.power_max_mw
        )
        cum_post = cum_pre[i_meltdown] + np.cumsum(power_post) * dt / 3.6
        i_off_rel = int(np.searchsorted(cum_post, plan.e_total_kwh))
        i_off_rel = min(i_off_rel, n_post - 1)

        power = np.round(
            np.concatenate([power_pre[: i_meltdown + 1], power_post[: i_off_rel + 1]]),
            TAG_DECIMALS[TAG_ACTIVE_POWER],
        )
        cum = np.cumsum(power) * dt / 3.6      # 저장값 기준으로 재적산 (정적 데이터와 정합)
        n = len(power)
        i_carbon = min(
            i_meltdown + int(round(rng.uniform(*cfg.carbon_delay_s_range) / dt)), n
        )
        phases = {
            HeatPhase.BORE_IN: (0, bore_in_end),
            HeatPhase.EXPANSION: (bore_in_end, i_meltdown),
            HeatPhase.MELTDOWN: (i_meltdown, i_carbon),
            HeatPhase.REFINING: (i_carbon, n),
        }
        return _HeatTrace(power=power, cum_kwh=cum, i_meltdown=i_meltdown, phases=phases)

    def _apply_collapses(
        self, base: np.ndarray, plan: _HeatPlan, plateau_start: int, plateau_end: int
    ) -> None:
        """스크랩 붕락에 의한 전력 급락(아크 불안정)을 용해기 평탄부에 배치한다."""
        dt = self._config.sample_period_s
        margin = int(30 / dt)
        window = plateau_end - plateau_start - 2 * margin
        if window <= 0 or not plan.collapses:
            return
        slot = window // len(plan.collapses)
        for k, (drop_mw, dur_s) in enumerate(plan.collapses):
            dur = max(1, int(round(dur_s / dt)))
            slot_start = plateau_start + margin + k * slot
            offset = int(self._rng.integers(0, max(1, slot - dur)))
            start = slot_start + offset
            base[start : start + dur] -= drop_mw

    def _build_o2(self, plan: _HeatPlan, trace: _HeatTrace) -> np.ndarray:
        """산소 랜싱 유량: 초기 → 붕락(1~2단 상향) → 용락 → 정련 말기(그룹 연동)."""
        cfg, rng = self._config, self._rng
        dt = cfg.sample_period_s
        n = len(trace.power)
        levels = np.full(n, rng.uniform(*cfg.o2_start_range))

        trigger_kwh = rng.uniform(*cfg.o2_trigger_kwh_per_t_range) * plan.charge_total_t
        i_trigger = int(np.searchsorted(trace.cum_kwh, trigger_kwh))
        if rng.random() < cfg.o2_mid_prob:      # 중간단 경유 2단 상향
            mid_end = min(i_trigger + int(round(rng.uniform(*cfg.o2_mid_dur_s_range) / dt)), n)
            levels[i_trigger:mid_end] = cfg.o2_mid_level
            levels[mid_end:] = cfg.o2_collapse_level
        else:
            levels[i_trigger:] = cfg.o2_collapse_level

        levels[trace.i_meltdown :] = cfg.o2_meltdown_level
        i_refine_end = int(np.searchsorted(
            trace.cum_kwh, rng.uniform(*cfg.o2_refine_end_frac_range) * plan.e_total_kwh
        ))
        levels[i_refine_end:] = rng.uniform(*GROUP_PARAMS[plan.steel_group].o2_refine_end)
        return np.maximum(levels * (1 + rng.normal(0.0, cfg.o2_rel_sigma, n)), 0.0)

    def _build_carbon(self, _plan: _HeatPlan, trace: _HeatTrace) -> np.ndarray:
        """분탄 인젝션: 용락 후 개시(슬래그 포밍), 드물게 설비 문제로 중단."""
        cfg, rng = self._config, self._rng
        dt = cfg.sample_period_s
        n = len(trace.power)
        values = np.zeros(n)
        start, end = trace.span(HeatPhase.REFINING)   # 정련 페이즈 = 분탄 인젝션 구간
        length = end - start
        if length <= 0:
            return values
        values[start:end] = cfg.carbon_rate_kg_min + rng.normal(0.0, cfg.carbon_sigma, length)
        if rng.random() < cfg.carbon_pause_prob:
            dur = int(round(rng.uniform(*cfg.carbon_pause_s_range) / dt))
            if length > dur + 2 * int(10 / dt):
                pause_at = start + int(rng.integers(int(10 / dt), length - dur))
                values[pause_at : pause_at + dur] = 0.0
        return np.maximum(values, 0.0)

    # -- 부원료 ------------------------------------------------------------

    def _build_additions(
        self, plan: _HeatPlan, trace: _HeatTrace, ts_index: pd.DatetimeIndex
    ) -> list[dict]:
        cfg, rng = self._config, self._rng
        dt = cfg.sample_period_s
        n = len(ts_index)
        rows: list[dict] = []

        # 예외 heat(2~3%): 이벤트② 누락 또는 투입량 ±25% 수준 이탈
        anomaly = rng.random() < cfg.addition_anomaly_p
        skip_meltdown_add = anomaly and rng.random() < 0.5
        deviate = anomaly and not skip_meltdown_add

        def amount(base_kg: float) -> float:
            if deviate:   # 통상 노이즈 밖으로 이탈
                dev = rng.uniform(*cfg.addition_anomaly_dev_range)
                factor = 1 + (dev if rng.random() < 0.5 else -dev)
            else:
                factor = 1 + rng.uniform(-cfg.addition_noise, cfg.addition_noise)
            return round(base_kg * factor, 1)

        # ① 장입 초기 조재제(생석회) + 괴탄 투입
        i_charge = min(int(np.searchsorted(
            trace.cum_kwh,
            rng.uniform(*cfg.lime_trigger_kwh_per_t_range) * plan.charge_total_t,
        )), n - 1)
        rows.append({
            "ts": ts_index[i_charge].to_pydatetime(),
            "material": LIME,
            "amount_kg": amount(cfg.lime_charge_kg),
        })
        i_lump = min(i_charge + int(round(rng.uniform(*cfg.lump_delay_s_range) / dt)), n - 1)
        rows.append({
            "ts": ts_index[i_lump].to_pydatetime(),
            "material": LUMP_CARBON,
            "amount_kg": amount(cfg.lump_carbon_kg),
        })
        # ② 용락 직후 추가 조재
        if not skip_meltdown_add:
            i_melt_add = min(
                trace.i_meltdown
                + int(round(rng.uniform(*cfg.lime_meltdown_delay_s_range) / dt)),
                n - 1,
            )
            rows.append({
                "ts": ts_index[i_melt_add].to_pydatetime(),
                "material": LIME,
                "amount_kg": amount(cfg.lime_meltdown_kg),
            })
        return rows

    # -- 스케줄 / 정적 데이터 ----------------------------------------------

    def _draw_pause_interval(self) -> int:
        return int(self._rng.integers(*self._config.pause_every_heats_range, endpoint=True))

    def _draw_schedule(self, power_on: datetime, power_off: datetime) -> dict:
        """출강 시각과 다음 heat 송전 시각. 유휴합은 idle_min_range로 클립."""
        cfg, rng = self._config, self._rng
        delay_s = round(rng.uniform(*cfg.tap_start_delay_min_range) * 60)
        tap_s = round(rng.uniform(*cfg.tap_dur_min_range) * 60)
        idle_lo, idle_hi = (round(v * 60) for v in cfg.idle_min_range)
        gap_lo, gap_hi = (round(v * 60) for v in cfg.gap_min_range)
        # 유휴합(=출강 지연 + 출강 + 대기)이 idle_min_range 안에 들도록 대기시간을 클립
        gap_s = int(np.clip(
            round(rng.uniform(gap_lo, gap_hi)),
            max(gap_lo, idle_lo - delay_s - tap_s),
            min(gap_hi, idle_hi - delay_s - tap_s),
        ))
        tap_start = power_off + timedelta(seconds=delay_s)
        tap_end = tap_start + timedelta(seconds=tap_s)
        return {
            "power_on": power_on,
            "power_off": power_off,
            "tap_start": tap_start,
            "tap_end": tap_end,
            "next_power_on": tap_end + timedelta(seconds=gap_s),
            "idle_min": (delay_s + tap_s + gap_s) / 60,
        }

    def _build_heat_row(
        self,
        plan: _HeatPlan,
        trace: _HeatTrace,
        series: dict[str, np.ndarray],
        additions: list[dict],
        schedule: dict,
    ) -> dict:
        cfg = self._config
        dt = cfg.sample_period_s
        params = GROUP_PARAMS[plan.steel_group]
        charge_t = plan.charge_total_t
        n = len(trace.power)
        add_totals = {
            code: sum(a["amount_kg"] for a in additions if a["material"] == code)
            for code in ADDITION_MATERIALS
        }
        scrap_t = self._sample_scrap_mix(params, charge_t)
        tap_weight_t = round(self._sample_tap_weight(charge_t), 2)
        return {
            "heat_id": plan.heat_id,
            "date": schedule["power_on"],
            "shift": self._shift_of(schedule["power_on"]),
            "steel_group": plan.steel_group,
            "ev_power_on": schedule["power_on"],
            "ev_meltdown": schedule["power_on"] + timedelta(seconds=trace.i_meltdown * dt),
            "ev_tap_start": schedule["tap_start"],
            "ev_tap_end": schedule["tap_end"],
            "charge_total_t": round(charge_t, 2),
            "charge_hot_heel_t": round(self._rng.uniform(*cfg.hot_heel_t_range), 2),
            **{f"charge_scrap_{code}_t": round(v, 2) for code, v in scrap_t.items()},
            "kpi_energy_kwh_per_t": round(trace.cum_kwh[-1] / charge_t, 2),
            "kpi_o2_nm3_per_t": round(
                series[TAG_O2_LANCE_FLOW].sum() * dt / 3600 / charge_t, 2
            ),
            "kpi_carbon_kg_per_t": round(
                (series[TAG_CARBON_INJ_RATE].sum() * dt / 60 + add_totals[LUMP_CARBON])
                / charge_t, 2,
            ),
            "kpi_power_on_min": round((n - 1) * dt / 60, 2),
            "kpi_tap_to_tap_min": round((n - 1) * dt / 60 + schedule["idle_min"], 2),
            "kpi_tap_weight_t": tap_weight_t,
            "kpi_yield_pct": round(tap_weight_t / round(charge_t, 2) * 100, 2),
            "eop_tap_temp_c": round(
                self._sample_banded(params.eop_tap_temp_c, TAP_TEMP_BAND), 1
            ),
            "eop_comp_c": round(self._sample_banded(params.eop_comp_c, COMP_C_BAND), 4),
            "eop_comp_p": round(self._sample_banded(params.eop_comp_p, COMP_P_BAND), 4),
            **{f"slag_add_{code}_kg": round(v, 1) for code, v in add_totals.items()},
        }

    def _sample_scrap_mix(self, params: GroupParams, charge_t: float) -> dict[str, float]:
        """단일 바스켓 스크랩 배합 (등급 코드는 SCRAP_GRADES 선언 기준)."""
        rng = self._rng
        grade_a = rng.normal(*params.scrap_grade_a)
        shredder = rng.normal(*params.scrap_shredder)
        balance = max(1e-3, 1.0 - grade_a - shredder)
        turnings_share = float(np.clip(rng.normal(*params.turnings_of_balance), 0.0, 1.0))
        ratios = {
            GRADE_A: max(grade_a, 0.0),
            SHREDDER: max(shredder, 0.0),
            TURNINGS: balance * turnings_share,
            COMMON: balance * (1.0 - turnings_share),
        }
        total = sum(ratios.values())
        return {code: v / total * charge_t for code, v in ratios.items()}

    def _sample_tap_weight(self, charge_t: float) -> float:
        """출강량. 목표 heat size를 수율 물리 한계로 제한한 뒤 밴드 내로 재샘플."""
        cfg, rng = self._config, self._rng
        hard_lo, hard_hi = (charge_t * y for y in cfg.yield_hard_range)   # 수율 물리 한계
        if rng.random() < TAP_WEIGHT_BAND.p:      # 이상치 heat
            weight = (
                rng.uniform(TAP_WEIGHT_BAND.lo_out, TAP_WEIGHT_BAND.lo)
                if rng.random() < 0.5
                else rng.uniform(TAP_WEIGHT_BAND.hi, TAP_WEIGHT_BAND.hi_out)
            )
            return float(np.clip(weight, hard_lo, hard_hi))
        yield_lo, yield_hi = cfg.yield_range
        mean_yield = float(np.clip(cfg.tap_weight_target_t / charge_t, yield_lo, yield_hi))
        for _ in range(cfg.tap_weight_resample):
            weight = charge_t * rng.normal(mean_yield, cfg.yield_sd)
            if TAP_WEIGHT_BAND.lo <= weight <= TAP_WEIGHT_BAND.hi:
                return weight
        return float(np.clip(charge_t * mean_yield, TAP_WEIGHT_BAND.lo, TAP_WEIGHT_BAND.hi))

    def _sample_banded(
        self, normal_range: tuple[float, float], band: OutlierBand
    ) -> float:
        """정상 범위에서 샘플링하되 확률 p로 밴드 밖 이상치를 뽑는다."""
        rng = self._rng
        if rng.random() < band.p:
            return (
                rng.uniform(band.lo_out, band.lo)
                if rng.random() < 0.5
                else rng.uniform(band.hi, band.hi_out)
            )
        return rng.uniform(*normal_range)

    @staticmethod
    def _shift_of(moment: datetime) -> str:
        for start, end, code in SHIFTS:
            if start <= moment.hour < end:
                return code
        return SHIFT_NIGHT

    # -- 저장 --------------------------------------------------------------

    @staticmethod
    def _write_timeseries(
        path: Path, ts_index: pd.DatetimeIndex, series: dict[str, np.ndarray]
    ) -> None:
        n = len(ts_index)
        pd.DataFrame({
            "ts": np.tile(ts_index.values, len(series)),
            "tag": np.repeat(list(series), n),
            "value": np.concatenate(list(series.values())).astype("float64"),
        }).to_parquet(path, index=False)


# --- CLI ---------------------------------------------------------------------


def main() -> None:
    from app.config import get_settings   # 설정 의존은 진입점에서만

    defaults = GeneratorConfig()
    parser = argparse.ArgumentParser(description="EAF 더미데이터 생성 (parquet)")
    parser.add_argument("--n-heats", type=int, default=defaults.n_heats)
    parser.add_argument("--seed", type=int, default=defaults.seed)
    parser.add_argument("--out-dir", type=Path, default=get_settings().data_dir)
    args = parser.parse_args()

    config = GeneratorConfig(n_heats=args.n_heats, seed=args.seed)
    print(f"[더미데이터] {args.n_heats} heat 생성 시작 (seed={args.seed}) → {args.out_dir}")
    summary = DummyHeatGenerator(config, args.out_dir, on_progress=print).generate()
    start, end = summary["period"]
    print(
        f"[완료] heat {summary['heats']}건 / 시계열 파일 {summary['timeseries_files']}개 / "
        f"부원료 {summary['addition_rows']}행 / 기간 {start:%Y-%m-%d %H:%M}~{end:%Y-%m-%d %H:%M} / "
        f"소요 {summary['elapsed_s']}s"
    )


if __name__ == "__main__":
    main()
