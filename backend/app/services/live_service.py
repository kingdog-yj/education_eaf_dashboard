"""실시간 모니터링 스트림 서비스.

더미 단계: 과거 heat의 시계열을 실시간 재생(시뮬레이션)하여 WebSocket으로 송출.
실 DB 연결 시: 최신 데이터 폴링(수집 주기 간격) 방식으로 교체 — 인터페이스 동일 유지.
"""
import asyncio
from collections.abc import AsyncIterator


class LiveStreamService:
    def __init__(self, replay_speed: float = 1.0):
        self._replay_speed = replay_speed

    async def stream(self) -> AsyncIterator[dict]:
        """1초(샘플링 주기) 간격으로 현재 진행 중 heat의 최신 값 묶음을 yield.

        더미데이터 생성 후 구현: ParquetHeatRepository에서 heat 하나를 골라
        타임스탬프 순으로 재생. 현재는 빈 스트림 유지(연결 검증용 heartbeat만).
        """
        while True:
            await asyncio.sleep(1.0 / self._replay_speed)
            yield {"type": "heartbeat", "payload": {}}
