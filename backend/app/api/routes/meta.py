"""메타 정보 — 프론트가 차트/필터를 TagRegistry 선언 기반으로 구성하게 한다."""
from fastapi import APIRouter

from app.domain import specs
from app.domain.materials import ADDITION_MATERIALS, SCRAP_GRADES, STEEL_GROUPS
from app.domain.phases import HeatPhase
from app.domain.tags import TAG_REGISTRY
from app.llm import modes

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


@router.get("/chat_modes")
def chat_modes():
    """Discussion 채팅 모드 선택지 + 기본값 (선언은 llm/modes.py)."""
    return {"modes": modes.as_dicts(), "default_mode": modes.DEFAULT_MODE_ID}


@router.get("/specs")
def list_specs():
    """지표/조업 스펙 레지스트리 — 프론트 수치 하드코딩을 없애기 위한 유일 공급원."""
    return [
        {
            "id": s.id,
            "label_ko": s.label_ko,
            "unit": s.unit,
            "decimals": s.decimals,
            "lo": s.lo,
            "hi": s.hi,
        }
        for s in specs.SPEC_REGISTRY
    ]


@router.get("/materials")
def list_materials():
    """장입 등급/부원료/강종 그룹 코드 → 한글 라벨 (domain/materials 선언 그대로)."""
    return {
        "scrap_grades": SCRAP_GRADES,
        "addition_materials": ADDITION_MATERIALS,
        "steel_groups": STEEL_GROUPS,
    }
