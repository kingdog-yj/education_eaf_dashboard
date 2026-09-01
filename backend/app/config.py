"""앱 전역 설정. 모든 환경 의존 값은 .env → 여기로만 들어온다 (코드 하드코딩 금지)."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: Literal["openai", "anthropic"] = "openai"
    # 채팅 기본 모델/강도. 선택지는 llm/options.py 선언, 사용자는 채팅 UI에서
    # 메시지 단위로 오버라이드할 수 있다(재기동 불필요).
    llm_model: str = "gpt-5-mini"
    # reasoning 강도: "" (SDK/모델 기본 유지) | minimal | low | medium | high
    # 기본 low — 수 초 내 응답 우선. 심층 분석은 UI에서 gpt-5/high로 전환.
    llm_reasoning_effort: str = "low"
    # 응답 상세도: low | medium | high (유효값은 llm/options.VERBOSITY_LEVELS).
    # 기본 low — 현업 전문가 대상 디스커션은 장황한 설명보다 결론·수치가 우선.
    llm_verbosity: str = "low"

    # 학술 검색 (무료 키 — 없으면 공용 rate limit으로 동작, 429 빈발 가능)
    semantic_scholar_api_key: str = ""

    # 데이터 백엔드: file(parquet 더미) | sql(향후 사내 DB)
    data_backend: Literal["file", "sql"] = "file"
    data_dir: Path = PROJECT_ROOT / "data" / "dummy"

    # 프론트 빌드 산출물 (존재 시 단일 포트 정적 서빙 + SPA fallback)
    frontend_dist_dir: Path = PROJECT_ROOT / "frontend" / "dist"

    # 향후 사내 DB (혼재: MSSQL + Oracle)
    mssql_conn_str: str = ""
    oracle_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
