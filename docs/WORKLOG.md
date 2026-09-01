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

### 2026-08-31 — 대시보드 v1 완성 (planner→병렬 코딩→verifier 34개 체크포인트 전 항목 PASS)

**인터뷰 확정**: LLM 기본 gpt-5 / 3개 뷰 집중(Live 골격 유지) / 판정은 조업 스펙 밴드 / 서빙은 dev 2프로세스 + 8000 단일 포트 정적 서빙 둘 다. 계획 문서: `docs/plans/dashboard-v1.md`

- **백엔드**: `domain/specs.py` 스펙 레지스트리(11지표, 수치 유일 선언 지점) + `GET /api/meta/specs`·`/api/meta/materials`·`/api/heats/{id}/phases` 신규, `kpi/summary` 일/주/월 집계 실구현(카드 8종, 데이터 최신 date 기준 버킷 + 직전 버킷 대비), trend 행 확장(steel_group·EOP·장입), slag additions 키 정리(P3 반영), FastAPI가 frontend/dist 정적 서빙(SPA fallback, 경로 탈출 방지). pytest 17개 통과.
- **OpenAI 실동작 검증 완료**: gpt-5 + Responses API 스트리밍 실호출 성공(web_search tool "web_search" 수락, SDK 3.6.0). 예외→ERROR 이벤트 정규화, 키 마스킹. 스모크: `backend/scripts/smoke_openai.py`(비용 주의 — 필요 시에만 실행).
- **프론트**: 디자인 토큰 CSS 변수화(reference-naver.md 실측 준수 — 흰 배경/1% 틴트 카드/헤어라인 보더/단일 액센트 #0078d4/그림자 미사용), 채팅 패널 드래그 리사이즈(기본 25vw, 20~50vw 클램프), HeatDetail(페이즈 음영+용락 수직선+부원료 마커+태그별 서브플롯+스펙 판정 카드/표), Trend(지표 선택+기간 필터+그룹 색상+스펙 밴드+이탈 하이라이트+클릭→상세), KPI 요약(카드 8종+직전 대비), 채팅 마크다운/tool 칩/출처/조건부 자동 스크롤. 스펙·태그·페이즈 id 하드코딩 0건(전부 meta API 기반).
- 신규 의존성: react-markdown, remark-gfm.

**실행**: dev는 README 명령 그대로(8000+5173). 단일 포트는 `npm run build` 후 uvicorn 8000만 → http://localhost:8000 (빌드를 서버 기동 후 처음 만든 경우 서버 재기동 필요 — dist 존재 여부를 기동 시점에 평가).

### 2026-09-01 — 채팅 응답성 개선 (검증 7/7 PASS)

- **진단**: "무응답"의 실체는 gpt-5 reasoning 지연(도구 유발 시 첫 토큰 17~148초) + 대기 UI 부재. 백엔드/컨텍스트 주입은 정상.
- **수정**: ① 대기 인디케이터(경과 초·점 애니메이션·20초 지연 안내)+tool 실행 칩+응답 중단 버튼 ② SSE 하트비트(15초 무이벤트 시 ": ping" — 유휴 끊김 예방) ③ `GET /api/meta/llm` + `DiscussionRequest.model/reasoning_effort` 요청 단위 오버라이드(선택지는 `llm/options.py` 유일 선언) ④ 채팅 헤더 드롭다운(모델/추론 강도, meta 기반, 새로고침 없이 다음 전송부터 적용) ⑤ **기본값 gpt-5-mini + effort low로 전환** (사용자 지시).
- **실측**: TTFB 148초(gpt-5 기본) → **8.45초**(gpt-5-mini+low, 도구 1회 포함; 도구 미사용 단문은 수 초 내). 심층 분석은 드롭다운에서 gpt-5/high 선택.

### 2026-09-01 — 채팅 백엔드 Claude Agent SDK 전환 파일럿 (검증 전 항목 PASS)

- **OpenAI 경로 전면 폐기** (provider·tools 4종·options·관련 설정/테스트 삭제, openai 패키지 제거). 롤백 지점: 커밋 `c59ffe8`.
- **ClaudeAgentProvider** (`llm/claude_agent_provider.py`): claude-agent-sdk `query()` 하네스, cwd=프로젝트 루트(CLAUDE.md 오염 방지 위해 setting_sources=[] — 채팅 전용 시스템 프롬프트 명시 구성), 스트리밍 → 기존 StreamEvent 정규화, 트랜스크립트 기록 억제. 인증은 이 PC의 Claude Code 구독 로그인 상속(팀 배포 시 `.env`에 ANTHROPIC_API_KEY만 설정하면 전환).
- **모드 2종** (`llm/modes.py` 유일 선언 + `GET /api/meta/chat_modes`): 빠른 대화(quick, Haiku 4.5, 도구 차단, 1턴) / 심화 분석(deep, Opus 5, Read·Grep·Glob·WebSearch·WebFetch·제한 Bash(.venv 파이썬만), 25턴). 연산 정책(헤비 연산 사전 동의 문구·`.chat_tmp/` 격리)은 시스템 프롬프트에 준강제 주입.
- **프론트**: 모델/강도 드롭다운 폐기 → 모드 세그먼트 2버튼 + 비전공자용 안내 캡션, tool 칩 한국어 병기(파일 읽기/파이썬 분석 등).
- **실측**: quick TTFB **1.7초**(총 3.8초) / deep TTFB 18.3초·총 26초(Bash 3회) — deep은 첫 토큰까지 20초 내외가 정상(SLOW_HINT·하트비트로 UX 보호). **정확성 교차검증**: 모델이 답한 A171400 active_power 평균 98.34 MW·n=2393·범위 0.72~118.0이 pandas 독립 산출과 완전 일치(환각 아님).

## 2. 향후 계획 작업 명세

각 단계는 CLAUDE.md 에이전트 체계(planner 명세 → 코딩 → verifier)로 수행한다.

### P1(잔여). LiveView 실구현
- `LiveStreamService.stream` 실구현(과거 heat 시계열 실시간 재생, 재생 속도 파라미터) + 프론트 차트 append. 현재는 heartbeat 골격만.

### P2(잔여). Discussion 고도화
- `QueryTimeseriesStatsTool`의 페이즈별(용락 전/후) 구간 통계 구현 (data_tools.py TODO)
- 컨텍스트 note 자동 요약 채우기(현재 빈 문자열 전송), 프롬프트/tool 튜닝
- search_scholar 무료 키 발급 권장: semanticscholar.org/product/api#api-key-form (없으면 429 잦음)

### P3(잔여). 품질 정리
- `llm/tools/data_tools.py`의 llm→data 측면 의존 정리 검토, config 모듈 최상단 import 정리(sql_repository/providers/context_builder)
- plotly 번들 4.4MB → 코드 스플리팅 검토
- `main.py`의 dist 존재 평가를 기동 시점→요청 시점으로 개선 검토(빌드 후 재기동 불필요하게)

### P4. 사내 DB 연결
- `SqlHeatRepository` 구현: ConnectionStrategy(MSSQL=pyodbc, Oracle=oracledb) 주입식, 데이터 종류별 쿼리 어댑터. requirements.txt 주석 해제, `.env`의 `DATA_BACKEND=sql` 전환. 사내 스키마 확정 후 착수

### P5. 배포·전환 옵션
- `AnthropicProvider` 구현(Claude API + web_search tool) → `.env` 한 줄 전환
- 사내 서버 배포: 프론트 정적 빌드 서빙, CORS 도메인 제한, 간단 인증(소수 팀원)
- 더미 → 실데이터 전환 시 `.gitignore`의 data 제외 규칙 복원 (파일 내 주석 참조)

## 3. 참고

- 더미데이터는 저장소에 포함(사용자 결정: 더미이므로 공개 무방). `.env`만 각 PC에서 `.env.example` 기반으로 생성
- frontend-design 플러그인 설치됨(2026-08-31) — P1 뷰 디자인 작업 시 활용 가능
