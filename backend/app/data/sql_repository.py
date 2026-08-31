"""사내 DB 연결 구현 (향후). 실 데이터는 MSSQL/Oracle에 혼재되어 있다.

설계 방침:
- 테이블/데이터 종류별로 소스 DB가 다를 수 있으므로, 커넥션을 직접 만들지 않고
  ConnectionStrategy를 주입받는다 (MSSQL=pyodbc, Oracle=oracledb).
- 쿼리는 데이터 종류별 어댑터로 분리하여 스키마 확정 시 어댑터만 구현한다.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.config import Settings
from app.data.repository import HeatRepository
from app.domain.models import AdditionEvent, Heat, HeatSummary, HeatTimeseries


class ConnectionStrategy(ABC):
    """DB 종류별 커넥션 전략. 구현 예: MssqlConnection(pyodbc), OracleConnection(oracledb)."""

    @abstractmethod
    def connect(self) -> Any: ...


class SqlHeatRepository(HeatRepository):
    """사내 DB 스키마 확정 후 구현. 현재는 명시적 미구현 상태를 유지한다."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def list_heats(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[HeatSummary]:
        raise NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")

    def get_heat(self, heat_id: str) -> Heat:
        raise NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")

    def get_timeseries(
        self,
        heat_id: str,
        tag_ids: list[str] | None = None,
        downsample_s: float | None = None,
    ) -> HeatTimeseries:
        raise NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")

    def get_kpi_trend(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        kpis: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")

    def get_additions(self, heat_id: str) -> list[AdditionEvent]:
        raise NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")
