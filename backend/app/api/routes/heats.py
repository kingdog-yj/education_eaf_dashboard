from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_heat_service
from app.data.repository import HeatNotFoundError
from app.domain.models import (
    AdditionEvent,
    Heat,
    HeatSummary,
    HeatTimeseries,
    PhaseInterval,
)
from app.services.heat_service import HeatService

router = APIRouter(prefix="/api/heats", tags=["heats"])


@router.get("", response_model=list[HeatSummary])
def list_heats(
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, le=1000),
    service: HeatService = Depends(get_heat_service),
):
    return service.list_heats(start, end, limit)


@router.get("/{heat_id}", response_model=Heat)
def get_heat(heat_id: str, service: HeatService = Depends(get_heat_service)):
    try:
        return service.get_heat(heat_id)
    except HeatNotFoundError:
        raise HTTPException(404, f"heat {heat_id} 없음")


@router.get("/{heat_id}/timeseries", response_model=HeatTimeseries)
def get_timeseries(
    heat_id: str,
    tags: str | None = Query(None, description="쉼표 구분 태그 id (생략 시 dev 프로필 전체)"),
    downsample: float | None = Query(None, description="다운샘플 주기(초)"),
    service: HeatService = Depends(get_heat_service),
):
    tag_ids = tags.split(",") if tags else None
    try:
        return service.get_timeseries(heat_id, tag_ids, downsample)
    except HeatNotFoundError:
        raise HTTPException(404, f"heat {heat_id} 시계열 없음")


@router.get("/{heat_id}/phases", response_model=list[PhaseInterval])
def get_phases(heat_id: str, service: HeatService = Depends(get_heat_service)):
    """조업 페이즈 구간(차트 음영용). 산출 불가 페이즈는 배열에서 생략된다."""
    try:
        return service.get_phases(heat_id)
    except HeatNotFoundError:
        raise HTTPException(404, f"heat {heat_id} 없음")


@router.get("/{heat_id}/additions", response_model=list[AdditionEvent])
def get_additions(heat_id: str, service: HeatService = Depends(get_heat_service)):
    """부원료 투입 이벤트. 데이터가 없으면 빈 배열(404 아님)."""
    return service.get_additions(heat_id)
