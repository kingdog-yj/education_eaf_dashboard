# EAF 공정 분석 대시보드 & Discussion

전기로(Electric Arc Furnace) 제강 공정 데이터를 인터랙티브 대시보드로 조회·모니터링하고, LLM 기반으로 업계 전문가 수준의 공정 디스커션을 제공하는 웹 애플리케이션.

## 문서 맵

| 문서 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 프로젝트 운영 가이드: 설계 원칙, 에이전트 체계, 아키텍처, 주의사항 |
| [SPEC.md](SPEC.md) | 확정 명세 (아키텍처, 데이터 모델, API, 로드맵) |
| [DOMAIN_INFO.md](DOMAIN_INFO.md) | 전기로 공정 도메인 지식 (지속 업데이트, LLM 프롬프트에 주입됨) |
| [docs/WORKLOG.md](docs/WORKLOG.md) | 작업 내역 및 향후 계획 작업 명세 |
| [docs/plans/](docs/plans/) | planner 에이전트가 작성한 작업별 상세 계획 |

## 다른 PC에서 시작하기 (클론 후 셋업)

요구사항: Python 3.14+, Node.js 24+ (git 포함)

```bash
git clone https://github.com/kingdog-yj/education_eaf_dashboard.git
cd education_eaf_dashboard

# 1) 백엔드
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

# 2) 프론트엔드
cd frontend && npm install && cd ..

# 3) 환경 변수 — .env.example을 .env로 복사 후 실제 키 입력 (.env는 커밋되지 않음)
cp .env.example .env
```

더미데이터(500 heat)는 저장소에 포함되어 있어 별도 생성 없이 바로 동작한다.
재생성이 필요하면: `cd backend && ../.venv/Scripts/python.exe -m app.data.dummy.generator` (seed 42 재현)

## 실행

```bash
# 백엔드 (http://localhost:8000)
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --app-dir backend

# 프론트엔드 (http://localhost:5173, /api는 8000으로 프록시)
cd frontend && npm run dev

# 테스트 / 빌드
.venv/Scripts/python.exe -m pytest backend/tests
cd frontend && npm run build
```
