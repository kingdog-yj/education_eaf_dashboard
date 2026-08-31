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
    llm_model: str = "gpt-5"

    # 학술 검색 (무료 키 — 없으면 공용 rate limit으로 동작, 429 빈발 가능)
    semantic_scholar_api_key: str = ""

    # 데이터 백엔드: file(parquet 더미) | sql(향후 사내 DB)
    data_backend: Literal["file", "sql"] = "file"
    data_dir: Path = PROJECT_ROOT / "data" / "dummy"

    # 향후 사내 DB (혼재: MSSQL + Oracle)
    mssql_conn_str: str = ""
    oracle_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
