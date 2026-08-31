"""학술 검색 tool — Semantic Scholar(주) + arXiv/CrossRef(확장 예약).

API 키 불필요(무료). 일반 웹 검색은 provider 내장 web_search가 담당하고,
이 tool은 논문/학술 문헌 검색에 특화한다 (SPEC.md §7).
"""
import json

import httpx

from app.llm.tools.base import DiscussionTool

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


class SearchScholarTool(DiscussionTool):
    name = "search_scholar"
    description = (
        "학술 논문 검색 (Semantic Scholar). EAF 야금학/전기로 공정 관련 논문의 "
        "제목/초록/인용수/링크를 반환한다. 검색어는 영어로 작성할 것."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "영어 검색어"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def run(self, query: str, limit: int = 5) -> str:
        from app.config import get_settings

        headers = {}
        if key := get_settings().semantic_scholar_api_key:
            headers["x-api-key"] = key
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                SEMANTIC_SCHOLAR_URL,
                headers=headers,
                params={
                    "query": query,
                    "limit": min(limit, 10),
                    "fields": "title,abstract,year,citationCount,externalIds,url",
                },
            )
        if resp.status_code != 200:
            return json.dumps({"error": f"Semantic Scholar 응답 {resp.status_code}"})
        papers = resp.json().get("data", [])
        return json.dumps(
            [
                {
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "citations": p.get("citationCount"),
                    "abstract": (p.get("abstract") or "")[:500],
                    "url": p.get("url"),
                }
                for p in papers
            ],
            ensure_ascii=False,
        )
