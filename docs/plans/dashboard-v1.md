# 작업 계획: 대시보드 v1 완성 (3개 뷰 + Discussion 실동작 + 단일 포트 서빙)

> 작성: planner · 2026-08-31 · 사용자 인터뷰 확정 요구사항 기반
> 근거: CLAUDE.md, SPEC.md, docs/WORKLOG.md(P1~P3), docs/reference-naver.md(디자인 지침), docs/plans/dummy-data-generation.md(데이터 스키마)

---

## 1. 목표·범위

- **완성**: HeatDetailView / TrendView / KpiSummaryView 3개 뷰 실구현. LiveView는 현 골격(연결 확인) 유지 — 수정 금지.
- **Discussion**: OpenAI(gpt-5) 실호출 스트리밍 대화 동작 + 프론트 채팅 UX(마크다운/tool 표시/출처/자동 스크롤).
- **서빙**: dev 2프로세스(8000+5173) 유지 + FastAPI가 `frontend/dist` 정적 서빙(SPA fallback, 8000 단일 포트).
- **디자인**: docs/reference-naver.md 실측 토큰 준수 재설계(다크 사이드바 제거).
- **판정**: 조업 스펙 밴드를 `backend/app/domain/specs.py`에 선언 → `GET /api/meta/specs`로 제공. 프론트 수치 하드코딩 금지.

## 2. 작업 분해·실행 순서

| 단위 | 에이전트 | 의존 |
|---|---|---|
| U1. 백엔드: specs/kpi summary/phases/materials/정적서빙/slag 키 수정/OpenAI 검증 | backend-coder ×1 | 없음 (병렬) |
| U2. 프론트: 디자인 시스템/리사이즈 패널/3개 뷰/채팅 UX/차트 테마 | frontend-coder ×1 | 없음 (병렬) — §3 계약만 의존 |
| U3. 검증 | verifier ×1 | U1·U2 완료 후 |

- 더 잘게 쪼개지 않는다: 백엔드 항목들은 specs.py 선언을 공유(집계·트렌드·판정이 같은 레지스트리 참조)하는 응집 단위, 프론트 항목들은 디자인 토큰을 공유하는 응집 단위.
- U1·U2는 **한 메시지에서 동시 스폰**. 결합 지점은 §3 계약으로 고정되어 양쪽 프롬프트에 동일 포함됨.

## 3. 고정 계약 (두 코더 공통 — 임의 변경 금지)

### C1. `GET /api/meta/specs` — 지표/스펙 레지스트리 (신규)

`backend/app/domain/specs.py`의 `SPEC_REGISTRY` 직렬화. 배열 원소:

```json
{ "id": "kpi_energy_kwh_per_t", "label_ko": "전력원단위", "unit": "kWh/t", "decimals": 1, "lo": 380.0, "hi": 410.0 }
```

- `id` = heats.parquet 평탄 컬럼명 = KPI 트렌드 행의 키 (기존 규약과 동일).
- `lo`/`hi`가 `null`이면 밴드 없음(트렌드 선택용 지표로만 사용).
- 확정 목록 (11개, 이 순서):

| id | label_ko | unit | decimals | lo | hi |
|---|---|---|---|---|---|
| kpi_energy_kwh_per_t | 전력원단위 | kWh/t | 1 | 380 | 410 |
| kpi_o2_nm3_per_t | 산소원단위 | Nm³/t | 1 | null | null |
| kpi_carbon_kg_per_t | 탄소원단위 | kg/t | 1 | null | null |
| kpi_power_on_min | Power-on Time (POT) | min | 1 | 33 | 40 |
| kpi_tap_to_tap_min | Tap-to-Tap | min | 1 | null | null |
| kpi_tap_weight_t | 출강량 | t | 1 | 148 | 153 |
| kpi_yield_pct | 수율 | % | 1 | null | null |
| eop_tap_temp_c | 출강 온도 | °C | 0 | 1590 | 1620 |
| eop_comp_c | 종점 C | % | 3 | 0.03 | 0.10 |
| eop_comp_p | 종점 P | % | 3 | 0.010 | 0.030 |
| charge_total_t | 총 장입량 | t | 1 | 155 | 165 |

- **스펙 이탈 판정**: 밴드 있는 지표 중 하나라도 값이 `[lo, hi]` 밖(경계 포함 = 정상)이면 해당 heat는 이탈. 결측값은 판정 제외.

### C2. `GET /api/kpi/summary?period=day|week|month` (실구현)

```json
{
  "period": "day",
  "bucket_start": "2026-08-20T00:00:00", "bucket_end": "2026-08-21T00:00:00",
  "prev_bucket_start": "2026-08-19T00:00:00",
  "cards": [
    { "id": "heat_count", "label_ko": "Heat 수", "unit": "heat", "decimals": 0,
      "value": 24.0, "prev_value": 26.0, "spec_id": null }
  ]
}
```

- **버킷 기준**: 데이터의 최신 heat `date`(현재 시각 아님 — 더미는 2026-08 고정). day=달력일, week=ISO 주(월요일 시작), month=달력월. `prev_value` = 직전 버킷 동일 집계(heat 없으면 null).
- 데이터 없음: `{"period": ..., "bucket_start": null, "bucket_end": null, "prev_bucket_start": null, "cards": []}`.
- **카드 8종 고정 (이 id·순서)**:

| id | label_ko | unit | decimals | 집계 | spec_id |
|---|---|---|---|---|---|
| heat_count | Heat 수 | heat | 0 | count | null |
| production_t | 생산량 합 | t | 0 | sum(kpi_tap_weight_t) | null |
| avg_energy_kwh_per_t | 평균 전력원단위 | kWh/t | 1 | mean(kpi_energy_kwh_per_t) | kpi_energy_kwh_per_t |
| avg_o2_nm3_per_t | 평균 산소원단위 | Nm³/t | 1 | mean(kpi_o2_nm3_per_t) | null |
| avg_power_on_min | 평균 Power-on Time | min | 1 | mean(kpi_power_on_min) | kpi_power_on_min |
| avg_tap_to_tap_min | 평균 Tap-to-Tap | min | 1 | mean(kpi_tap_to_tap_min) | null |
| avg_yield_pct | 평균 수율 | % | 1 | mean(kpi_yield_pct) | null |
| out_of_spec_count | 스펙 이탈 Heat 수 | heat | 0 | C1 판정 위반 heat 수 | null |

- 프론트 색상 규칙: `spec_id`가 있고 value가 밴드 밖 → 이탈색(danger). `out_of_spec_count`는 value>0 → 이탈색. 그 외 기본색.

### C3. `GET /api/kpi/trend` 행 키 확장 (기존 변경)

행 키 = `heat_id`, `date`, `steel_group` + 모든 `kpi_*` 컬럼 + SPEC_REGISTRY의 비-kpi 컬럼(`eop_tap_temp_c`, `eop_comp_c`, `eop_comp_p`, `charge_total_t`). date 오름차순. 컬럼 목록은 하드코딩하지 않고 SPEC_REGISTRY에서 파생(df에 존재하는 것만).

### C4. `GET /api/heats/{heat_id}/phases` (신규)

```json
[ { "phase": "bore_in", "label_ko": "천공 (bore-in)", "start": "2026-08-20T06:00:00", "end": "2026-08-20T06:03:00" } ]
```

- `phase` = `HeatPhase` enum 값. 이벤트 기반 산출(서비스 계층), 산출 불가 페이즈는 **배열에서 생략**. 시간 오름차순.
- 산출 규칙(휴리스틱 — `domain/phases.py`에 상수 선언, §8 참조):
  - `power_off` = `power_on + kpi.power_on_min분` (kpi 결측 시 meltdown 이후 페이즈 일부 생략 허용)
  - BORE_IN: `[power_on, power_on + BORE_IN_DURATION_S]` (단 meltdown/power_off 초과 금지)
  - EXPANSION: `[BORE_IN 끝, meltdown]` (meltdown 있을 때)
  - MELTDOWN: `[meltdown, meltdown + MELTDOWN_SETTLE_S]` (power_off 초과 금지)
  - REFINING: `[MELTDOWN 끝, power_off]`
  - TAPPING: `[tap_start, tap_end]` (둘 다 있을 때)
  - 길이 0 이하 구간은 생략.
- 프론트는 배열을 **일반적으로**(페이즈 id 하드코딩 없이) 음영 렌더.

### C5. `GET /api/meta/materials` (신규)

```json
{ "scrap_grades": {"grade_a": "A급", "shredder": "슈레더", "turnings": "선반설", "common": "일반"},
  "addition_materials": {"lime": "생석회", "lump_carbon": "괴탄"},
  "steel_groups": {"high": "고급강종", "mid": "일반강종", "low": "저급 배합"} }
```

`domain/materials.py`의 3개 dict 그대로 (라벨 유일 선언 지점 유지).

### C6. 기존 스키마 변경분·프론트 타입 반영

- **`Heat.slag.additions_kg` 키 변경**: `"lime_kg"` → `"lime"` (`_kg` 접미사 제거, `ADDITION_MATERIALS` 코드와 일치 — WORKLOG P3).
- `HeatSummary.steel_group: str` — 백엔드는 이미 제공, **types.ts에 추가**.
- `GET /api/heats/{id}/additions` → `AdditionEvent { ts, material, label_ko, amount_kg }` (기존 엔드포인트 — 프론트 타입·클라이언트 신규 반영).
- `StreamEvent`/`ChatMessage`/`DashboardContextPayload`/`HeatTimeseries`/`TagMeta`/`PhaseMeta`: **변경 없음**.

프론트 타입 정의(=types.ts에 이 형태로 추가):

```ts
export interface MetricSpec { id: string; label_ko: string; unit: string; decimals: number; lo: number | null; hi: number | null; }
export interface KpiSummaryCard { id: string; label_ko: string; unit: string; decimals: number; value: number | null; prev_value: number | null; spec_id: string | null; }
export interface KpiSummaryResponse { period: "day" | "week" | "month"; bucket_start: string | null; bucket_end: string | null; prev_bucket_start: string | null; cards: KpiSummaryCard[]; }
export interface PhaseInterval { phase: string; label_ko: string; start: string; end: string; }
export interface MaterialsMeta { scrap_grades: Record<string, string>; addition_materials: Record<string, string>; steel_groups: Record<string, string>; }
export interface AdditionEvent { ts: string; material: string; label_ko: string; amount_kg: number; }
export type KpiTrendRow = { heat_id: string; date: string; steel_group: string } & Record<string, number | string | null>;
```

`Heat` 중첩 모델 ↔ 스펙 `id` 매핑 규칙(프론트 상세 뷰 판정용, 기존 컬럼 규약 그대로): `heat.kpi.{k}` ↔ `kpi_{k}` / `heat.eop.tap_temp_c` ↔ `eop_tap_temp_c` / `heat.eop.composition_pct.{el}` ↔ `eop_comp_{el}` / `heat.charge.total_charge_t` ↔ `charge_total_t`.

### C7. 정적 서빙 (신규)

- `frontend/dist` 존재 시: `/assets/*` 정적 서빙 + 비-`/api` GET 경로는 SPA fallback(dist 내 실제 파일이면 그 파일, 아니면 `index.html`).
- `/api/*` 미정의 경로는 fallback 대상 아님(FastAPI 기본 404 JSON).
- dist 경로는 `config.py`의 `frontend_dist_dir` 설정(기본 `PROJECT_ROOT/frontend/dist`). dist 미존재 시 앱은 정상 기동(API 전용).
- WS `/api/live`, SSE `/api/discussion` 영향 없음.

## 4. 파일 단위 변경 명세

### 백엔드 (U1)

| 파일 | 작업 |
|---|---|
| `backend/app/domain/specs.py` **신규** | `MetricSpec` dataclass(frozen) + `SPEC_REGISTRY`(C1의 11개) + `banded()`/`get()` 헬퍼 + `is_out_of_spec(row: Mapping) -> bool`. `SummaryCardDef` dataclass + `SUMMARY_CARDS`(C2의 8개, 집계 종류 `agg: "count"|"sum"|"mean"|"out_of_spec_count"` + `column`). 순수 선언 — 타 계층 의존 금지 |
| `backend/app/domain/phases.py` 수정 | 페이즈 경계 휴리스틱 상수 선언: `BORE_IN_DURATION_S = 180`, `MELTDOWN_SETTLE_S = 120` (주석: 데이터에 경계 이벤트 없음 → 더미 단계 추정값, 조정은 이 선언만) |
| `backend/app/domain/models.py` 수정 | `PhaseInterval`, `KpiSummaryCard`, `KpiSummaryResponse` Pydantic 모델 추가 (C2/C4 스키마 그대로) |
| `backend/app/data/file_repository.py` 수정 | ① `_row_to_heat`의 `group()`에 suffix 인자 추가 → `slag_add_` 그룹에서 `_kg` 제거(C6) ② `get_kpi_trend` 반환 컬럼 확장(C3): base(`heat_id`,`date`,`steel_group`) + `kpi_*` + SPEC_REGISTRY 파생 컬럼(존재하는 것만, 중복 제거) |
| `backend/app/services/heat_service.py` 수정 | `get_kpi_summary(period)` 실구현(C2: repo.get_kpi_trend 행 → 최신 date 버킷/직전 버킷 집계, SUMMARY_CARDS·SPEC_REGISTRY 참조, `KpiSummaryResponse` 반환). `get_phases(heat_id) -> list[PhaseInterval]` 신규(C4 규칙) |
| `backend/app/api/routes/heats.py` 수정 | `GET /api/heats/{heat_id}/phases` (response_model=`list[PhaseInterval]`, 404 처리 기존 패턴) |
| `backend/app/api/routes/kpi.py` 수정 | `/summary`에 `response_model=KpiSummaryResponse` |
| `backend/app/api/routes/meta.py` 수정 | `GET /api/meta/specs`(SPEC_REGISTRY 직렬화), `GET /api/meta/materials`(C5) |
| `backend/app/config.py` 수정 | `frontend_dist_dir: Path = PROJECT_ROOT / "frontend" / "dist"` |
| `backend/app/main.py` 수정 | C7 정적 서빙 + SPA fallback (라우터 등록 뒤 catch-all) |
| `backend/app/llm/openai_provider.py` 수정 | 실호출 검증·보정: 스트림 예외 → `ERROR` StreamEvent(키 미노출), annotation dict/객체 양쪽 대응, web_search tool type 상수화(실호출로 확정), 알 수 없는 이벤트 무시 유지, 대화 이력 role(user/assistant) 전달 확인 |
| `backend/scripts/smoke_openai.py` **신규** | provider factory로 실호출 1회(짧은 프롬프트, tool 미유발 유도), 이벤트 타입 로그, text_delta≥1·done 확인 시 exit 0. pytest에 포함하지 않음(비용) |
| `backend/tests/` 신규 테스트 | meta/specs·materials 계약, kpi/summary 스키마·카드 순서, phases 시간 순서·구간 정합, slag additions 키(`_kg` 없음·ADDITION_MATERIALS 코드 일치), trend 행 키 확장, 정적 fallback(dist 없으면 skip). LLM 실호출 테스트 금지 |

### 프론트엔드 (U2)

| 파일 | 작업 |
|---|---|
| `frontend/package.json` | `react-markdown`, `remark-gfm` 추가 (허용된 유일한 신규 의존성) |
| `frontend/src/styles.css` | 디자인 토큰(CSS 변수) 선언 + 전면 재설계(§5 프론트 프롬프트의 토큰 표). 다크 사이드바 제거. 카드 box-shadow 금지 |
| `frontend/src/api/types.ts` | C6 타입 추가 + `HeatSummary.steel_group` |
| `frontend/src/api/client.ts` | `getSpecs`/`getMaterials`/`getAdditions`/`getPhases` 추가, `getKpiSummary`/`getKpiTrend` 반환 타입 갱신. 정적 메타(tags/phases/specs/materials)는 간단 메모이즈 허용 |
| `frontend/src/layout/AppLayout.tsx` | 라이트 사이드바, Discussion 패널 리사이즈(기본 25vw, 20~50vw 클램프, 드래그 핸들) + 접기/펼치기 유지 |
| `frontend/src/components/charts/theme.ts` **신규** | Plotly 공통 테마(폰트 system-ui, 본문색 #333, 격자 rgba(0,0,0,0.06~0.1), 배경 투명/흰색, colorway=차트 팔레트) |
| `frontend/src/components/charts/PlotlyChart.tsx` | 테마 기본값 병합 + `onClick`(plotly_click) prop 추가 |
| `frontend/src/views/HeatDetailView.tsx` | 태그별 서브플롯(공유 x축, 태그 수 기반 동적 도메인 — 태그명 하드코딩 금지), 페이즈 음영(phases API), 용락 수직선, 부원료 마커(additions API), 정적 정보 표/카드(KPI 카드 스펙 색상, EOP/슬래그/장입 표 — 라벨은 specs/materials/tags 메타) |
| `frontend/src/views/TrendView.tsx` | 지표 선택(specs 메타), 기간 필터(`setPeriod` 연동), 강종 그룹별 색상(materials 라벨), 스펙 밴드 음영+경계선, 이탈 heat 하이라이트, 포인트 클릭 → `setHeatId`+`setView("heat_detail")` |
| `frontend/src/views/KpiSummaryView.tsx` | 일/주/월 전환, C2 카드 그리드(값+단위+직전 대비+스펙 색상), 버킷 기간 캡션 |
| `frontend/src/discussion/DiscussionPanel.tsx` | 마크다운 렌더링(react-markdown+remark-gfm), tool 실행 칩, 출처 목록, 조건부 자동 스크롤, 토큰 기반 재스타일 |
| (선택) `frontend/src/components/` 공통 컴포넌트 | KpiCard/SpecBadge 등 — 코더 재량, 토큰 준수 |

**금지**: `LiveView.tsx` 수정, localStorage 영속화, 백엔드 수정, 계약 외 엔드포인트 호출.

## 5. 에이전트 실행 프롬프트

§5.1(backend-coder), §5.2(frontend-coder) 전문은 main 오케스트레이터 보고에 포함(이 문서와 동일 내용). 프롬프트에는 §3 계약 전체가 각각 자체 포함되어 있어 코더가 이 문서를 읽지 않아도 실행 가능하지만, 프롬프트 서두에 이 문서(`docs/plans/dashboard-v1.md`)·CLAUDE.md·docs/reference-naver.md 정독을 지시한다.

## 6. verifier 체크리스트

보고에 전문 포함 (테스트/빌드 → 실기동 curl → 단일 포트 → OpenAI SSE 1회 → 디자인 토큰 → 계약 정합 → 설계 원칙 → 스코프).

## 7. 완료 조건 (요약)

- backend: `cd backend && ../.venv/Scripts/python.exe -m pytest tests -q` 전체 통과 + `smoke_openai.py` 실행 로그(text_delta 수신·done 종료) 보고 포함.
- frontend: `cd frontend && npm run build` 성공(타입 에러 0).
- verifier: §6 전 항목 PASS.

## 8. 판단으로 확정한 사항 (비차단 — 사용자 확인 권장)

1. **페이즈 경계 휴리스틱**: BORE_IN/EXPANSION 경계와 MELTDOWN 안정화 구간은 데이터에 이벤트가 없어 산출 불가 → `domain/phases.py`에 `BORE_IN_DURATION_S=180`, `MELTDOWN_SETTLE_S=120` 선언값으로 추정(향후 조정은 선언 수정만). 실데이터 연결 시 재검토 필요.
2. **KPI 요약 버킷**: "일/주/월 집계"를 "데이터 최신 heat가 속한 버킷 + 직전 버킷 대비"로 해석(더미 데이터가 과거 고정이라 현재 시각 기준은 항상 빈 결과).
3. **디자인 확장 토큰**: reference 문서에 없는 이탈색(danger `#d13438` — 액센트와 같은 Fluent 계열)과 차트 3색 팔레트(`#0078d4`/`#038387`/`#8764b8`)를 최소로 추가. UI 크롬은 단일 블루 원칙 유지, 확장색은 데이터 표현(판정/시리즈)에만 사용.
4. **ContextBuilder note 자동 요약**(알려진 작업 ⑥): 이번 범위에서 제외(스코프 최소화 — 기존 `note` 필드 유지, P2 후속에서 고도화).
5. 산소원단위/수율/tap-to-tap은 사용자 제시 밴드가 없어 `lo/hi=null`(지표로만 제공).
