from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_heat_service
from app.domain.models import KpiSummaryResponse
from app.services.heat_service import HeatService

router = APIRouter(prefix="/api/kpi", tags=["kpi"])


@router.get("/trend")
def kpi_trend(
    start: datetime | None = None,
    end: datetime | None = None,
    service: HeatService = Depends(get_heat_service),
):
    return service.get_kpi_trend(start, end)


@router.get("/summary", response_model=KpiSummaryResponse)
def kpi_summary(
    period: str = Query("day", pattern="^(day|week|month)$"),
    service: HeatService = Depends(get_heat_service),
):
    return service.get_kpi_summary(period)
