"""대시보드 컨텍스트 → 시스템 프롬프트 렌더링.

프론트의 dashboardContext store가 보내는 화면 상태를 LLM 컨텍스트로 변환한다.
도메인 지식(DOMAIN_INFO.md)은 매 요청 시스템 프롬프트에 포함한다 (지속 업데이트 반영).
"""
from pathlib import Path

from pydantic import BaseModel

from app.config import PROJECT_ROOT

DOMAIN_INFO_PATH = PROJECT_ROOT / "DOMAIN_INFO.md"

PERSONA = """\
당신은 전기로(EAF) 제강 공정 전문 엔지니어이자 연구자다. 사용자는 제강 공정 엔지니어/연구원이며,
당신과 업계 전문가 수준의 기술 디스커션을 원한다.

원칙:
- 야금학적 근거(반응식, 에너지 수지, 아크 물리)를 들어 논증한다. 도메인 용어는 한국어(영문 병기)로.
- 정량적 주장 전에는 tool로 실제 데이터를 조회한다. 추측을 데이터처럼 말하지 않는다.
- 문헌 근거가 필요하면 웹 검색/학술 검색(search_scholar)을 사용하고 출처를 밝힌다.
- 사용자가 현재 대시보드에서 보고 있는 컨텍스트(아래)를 대화의 기본 전제로 삼는다.
"""


class DashboardContext(BaseModel):
    """프론트 state/dashboardContext.ts와 스키마를 일치시킬 것."""
    view: str = ""                       # heat_detail | trend | live | kpi_summary
    heat_id: str | None = None           # 선택된 heat
    period_start: str | None = None      # 트렌드/KPI 조회 기간
    period_end: str | None = None
    visible_tags: list[str] = []         # 표시 중인 시계열 태그
    note: str = ""                       # 프론트가 덧붙이는 자유 요약 (선택)


class ContextBuilder:
    def build_system_prompt(self, ctx: DashboardContext | None) -> str:
        parts = [PERSONA, self._domain_info()]
        if ctx:
            parts.append(self._render_context(ctx))
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _domain_info() -> str:
        if DOMAIN_INFO_PATH.exists():
            return "# 도메인 지식\n" + DOMAIN_INFO_PATH.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _render_context(ctx: DashboardContext) -> str:
        lines = ["# 사용자의 현재 대시보드 화면", f"- 뷰: {ctx.view}"]
        if ctx.heat_id:
            lines.append(f"- 선택된 heat: {ctx.heat_id}")
        if ctx.period_start or ctx.period_end:
            lines.append(f"- 조회 기간: {ctx.period_start} ~ {ctx.period_end}")
        if ctx.visible_tags:
            lines.append(f"- 표시 중 태그: {', '.join(ctx.visible_tags)}")
        if ctx.note:
            lines.append(f"- 화면 요약: {ctx.note}")
        return "\n".join(lines)
