"""전기로 조업 페이즈. DOMAIN_INFO.md의 공정 흐름을 코드 공통 어휘로 고정한다.

차트 구간 음영, 더미데이터 생성, LLM 디스커션 프롬프트가 모두 이 enum을 참조한다.
"""
from enum import Enum


class HeatPhase(str, Enum):
    BORE_IN = "bore_in"        # 천공: 전극 하강, short arc, 아크 불안정
    EXPANSION = "expansion"    # 천공 확장: long arc, 스크랩 붕락 반복
    MELTDOWN = "meltdown"      # 용락 후: 잔류 스크랩 수면 아래, 아크 안정화
    REFINING = "refining"      # 승온/정련: 슬래그 포밍, 탈탄/탈린, ~1600°C 승온
    TAPPING = "tapping"        # 출강

    @property
    def label_ko(self) -> str:
        return _LABELS_KO[self]


_LABELS_KO: dict[HeatPhase, str] = {
    HeatPhase.BORE_IN: "천공 (bore-in)",
    HeatPhase.EXPANSION: "천공 확장",
    HeatPhase.MELTDOWN: "용락 (meltdown)",
    HeatPhase.REFINING: "승온/정련",
    HeatPhase.TAPPING: "출강",
}
