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
    # 파일럿은 미설정 — 이 PC의 Claude Code CLI 로그인(구독) 자격증명을 SDK가
    # 상속한다. 팀 배포 시 이 값만 설정하면 API 키 인증으로 전환된다.
    anthropic_api_key: str = ""
    # provider 구현체 선택 (ABC/factory 경유 — 추가 시 Literal 확장)
    llm_provider: Literal["claude_agent"] = "claude_agent"

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
