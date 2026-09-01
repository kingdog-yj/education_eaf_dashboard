# EAF 대시보드 — Streamlit 스냅샷 데모

이 앱은 **c59ffe8 스냅샷**이며 향후 업데이트되지 않습니다.
최신 개발은 `main` 브랜치(FastAPI + React)에서 계속됩니다.

원본 대시보드의 데이터·도메인·프롬프트 계층(`backend/app/`)을 그대로 import해서
UI만 Streamlit으로 대체한 1회성 데모입니다. `backend/`·`frontend/` 코드는 수정하지 않습니다.

## 포함 범위

| 뷰 | 상태 |
|---|---|
| Heat 상세 (heat detail) | 시계열 3종 + KPI/EOP/장입/슬래그 표 |
| 트렌드 (trend) | 지표 선택 + 스펙 밴드(spec band) 점선 |
| KPI 요약 (KPI summary) | 일/주/월 집계 카드 8개 |
| 실시간 모니터링 (live) | 미포함(안내 문구만) |
| Discussion(채팅) | 단발성 chat completion 스트리밍. 데이터 조회 tool·웹/학술 검색 없음 |

## Streamlit Cloud 배포 설정

- **Repository**: 이 레포
- **Branch**: `streamlit-snapshot`
- **Main file path**: `streamlit_app/app.py`
- **Advanced settings**: Python 버전 **3.11 이상** 선택 권장 (backend 코드가 `X | None` 문법 사용)

### Secrets

App settings → Secrets 에 아래 한 줄을 넣습니다.

```toml
OPENAI_API_KEY = "sk-..."
```

미설정 시 **채팅만 비활성화**되고(안내 문구 표시) 대시보드는 정상 동작합니다.

> 앱을 public으로 두면 URL을 아는 누구나 이 키로 채팅할 수 있습니다(과금 발생).
> 필요 시 Streamlit Cloud의 뷰어 인증(private)으로 설정하세요.

## 로컬 실행

레포 루트에서:

```bash
pip install -r requirements.txt
streamlit run streamlit_app/app.py
```

채팅 테스트는 환경변수로 가능합니다.

```bash
# PowerShell
$env:OPENAI_API_KEY = "sk-..."
# bash
export OPENAI_API_KEY="sk-..."
```

## 데이터

`data/dummy/`의 더미 500 heat(parquet)이 레포에 포함되어 있어 별도 준비가 필요 없습니다.
경로는 `streamlit_app/app.py` 위치 기준(`REPO_ROOT / "data" / "dummy"`)으로 해석되므로
실행 디렉터리(cwd)나 `.env`에 의존하지 않습니다.
