"""LLM이 디스커션 중 서버 데이터를 심층 조회하는 tools.

화면에 요약만 주입된 상태에서, LLM이 필요 판단 시 스스로 상세 데이터를 가져온다.
"""
import json

from app.data.repository import HeatNotFoundError, HeatRepository
from app.domain.tags import TAG_REGISTRY
from app.llm.tools.base import DiscussionTool


class QueryHeatDetailTool(DiscussionTool):
    name = "query_heat_detail"
    description = (
        "특정 heat의 정적 데이터 전체(장입, KPI, 종점 성분/온도, 슬래그)를 조회한다. "
        "특정 heat에 대한 정량적 논의 전에 반드시 호출할 것."
    )
    parameters_schema = {
        "type": "object",
        "properties": {"heat_id": {"type": "string"}},
        "required": ["heat_id"],
    }

    def __init__(self, repo: HeatRepository):
        self._repo = repo

    async def run(self, heat_id: str) -> str:
        try:
            return self._repo.get_heat(heat_id).model_dump_json()
        except HeatNotFoundError:
            return json.dumps({"error": f"heat {heat_id} 없음"})


class QueryTimeseriesStatsTool(DiscussionTool):
    name = "query_timeseries_stats"
    description = (
        "특정 heat의 시계열 태그 요약 통계(구간별 평균/최대/표준편차 등)를 조회한다. "
        f"사용 가능 태그: {', '.join(TAG_REGISTRY.ids())}"
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "heat_id": {"type": "string"},
            "tag_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["heat_id"],
    }

    def __init__(self, repo: HeatRepository):
        self._repo = repo

    async def run(self, heat_id: str, tag_ids: list[str] | None = None) -> str:
        try:
            ts = self._repo.get_timeseries(heat_id, tag_ids, downsample_s=10.0)
        except HeatNotFoundError:
            return json.dumps({"error": f"heat {heat_id} 시계열 없음"})
        stats = {}
        for s in ts.series:
            values = [p.value for p in s.points]
            if not values:
                continue
            stats[s.tag_id] = {
                "unit": s.unit,
                "mean": sum(values) / len(values),
                "max": max(values),
                "min": min(values),
                "n": len(values),
            }
        # TODO(구현 예정): 페이즈(용락 전/후)별 구간 통계 — LLM 디스커션 품질에 중요
        return json.dumps(stats, ensure_ascii=False)


class QueryKpiTrendTool(DiscussionTool):
    name = "query_kpi_trend"
    description = "기간별 heat KPI 트렌드(전력원단위, tap-to-tap 등)를 조회한다. 날짜는 ISO 형식."
    parameters_schema = {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO date"},
            "end": {"type": "string", "description": "ISO date"},
        },
        "required": [],
    }

    def __init__(self, repo: HeatRepository):
        self._repo = repo

    async def run(self, start: str | None = None, end: str | None = None) -> str:
        from datetime import datetime

        rows = self._repo.get_kpi_trend(
            datetime.fromisoformat(start) if start else None,
            datetime.fromisoformat(end) if end else None,
        )
        return json.dumps(rows, ensure_ascii=False, default=str)
