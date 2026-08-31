"""메타 정보 — 프론트가 차트/필터를 TagRegistry 선언 기반으로 구성하게 한다."""
from fastapi import APIRouter

from app.domain.phases import HeatPhase
from app.domain.tags import TAG_REGISTRY

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/tags")
def list_tags():
    return [
        {
            "id": t.id,
            "group": t.group.value,
            "unit": t.unit,
            "label_ko": t.label_ko,
            "sample_period_s": t.sample_period_s,
            "cumulative": t.cumulative,
        }
        for t in TAG_REGISTRY.all()
    ]


@router.get("/phases")
def list_phases():
    return [{"id": p.value, "label_ko": p.label_ko} for p in HeatPhase]
