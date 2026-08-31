# 작업 계획: 더미데이터 생성기 구현 + 실제 parquet 생성 실행

> 작성: planner · 2026-08-31 · 사용자 승인 완료 (생성기 구현 + **생성 실행까지** 진행)
> 근거 문서: CLAUDE.md, SPEC.md §4, DOMAIN_INFO.md, 사용자 인터뷰 확정 요구사항

---

## 1. 작업 분해

**backend-coder 1개 인스턴스 + verifier 1개 인스턴스, 순차 실행.**

- 이 작업은 생성기 물리 모델 ↔ 스키마 ↔ Repository/API 확장 ↔ 실행이 강하게 결합된 단일 응집 단위다. 병렬화하면 계약 조정 비용이 이득을 초과하므로 분할하지 않는다.
- 순서: `backend-coder`(구현 + 테스트 수정 + pytest 통과 + 생성 실행) → `verifier`(분포/정합/API 검증, 코드 수정 없음, FAIL 시 리포트를 backend-coder에 SendMessage로 전달하여 수정 후 재검증).
- 프론트엔드 작업 없음 (기존 API 스키마의 하위호환 확장만 있음).

## 2. 테이블 스키마 계약 (확정 — 코더/verifier 공통)

### 2.1 `data/dummy/heats.parquet` (500행, heat당 1행)

| 컬럼 | dtype | 내용 |
|---|---|---|
| `heat_id` | str | "A" + 6자리, 일의 자리 0, 10씩 증가 연속 (예: A520010, A520020, …) |
| `date` | datetime64[ns] | = `ev_power_on` (목록 정렬/기간 필터 기준) |
| `shift` | str | 근무조: "D"(06~14시) / "S"(14~22시) / "N"(22~06시), power_on 시각 기준 |
| `steel_group` | str | 조업 패턴 그룹 코드: `high` / `mid` / `low` |
| `ev_power_on` | datetime64[ns] | 송전 시작 |
| `ev_meltdown` | datetime64[ns] | 용락 시점 (누적 전력 f×E_total 도달, f∈[0.70,0.75]) |
| `ev_tap_start` | datetime64[ns] | 출강 시작 = power_off + U(1,3)분 |
| `ev_tap_end` | datetime64[ns] | 출강 종료 = tap_start + U(3,6)분 |
| `charge_total_t` | float | 총 장입량 155~165 t (+이상치) |
| `charge_hot_heel_t` | float | 잔탕 30~40 t |
| `charge_scrap_grade_a_t` | float | A급 장입량 (t) |
| `charge_scrap_shredder_t` | float | 슈레더 장입량 (t) |
| `charge_scrap_turnings_t` | float | 선반설 장입량 (t) |
| `charge_scrap_common_t` | float | 일반 장입량 (t) |
| `kpi_energy_kwh_per_t` | float | **시계열 active_power 적분/장입톤** (380~410 + 이상치) |
| `kpi_o2_nm3_per_t` | float | 시계열 o2_lance_flow 적분(Nm3)/장입톤 |
| `kpi_carbon_kg_per_t` | float | (분탄 적분 kg + 괴탄 투입 kg)/장입톤 |
| `kpi_power_on_min` | float | (power_off − power_on)/60, 33~40분 (이상치 소수 허용) |
| `kpi_tap_to_tap_min` | float | POT + 유휴(10~20분) |
| `kpi_tap_weight_t` | float | 출강량 148~153 t (+이상치) |
| `kpi_yield_pct` | float | = tap_weight/charge_total×100 (정합 강제) |
| `eop_tap_temp_c` | float | 출강 온도 1590~1620°C (그룹 연동, +이상치) |
| `eop_comp_c` | float | 용강 C % 0.03~0.10 (그룹 연동, +이상치) |
| `eop_comp_p` | float | 용강 P % 0.010~0.030 (=100~300 ppm, 그룹 연동, +이상치) |
| `slag_add_lime_kg` | float | additions.parquet의 lime 합계 (정합 강제) |
| `slag_add_lump_carbon_kg` | float | additions.parquet의 lump_carbon 합계 (정합 강제) |

- kpi_ 컬럼명은 `KpiInfo` 필드명과 prefix 제거 후 정확히 일치해야 한다 (기존 `_row_to_heat`의 `group("kpi_")` 규약).
- eop_comp_ / slag_add_ 도 동일 prefix 규약. slag 성분/염기도 컬럼은 **생성하지 않는다** (확정 요구사항 외 — 스코프 최소화; Repository는 결측을 이미 허용).

### 2.2 `data/dummy/timeseries/{heat_id}.parquet` (heat당 1파일, long format)

| 컬럼 | dtype | 내용 |
|---|---|---|
| `ts` | datetime64[ns] | 1초 간격, [ev_power_on, power_off] 구간만 |
| `tag` | str | `active_power` / `o2_lance_flow` / `carbon_inj_rate` (TAG_REGISTRY dev 프로필과 정확히 일치) |
| `value` | float64 | 태그값 |

### 2.3 `data/dummy/additions.parquet` (신규 — 전체 heat 통합 1파일)

| 컬럼 | dtype | 내용 |
|---|---|---|
| `heat_id` | str | 대상 heat |
| `ts` | datetime64[ns] | 투입 시점 |
| `material` | str | ASCII 코드: `lime`(생석회) / `lump_carbon`(괴탄) |
| `amount_kg` | float64 | 투입량 kg |

- heat당 통상 3행: ①cumE≈150 kWh/t 시점 lime 1500kg + lump_carbon 800kg(같은 시점±30s), ②용락 직후(+30~120s) lime 1000kg. 각 ±10% 노이즈, 2~3% heat는 예외(②누락 또는 ±25% 이탈).

## 3. 도메인/Repository/API 확장 계약

### 3.1 `domain/materials.py` (신규) — 코드/라벨 유일 선언 지점
```python
SCRAP_GRADES: dict[str, str] = {"grade_a": "A급", "shredder": "슈레더", "turnings": "선반설", "common": "일반"}
ADDITION_MATERIALS: dict[str, str] = {"lime": "생석회", "lump_carbon": "괴탄"}
STEEL_GROUPS: dict[str, str] = {"high": "고급강종", "mid": "일반강종", "low": "저급 배합"}
```
생성기·Repository는 이 선언만 참조 (다른 곳 하드코딩 금지).

### 3.2 `domain/models.py`
- `AdditionEvent(BaseModel)`: `ts: datetime`, `material: str`, `label_ko: str = ""`, `amount_kg: float`
- `HeatSummary`에 `steel_group: str = ""` 필드 추가 (하위호환 기본값).

### 3.3 `domain/tags.py`
- dev 프로필을 실제 생성 3태그와 일치: `energy_total`, `tap_position`, `panel_temp`, `offgas_temp` → `dev_profile=False` (주석: energy_total은 active_power 적분으로 파생 가능). `active_power`, `o2_lance_flow`, `carbon_inj_rate`는 유지.

### 3.4 `data/repository.py`
- `HeatRepository`에 추상 메서드 추가:
  `def get_additions(self, heat_id: str) -> list[AdditionEvent]: ...`

### 3.5 `data/file_repository.py`
- `get_additions`: `{data_dir}/additions.parquet` 로드(없으면 `[]`), heat_id 필터, ts 정렬, `label_ko`는 `ADDITION_MATERIALS`에서 매핑.
- `_row_to_summary`: `steel_group=row.get("steel_group", "")` 추가 (NaN 방어).
- `_row_to_heat`: charge에 `baskets=[{code: t}]` 단일 바스켓 구성 — `charge_scrap_{code}_t` 패턴 파싱.

### 3.6 `data/sql_repository.py`
- `get_additions` 스텁 추가 (`NotImplementedError`, 기존 문구와 동일 스타일) — ABC 추가로 인한 인스턴스화 오류 방지.

### 3.7 `services/heat_service.py` / `api/routes/heats.py`
- `HeatService.get_additions(heat_id)` 위임 메서드.
- `GET /api/heats/{heat_id}/additions` → `response_model=list[AdditionEvent]` (heat 미존재/데이터 없음 → 빈 배열 200).

## 4. 생성 물리 모델 계약 (수치 확정)

### 4.1 heat별 샘플링 & POT 역산
1. `steel_group` ~ {high: 0.25, mid: 0.55, low: 0.20}
2. `charge_total_t` ~ U(155, 165); 이상치(확률 ~2.5%): [152,155)∪(165,169]
3. 목표 전력원단위(kWh/t): high U(388,410) / mid U(382,404) / low U(380,398); 이상치(~2.5%): [372,380)∪(410,420]
4. `E_total_kwh = charge_total_t × 원단위`
5. 용락 비율 `f ~ U(0.70, 0.75)`
6. 전력 프로필 파라미터: 램프 2~3단계(시작 ~2MW 30~60s → 20~40MW 45~90s → [60~80MW 45~90s]), 용해기 평탄부 `P_melt ~ U(100,110)` MW, 정련기 평탄부 `P_ref ~ U(90,95)` MW
7. POT 역산: `POT = t_ramp + (f·E − E_ramp)/P_melt + (1−f)·E/P_ref`. POT ∉ [33,40]분이면 (f, P_melt, P_ref, 램프) 재샘플 (최대 200회; 이상치 원단위 heat는 실패 시 가장 근접값 채택 — 자연스러운 POT 예외, 하드 바운드 [31,42])

### 4.2 1초 시계열 (노이즈 포함, 실제 적분으로 이벤트/KPI 확정)
- **active_power (MW)**: 계획 프로필 + 노이즈. 램프·용해기(용락 전): σ≈4~6MW + 붕락 이벤트 2~5회(10~30s 동안 15~40MW 급락 후 복귀 — 아크 불안정); 용락 후: σ≈1.5~2.5MW. 클립 [0, 118]. **누적 전력 cumE ≥ E_total 도달 시점 = power_off** (원단위 정확 보장).
- **ev_meltdown** = cumE가 f×E_total을 넘는 첫 ts. 이 시점에 전력 평탄부 P_melt→P_ref 전환.
- **o2_lance_flow (Nm3/h)**: 송전 시작~붕락 전 4000~6000 (σ≈2%); 붕락 트리거(cumE ≥ (100±10) kWh/장입톤)에서 1~2 step(중간단 ~8000, 간격 30~90s)으로 **10000**; 용락 시점부터 **12800**; 정련 말기(cumE ≥ U(0.90,0.94)×E_total)부터 그룹 연동 하향 — high 8000~9000 / mid 8500~9500 / low 9000~10000; power_off 이후 없음(구간 종료).
- **carbon_inj_rate (kg/min)**: 용락+U(30,120)s부터 power_off까지 **40** (σ≈1.5); 그 전 0. heat의 ~5%에 30~90s 중단 1회(예외성).

### 4.3 스케줄
- 시작: 2026-08-01 06:00 (config 기본값). heat 연쇄: 다음 power_on = tap_end + c분, 유휴 합(power_off→다음 power_on) = a(1~3) + b(3~6) + c(클립으로 합계 10~20분).
- `kpi_tap_to_tap_min = POT + 유휴합`. 일 20~30 heat 유지를 위해 ~15±5 heat마다 추가 휴지 U(30,90)분 삽입. 500 heats ≈ 3~4주.

### 4.4 정적/그룹 연동 (모든 분포: 실공정 유사 편차 + 변수별 ~2.5% 이상치는 경계 ≤5% 이탈)

| 파라미터 | high (25%) | mid (55%) | low (20%) |
|---|---|---|---|
| 스크랩 A급 비율 | 0.75±0.03 | 0.70±0.03 | 0.62±0.04 |
| 슈레더 비율 | 0.10±0.02 | 0.10±0.02 | 0.12±0.03 |
| 잔여(bal) 중 선반설:일반 | 40:60 | 50:50 | 55:45 |
| EOP C % | 0.03~0.06 | 0.05~0.08 | 0.06~0.10 |
| EOP P ppm | 100~180 | 150~250 | 200~300 |
| 출강온도 °C | 1600~1620 | 1595~1615 | 1590~1610 |
| 정련말기 O2 Nm3/h | 8000~9000 | 8500~9500 | 9000~10000 |
| 원단위 kWh/t | 388~410 | 382~404 | 380~398 |

- 비율은 정규화 후 charge_total_t 곱해 등급별 톤수 산출. 단일 바스켓.
- `kpi_tap_weight_t = charge_total_t × yield(N(0.925, 0.007))` → 정상 heat는 [148,153] 클립, 이상치 heat는 [146,155.5]. `kpi_yield_pct`는 항상 tap/charge×100 재계산 (정합).

### 4.5 재현성/실행
- `numpy.random.default_rng(seed=42)` 단일 rng, heat 순차 생성. 동일 시드 → 동일 산출.
- 수치 파라미터는 GeneratorConfig/모듈 상단 선언 테이블(GROUP_PARAMS 등)로 모은다 (함수 본문 하드코딩 금지).
- 실행 (프로젝트 루트 기준):
  ```powershell
  cd C:\Users\user\Desktop\project\backend
  ..\.venv\Scripts\python.exe -m app.data.dummy.generator
  ```
  argparse: `--n-heats`(기본 500), `--seed`(기본 42), `--out-dir`(기본 `get_settings().data_dir`). 출력: `data/dummy/` (git 제외 확인됨).

## 5. 파일 단위 변경 명세

| 파일 | 작업 |
|---|---|
| `backend/app/domain/materials.py` | **신규**: SCRAP_GRADES / ADDITION_MATERIALS / STEEL_GROUPS 코드·한글 라벨 선언 |
| `backend/app/domain/models.py` | 수정: `AdditionEvent` 추가, `HeatSummary.steel_group: str = ""` 추가 |
| `backend/app/domain/tags.py` | 수정: 미생성 4태그 `dev_profile=False` 전환 + 주석 |
| `backend/app/data/repository.py` | 수정: `get_additions` 추상 메서드 추가 |
| `backend/app/data/file_repository.py` | 수정: `get_additions` 구현, `_row_to_summary` steel_group, `_row_to_heat` 바스켓 파싱 |
| `backend/app/data/sql_repository.py` | 수정: `get_additions` NotImplementedError 스텁 |
| `backend/app/services/heat_service.py` | 수정: `get_additions` 위임 |
| `backend/app/api/routes/heats.py` | 수정: `GET /api/heats/{heat_id}/additions` |
| `backend/app/data/dummy/generator.py` | **전면 구현**: §4 물리 모델 + `__main__` CLI |
| `backend/tests/test_smoke.py` | 수정: dev 프로필 그룹 집합 `{"electrical","chemical"}`, heats 목록 테스트를 데이터 유무 무관형으로 교체(+데이터 존재 시 상세/additions 200 확인) |
| `data/dummy/*.parquet` | **생성 실행** (500 heats) |

레이어 준수: generator·repository는 domain(tags/materials/models)만 참조, config는 factory/CLI 진입점에서만. api→services→data→domain 방향 유지.

## 6. backend-coder 실행 프롬프트 (전문 — 이대로 전달)

```
[작업] EAF 더미데이터 생성기 구현 + 실제 parquet 생성 실행 (사용자 승인 완료)

프로젝트: C:\Users\user\Desktop\project (backend/ = FastAPI). 계획 전문: docs/plans/dummy-data-generation.md — 반드시 먼저 읽고, CLAUDE.md·DOMAIN_INFO.md·SPEC.md §4도 읽어라. 아래 명세가 계약이며 임의 변경 금지. 명세 외 파일·기능 추가 금지(스코프 최소화). 프론트엔드 수정 금지.

== A. 도메인/Repository/API 확장 ==

A1. backend/app/domain/materials.py 신규 — 코드·라벨 유일 선언 지점:
    SCRAP_GRADES = {"grade_a": "A급", "shredder": "슈레더", "turnings": "선반설", "common": "일반"}
    ADDITION_MATERIALS = {"lime": "생석회", "lump_carbon": "괴탄"}
    STEEL_GROUPS = {"high": "고급강종", "mid": "일반강종", "low": "저급 배합"}
    (dict[str, str], 모듈 docstring으로 용도 명시. 다른 파일에서 이 코드 문자열을 하드코딩하지 말고 여기서 import)

A2. backend/app/domain/models.py:
    - class AdditionEvent(BaseModel): ts: datetime / material: str / label_ko: str = "" / amount_kg: float
    - HeatSummary에 steel_group: str = "" 필드 추가

A3. backend/app/domain/tags.py: energy_total, tap_position, panel_temp, offgas_temp를 dev_profile=False로 전환(선언만 수정, 삭제 금지). energy_total에는 "더미 단계 미생성 — active_power 적분으로 파생 가능" 주석. active_power, o2_lance_flow, carbon_inj_rate 3태그만 dev 프로필로 남는다.

A4. backend/app/data/repository.py: HeatRepository에 추상 메서드 추가
    def get_additions(self, heat_id: str) -> list[AdditionEvent]: ...

A5. backend/app/data/file_repository.py:
    - get_additions: {data_dir}/additions.parquet 로드(파일 없으면 [] 반환), heat_id 필터, ts 정렬, label_ko는 ADDITION_MATERIALS 매핑(미등록 코드는 "")
    - _row_to_summary: steel_group=row.get("steel_group", "") (NaN이면 "")
    - _row_to_heat: charge에 baskets=[{grade_code: t}] 단일 바스켓 — 컬럼 패턴 charge_scrap_{code}_t 파싱 (prefix "charge_scrap_" 제거 + suffix "_t" 제거)

A6. backend/app/data/sql_repository.py: get_additions 스텁 추가 — 기존 메서드와 동일하게 NotImplementedError("사내 DB 연결은 스키마 확정 후 구현 (SPEC.md §8)")

A7. backend/app/services/heat_service.py: get_additions(heat_id) 위임 메서드 추가.
    backend/app/api/routes/heats.py: GET /api/heats/{heat_id}/additions, response_model=list[AdditionEvent], 데이터 없으면 빈 배열 200 (404 아님).

== B. 생성기 구현 (backend/app/data/dummy/generator.py 전면 구현) ==

객체지향 구조 유지: GeneratorConfig(dataclass) + DummyHeatGenerator. 수치 파라미터는 함수 본문에 흩어 하드코딩하지 말고 GeneratorConfig 필드 또는 모듈 상단 선언 테이블(GROUP_PARAMS: dict[str, GroupParams] — 키는 materials.STEEL_GROUPS의 키와 일치해야 하며 이를 assert)로 모은다. 태그 id는 domain.tags.TAG_REGISTRY에서 얻고, 생성 프로필 매핑 키 집합 == set(TAG_REGISTRY.ids(dev_only=True)) 임을 generate() 시작 시 assert. HeatPhase enum(domain.phases)을 페이즈 경계 로직의 공통 어휘로 사용. 재현성: numpy.random.default_rng(config.seed) 단일 rng.

GeneratorConfig 기본값: n_heats=500, seed=42, start_date=datetime(2026, 8, 1, 6, 0), sample_period_s=1.0. 기존 tap_to_tap_min_range 필드는 pot_min_range=(33.0, 40.0), idle_min_range=(10.0, 20.0)로 교체.

B1. heat_id: "A" + 6자리. 시작 번호 = rng로 뽑은 10의 배수(범위 100010~899990), 이후 heat마다 +10 (예: A520010, A520020, ...). 일의 자리 항상 0, 500개 연속.

B2. heat별 샘플링(순서):
    1) steel_group ~ {high: 0.25, mid: 0.55, low: 0.20}
    2) charge_total_t ~ U(155,165); 확률 2.5%로 이상치: U(152,155) 또는 U(165,169)
    3) 목표 전력원단위(kWh/t): high U(388,410) / mid U(382,404) / low U(380,398); 확률 2.5%로 이상치: U(372,380) 또는 U(410,420)
    4) E_total_kwh = charge_total_t × 원단위
    5) 용락 에너지 비율 f ~ U(0.70, 0.75)
    6) 전력 프로필: 램프 2~3단계 — 1단 ~2MW를 30~60s, 2단 U(20,40)MW를 45~90s, (3단 있으면 U(60,80)MW를 45~90s) → 용해기 평탄부 P_melt ~ U(100,110)MW → (용락 후) 정련기 평탄부 P_ref ~ U(90,95)MW
    7) POT 역산: POT_min = t_ramp + (f×E − E_ramp)/P_melt/1000×60 + (1−f)×E/P_ref/1000×60 (E는 kWh, P는 MW). POT가 33~40분을 벗어나면 (f, P_melt, P_ref, 램프 단수·시간) 재샘플, 최대 200회. 200회 실패 시(이상치 원단위 heat에서 발생 가능) 가장 근접한 조합 채택 — 이때도 POT는 [31,42] 안이어야 한다.

B3. 1초 시계열 생성 (long format: ts, tag, value — [ev_power_on, power_off] 구간만):
    - active_power(MW): 계획 프로필 + 가우시안 노이즈. 용락 전(램프+용해기): σ 4~6MW, 추가로 붕락 이벤트 2~5회(각 10~30s 동안 15~40MW 급락 후 복귀 — 아크 불안정 재현). 용락 후: σ 1.5~2.5MW(아크 안정). 값 클립 [0, 118].
    - 누적 전력 cumE(kWh) = Σ(MW)/3.6 를 1초마다 적산. cumE ≥ E_total_kwh 도달한 시점을 power_off로 확정(→ 실제 원단위가 목표와 일치). ev_meltdown = cumE ≥ f×E_total 최초 ts. 이 ts부터 평탄부를 P_melt→P_ref로 전환.
    - o2_lance_flow(Nm3/h): 송전~붕락 전 U(4000,6000) 수준(σ 2%); 붕락 트리거 = cumE ≥ (100±10)×charge_total_t kWh 시점 — 50% 확률로 중간단(~8000, 30~90s) 경유 2단 상향, 아니면 1단 → 10000; ev_meltdown부터 12800; 정련 말기(cumE ≥ U(0.90,0.94)×E_total)부터 그룹 연동: high U(8000,9000) / mid U(8500,9500) / low U(9000,10000). 각 구간 σ 2% 노이즈, 음수 클립.
    - carbon_inj_rate(kg/min): ev_meltdown + U(30,120)s 부터 power_off까지 40 (σ 1.5, 음수 클립); 그 전 0. 전체 heat의 5%는 중간에 30~90s 중단(0) 1회 삽입(예외성).
    - 값 반올림: active_power 소수 2자리, o2 정수 또는 1자리, carbon 2자리.

B4. 스케줄: 첫 heat power_on = start_date. ev_tap_start = power_off + U(1,3)분, ev_tap_end = tap_start + U(3,6)분, 다음 power_on = tap_end + c분 (c ~ U(2,12)를 조정해 유휴합 = tap_start지연 + 출강시간 + c가 10~20분이 되도록 클립). kpi_tap_to_tap_min = POT + 유휴합. 약 15±5 heat마다 추가 휴지 U(30,90)분 삽입(정비/지연 — 일 20~30 heat 유지 목적). shift는 power_on 시각으로 "D"(06~14)/"S"(14~22)/"N"(22~06).

B5. 정적 데이터:
    - 스크랩 배합(단일 바스켓): 그룹별 목표비율 — A급: high 0.75±0.03 / mid 0.70±0.03 / low 0.62±0.04; 슈레더: high 0.10±0.02 / mid 0.10±0.02 / low 0.12±0.03; 잔여는 선반설:일반 = high 40:60 / mid 50:50 / low 55:45 (±약간 노이즈). 정규화 후 charge_total_t를 곱해 charge_scrap_{code}_t 4컬럼 산출(코드는 materials.SCRAP_GRADES 키).
    - charge_hot_heel_t ~ U(30,40).
    - kpi_tap_weight_t = charge_total_t × yield, yield ~ N(0.925, 0.007); 정상 heat는 결과를 [148,153]으로 클립, 이상치 heat(확률 2.5%)는 [146,155.5] 허용. kpi_yield_pct = tap_weight/charge_total×100 재계산(항상 정합).
    - EOP (그룹 연동 + 노이즈, 각각 확률 2.5%로 경계 최대 ~5% 이탈 이상치):
      eop_tap_temp_c: high U(1600,1620) / mid U(1595,1615) / low U(1590,1610) — 전역 밴드 1590~1620
      eop_comp_c(%): high U(0.03,0.06) / mid U(0.05,0.08) / low U(0.06,0.10) — 전역 0.03~0.10
      eop_comp_p(%): high U(0.010,0.018) / mid U(0.015,0.025) / low U(0.020,0.030) — 전역 0.010~0.030 (=100~300ppm)
    - KPI는 전부 시계열/정적에서 파생: kpi_energy_kwh_per_t = 실제 cumE_total/charge_total_t; kpi_o2_nm3_per_t = Σ(o2)/3600/charge_total_t; kpi_carbon_kg_per_t = (Σ(carbon)/60 + 괴탄kg)/charge_total_t; kpi_power_on_min = 실제 (power_off−power_on)/60.

B6. 부원료 additions (전 heat 통합 data/dummy/additions.parquet — heat_id, ts, material, amount_kg):
    - 이벤트1: cumE ≥ (150±15)×charge_total_t kWh 최초 ts에 lime 1500kg(±10%) + lump_carbon 800kg(±10%) 2행 (lump는 같은 ts 또는 +30s 이내).
    - 이벤트2: ev_meltdown + U(30,120)s에 lime 1000kg(±10%) 1행.
    - 예외성: 전체 heat의 2~3%는 이벤트2 누락 또는 투입량 ±25% 이탈.
    - heats.parquet에 slag_add_lime_kg / slag_add_lump_carbon_kg = 해당 heat 합계(정합 강제).

B7. heats.parquet 컬럼 전체(계약 — 계획 문서 §2.1 표와 동일, 순서 포함 권장):
    heat_id, date(=ev_power_on), shift, steel_group, ev_power_on, ev_meltdown, ev_tap_start, ev_tap_end,
    charge_total_t, charge_hot_heel_t, charge_scrap_grade_a_t, charge_scrap_shredder_t, charge_scrap_turnings_t, charge_scrap_common_t,
    kpi_energy_kwh_per_t, kpi_o2_nm3_per_t, kpi_carbon_kg_per_t, kpi_power_on_min, kpi_tap_to_tap_min, kpi_tap_weight_t, kpi_yield_pct,
    eop_tap_temp_c, eop_comp_c, eop_comp_p, slag_add_lime_kg, slag_add_lump_carbon_kg
    (datetime은 naive datetime64[ns]. slag 성분/염기도 컬럼은 만들지 않는다)

B8. CLI: python -m app.data.dummy.generator 로 실행되게 __main__ 블록 + argparse(--n-heats 기본 500, --seed 기본 42, --out-dir 기본 app.config.get_settings().data_dir). 진행 로그(10% 단위)와 완료 요약(heat 수, 파일 수, 소요시간) print. config import는 CLI 진입점에서만.

== C. 테스트 수정 (backend/tests/test_smoke.py) ==
    - test_meta_tags: dev 프로필 태그가 3개가 되므로 그룹 집합 단언을 {"electrical", "chemical"}로 수정 (len 단언은 레지스트리 기준 그대로 유지).
    - test_heats_empty_before_dummy_generation → 데이터 유무 무관형으로 교체: GET /api/heats 200 + list 타입. 목록이 비어있지 않으면 첫 heat로 GET /api/heats/{id} 200, GET /api/heats/{id}/timeseries?tags=active_power 200, GET /api/heats/{id}/additions 200(list)을 추가 확인.

== D. 실행 (승인 완료 — 실제 생성까지 수행) ==
    1) 테스트: cd C:\Users\user\Desktop\project 에서 .venv\Scripts\python.exe -m pytest backend/tests → 전부 통과시킬 것
    2) 생성: cd C:\Users\user\Desktop\project\backend 후 ..\.venv\Scripts\python.exe -m app.data.dummy.generator
       (출력: C:\Users\user\Desktop\project\data\dummy\heats.parquet + timeseries\*.parquet 500개 + additions.parquet — git 제외 경로)
    3) 자가 점검 후 보고: heats.parquet 행수 500, timeseries 파일 수 500, 임의 3개 heat의 kpi_energy_kwh_per_t 범위, POT 범위, ev_meltdown 존재, additions 행수(~1500), 생성 소요시간.

== 제약 ==
- 레이어 방향(api→services→data→domain) 준수. domain은 어디에도 의존 금지.
- .env 열람/출력 금지. data/dummy 외 위치에 데이터 쓰기 금지. 기존 API 응답 스키마는 하위호환 확장만(필드 추가는 기본값 필수).
- pandas/numpy/pyarrow는 기존 의존성 사용, 새 패키지 추가 금지.
```

## 7. verifier 검증 체크리스트 (전문 — 이대로 전달)

```
[검증] 더미데이터 생성 결과 + 코드 계약 검증. 코드 수정 금지, 리포트만.
계획 전문: docs/plans/dummy-data-generation.md (계약 기준). 검증 스크립트는 scratchpad에 작성해 .venv\Scripts\python.exe로 실행하라. 각 항목 PASS/FAIL + 실측치를 표로 보고.

1. 파일/스키마
   [ ] data/dummy/heats.parquet 존재, 정확히 500행, 계획 §2.1의 26개 컬럼 전부 존재(이름 정확 일치), datetime 컬럼 dtype datetime64
   [ ] data/dummy/timeseries/*.parquet 정확히 500개, 파일명 = heat_id, 컬럼 ts/tag/value
   [ ] data/dummy/additions.parquet 존재, 컬럼 heat_id/ts/material/amount_kg, material ∈ {lime, lump_carbon}
   [ ] heat_id: 정규식 ^A\d{6}$, 일의 자리 0, 10씩 증가 연속 500개

2. 분포 (heats.parquet 전수)
   [ ] kpi_energy_kwh_per_t: [380,410] 내 비율 95~99% (이상치 1~5%, 목표 2~3%), 이상치도 [372,420] 내
   [ ] kpi_power_on_min: [33,40] 내 비율 ≥ 97%, 전량 [31,42] 내
   [ ] charge_total_t: [155,165] 내 95~99%, 전량 [152,169]
   [ ] kpi_tap_weight_t: [148,153] 내 ≥ 95%, 전량 [146,155.5]
   [ ] eop_tap_temp_c: [1590,1620] 내 95~99% / eop_comp_c: [0.03,0.10] 내 95~99% / eop_comp_p: [0.010,0.030] 내 95~99% (모두 이상치는 경계 ~5% 이내 이탈)
   [ ] kpi_tap_to_tap_min: 전량 [43,62] 근방(POT+10~20), kpi_tap_to_tap_min − kpi_power_on_min ∈ [10,20] (±0.5)
   [ ] 일별 heat 수(완전한 조업일 기준): 20~30, 전체 스케줄 span 17~28일, date 단조 증가
   [ ] shift ∈ {D,S,N}이고 power_on 시각과 일치

3. 그룹 (steel_group)
   [ ] 고유값 정확히 {high, mid, low}, 비율 대략 25/55/20 (±8%p)
   [ ] 그룹별 평균 ordering: eop_comp_c(high < mid < low), eop_comp_p(high < mid < low), eop_tap_temp_c(high > low), A급 배합비(high > mid > low), kpi_energy_kwh_per_t(high > low)

4. 시계열 물리 정합 (무작위 30개 heat 샘플 + 전수 요약)
   [ ] 1초 간격 결측 없음, 태그 정확히 {active_power, o2_lance_flow, carbon_inj_rate}, 구간 = [ev_power_on, power_off], active_power ≤ 118
   [ ] 전력 프로필: 초반 ~2MW 저전력 존재 → 계단 상승 → 용락 전 플래토 평균 100~110 → 용락 후 평균 90~95, 용락 후 표준편차 < 용락 전 표준편차
   [ ] cumE(active_power 적분, Σ/3.6) 총합/charge_total_t ≈ kpi_energy_kwh_per_t (상대오차 <1%)
   [ ] 용락 시점: cumE(ev_meltdown)/cumE_total ∈ [0.69,0.76] 전수(500 heat, cumE는 시계열에서 재계산)
   [ ] o2: 붕락 전 4000~6000대 → 붕락 후 ~10000(±5%) 구간 존재(붕락 시점의 cumE/charge ≈ 90~110 kWh/t) → 용락 후 ~12800(±3%) → 말기 평균 [7800,10300], power_off 이후 데이터 없음
   [ ] carbon: ev_meltdown 이전 = 0, 용락 +30~120s 이후 평균 38~42, ~5% heat에 중단 구간 존재
   [ ] kpi_o2_nm3_per_t = Σ(o2)/3600/charge (오차<1%), kpi_carbon_kg_per_t = (Σ(carbon)/60+괴탄)/charge (오차<2%)

5. 부원료 additions
   [ ] heat당 이벤트 구조: lime ~1500kg + lump_carbon ~800kg 1회(±10%±) + 용락 직후 lime ~1000kg 1회; 2~3% heat는 예외(누락/이탈)
   [ ] 이벤트1 시점의 cumE/charge ∈ [130,170] kWh/t (시계열에서 재계산, ≥95% heat)
   [ ] 이벤트2 ts − ev_meltdown ∈ [30,120]s (예외 heat 제외)
   [ ] heats.parquet의 slag_add_lime_kg / slag_add_lump_carbon_kg = additions 합계와 일치 (오차<0.1)
   [ ] kpi_yield_pct = kpi_tap_weight_t/charge_total_t×100 (오차<0.01)

6. 코드/API 계약
   [ ] .venv\Scripts\python.exe -m pytest backend/tests 전체 통과
   [ ] TAG_REGISTRY.ids(dev_only=True) == [active_power, o2_lance_flow, carbon_inj_rate] (energy_total 등은 dev_profile=False로 선언 유지)
   [ ] TestClient로: GET /api/heats → 비어있지 않은 목록, steel_group 필드 포함; GET /api/heats/{id} → charge.baskets 단일 바스켓에 4개 등급 코드(grade_a/shredder/turnings/common), kpi/eop 값 채워짐; GET /api/heats/{id}/timeseries?downsample=10 → 3개 series; GET /api/heats/{id}/additions → AdditionEvent 목록(label_ko 한글 라벨); GET /api/kpi/trend → 500행 kpi_ 컬럼; GET /api/meta/tags → 3개
   [ ] HeatRepository ABC에 get_additions 추상 메서드, SqlHeatRepository 스텁 존재
   [ ] 설계 원칙: 태그 id·스크랩 코드·그룹 코드가 domain(tags.py/materials.py) 외 파일에 리터럴 하드코딩되지 않음(생성기의 물리 파라미터 테이블은 허용), 레이어 역방향 import 없음
   [ ] 재현성: generator를 --n-heats 5 --seed 42 --out-dir <scratchpad> 로 2회 실행 → 산출 parquet 바이트 동일 또는 값 전체 동일 (data/dummy를 덮어쓰지 말 것)

판정: 2·4·5의 분포/정합 항목 중 하나라도 명백히 계약을 벗어나면 FAIL로 보고하고 실측 수치를 첨부하라.
```

