"""FastAPI 의존성 주입. 구현체 선택은 factory(설정 기반)에 위임한다."""
from functools import lru_cache

from app.data.repository import create_repository
from app.services.discussion_service import DiscussionService
from app.services.heat_service import HeatService
from app.services.live_service import LiveStreamService


@lru_cache
def get_heat_service() -> HeatService:
    return HeatService(create_repository())


@lru_cache
def get_discussion_service() -> DiscussionService:
    from app.llm.base import create_provider

    return DiscussionService(create_provider())


@lru_cache
def get_live_service() -> LiveStreamService:
    return LiveStreamService()
