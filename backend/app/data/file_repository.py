"""parquet/csv 파일 기반 구현 (더미데이터 단계).

저장 레이아웃 (SPEC.md §4.4):
  {data_dir}/heats.parquet                  — 정적 데이터 (heat당 1행, 그룹별 컬럼 prefix)
  {data_dir}/timeseries/{heat_id}.parquet   — long format: ts, tag, value
  {data_dir}/additions.parquet              — 부원료 투입 이벤트(전 heat 통합): heat_id, ts, material, amount_kg
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.data.repository import HeatNotFoundError, HeatRepository
from app.domain.materials import ADDITION_MATERIALS, SCRAP_GRADES
from app.domain.models import (
    AdditionEvent,
    Heat,
    HeatSummary,
    HeatTimeseries,
    TimeseriesPoint,
    TimeseriesSeries,
)
from app.domain.tags import TAG_REGISTRY

# charge_scrap_{code}_t 컬럼 규약 (등급 코드는 domain/materials.SCRAP_GRADES가 유일 선언 지점)
_SCRAP_COL_PREFIX = "charge_scrap_"
_SCRAP_COL_SUFFIX = "_t"


class ParquetHeatRepository(HeatRepository):
    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)
        self._heats_path = self._data_dir / "heats.parquet"
        self._ts_dir = self._data_dir / "timeseries"
        self._additions_path = self._data_dir / "additions.parquet"

    # -- 내부 --------------------------------------------------------------

    def _load_heats_df(self) -> pd.DataFrame:
        if not self._heats_path.exists():
            # 더미데이터 미생성 상태에서도 앱은 기동되어야 함 (빈 대시보드)
            return pd.DataFrame()
        return pd.read_parquet(self._heats_path)

    # -- HeatRepository ----------------------------------------------------

    def list_heats(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[HeatSummary]:
        df = self._load_heats_df()
        if df.empty:
            return []
        if start is not None:
            df = df[df["date"] >= start]
        if end is not None:
            df = df[df["date"] <= end]
        df = df.sort_values("date", ascending=False).head(limit)
        return [self._row_to_summary(row) for _, row in df.iterrows()]

    def get_heat(self, heat_id: str) -> Heat:
        df = self._load_heats_df()
        if df.empty or heat_id not in set(df["heat_id"]):
            raise HeatNotFoundError(heat_id)
        row = df[df["heat_id"] == heat_id].iloc[0]
        return self._row_to_heat(row)

    def get_timeseries(
        self,
        heat_id: str,
        tag_ids: list[str] | None = None,
        downsample_s: float | None = None,
    ) -> HeatTimeseries:
        path = self._ts_dir / f"{heat_id}.parquet"
        if not path.exists():
            raise HeatNotFoundError(heat_id)
        df = pd.read_parquet(path)
        tag_ids = tag_ids or TAG_REGISTRY.ids()
        series: list[TimeseriesSeries] = []
        for tag_id in tag_ids:
            sub = df[df["tag"] == tag_id][["ts", "value"]]
            if downsample_s:
                sub = (
                    sub.set_index("ts")
                    .resample(f"{downsample_s}s")
                    .mean()
                    .dropna()
                    .reset_index()
                )
            series.append(
                TimeseriesSeries(
                    tag_id=tag_id,
                    unit=TAG_REGISTRY.get(tag_id).unit,
                    points=[
                        TimeseriesPoint(ts=r.ts, value=float(r.value))
                        for r in sub.itertuples()
                    ],
                )
            )
        return HeatTimeseries(heat_id=heat_id, series=series, downsample_s=downsample_s)

    def get_kpi_trend(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        kpis: list[str] | None = None,
    ) -> list[dict]:
        df = self._load_heats_df()
        if df.empty:
            return []
        if start is not None:
            df = df[df["date"] >= start]
        if end is not None:
            df = df[df["date"] <= end]
        cols = ["heat_id", "date"] + [
            c for c in df.columns if c.startswith("kpi_") and (not kpis or c in kpis)
        ]
        return df[cols].sort_values("date").to_dict(orient="records")

    def get_additions(self, heat_id: str) -> list[AdditionEvent]:
        if not self._additions_path.exists():
            # 부원료 파일은 선택 사항 — 없으면 빈 목록 (heat 자체는 유효)
            return []
        df = pd.read_parquet(self._additions_path)
        if df.empty:
            return []
        df = df[df["heat_id"] == heat_id].sort_values("ts")
        return [
            AdditionEvent(
                ts=r.ts,
                material=str(r.material),
                label_ko=ADDITION_MATERIALS.get(str(r.material), ""),
                amount_kg=float(r.amount_kg),
            )
            for r in df.itertuples()
        ]

    # -- 행 → 모델 변환 (heats.parquet 컬럼 규약: 그룹별 prefix) -------------
    # summary: heat_id, date, shift, ev_power_on, ev_meltdown, ev_tap_start, ev_tap_end
    # kpi_*: kpi_energy_kwh_per_t, ... / eop_*: eop_tap_temp_c, eop_c_pct, ...
    # charge_*, slag_*: 동일 규약. 더미 생성기(generator.py)가 이 규약으로 저장한다.

    @staticmethod
    def _text(row: pd.Series, col: str) -> str:
        """결측(NaN/None)을 빈 문자열로 정규화한 문자열 컬럼 조회."""
        value = row.get(col)
        return "" if value is None or pd.isna(value) else str(value)

    @classmethod
    def _row_to_summary(cls, row: pd.Series) -> HeatSummary:
        return HeatSummary(
            heat_id=row["heat_id"],
            date=row["date"],
            shift=cls._text(row, "shift"),
            steel_group=cls._text(row, "steel_group"),
            events={
                "power_on": row["ev_power_on"],
                "meltdown": row.get("ev_meltdown"),
                "tap_start": row.get("ev_tap_start"),
                "tap_end": row.get("ev_tap_end"),
            },
            tap_weight_t=row.get("kpi_tap_weight_t"),
            energy_kwh_per_t=row.get("kpi_energy_kwh_per_t"),
        )

    def _row_to_heat(self, row: pd.Series) -> Heat:
        def group(prefix: str) -> dict:
            return {
                k.removeprefix(prefix): v
                for k, v in row.items()
                if k.startswith(prefix) and pd.notna(v)
            }

        return Heat(
            summary=self._row_to_summary(row),
            kpi=group("kpi_"),
            eop={
                "tap_temp_c": row.get("eop_tap_temp_c"),
                "composition_pct": group("eop_comp_"),
            },
            slag={
                "composition_pct": group("slag_comp_"),
                "basicity": row.get("slag_basicity"),
                "additions_kg": group("slag_add_"),
            },
            charge={
                "baskets": self._baskets(row),
                "total_charge_t": row.get("charge_total_t", 0.0),
                "hot_heel_t": row.get("charge_hot_heel_t", 0.0),
            },
        )

    @staticmethod
    def _baskets(row: pd.Series) -> list[dict[str, float]]:
        """charge_scrap_{code}_t 컬럼 → 바스켓 목록.

        더미 단계는 단일 바스켓(장입 1회)이므로 등급별 장입량 1개 dict로 묶는다.
        복수 바스켓 데이터 소스 연결 시 이 메서드만 확장한다.
        """
        basket = {
            k.removeprefix(_SCRAP_COL_PREFIX).removesuffix(_SCRAP_COL_SUFFIX): float(v)
            for k, v in row.items()
            if k.startswith(_SCRAP_COL_PREFIX)
            and k.endswith(_SCRAP_COL_SUFFIX)
            and pd.notna(v)
        }
        # 미등록 등급 코드는 무시 (등급 체계 유일 선언 지점 = domain/materials)
        basket = {k: v for k, v in basket.items() if k in SCRAP_GRADES}
        return [basket] if basket else []
