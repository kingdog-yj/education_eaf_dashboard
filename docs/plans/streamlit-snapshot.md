# Streamlit Cloud 1회성 스냅샷 배포 계획 (streamlit-snapshot 브랜치)

작성: planner / 2026-09-01
전제: 이 브랜치(c59ffe8 분기)는 향후 업데이트되지 않는 고정 스냅샷. main 개발 라인과 완전 격리.
원칙: 최소 작업. `backend/`·`frontend/` 무수정. 신규 파일만 추가.

## 1. 작업 분해

| 단위 | 담당 | 의존 |
|---|---|---|
| U1. `streamlit_app/app.py` + `streamlit_app/README.md` + 루트 `requirements.txt` 작성 | backend-coder 1인스턴스 | 없음 (단일 작업 — 병렬화 불필요, 파일 3개가 한 기능) |
| U2. 검증 | verifier | U1 완료 후 |

프론트엔드 작업 없음. 병렬 실행 지점 없음(신규 파일 3개가 결합되어 있어 분리 이득 없음).

## 2. 계약 고정 (재사용 API — 코더는 이 시그니처를 신뢰하고 재구현 금지)

backend/app에서 import하여 그대로 사용 (sys.path에 `<repo>/backend` 추가 후):

- `app.data.file_repository.ParquetHeatRepository(data_dir: Path)`
- `app.data.repository.HeatNotFoundError`
- `app.services.heat_service.HeatService(repo)`
  - `.list_heats(start, end, limit) -> list[HeatSummary]`
  - `.get_heat(heat_id) -> Heat` (필드: summary/charge/kpi/eop/slag)
  - `.get_timeseries(heat_id, tag_ids: list[str] | None, downsample_s: float | None) -> HeatTimeseries`
    (tag_ids=None → TAG_REGISTRY dev 프로필 3종: active_power, o2_lance_flow, carbon_inj_rate)
  - `.get_kpi_trend(start, end) -> list[dict]` (키: heat_id, date, steel_group, kpi_*, eop_*, charge_total_t)
  - `.get_kpi_summary(period: "day"|"week"|"month") -> KpiSummaryResponse` (cards: 8개, 각 label_ko/unit/decimals/value/prev_value)
- `app.domain.tags.TAG_REGISTRY` (`.all()`, `.get(id).label_ko/.unit`)
- `app.domain.specs.SPEC_REGISTRY` (MetricSpec: id/label_ko/unit/decimals/lo/hi)
- `app.domain.materials.STEEL_GROUPS`
- `app.llm.context_builder.ContextBuilder().build_system_prompt(ctx: DashboardContext | None) -> str`
  및 `DashboardContext(view, heat_id, period_start, period_end, visible_tags, note)`
  — view 값: `heat_detail | trend | live | kpi_summary` (원본 프론트와 동일 문자열)
- `app.llm.options.LLM_MODEL_OPTIONS` (첫 항목 `LLM_MODEL_OPTIONS[0].id` == "gpt-5-mini"를 채팅 모델로)

데이터 경로 계약: `REPO_ROOT = Path(__file__).resolve().parent.parent` (streamlit_app/app.py 기준) →
`DATA_DIR = REPO_ROOT / "data" / "dummy"`. cwd·.env 비의존. `get_settings()` 호출 금지.

## 3. 파일 단위 변경 명세

### 신규
1. `streamlit_app/app.py` — 단일 파일 Streamlit 앱 (뷰 4 + Live 플레이스홀더 + 채팅). 상세는 §4 코더 프롬프트.
2. `streamlit_app/README.md` — 스냅샷 고지 + Streamlit Cloud 설정 안내(Main file path=`streamlit_app/app.py`, Secrets `OPENAI_API_KEY`, Python 3.11+ 권장).
3. `requirements.txt` (레포 루트) — 정확히 7개:
   ```
   streamlit
   pandas
   pyarrow
   plotly
   openai
   pydantic
   pydantic-settings
   ```
   (pydantic-settings는 `app.llm.context_builder` → `app.config` import 경로 때문에 필요.
   fastapi/uvicorn/httpx/numpy 명시 불필요 — numpy는 pandas 의존으로 유입.)
4. `docs/plans/streamlit-snapshot.md` — 본 문서.

### 수정 금지
`backend/**`, `frontend/**`, `CLAUDE.md`, `SPEC.md`, `DOMAIN_INFO.md`, `.env`, `.gitignore` — 일체 수정 금지.
`.streamlit/config.toml` 생성하지 않음(불필요).

## 4. backend-coder 실행 프롬프트

(보고서 본문에 전문 포함 — 본 문서 §4와 동일 내용을 그대로 전달한다)

### 프롬프트 전문

당신은 이 레포의 `streamlit-snapshot` 브랜치에서 작업한다. 이 브랜치는 FastAPI+React 대시보드의 고정 스냅샷이며, Streamlit Cloud에 1회성 데모로 배포된다. 신규 파일 3개만 만든다. **`backend/`, `frontend/`, 루트 문서(.md), `.env`는 절대 수정하지 않는다.**

#### 만들 파일
1. `streamlit_app/app.py`
2. `streamlit_app/README.md`
3. `requirements.txt` (레포 루트, 신규)

#### 전체 구조 — streamlit_app/app.py (단일 파일, 과도한 추상화 금지)

파일 최상단(다른 import보다 먼저):
```python
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
```
그 다음 import: `streamlit as st`, `pandas as pd`, `plotly.graph_objects as go`, `plotly.subplots.make_subplots`, 그리고 backend 재사용 모듈:
```python
from app.data.file_repository import ParquetHeatRepository
from app.data.repository import HeatNotFoundError
from app.services.heat_service import HeatService
from app.domain.tags import TAG_REGISTRY
from app.domain import specs
from app.domain.materials import STEEL_GROUPS
from app.llm.context_builder import ContextBuilder, DashboardContext
from app.llm.options import LLM_MODEL_OPTIONS
```
데이터 접근·모델·집계 로직을 재작성하지 마라 — 전부 위 모듈을 호출만 한다.

`st.set_page_config(page_title="EAF 공정 분석 대시보드 (스냅샷)", layout="wide")`.

캐시 팩토리:
```python
DATA_DIR = REPO_ROOT / "data" / "dummy"

@st.cache_resource
def get_service() -> HeatService:
    return HeatService(ParquetHeatRepository(DATA_DIR))

@st.cache_data(show_spinner=False)
def load_heat_ids() -> list[str]:
    return [h.heat_id for h in get_service().list_heats(None, None, 500)]

@st.cache_data(show_spinner=False)
def load_timeseries(heat_id: str, downsample_s: float = 5.0):
    return get_service().get_timeseries(heat_id, None, downsample_s)

@st.cache_data(show_spinner=False)
def load_kpi_trend() -> pd.DataFrame:
    return pd.DataFrame(get_service().get_kpi_trend(None, None))
```
(pydantic 모델 반환은 pickle 가능하므로 cache_data 사용 가능.)

사이드바: `st.sidebar.radio`로 뷰 선택 — 선택지 4개: "Heat 상세", "트렌드", "KPI 요약", "실시간 모니터링". 선택값을 내부 view id(`heat_detail | trend | kpi_summary | live`)로 매핑. 메인 영역에서 해당 `render_*` 함수 호출 후, 맨 아래에 `st.divider()` + `render_chat(...)`.

각 뷰는 독립 함수로:

**`render_heat_detail() -> str | None`** (선택된 heat_id 반환 — 채팅 컨텍스트용):
- `st.selectbox("Heat 선택", load_heat_ids())` — heat_id 선택.
- `heat = get_service().get_heat(heat_id)`를 try/except `HeatNotFoundError`로 감싸고 실패 시 `st.warning` 후 return.
- 시계열: `ts = load_timeseries(heat_id)` → `make_subplots(rows=len(ts.series), cols=1, shared_xaxes=True)`, 각 series를 `go.Scatter(x=[p.ts for p in s.points], y=[p.value for p in s.points], mode="lines")`로 행마다 추가. 트레이스명·y축 제목은 `TAG_REGISTRY.get(s.tag_id)`의 `label_ko`/`unit` 사용(태그명·단위 하드코딩 금지). `st.plotly_chart(fig, use_container_width=True)`. 페이즈 음영·용락 수직선·부원료 마커는 구현하지 않는다.
- 정적 정보: `st.columns(4)`에 `st.metric` 4개 — 전력원단위(`heat.kpi.energy_kwh_per_t`), 출강량(`heat.kpi.tap_weight_t`), Power-on(`heat.kpi.power_on_min`), Tap-to-Tap(`heat.kpi.tap_to_tap_min`). None이면 "-" 표시.
- 그 아래 2컬럼: 좌측 KPI 전체 + EOP(출강온도, 성분 dict), 우측 장입(baskets, total_charge_t, hot_heel_t) + 슬래그(composition_pct, basicity, additions_kg)를 `st.dataframe` 또는 `st.table`로 (dict → 2열 표 변환 헬퍼 하나 허용). 라벨은 한국어(영문 병기)로 간단히.
- 반환값: heat_id.

**`render_trend()`**:
- 지표 선택: `st.selectbox`의 선택지는 `specs.SPEC_REGISTRY`(format_func로 `f"{s.label_ko} ({s.unit})"`). 기본 선택 `kpi_energy_kwh_per_t`.
- `df = load_kpi_trend()` — 비어 있으면 `st.info` 후 return. 선택 지표 컬럼이 df에 없으면 `st.info("해당 지표 데이터 없음")`.
- `go.Figure`에 `go.Scatter(x=df["date"], y=df[metric_id], mode="lines+markers")` (NaN은 plotly가 무시하므로 별도 처리 불필요, 정렬은 이미 date 오름차순). 스펙 밴드(`s.lo/s.hi`)가 있으면 `fig.add_hline` 2개 정도만(점선) — 그 이상(이탈 하이라이트, 강종 그룹 분리)은 구현하지 않는다.

**`render_kpi_summary()`**:
- `st.radio("집계 기간", horizontal=True)` — 일/주/월 → `"day"/"week"/"month"`.
- `resp = get_service().get_kpi_summary(period)` → `resp.bucket_start ~ bucket_end`를 캡션으로 표시.
- `resp.cards`(8개)를 `st.columns(4)` 2행으로 `st.metric(label=f"{c.label_ko} ({c.unit})", value=f"{c.value:.{c.decimals}f}", delta=...)`. value가 None이면 "-". delta는 value·prev_value 모두 있을 때만 `value - prev_value`를 decimals 자리로.

**`render_live()`**: `st.info("실시간 모니터링은 이 스냅샷에 포함되지 않습니다.")` 한 줄.

**`render_chat(view_id: str, heat_id: str | None)`**:
- API 키 조회 헬퍼:
```python
import os

def _openai_key() -> str:
    try:
        return st.secrets.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    except Exception:            # secrets.toml 자체가 없는 로컬 환경
        return os.environ.get("OPENAI_API_KEY", "")
```
- 키가 빈 문자열이면 `st.info("OPENAI_API_KEY가 설정되지 않아 채팅이 비활성화되어 있습니다.")` 표시 후 return — **앱은 절대 죽지 않는다.**
- 시스템 프롬프트: `ContextBuilder().build_system_prompt(ctx)` 재사용. ctx는:
```python
ctx = DashboardContext(
    view=view_id,
    heat_id=heat_id,
    visible_tags=[t.id for t in TAG_REGISTRY.all()] if view_id == "heat_detail" and heat_id else [],
    note=note,   # 아래 참조
)
```
  `note`: heat_detail 뷰에서 heat 선택 시, `get_heat` 결과의 핵심 수치를 2~3줄 텍스트로 요약해 넣는다(예: "KPI: 전력원단위 395.2 kWh/t, 출강량 150.1 t, POT 36.5 min / EOP: 출강온도 1602°C, C 0.045%, P 0.012%"). tool이 없으므로 이것이 LLM의 유일한 실데이터다. None 필드는 생략.
- 시스템 프롬프트 끝에 데모 한계 문구를 덧붙인다(context_builder.py 수정 금지 — 문자열 결합으로):
  `"\n\n---\n\n주의: 이 데모 환경에는 데이터 조회 tool과 웹/학술 검색이 없다. 위 컨텍스트에 제공된 수치만 실데이터로 인용하고, 추가 조회가 필요한 질문에는 이 스냅샷 데모에서 조회 불가함을 밝혀라."`
- 대화 이력: `st.session_state.setdefault("messages", [])` — `{"role": "user"|"assistant", "content": str}` dict 목록. 매 rerun마다 `st.chat_message(m["role"])`로 전체 재렌더.
- 입력: `st.chat_input("공정에 대해 질문하세요")`. 입력 시 user 메시지 append → OpenAI 호출:
```python
from openai import OpenAI

CHAT_MODEL = LLM_MODEL_OPTIONS[0].id   # "gpt-5-mini" — 모델 id 하드코딩 금지

client = OpenAI(api_key=key)
stream = client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[{"role": "system", "content": system_prompt}, *st.session_state["messages"]],
    stream=True,
)
```
  `st.chat_message("assistant")` 블록 안에서 `st.write_stream`으로 스트리밍(제너레이터에서 `chunk.choices[0].delta.content`가 None이 아닐 때만 yield). 완료 후 전체 텍스트를 assistant 메시지로 append.
- 호출 전체를 try/except로 감싸 실패 시 `st.error(f"LLM 호출 실패: {...}")` — 예외 메시지에 `sk-`로 시작하는 토큰이 있으면 `***`로 마스킹(backend의 `_mask_secrets`와 같은 취지, 4~5줄 인라인 구현 허용). tool-calling·web_search·reasoning 파라미터는 일절 보내지 않는다.
- SSE·에이전트 루프·`OpenAIProvider`·`llm/tools` 재구현/재사용 금지 — 단발성 chat completion만.

기타:
- UI 텍스트는 한국어(기술 용어 영문 병기).
- 페이지 상단에 `st.caption`으로 "고정 스냅샷 데모 (c59ffe8) — 최신 버전은 별도 개발 중" 한 줄.
- `app.config.get_settings()` 호출 금지, `.env` 읽기 금지, API 키를 코드·로그에 남기지 않는다.
- Python 3.10+ 문법(backend가 `X | None` 사용) 전제 — 하위 호환 작업 불필요.

#### streamlit_app/README.md 내용
- "이 앱은 c59ffe8 스냅샷이며 향후 업데이트되지 않습니다. 최신 개발은 main 브랜치(FastAPI+React)에서 계속됩니다."
- Streamlit Cloud 배포 설정: Repository=이 레포, Branch=`streamlit-snapshot`, **Main file path=`streamlit_app/app.py`**, Advanced settings에서 Python 3.11 이상 선택 권장.
- Secrets 설정: App settings → Secrets에 `OPENAI_API_KEY = "sk-..."` 한 줄. 미설정 시 채팅만 비활성화되고 대시보드는 정상 동작.
- 로컬 실행: 레포 루트에서 `pip install -r requirements.txt` 후 `streamlit run streamlit_app/app.py`. (채팅 테스트는 환경변수 `OPENAI_API_KEY`로 가능.)
- 데이터: `data/dummy/`의 더미 500 heat가 레포에 포함되어 있어 별도 준비 불필요.

#### requirements.txt (레포 루트, 정확히 아래 7줄)
```
streamlit
pandas
pyarrow
plotly
openai
pydantic
pydantic-settings
```

#### 완료 조건
- `streamlit run streamlit_app/app.py`가 OPENAI_API_KEY 없이도 예외 없이 기동.
- 4개 뷰 전환·heat 선택·지표 선택·기간 라디오가 동작.
- `git status`에 신규 파일 3개 외 변경 없음(기존 `M backend/app/llm/context_builder.py`는 이 작업 이전부터 존재 — 건드리지 말 것).

## 5. verifier 체크리스트

(보고서 본문에 전문 포함)

1. **스코프 격리**: `git status --porcelain` — 추가 파일이 `streamlit_app/app.py`, `streamlit_app/README.md`, `requirements.txt`, `docs/plans/streamlit-snapshot.md`뿐인지. `backend/**`·`frontend/**`에 이번 작업으로 인한 수정이 없는지. (주의: `M backend/app/llm/context_builder.py`는 작업 시작 전부터 존재하던 변경 — 코더 책임 아님. 그 외 backend 수정이 보이면 FAIL.)
2. **의존성 완결성**: 임시 가상환경(`python -m venv .venv-verify`)에서 루트 `requirements.txt`만 설치 → 아래 3·4 수행. (기존 `.venv`는 backend 의존성이 있어 누락을 가릴 수 있으므로 사용 금지.) 종료 후 `.venv-verify` 삭제. requirements.txt에 fastapi/uvicorn/httpx가 없는지 확인.
3. **데이터 계층 스모크** (streamlit 미개입, `.venv-verify`의 python으로 인라인 스크립트):
   - `sys.path.insert(0, "<repo>/backend")` 후 `ParquetHeatRepository(Path("<repo>/data/dummy"))` + `HeatService`로:
     `list_heats(None, None, 500)` 길이 500 / 첫 heat_id로 `get_heat` 성공 / `get_timeseries(id, None, 5.0)`의 series 3개(tag: active_power, o2_lance_flow, carbon_inj_rate) 각 points 비어있지 않음 / `get_kpi_trend(None, None)` 비어있지 않음 / `get_kpi_summary("day"|"week"|"month")` 각각 cards 8개.
   - `ContextBuilder().build_system_prompt(DashboardContext(view="heat_detail", heat_id="TEST"))`이 예외 없이 문자열 반환(DOMAIN_INFO.md 포함 여부 확인).
4. **기동 테스트 (secrets 없음)**: 환경변수 OPENAI_API_KEY 미설정 상태에서
   `streamlit run streamlit_app/app.py --server.headless true --server.port 8599` 백그라운드 기동 → 수 초 대기 → `curl http://localhost:8599` (PowerShell이면 `Invoke-WebRequest`) HTTP 200 확인 → stdout/stderr 로그에 Traceback 없음 확인 → 프로세스 종료. 채팅 비활성 안내 로직이 `st.info` 경로로 존재하는지 코드 확인(키 부재 시 `st.secrets[...]` 직접 인덱싱으로 예외 나는 패턴이 없는지).
5. **정적/계약 검토** (app.py 코드 리뷰):
   - `sys.path` 부트스트랩이 backend import보다 앞에 있는지, `REPO_ROOT`가 `Path(__file__)` 기반인지(cwd·하드코딩 경로 없음).
   - 태그명·단위·지표명·모델 id 하드코딩 없음 — `TAG_REGISTRY`/`specs.SPEC_REGISTRY`/`LLM_MODEL_OPTIONS` 참조.
   - `get_settings()`·`.env` 접근 없음. `sk-` 리터럴·실키 없음. tool-calling/SSE 재구현 없음.
   - 4개 render 함수 + Live 플레이스홀더 + chat 함수 존재, 뷰 id 문자열이 `heat_detail|trend|kpi_summary|live`.
6. **README**: 스냅샷 고지(c59ffe8, 업데이트 없음) + Main file path=`streamlit_app/app.py` + Secrets `OPENAI_API_KEY` 안내 포함.

## 6. 사용자 확인 필요 사항

1. **미커밋 변경 `backend/app/llm/context_builder.py`(git status M)**: Streamlit Cloud는 커밋된 상태를 배포한다. 이 변경을 (a) 폐기(`git checkout -- backend/app/llm/context_builder.py`)할지 (b) 이 브랜치에 커밋할지 결정 필요. streamlit 앱이 `ContextBuilder.build_system_prompt`/`DashboardContext`를 사용하므로, 커밋본과 작업본의 해당 시그니처가 같은지 커밋 전 확인 권장. (이번 작업 범위 밖 — 코더는 이 파일을 건드리지 않는다.)
2. **공개 범위**: 앱이 공개(public)면 URL을 아는 누구나 사용자 OpenAI 키로 채팅 가능(과금 발생) + DOMAIN_INFO.md 전문이 시스템 프롬프트로 전송됨. Streamlit Cloud 앱을 private(뷰어 인증)으로 설정할지 결정 필요. 기본 권고: private.
3. (참고, 결정 불요) 배포 전 이 브랜치를 GitHub 원격에 push해야 Cloud가 인식한다 — data/dummy 503개 parquet 포함 push.
