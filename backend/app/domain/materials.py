"""장입/부원료/강종그룹 코드 레지스트리 — 코드·한글 라벨의 유일한 선언 지점.

스크랩 등급 코드, 부원료 코드, 조업 패턴(강종) 그룹 코드는 데이터 컬럼명
(`charge_scrap_{code}_t`)·parquet 값·API 응답에 그대로 실린다. 코드 문자열을
생성기·Repository·서비스에 하드코딩하지 말고 반드시 여기서 import 한다
(CLAUDE.md 선언 중심 확장 원칙 — 등급 추가는 이 파일의 선언 추가로 완결).

domain 계층이므로 다른 계층에 의존하지 않는다.
"""

#: 스크랩 등급 코드 → 한글 라벨. 컬럼명 규약: charge_scrap_{code}_t
SCRAP_GRADES: dict[str, str] = {
    "grade_a": "A급",
    "shredder": "슈레더",
    "turnings": "선반설",
    "common": "일반",
}

#: 부원료 코드 → 한글 라벨. additions.parquet의 material 값 / slag_add_{code}_kg
ADDITION_MATERIALS: dict[str, str] = {
    "lime": "생석회",
    "lump_carbon": "괴탄",
}

#: 조업 패턴(강종) 그룹 코드 → 한글 라벨. heats.parquet의 steel_group 값
STEEL_GROUPS: dict[str, str] = {
    "high": "고급강종",
    "mid": "일반강종",
    "low": "저급 배합",
}
