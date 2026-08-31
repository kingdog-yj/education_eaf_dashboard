"""heat 조회 서비스. 라우트와 repository 사이의 오케스트레이션 지점.

파생 지표 계산·페이즈 경계 산출·집계는 이 계층에 둔다
(repository는 저장 포맷만, domain은 선언만 책임진다).
"""
from datetime import date as date_cls
from datetime import datetime, timedelta

from app.data.repository import HeatRepository
from app.domain import specs
from app.domain.models import (
    AdditionEvent,
    Heat,
    HeatSummary,
    HeatTimeseries,
    KpiSummaryCard,
    KpiSummaryResponse,
    PhaseInterval,
)
from app.domain.phases import BORE_IN_DURATION_S, MELTDOWN_SETTLE_S, HeatPhase


class HeatService:
    def __init__(self, repo: HeatRepository):
        self._repo = repo

    def list_heats(
        self,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[HeatSummary]:
        return self._repo.list_heats(start, end, limit)

    def get_heat(self, heat_id: str) -> Heat:
        return self._repo.get_heat(heat_id)

    def get_timeseries(
        self,
        heat_id: str,
        tag_ids: list[str] | None,
        downsample_s: float | None,
    ) -> HeatTimeseries:
        return self._repo.get_timeseries(heat_id, tag_ids, downsample_s)

    def get_additions(self, heat_id: str) -> list[AdditionEvent]:
        return self._repo.get_additions(heat_id)

    def get_kpi_trend(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> list[dict]:
        return self._repo.get_kpi_trend(start, end)

    # -- 페이즈 경계 산출 ---------------------------------------------------

    def get_phases(self, heat_id: str) -> list[PhaseInterval]:
        """이벤트 시각 + 휴리스틱 상수로 조업 페이즈 구간을 산출한다.

        산출 불가한 페이즈(근거 이벤트 결측, 길이 0 이하)는 생략한다.
        경계 규칙의 상수는 domain/phases.py가 유일 선언 지점.
        """
        heat = self._repo.get_heat(heat_id)   # HeatNotFoundError는 라우트로 전파
        ev = heat.summary.events

        power_on = ev.power_on
        meltdown = ev.meltdown
        power_off: datetime | None = None
        if power_on is not None and heat.kpi.power_on_min is not None:
            power_off = power_on + timedelta(minutes=float(heat.kpi.power_on_min))

        intervals: list[tuple[HeatPhase, datetime | None, datetime | None]] = []

        bore_in_end: datetime | None = None
        if power_on is not None:
            bore_in_end = power_on + timedelta(seconds=BORE_IN_DURATION_S)
            # 후속 이벤트를 넘지 않도록 절단
            for limit in (meltdown, power_off):
                if limit is not None and bore_in_end > limit:
                    bore_in_end = limit
            intervals.append((HeatPhase.BORE_IN, power_on, bore_in_end))

        if bore_in_end is not None and meltdown is not None:
            intervals.append((HeatPhase.EXPANSION, bore_in_end, meltdown))

        meltdown_end: datetime | None = None
        if meltdown is not None:
            meltdown_end = meltdown + timedelta(seconds=MELTDOWN_SETTLE_S)
            if power_off is not None and meltdown_end > power_off:
                meltdown_end = power_off
            intervals.append((HeatPhase.MELTDOWN, meltdown, meltdown_end))

        if meltdown_end is not None and power_off is not None:
            intervals.append((HeatPhase.REFINING, meltdown_end, power_off))

        if ev.tap_start is not None and ev.tap_end is not None:
            intervals.append((HeatPhase.TAPPING, ev.tap_start, ev.tap_end))

        result = [
            PhaseInterval(
                phase=phase.value, label_ko=phase.label_ko, start=start, end=end
            )
            for phase, start, end in intervals
            if start is not None and end is not None and end > start
        ]
        result.sort(key=lambda p: p.start)
        return result

    # -- KPI 요약 집계 ------------------------------------------------------

    def get_kpi_summary(self, period: str) -> KpiSummaryResponse:
        """일/주/월 KPI 요약 카드.

        버킷 기준은 '현재 시각'이 아니라 데이터의 최신 heat date다
        (더미데이터가 과거 고정이라 현재 시각 기준은 항상 빈 결과가 된다).
        """
        rows = self._repo.get_kpi_trend(None, None)
        dated = [(d, r) for r in rows if (d := _as_datetime(r.get("date"))) is not None]
        if not dated:
            return KpiSummaryResponse(period=period, cards=[])

        latest = max(d for d, _ in dated)
        bucket_start = _bucket_start(latest, period)
        bucket_end = _bucket_end(bucket_start, period)
        prev_start = _prev_bucket_start(bucket_start, period)

        current = [r for d, r in dated if bucket_start <= d < bucket_end]
        previous = [r for d, r in dated if prev_start <= d < bucket_start]

        cards = [
            KpiSummaryCard(
                id=card.id,
                label_ko=card.label_ko,
                unit=card.unit,
                decimals=card.decimals,
                value=_aggregate(card, current),
                prev_value=_aggregate(card, previous),
                spec_id=card.spec_id,
            )
            for card in specs.SUMMARY_CARDS
        ]
        return KpiSummaryResponse(
            period=period,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            prev_bucket_start=prev_start,
            cards=cards,
        )


# -- 집계/버킷 헬퍼 ---------------------------------------------------------


def _as_datetime(value: object) -> datetime | None:
    """행의 date 값을 naive datetime으로 정규화 (pandas Timestamp 포함)."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date_cls):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    to_pydatetime = getattr(value, "to_pydatetime", None)   # pandas Timestamp
    if callable(to_pydatetime):
        try:
            return _as_datetime(to_pydatetime())
        except Exception:
            return None
    return None


def _bucket_start(moment: datetime, period: str) -> datetime:
    day = datetime(moment.year, moment.month, moment.day)
    if period == "week":                       # ISO 주 = 월요일 시작
        return day - timedelta(days=day.weekday())
    if period == "month":
        return datetime(moment.year, moment.month, 1)
    return day


def _bucket_end(start: datetime, period: str) -> datetime:
    if period == "week":
        return start + timedelta(days=7)
    if period == "month":
        return (
            datetime(start.year + 1, 1, 1)
            if start.month == 12
            else datetime(start.year, start.month + 1, 1)
        )
    return start + timedelta(days=1)


def _prev_bucket_start(start: datetime, period: str) -> datetime:
    if period == "week":
        return start - timedelta(days=7)
    if period == "month":
        return (
            datetime(start.year - 1, 12, 1)
            if start.month == 1
            else datetime(start.year, start.month - 1, 1)
        )
    return start - timedelta(days=1)


def _numeric(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if f != f else f       # NaN 제외


def _aggregate(card: specs.SummaryCardDef, rows: list[dict]) -> float | None:
    """카드 선언의 agg 종류에 따른 집계. 빈 버킷·결측 컬럼은 None."""
    if not rows:
        return None
    if card.agg == "count":
        return float(len(rows))
    if card.agg == "out_of_spec_count":
        return float(sum(1 for r in rows if specs.is_out_of_spec(r)))
    if card.column is None:
        return None
    values = [v for r in rows if (v := _numeric(r.get(card.column))) is not None]
    if not values:
        return None
    if card.agg == "sum":
        return float(sum(values))
    if card.agg == "mean":
        return float(sum(values) / len(values))
    return None
