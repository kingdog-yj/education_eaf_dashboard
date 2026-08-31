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


#: 페이즈 경계 휴리스틱 상수 — 경계 산출의 유일한 선언 지점.
#: 현재 데이터에는 천공 종료·용락 안정화 같은 경계 이벤트가 없어(이벤트는
#: power_on/meltdown/tap_start/tap_end 4종뿐) 더미 단계의 추정값을 쓴다.
#: 실데이터(경계 이벤트 포함) 연결 시 재검토하되, 조정은 이 선언 수정만으로 완결된다.
BORE_IN_DURATION_S: float = 180.0    # 천공(bore-in) 지속 시간 추정 — power_on 기준
MELTDOWN_SETTLE_S: float = 120.0     # 용락 후 아크 안정화 구간 추정 — meltdown 기준


_LABELS_KO: dict[HeatPhase, str] = {
    HeatPhase.BORE_IN: "천공 (bore-in)",
    HeatPhase.EXPANSION: "천공 확장",
    HeatPhase.MELTDOWN: "용락 (meltdown)",
    HeatPhase.REFINING: "승온/정련",
    HeatPhase.TAPPING: "출강",
}
