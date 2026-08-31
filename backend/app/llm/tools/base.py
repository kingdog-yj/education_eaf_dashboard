"""Discussion용 LLM tool 추상화 + 레지스트리.

tool 추가 = DiscussionTool 상속 클래스 작성 + create_default_tools()에 등록. 그 외 수정 불필요.
provider가 각 tool의 스키마를 자기 API 형식으로 변환해 브릿지한다.
"""
from abc import ABC, abstractmethod
from typing import Any


class DiscussionTool(ABC):
    name: str
    description: str
    parameters_schema: dict[str, Any]   # JSON Schema (provider가 자체 형식으로 변환)

    @abstractmethod
    async def run(self, **kwargs) -> str:
        """실행 결과를 LLM에 넘길 문자열(JSON 권장)로 반환."""


class ToolRegistry:
    def __init__(self, tools: list[DiscussionTool] | None = None):
        self._tools: dict[str, DiscussionTool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: DiscussionTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"중복 tool 이름: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> DiscussionTool:
        return self._tools[name]

    def all(self) -> list[DiscussionTool]:
        return list(self._tools.values())


def create_default_tools() -> ToolRegistry:
    from app.data.repository import create_repository
    from app.llm.tools.data_tools import (
        QueryHeatDetailTool,
        QueryKpiTrendTool,
        QueryTimeseriesStatsTool,
    )
    from app.llm.tools.scholar import SearchScholarTool

    repo = create_repository()
    return ToolRegistry(
        [
            QueryHeatDetailTool(repo),
            QueryTimeseriesStatsTool(repo),
            QueryKpiTrendTool(repo),
            SearchScholarTool(),
        ]
    )
