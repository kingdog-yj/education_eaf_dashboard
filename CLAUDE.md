# CLAUDE.md

전기로(EAF, Electric Arc Furnace) 제강 공정 분석 대시보드 & Discussion 웹 애플리케이션.

## 프로젝트 개요

1. **공정 데이터 연결**: heat(1회 조업 사이클) 단위의 시계열 데이터(1초 샘플링: 전력/화학에너지/온도·부생 계통)와 정적 데이터(스크랩 장입, KPI, 종점(EOP), 슬래그). 현재는 parquet/csv 더미데이터(~500 heat), 향후 사내 DB(MSSQL/Oracle 혼재, pyodbc/oracledb) 연결.
2. **인터랙티브 대시보드**: 단일 heat 상세 / 다수 heat 트렌드·비교 / 실시간 모니터링 / KPI 요약 — 4개 뷰.
3. **Discussion**: 대시보드와 한 화면에 공존하는 LLM 채팅 사이드패널. 현재 보고 있는 화면 컨텍스트 자동 주입 + 데이터 조회 tool + 웹/학술 검색. 업계 전문가(엔지니어·연구원·교수)와 디스커션하는 수준의 UX가 목표.

상세 명세: `SPEC.md` · 도메인 지식: `DOMAIN_INFO.md` (지속 업데이트됨 — 공정 관련 판단 전 반드시 참조)

## 핵심 설계 원칙 (필수 준수)

- **객체지향 + 확장/수정/유지보수 용이성이 최우선 지침이다.** 모든 교체 가능 지점은 추상화(ABC) 뒤에 둔다:
  - 데이터 소스: `HeatRepository` ABC → `ParquetHeatRepository`(현재) / `SqlHeatRepository`(향후 MSSQL·Oracle)
  - LLM: `LLMProvider` ABC → `OpenAIProvider`(현재) / `AnthropicProvider`(향후 전환 예정)
  - LLM tool: `DiscussionTool` ABC + 레지스트리 등록 방식
- **선언 중심 확장**: 시계열 태그는 `backend/app/domain/tags.py`의 TagRegistry에만 선언한다. 태그 추가/샘플링 주기 변경이 레지스트리 수정만으로 끝나야 하며, 태그명·주기를 다른 곳에 하드코딩하지 않는다. KPI, 뷰도 같은 원칙.
- **레이어 의존 방향**: `api → services → (data | llm) → domain`. 역방향 금지. `domain`은 순수 모델만.
- 설정값(provider 선택, 데이터 백엔드, 경로)은 `.env` + `config.py`로. 코드에 하드코딩 금지.

## 에이전트 운영 (필수 준수)

**main 세션은 오케스트레이션 전담이다.** 코드 구현과 기능 검증을 main이 직접 수행하지 않고 `.claude/agents/`의 전문 에이전트에 위임한다. main의 역할: 요구사항 접수 → planner 위임 → 코딩 에이전트 병렬 실행 → verifier 검증 → 결과 통합 및 사용자 보고.

| 에이전트 | 모델 | 역할 |
|---|---|---|
| `planner` | **Fable 5** (`fable`) | 요구사항을 Claude Code 작업에 최적화된 명세로 구조화: 작업 분해, 병렬화 경계·API 계약 고정, 코딩/검증 에이전트용 실행 프롬프트 작성 |
| `backend-coder` | **Opus 5** (`opus`) | `backend/` Python/FastAPI 구현 (명세 단순 구현) |
| `frontend-coder` | **Opus 5** (`opus`) | `frontend/` React/TS 구현 (명세 단순 구현) |
| `verifier` | **Opus 5** (`opus`) | 테스트/빌드/API 계약/설계 원칙 검증. 코드 수정 없이 리포트만 |

운영 규칙:
- 구현 작업은 **planner 명세 → 코딩 → 검증** 순서를 기본으로 한다. 사소한 단일 파일 수정도 코딩 에이전트에 위임한다(main이 직접 편집하지 않음).
- 독립 작업(예: 백엔드 ↔ 프론트엔드)은 **한 메시지에서 동시 스폰하여 병렬 실행**한다. 같은 에이전트도 독립 작업이면 복수 인스턴스 병렬 실행 가능.
- 병렬 실행 전 결합 지점(API 스키마: `models.py` ↔ `types.ts`, `StreamEvent`, 엔드포인트)은 planner가 계약으로 고정하여 각 에이전트 프롬프트에 동일하게 포함시킨다.
- 검증 FAIL 시 verifier 리포트를 해당 코딩 에이전트에 전달(SendMessage로 기존 컨텍스트 이어가기)하여 수정 후 재검증한다.
- 에이전트를 더 잘게 쪼개지 않는다 — 위 4개의 큰 기능 단위를 유지하고, 필요 시 인스턴스 수로 병렬성을 확보한다.

## 아키텍처

```
backend/app/
  domain/     # Pydantic 모델(Heat, ChargeInfo, KpiInfo, EopInfo, SlagInfo), TagRegistry, HeatPhase
  data/       # HeatRepository ABC, ParquetHeatRepository, SqlHeatRepository(stub), dummy/generator
  llm/        # LLMProvider ABC, OpenAIProvider, AnthropicProvider(stub), ContextBuilder, tools/
  services/   # heat_service, live_service(실시간 시뮬레이션), discussion_service
  api/routes/ # heats, kpi, live(WS), discussion(SSE), meta
frontend/src/
  layout/     # AppLayout: 대시보드 + Discussion 사이드패널 공존
  views/      # HeatDetailView, TrendView, LiveView, KpiSummaryView
  discussion/ # DiscussionPanel, useChatStream (SSE)
  state/      # zustand: dashboardContext(채팅에 자동 주입), chatStore(휘발성)
  components/charts/  # PlotlyChart wrapper
data/dummy/   # parquet 더미 (git 제외, 아직 미생성)
```

## 명령어

```bash
# 백엔드 (프로젝트 루트에서, .venv 사용)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --app-dir backend   # http://localhost:8000
.venv/Scripts/python.exe -m pytest backend/tests

# 프론트엔드
cd frontend && npm run dev     # http://localhost:5173 (API는 8000으로 프록시)
cd frontend && npm run build
```

## 도메인 필수 지식 (요약 — 전문은 DOMAIN_INFO.md)

- **heat** = 1회 조업 사이클(장입→용해→승온·정련→출강), batch 공정. tap-to-tap 통상 40~70분, 일 20~30 heat.
- **조업 페이즈** (`domain/phases.py` enum): BORE_IN(천공) → EXPANSION(천공 확장/붕락) → MELTDOWN(용락) → REFINING(승온·정련) → TAPPING(출강). **용락(meltdown)** = 잔류 스크랩이 용강 수면 아래로 잠기는 시점으로, 전후로 아크 안정도·조업 방식이 급변하는 최중요 이벤트.
- 에너지: 전기(아크) ~2/3 + 화학에너지(산소 랜싱에 의한 Fe/C 산화, 분탄 인젝션) ~1/3. 슬래그 포밍(FeO+C→CO)이 아크 효율의 핵심.
- 종점 관리: 출강 온도 ~1600°C, 탈탄·탈린(C, P), 슬래그 염기도(CaO/SiO₂).
- Discussion 프롬프트/분석 코드 작성 시 이 용어 체계(한국어 + 영문 병기)를 일관되게 사용할 것.

## 주의사항

- **`.env`에 실제 API 키가 있다. 절대 커밋/출력/외부 전송 금지.** (.gitignore로 제외됨)
- **더미데이터 생성은 사용자 승인 후에만 실행한다.** 생성기(`data/dummy/generator.py`)는 스켈레톤 유지, 임의로 `generate` 실행하지 않는다.
- 더미데이터는 개발 단계에서 필드 수 최소화(로딩 시간 최소화) — 태그 프로필은 SPEC.md §4.1.
- LLM 호출 응답은 SSE 스트리밍이 기본. provider 중립 `StreamEvent`로 정규화하여 프론트에 전달.
- 대화 이력은 서버에 저장하지 않는다(휘발성). 매 요청에 프론트가 이력을 전송.
- UI 텍스트는 한국어(기술 용어 영문 병기).
