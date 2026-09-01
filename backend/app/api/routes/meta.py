"""메타 정보 — 프론트가 차트/필터를 TagRegistry 선언 기반으로 구성하게 한다."""
from fastapi import APIRouter

from app.config import get_settings
from app.domain import specs
from app.domain.materials import ADDITION_MATERIALS, SCRAP_GRADES, STEEL_GROUPS
from app.domain.phases import HeatPhase
from app.domain.tags import TAG_REGISTRY
from app.llm import options

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


@router.get("/llm")
def llm_options():
    """채팅에서 선택 가능한 모델/reasoning 강도 + 서버 기본값.

    선택지는 llm/options.py, 기본값은 설정(.env)에서 온다. 기본값이 선택지에
    없더라도 목록은 그대로 두고 default만 설정값을 반환한다.
    """
    settings = get_settings()
    return {
        "models": options.as_dicts(options.LLM_MODEL_OPTIONS),
        "efforts": options.as_dicts(options.EFFORT_OPTIONS),
        "default_model": settings.llm_model,
        "default_effort": settings.llm_reasoning_effort,
    }


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
