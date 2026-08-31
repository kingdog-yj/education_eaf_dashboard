"""데이터 소스 추상화. 대시보드/LLM tool은 이 인터페이스만 사용한다.

더미(parquet) ↔ 사내 DB(MSSQL/Oracle 혼재) 전환은 .env의 DATA_BACKEND 변경으로 완결.
"""
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models import AdditionEvent, Heat, HeatSummary, HeatTimeseries


class HeatRepository(ABC):
    @abstractmethod
    def list_heats(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[HeatSummary]: ...

    @abstractmethod
    def get_heat(self, heat_id: str) -> Heat: ...

    @abstractmethod
    def get_timeseries(
        self,
        heat_id: str,
        tag_ids: list[str] | None = None,
        downsample_s: float | None = None,
    ) -> HeatTimeseries: ...

    @abstractmethod
    def get_kpi_trend(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        kpis: list[str] | None = None,
    ) -> list[dict]: ...

    @abstractmethod
    def get_additions(self, heat_id: str) -> list[AdditionEvent]:
        """heat의 부원료 투입 이벤트(시각 오름차순). 데이터 없으면 빈 리스트."""
        ...


class HeatNotFoundError(KeyError):
    pass


def create_repository() -> HeatRepository:
    """DATA_BACKEND 설정에 따른 구현체 factory."""
    from app.config import get_settings

    settings = get_settings()
    if settings.data_backend == "file":
        from app.data.file_repository import ParquetHeatRepository

        return ParquetHeatRepository(settings.data_dir)
    if settings.data_backend == "sql":
        from app.data.sql_repository import SqlHeatRepository

        return SqlHeatRepository(settings)
    raise ValueError(f"알 수 없는 DATA_BACKEND: {settings.data_backend}")
