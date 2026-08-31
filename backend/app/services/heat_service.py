"""heat 조회 서비스. 라우트와 repository 사이의 오케스트레이션 지점.

현재는 얇은 위임이지만, 파생 지표 계산·페이즈 경계 산출·캐싱은 이 계층에 둔다.
"""
from datetime import datetime

from app.data.repository import HeatRepository
from app.domain.models import AdditionEvent, Heat, HeatSummary, HeatTimeseries


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

    def get_kpi_summary(self, period: str) -> dict:
        """일/주/월 KPI 요약 카드. 더미데이터 생성 후 집계 로직 구현."""
        # TODO: get_kpi_trend 결과를 period 단위로 집계 (평균 원단위, 생산량 합 등)
        return {"period": period, "cards": []}
