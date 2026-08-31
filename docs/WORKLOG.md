# 작업 내역 및 향후 계획 (WORKLOG)

> 다른 PC에서 클론해도 맥락이 이어지도록 유지하는 문서. 작업 완료/계획 변경 시 갱신할 것.
> 최종 갱신: 2026-08-31

## 1. 완료된 작업

### 2026-08-31 — 프로젝트 초기 구축

**① 명세 확정 (인터뷰 3라운드)** → `SPEC.md`
- 스택: FastAPI + React(Vite/TS) / LLM: OpenAI 우선, Claude 전환 대비 provider 추상화 / 웹검색: LLM 내장 web_search + Semantic Scholar(무료) / 배포: 사내 서버·소수 팀원 / 대화 기록: 휘발성
- 4개 뷰(단일 heat 상세·트렌드·실시간·KPI 요약) + Discussion 사이드패널 한 화면 공존, 화면 컨텍스트 자동 주입

**② 스켈레톤 구축** (백엔드 pytest 통과 / 프론트 빌드 성공 검증 완료)
- 백엔드: 레이어드 구조 `api → services → (data | llm) → domain`. `HeatRepository` ABC(parquet↔SQL 교체), `LLMProvider` ABC(OpenAI↔Claude 교체), `TagRegistry` 선언 중심 태그 관리, Discussion SSE 파이프라인, 학술검색 tool
- 프론트: AppLayout(대시보드+채팅 공존), 4개 뷰, zustand store(dashboardContext→채팅 자동 주입), PlotlyChart wrapper, SSE 채팅 훅

**③ 에이전트 체계 확립** → `.claude/agents/`, CLAUDE.md "에이전트 운영" 섹션
- planner(Fable 5) / backend-coder(Opus 5) / frontend-coder(Opus 5) / verifier(Opus 5). main은 오케스트레이션 전담. 흐름: planner 명세 → 코딩(병렬) → verifier 검증

**④ 더미데이터 생성** (planner→coder→verifier 체계로 수행, 검증 전 항목 PASS) → `docs/plans/dummy-data-generation.md`
- 500 heat (A171400~A176390), 2026-08-01부터 ~19.5일, 1초 시계열 3태그(active_power/o2_lance_flow/carbon_inj_rate), heats.parquet(26컬럼)+additions.parquet, seed 42 재현 가능
- 물리 정합: KPI가 시계열 적분에서 파생(원단위 오차 ≤0.004%), 용락=누적 전력 70~75%, 붕락 시 산소 스텝(90~110 kWh/t), 강종 그룹 3개(high/mid/low) 패턴 연동, 이상치 2~3%
- API 확장: `GET /api/heats/{id}/additions`, `HeatSummary.steel_group`, `domain/materials.py`(코드·라벨 유일 선언)

**주요 확정/편차 사항 (맥락 유지용)**
- 전력원단위 380~410 kWh/t와 POT 33~40분 양립을 위해 전력 레벨 상향 확정: 용해기 100~110 MW / 용락 후 90~95 MW (원안 최대 90 MW에서 사용자 조정, 2026-08-31 인터뷰)
- 수율 모델: 명세 N(92.5%, 0.7%)는 출강 148~153t 제약과 수학적으로 양립 불가 → 출강 목표에서 역산, 결과 수율 평균 93.95%
- POT 실분포는 36.4~40.3분(밴드 상반부 집중). 계약 충족이나 33~36분대가 필요하면 생성기 조정 필요

## 2. 향후 계획 작업 명세

각 단계는 CLAUDE.md 에이전트 체계(planner 명세 → 코딩 → verifier)로 수행한다.

### P1. 대시보드 실데이터 완성 (다음 작업, 우선순위 최상)
- **HeatDetailView**: 페이즈 구간 음영(BORE_IN~TAPPING) + 용락/출강 이벤트 수직선 + 부원료 투입 마커(additions API), 태그 그룹별 서브플롯(전력/산소/분탄 개별 y축), 정적 패널을 JSON pre → 정식 표/카드로 (KPI·EOP·슬래그·장입 한국어 라벨은 meta API/materials 기반)
- **TrendView**: KPI 선택 UI, 기간 필터(dashboardContext.setPeriod 연동), 강종 그룹별 색상 구분, heat 클릭 → 상세 뷰 이동
- **KpiSummaryView**: 백엔드 `HeatService.get_kpi_summary` 집계 구현(일/주/월: 생산량 합, 평균 원단위, 평균 수율 등) + 프론트 카드 UI
- **LiveView**: `LiveStreamService.stream` 실구현(과거 heat 시계열 실시간 재생, 재생 속도 파라미터) + 프론트 차트 append
- 병렬화: KPI 집계·Live 백엔드(backend-coder) ↔ 차트/뷰(frontend-coder), 계약은 planner가 사전 고정

### P2. Discussion 실동작 검증·고도화
- OpenAIProvider 스트리밍 이벤트 필드를 SDK 실호출로 검증/보정 (`llm/openai_provider.py`의 스켈레톤 주석 참조)
- tool 실동작 확인: query_heat_detail/query_timeseries_stats/query_kpi_trend + 내장 web_search + search_scholar(무료 키 발급 권장: semanticscholar.org/product/api#api-key-form)
- `QueryTimeseriesStatsTool`의 페이즈별(용락 전/후) 구간 통계 구현 (data_tools.py TODO)
- 프론트: 마크다운 렌더링, 출처(citation) UI 정리, 컨텍스트 note 자동 요약 채우기

### P3. 품질 정리 (verifier 지적 사항)
- `Heat.slag.additions_kg` 키 규약 통일: `group("slag_add_")`가 `_kg` 접미사를 남김(`file_repository.py`) — `_baskets`처럼 suffix 제거로 통일
- `llm/tools/data_tools.py`의 llm→data 측면 의존 정리 검토, config 모듈 최상단 import 정리(sql_repository/providers/context_builder)
- 테스트 확충(생성 데이터 기반 계약 테스트)

### P4. 사내 DB 연결
- `SqlHeatRepository` 구현: ConnectionStrategy(MSSQL=pyodbc, Oracle=oracledb) 주입식, 데이터 종류별 쿼리 어댑터. requirements.txt 주석 해제, `.env`의 `DATA_BACKEND=sql` 전환. 사내 스키마 확정 후 착수

### P5. 배포·전환 옵션
- `AnthropicProvider` 구현(Claude API + web_search tool) → `.env` 한 줄 전환
- 사내 서버 배포: 프론트 정적 빌드 서빙, CORS 도메인 제한, 간단 인증(소수 팀원)
- 더미 → 실데이터 전환 시 `.gitignore`의 data 제외 규칙 복원 (파일 내 주석 참조)

## 3. 참고

- 더미데이터는 저장소에 포함(사용자 결정: 더미이므로 공개 무방). `.env`만 각 PC에서 `.env.example` 기반으로 생성
- frontend-design 플러그인 설치됨(2026-08-31) — P1 뷰 디자인 작업 시 활용 가능
