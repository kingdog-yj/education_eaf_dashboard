# EAF 공정 분석 대시보드 & Discussion 웹앱 — 명세서 (SPEC)

> 작성일: 2026-08-31 · 인터뷰(3라운드) 결과를 반영한 확정 명세.
> 도메인 지식은 [DOMAIN_INFO.md](DOMAIN_INFO.md) 참조 (지속 업데이트 예정).

## 1. 목표

전기로(EAF) 제강 공정 데이터를 (1) 연결/확보하고, (2) 인터랙티브 대시보드로 조회·검토·모니터링하며, (3) 그 결과와 트렌드에 대해 **업계 전문가(엔지니어/연구원/교수)와 디스커션하는 수준**의 자연어 심화 분석을 제공하는 웹 애플리케이션.

## 2. 확정 요구사항 (인터뷰 결과)

| 항목 | 결정 |
|---|---|
| 기술 스택 | **FastAPI(백엔드) + React(프론트엔드, Vite/TypeScript)** |
| LLM | **OpenAI 우선 개발**, 향후 Claude API 전환 가능하도록 **provider 추상화 계층** 필수 |
| 웹 검색 | **LLM 내장 웹 검색**(OpenAI web_search tool) + **학술 특화 API**(Semantic Scholar, arXiv, CrossRef) 병행 |
| 배포 | 사내 서버, 소수 팀원 사용. 사내망에서 외부 API(LLM/검색) 접근 가능 전제 |
| 시계열 태그 | 전력 계통 + 화학에너지 계통 + 온도/부생 계통 (전극/기계 계통은 현재 제외, 확장 가능 구조) |
| 샘플링 주기 | **1초 가정**, 태그별 주기 변경이 용이한 구조 |
| 정적 데이터 | 스크랩 장입 상세 + 조업 결과 KPI + 종점(EOP) 정보 + 슬래그/부재료 (전 그룹 포함) |
| 실 DB | Oracle/MSSQL **혼재** → Repository 패턴으로 추상화, pyodbc/oracledb 어댑터는 향후 구현 |
| 더미데이터 | **parquet/csv 파일**, 약 **500 heat** 규모. 개발 단계에서는 **필드 수 최소화**로 로딩 시간 단축. **생성은 별도 승인 후 진행** (현재 생성기 스켈레톤만) |
| 화면 구성 | 단일 heat 상세 / 트렌드·비교 / 실시간 모니터링 / KPI 요약 — 4개 뷰 모두. **대시보드와 Discussion 채팅이 한 화면에 공존**(사이드패널), 대시보드와 상호작용하며 대화 |
| Discussion 컨텍스트 | 현재 보고 있는 heat/트렌드 데이터를 **자동 주입** + LLM이 추가 데이터를 조회할 수 있는 tool 제공 |
| 대화 기록 | **휘발성** (서버 저장 안 함, 브라우저 세션 동안만 유지) |
| 설계 원칙 | **객체지향 + 확장/수정/유지보수 용이성**을 최우선 기본 지침으로 함 (CLAUDE.md에 명시) |

## 3. 시스템 아키텍처

```
┌────────────────────────── Browser (React/Vite/TS) ──────────────────────────┐
│  AppLayout: [대시보드 뷰 영역]  ←공존→  [Discussion 사이드패널]              │
│   · HeatDetailView   · TrendView                                            │
│   · LiveView         · KpiSummaryView                                       │
│   · dashboardContext store(zustand): 현재 뷰/선택 heat/기간 → 채팅에 주입    │
└──────────┬───────────────────────────────┬──────────────────────────────────┘
           │ REST /api/*                   │ SSE /api/discussion  · WS /api/live
┌──────────▼───────────────────────────────▼──────────────────────────────────┐
│                          FastAPI (backend/app)                              │
│  api/routes ─→ services ─→ data(Repository ABC) ─→ file(parquet) | sql(향후)│
│                    │                                                        │
│                    └─→ llm(LLMProvider ABC) ─→ OpenAI(현재) | Anthropic(향후)│
│                         · ContextBuilder(대시보드 컨텍스트 → 프롬프트)       │
│                         · Tools: 데이터 조회 / 학술 검색 / LLM 내장 웹검색   │
└─────────────────────────────────────────────────────────────────────────────┘
```

레이어 규칙: `api → services → (data | llm) → domain`. 역방향 의존 금지. `domain`은 순수 모델/레지스트리만 가지며 어디에도 의존하지 않는다.

## 4. 데이터 모델

### 4.1 시계열 (heat별 1초 단위)

태그는 코드 곳곳에 하드코딩하지 않고 **`domain/tags.py`의 TagRegistry 한 곳에 선언**한다. 태그 추가/샘플링 주기 변경은 레지스트리 선언 수정만으로 완결되어야 한다.

개발 단계 최소 태그 프로필(로딩 시간 최소화, 인터뷰 결정):

| group | tag id | 단위 | 설명 |
|---|---|---|---|
| electrical | `active_power` | MW | 유효전력 |
| electrical | `energy_total` | kWh | 누적 전력량 |
| electrical | `tap_position` | - | 변압기 탭 |
| chemical | `o2_lance_flow` | Nm³/h | 산소 랜싱 유량 |
| chemical | `carbon_inj_rate` | kg/min | 분탄 인젝션 속도 |
| thermal | `panel_temp` | °C | 수냉 패널 온도(대표) |
| thermal | `offgas_temp` | °C | 배가스 온도 |

확장 예약(레지스트리에 주석으로 명시): 전압/전류/아크안정도, 누적 산소량, 버너 유량, off-gas 성분(CO/CO₂/O₂), 전극 위치 등.

### 4.2 heat 정적 데이터

`domain/models.py`의 Pydantic 모델. 그룹별 서브모델로 분리하여 그룹 추가가 용이하도록 한다.

- **HeatSummary**: `heat_id`, `date`, `shift`, 이벤트 시각(`power_on`, `meltdown`(용락), `tap_start`, `tap_end`)
- **ChargeInfo** (장입): 바스켓별 × 스크랩 등급별 장입량(dict), 총 장입량(t), hot heel(t)
- **KpiInfo** (조업 결과): 전력원단위(kWh/t), 산소원단위(Nm³/t), power-on time(min), tap-to-tap(min), 출강량(t), 수율(%)
- **EopInfo** (종점): 출강 온도(°C), 종점 성분 {C, P, S, Mn}(%)
- **SlagInfo** (슬래그/부재료): {FeO, CaO, SiO₂, MgO}(%), 염기도(CaO/SiO₂), 생석회/돌로마이트 투입량(kg)

### 4.3 조업 페이즈

DOMAIN_INFO.md의 공정 흐름을 enum으로 코드화: `BORE_IN → EXPANSION(천공 확장) → MELTDOWN(용락 후) → REFINING(승온/정련) → TAPPING(출강)`. 시계열 차트의 구간 주석과 LLM 디스커션의 공통 어휘로 사용.

### 4.4 저장 포맷 (더미 단계)

- `data/dummy/heats.parquet` — 정적 데이터 (500행, heat당 1행)
- `data/dummy/timeseries/{heat_id}.parquet` — heat별 시계열 (long format: `ts`, `tag`, `value`)
- **아직 생성하지 않음.** `DummyHeatGenerator`는 페이즈 기반 물리적 개연성(예: 용락 전 아크 불안정 → 용락 후 안정, 정련기 온도 상승)을 반영하도록 설계하고, 생성 실행은 별도 지시에 따름.

## 5. 백엔드 설계

### 5.1 데이터 액세스 — Repository 패턴

```python
class HeatRepository(ABC):          # data/repository.py
    def list_heats(period, filters) -> list[HeatSummary]
    def get_heat(heat_id) -> Heat            # 정적 전체
    def get_timeseries(heat_id, tags, downsample) -> TimeseriesFrame
    def get_kpi_trend(period, kpis) -> KpiTrendFrame
```

- `ParquetHeatRepository` (현재): parquet/csv 로딩, 다운샘플링 지원(차트 성능)
- `SqlHeatRepository` (향후): pyodbc(MSSQL)/oracledb(Oracle) — DSN별 어댑터 주입. **혼재 DB 대응을 위해 connection 전략도 주입식으로 설계**
- 선택은 `.env`의 `DATA_BACKEND`로 결정 (factory)

### 5.2 LLM — Provider 추상화

```python
class LLMProvider(ABC):             # llm/base.py
    async def stream_chat(messages, tools, system) -> AsyncIterator[StreamEvent]
```

- `OpenAIProvider` (현재): Responses API, **내장 web_search tool 활성화**, function tool 브릿지
- `AnthropicProvider` (향후 스텁): Claude API + server-side web_search tool
- `StreamEvent`: `text_delta | tool_call | tool_result | citation | done` — provider 중립 이벤트로 정규화하여 프론트가 provider를 몰라도 되게 함

### 5.3 Discussion 파이프라인

1. 프론트가 메시지 + **DashboardContext**(현재 뷰, 선택 heat_id, 조회 기간, 표시 중 태그) 전송
2. `ContextBuilder`가 컨텍스트를 시스템 프롬프트로 렌더링: DOMAIN_INFO.md 요약 + 현재 화면 데이터 요약(경량) 포함
3. LLM tools (`llm/tools/`):
   - `query_heat_detail`, `query_timeseries_stats`, `query_kpi_trend` — 서버 데이터 심층 조회
   - `search_scholar` — Semantic Scholar/arXiv/CrossRef (키 불필요, 무료)
   - 웹 검색은 provider 내장 tool 사용 (별도 구현 없음)
4. SSE로 스트리밍 응답 (인용/출처 이벤트 포함)
5. 대화 이력은 서버에 저장하지 않음 (요청마다 프론트가 이력 전체 전송)

### 5.4 API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/heats` | heat 목록 (기간/필터) |
| GET | `/api/heats/{heat_id}` | 정적 데이터 전체 |
| GET | `/api/heats/{heat_id}/timeseries` | 시계열 (tags, downsample 파라미터) |
| GET | `/api/kpi/trend` | 기간별 KPI 트렌드 |
| GET | `/api/kpi/summary` | 일/주/월 KPI 요약 |
| WS | `/api/live` | 실시간 모니터링 스트림 (더미: 시뮬레이션 재생) |
| POST | `/api/discussion` | 채팅 (SSE 스트리밍 응답) |
| GET | `/api/meta/tags` | TagRegistry 조회 (프론트 차트 구성용) |

## 6. 프론트엔드 설계

- **AppLayout**: 좌측 네비(4개 뷰 전환) + 중앙 대시보드 + **우측 Discussion 사이드패널(접기/펼치기)**. 뷰를 전환해도 채팅 상태 유지.
- **상태**: zustand — `dashboardContext` (현재 뷰/heat/기간/태그)와 `chatStore` (메시지 목록, 휘발성). 대시보드 조작 시 `dashboardContext`가 갱신되고 다음 채팅 메시지에 자동 첨부.
- **차트**: plotly.js (자체 얇은 React wrapper `PlotlyChart`). 멀티트랙 시계열 + 페이즈 구간 음영 + 이벤트(용락 등) 수직선.
- **채팅 스트리밍**: fetch + ReadableStream으로 SSE 파싱, 마크다운 렌더링, 출처(citation) 표시.
- **실시간 뷰**: WebSocket 수신 → 차트 append.
- UI 언어: 한국어 (기술 용어는 영문 병기).

## 7. 전문 지식 검색 환경

| 채널 | 방식 | 키 필요 |
|---|---|---|
| 일반 웹/테크니컬 페이퍼 | OpenAI 내장 `web_search` tool | 기존 OPENAI_API_KEY로 충분 |
| 학술 논문 | Semantic Scholar Graph API | 불필요 (무료; 대량 사용 시 무료 키 발급 가능) |
| 프리프린트 | arXiv API | 불필요 |
| DOI/서지 | CrossRef API | 불필요 |
| 도메인 지식 | DOMAIN_INFO.md → 시스템 프롬프트 주입 | - |

→ **추가 MCP/유료 검색 API 불필요.** 개발 환경(Claude Code)에는 WebSearch/WebFetch가 내장되어 있어 개발 중 조사도 별도 설정 없이 가능.

## 8. 향후 로드맵 (스켈레톤에 반영된 확장 지점)

1. 더미데이터 생성기 구현 및 생성 (승인 후) → 대시보드 실동작
2. Discussion 품질 고도화 (프롬프트/tool 튜닝, DOMAIN_INFO.md 확충)
3. 사내 DB 연결: `SqlHeatRepository` 구현 (MSSQL/Oracle 혼재 어댑터)
4. Claude API 전환 옵션: `AnthropicProvider` 구현 후 `.env` 한 줄 변경
5. 다중 사용자 대비: 간단 인증, 필요 시 대화 저장 옵션

## 9. 개발 원칙 (요약 — CLAUDE.md에 전문)

- 객체지향, 인터페이스(ABC) 우선. 구현 교체 지점(데이터 소스, LLM, 태그 구성)은 반드시 추상화 뒤에 둔다.
- 설정은 코드가 아닌 `.env`/레지스트리로. 하드코딩 금지.
- 태그·KPI·뷰 추가가 "선언 추가"만으로 가능해야 한다.
