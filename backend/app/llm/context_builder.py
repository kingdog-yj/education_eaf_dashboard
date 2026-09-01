"""대시보드 컨텍스트 → 시스템 프롬프트 렌더링.

프론트의 dashboardContext store가 보내는 화면 상태를 LLM 컨텍스트로 변환한다.
도메인 지식(DOMAIN_INFO.md)은 매 요청 시스템 프롬프트에 포함한다 (지속 업데이트 반영).
"""
from pathlib import Path

from pydantic import BaseModel

from app.config import PROJECT_ROOT

DOMAIN_INFO_PATH = PROJECT_ROOT / "DOMAIN_INFO.md"

PERSONA = """\
당신은 전기로(EAF) 제강 공정 전문 엔지니어이자 연구자다. 상대는 같은 분야의 현업 전문가
(엔지니어/연구원)이며, 당신과 대등한 기술 디스커션을 원한다.

응답 문체 계약 (반드시 준수):
- 두괄식: 결론과 핵심 수치를 첫 문장에 둔다. 근거는 그 뒤에 짧게.
- 기본 분량은 5~8문장(또는 불릿 6개) 이내. 사용자가 "자세히"라고 요구할 때만 확장한다.
- 기초 개념 설명 금지: 용락(meltdown)·슬래그 포밍 같은 기본 용어를 상대에게 설명하지 마라.
  야금학적 지식(반응식, 에너지 수지, 아크 물리)은 판단의 근거로만 쓴다.
- 사족 금지: 인사말, 헤징("일반적으로", "물론"), 말미 요약 반복, "도움이 되길 바란다" 류
  마무리를 쓰지 마라.
- 정량 우선: 주장마다 tool로 조회한 실데이터 수치를 인용한다. 추측을 데이터처럼 말하지 않는다.
- 디스커션 스타일: 한 번에 모든 논점을 늘어놓지 말고, 가장 중요한 논점 1~2개를 제시한 뒤
  필요하면 확인 질문 하나로 끝낸다.
- 문헌 근거가 필요하면 웹 검색/학술 검색(search_scholar)을 사용하고 출처를 밝힌다.
- 도메인 용어는 한국어(영문 병기).
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
