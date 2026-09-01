# Discussion 백엔드 Claude Agent SDK 전환 파일럿 — 작업 계획

> 작성: 2026-09-01 (planner) · 롤백 지점: 직전 커밋 `c59ffe8`
> 목표: Discussion 채팅의 LLM 백엔드를 OpenAI API에서 Claude Agent SDK(Claude Code 하네스)로 전면 전환. OpenAI 경로는 백엔드/프론트에서 전면 폐기.

## 0. 확정 요구사항 요약 (변경 불가)

1. **인증**: 이 PC의 Claude Code CLI 로그인(구독) 자격증명을 SDK가 상속. `.env`에 `ANTHROPIC_API_KEY` 불필요(향후 팀 배포 시 키 설정만으로 전환 — 주석 문서화). OPENAI 관련 설정 전부 제거.
2. **모드 2종** (기존 모델/추론강도 드롭다운 폐기):
   - `quick` = Haiku 4.5 (`claude-haiku-4-5`) — 도구 없이 주입 컨텍스트만으로 즉답, TTFB 수 초 목표.
   - `deep` = Opus 5 (`claude-opus-5`) — 프로젝트 문서/데이터 탐색 + 웹 + 파이썬 분석, 수 분 소요 가능.
3. **작업 디렉토리 = 프로젝트 루트** (CLAUDE.md·DOMAIN_INFO.md·SPEC.md·docs·backend·data/dummy 접근 가능).
4. **심화 허용 도구**: Read/Grep/Glob + WebSearch/WebFetch + 제한 Bash(.venv 파이썬 실행만).
5. **연산 정책**: 시스템 프롬프트 준강제 지침(§3.7 원문 참조). 생성 코드는 루트 `.chat_tmp/`에만(.gitignore 추가).

## 1. SDK 공식 문서 확인 결과 (구현 근거 — 2026-09-01 확인)

- `claude_agent_sdk.query(prompt=..., options=ClaudeAgentOptions(...))` → `AsyncIterator[Message]`. 호출마다 새 세션(stateless 1회 호출 모델에 부합).
- **스트리밍**: `include_partial_messages=True` → `claude_agent_sdk.types.StreamEvent`(SDK 타입, 우리 StreamEvent와 이름 충돌 — 별칭 임포트 필요)가 원시 API 이벤트를 담아 옴. `event["type"]`:
  - `content_block_delta` + `delta.type=="text_delta"` → 본문 토큰 (`delta["text"]`)
  - `content_block_start` + `content_block.type=="tool_use"` → 도구 시작 (`content_block["name"]` = Read/Bash/WebSearch 등)
  - `thinking_delta`/`input_json_delta` 등은 무시
  - 완결 `AssistantMessage`도 **함께** 옴 → 텍스트 중복 방출 금지(델타만 사용)
  - 도구 실행 완료는 `UserMessage` 내 `ToolResultBlock`(tool_use_id 매칭)으로 수신 — 미관측 시 폴백은 tool_use 블록의 `content_block_stop`
  - `ResultMessage` → 종료(subtype "success"/"error")
- **권한 잠금(공식 패턴)**: `allowed_tools`(사전 승인 목록, 패턴 지원: `Bash(ls *)` 형식 접두 매칭) + `permission_mode="dontAsk"` → **목록 밖 도구/명령은 프롬프트 없이 즉시 거부**. `can_use_tool` 콜백/훅 불필요. `disallowed_tools=["*"]`는 모든 도구 정의를 컨텍스트에서 제거(quick 모드용). bare name(`"Write"`)은 도구 자체를 컨텍스트에서 제거.
- **시스템 프롬프트**: `system_prompt`에 커스텀 문자열 → 기본 프롬프트 완전 대체. **CLAUDE.md 주입은 `setting_sources`가 제어**(기본값이 user+project 로드) → `setting_sources=[]`로 차단해야 개발용 CLAUDE.md가 채팅 페르소나를 오염하지 않음. 문자열 프롬프트는 CLI 인자로 전달되어 OS 인자 길이 제한(Windows ~32K자) 존재 → 길면 `{"type": "file", "path": ...}` 폴백.
- **세션 파일**: `~/.claude/projects/<encoded-cwd>/*.jsonl`에 자동 기록됨 → stateless 서버 위생을 위해 `env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}`로 억제(Python 공식 방법).
- **인증**: SDK가 CLI 서브프로세스를 스폰하며 `claude login` 자격증명(`~/.claude/credentials.json`)을 자동 상속. `ANTHROPIC_API_KEY` 환경변수가 있으면 그것을 사용 → 팀 배포 전환 경로.
- **설치**: `pip install claude-agent-sdk` (CLI 번들, Node 불필요, Python 3.10+).
- `ClaudeAgentOptions` 주요 필드: `cwd`, `model`, `system_prompt`, `allowed_tools`, `disallowed_tools`, `permission_mode`, `max_turns`, `include_partial_messages`, `setting_sources`, `thinking`({"type":"disabled"} 등), `env`.

## 2. 작업 분해

| 단위 | 에이전트 | 의존 | 내용 |
|---|---|---|---|
| U1 백엔드 전환 | backend-coder | 없음 (U2와 병렬) | provider 교체, modes.py, meta/chat_modes, 요청 스키마, 테스트, 스모크 스크립트, requirements/.env.example/.gitignore |
| U2 프론트 전환 | frontend-coder | 없음 (U1과 병렬) | 모드 세그먼트 UI, chatStore/타입/클라이언트 교체, tool 칩 한국어 매핑 |
| U3 검증 | verifier | U1+U2 완료 후 | §6 체크리스트. 실호출 스모크는 quick/deep 각 **정확히 1회** |

U1/U2는 §3의 계약만 공유하며 완전 독립 — 한 메시지에서 동시 스폰.

## 3. 계약 (양쪽 프롬프트에 동일 포함 — 임의 변경 금지)

### C1. `GET /api/meta/chat_modes` (신규)

```json
{
  "modes": [
    {"id": "quick", "label_ko": "빠른 대화",
     "description_ko": "수 초 안에 답합니다. 일반 질문이나 화면 내용의 간단한 확인에 적합합니다."},
    {"id": "deep", "label_ko": "심화 분석",
     "description_ko": "데이터와 문서를 직접 확인하며 답합니다. 정확하지만 수 분까지 걸릴 수 있습니다."}
  ],
  "default_mode": "quick"
}
```

- 항목 필드는 `{id, label_ko, description_ko}` 정확히 3개. 순서 quick → deep. 문구는 위 원문 그대로.
- **`GET /api/meta/llm`은 제거**(404).

### C2. `POST /api/discussion` 요청 (DiscussionRequest)

```json
{
  "messages": [{"role": "user|assistant", "content": "..."}],
  "context": { "view": "...", "heat_id": null, "period_start": null, "period_end": null, "visible_tags": [], "note": "" },
  "mode": "quick" | "deep" | null
}
```

- `model`/`reasoning_effort` 필드 **삭제**. `mode`는 선택(누락/null/목록 밖 값 → `quick` 폴백, 400 아님 — 기존 폴백 철학 유지).
- `context` 스키마(DashboardContext) 무변경.

### C3. SSE 응답 — **무변경**

- `StreamEvent` 스키마 그대로: `{type: "text_delta"|"tool_call"|"tool_result"|"citation"|"done"|"error", text, tool_name, url, title}`.
- SSE 프레이밍(`data: {...}\n\n`)·하트비트(`": ping"` 15초) 무변경.
- `tool_call`/`tool_result`의 `tool_name`은 SDK 도구명 원문(Read/Grep/Glob/Bash/WebSearch/WebFetch). 한국어 병기는 프론트 표시 계층 책임.
- `citation`: 파일럿 provider는 방출하지 않을 수 있음(SDK WebSearch 출처는 별도 이벤트가 없음) — 출처는 본문 마크다운 링크로 표기. 스키마·프론트 렌더링은 유지.

### C4. 제거 목록

- 백엔드: `GET /api/meta/llm`, `DiscussionRequest.model/.reasoning_effort`, `llm/options.py`, `llm/openai_provider.py`, `llm/anthropic_provider.py`, `llm/tools/`(4파일 전체), `scripts/smoke_openai.py`, `tests/test_openai_tools.py`, config의 `openai_api_key`/`llm_model`/`llm_reasoning_effort`/`llm_verbosity`/`semantic_scholar_api_key`, requirements의 `openai`.
- 프론트: `LlmMeta` 타입, `api.getLlmMeta`, `chatStore.model/reasoningEffort/setModel/setReasoningEffort`, 모델·추론 드롭다운 UI, `styles.css`의 `.llm-controls`/`.llm-hint`.

### C5. `LLMProvider` ABC (유지 — 시그니처만 변경)

```python
@abstractmethod
def stream_chat(
    self, system: str, messages: list[ChatMessage], mode: str | None = None,
) -> AsyncIterator[StreamEvent]: ...
```

`create_provider()` factory 유지: `llm_provider == "claude_agent"` → `ClaudeAgentProvider`.

### C6. 모드 선언 (`backend/app/llm/modes.py` — 수치 유일 선언 지점)

| 항목 | quick | deep |
|---|---|---|
| model | `claude-haiku-4-5` | `claude-opus-5` |
| allowed_tools | `()` | `("Read", "Grep", "Glob", "WebSearch", "WebFetch", "Bash(.venv/Scripts/python.exe *)", "Bash(.venv\\Scripts\\python.exe *)")` |
| disallowed_tools | `("*",)` (전 도구 컨텍스트 제거) | `("Write", "Edit", "NotebookEdit", "Task", "TodoWrite")` |
| max_turns | 1 | 25 |
| thinking | `{"type": "disabled"}` | 미지정(SDK 기본) |

공통 `ClaudeAgentOptions`: `cwd=PROJECT_ROOT`, `permission_mode="dontAsk"`, `setting_sources=[]`, `include_partial_messages=True`, `env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"}`(+ `anthropic_api_key` 설정 시 `ANTHROPIC_API_KEY` 추가). `VENV_PYTHON = ".venv/Scripts/python.exe"` 상수를 Bash 패턴과 시스템 프롬프트 지침 양쪽의 유일 출처로 사용.

### C7. 시스템/유저 프롬프트 구성 계약

- 시스템 프롬프트(모드별, `ContextBuilder.build_system_prompt(ctx, mode_spec)`):
  1. PERSONA(기존 문체 계약 유지 — search_scholar 문구만 WebSearch/WebFetch로 교체)
  2. DOMAIN_INFO.md 전문(두 모드 공통 — 기존 방식 유지, quick은 도구가 없어 유일한 도메인 근거)
  3. 대시보드 컨텍스트(기존 렌더링 유지)
  4. quick 전용: 즉답 지침(§3.7-Q)
  5. deep 전용: 프로젝트 탐색 가이드 + 연산 정책(§3.7-D — 원문 그대로)
- 대화 이력: provider가 유저 프롬프트로 렌더링(마지막 user 메시지 = `# 이번 질문`, 그 이전 = `# 이전 대화 이력` 블록, `[사용자]`/`[어시스턴트]` 접두).

### 3.7 정책 문구 원문 (시스템 프롬프트 상수 — 취지 변경 금지)

**§3.7-D `COMPUTE_POLICY` (deep 전용):**

```
# 연산 정책 (반드시 준수)
- 이 채팅 세션은 가볍게 유지한다. 헤비한 개발성 코드 실행은 금지한다.
- 값 확인·트렌드 확인은 데이터 읽기만으로 대응한다. 집계(합계/평균) 요청은 가벼운
  코드 실행을 허용한다. 간단한 선형회귀(회귀식·R² 산출) 수준까지 허용한다.
- 그 이상의 명시적으로 헤비한 연산(다변량 모델링, 대량 반복 계산, 전체 heat 전수
  시뮬레이션 등)이 필요한 요청이면, 실행 전에 반드시 사용자에게 다음과 같이 묻고
  진행 의사를 응답받은 후에만 진행한다:
  "이 작업은 내부적으로 스크립트 작성·계산·검증을 거쳐야 하므로 응답이 상당히
  오래 걸릴 수 있습니다. 오래 걸리더라도 객관적으로 확인된 결론을 원하시면
  진행하겠습니다. 진행할까요?"
- 코드/스크립트 파일이 필요하면 프로젝트 루트의 .chat_tmp/ 아래에만 생성한다
  (파이썬 코드로 생성). 프로젝트 소스 파일은 절대 수정하지 않는다.
```

**§3.7-D 프로젝트 탐색 가이드 (deep 전용, 취지 유지·문구 조정 가능):**

```
# 프로젝트 탐색 가이드
- 작업 디렉토리는 이 대시보드 프로젝트의 루트다. 필요하면 직접 파일을 확인하라:
  - SPEC.md: 대시보드/데이터 명세 · docs/: 작업 이력과 계획
  - backend/app/domain, backend/app/data: 데이터 모델·태그·스펙 정의 코드
  - data/dummy/heats.parquet: heat 단위 정적 데이터(장입/KPI/종점/슬래그, ~500 heat)
  - data/dummy/additions.parquet: 부원료 투입 이벤트
  - data/dummy/timeseries/<heat_id>.parquet: heat별 1초 시계열(active_power 등)
- 파이썬 실행은 반드시 `.venv/Scripts/python.exe ...` 로만 한다(pandas/pyarrow 사용
  가능). 다른 셸 명령은 권한 정책상 거부된다.
- 웹/문헌 확인은 WebSearch/WebFetch를 사용하고 본문에 출처 링크를 남긴다.
```

**§3.7-Q quick 전용 지침 (취지 유지·문구 조정 가능):**

```
# 응답 지침 (빠른 대화 모드)
- 도구 없이, 위 도메인 지식과 화면 컨텍스트만으로 즉시 답한다.
- 실데이터 조회·파일 확인·계산이 필요한 질문이면 추측하지 말고, "심화 분석 모드로
  전환해 다시 질문해 달라"고 한 문장으로 안내한다.
```

## 4. 파일 단위 변경 명세

### U1 — backend-coder (스코프: `backend/`, `requirements.txt`, `.env.example`, `.gitignore`)

**삭제**
- `backend/app/llm/openai_provider.py`
- `backend/app/llm/anthropic_provider.py`
- `backend/app/llm/options.py`
- `backend/app/llm/tools/` 디렉토리 전체(`__init__.py`, `base.py`, `data_tools.py`, `scholar.py`)
- `backend/scripts/smoke_openai.py`
- `backend/tests/test_openai_tools.py`

**신규**
- `backend/app/llm/modes.py` — C6 선언 + `ChatModeSpec` dataclass + `CHAT_MODES` + `DEFAULT_MODE_ID="quick"` + `resolve_mode()` + `as_dicts()` + `VENV_PYTHON`
- `backend/app/llm/claude_agent_provider.py` — `ClaudeAgentProvider(LLMProvider)`: 프롬프트 렌더링, `ClaudeAgentOptions` 구성, `query()` 스트림 → StreamEvent 정규화
- `backend/scripts/smoke_claude_agent.py` — 실호출 스모크(quick/deep 서브커맨드, TTFB·소요시간 측정, 수동 실행 전용)
- `backend/tests/test_chat_modes.py` — 모드 선언/폴백 테스트
- `backend/tests/test_claude_agent_provider.py` — 정규화/프롬프트 렌더링/옵션 구성 테스트(SDK 실호출 없음)

**수정**
- `backend/app/llm/base.py` — C5 시그니처, factory, docstring(OpenAI 언급 제거)
- `backend/app/llm/context_builder.py` — C7 모드별 구성(PERSONA 유지, COMPUTE_POLICY 등 상수 추가)
- `backend/app/services/discussion_service.py` — `DiscussionRequest.mode`(C2), 서비스가 mode_spec 해석 후 빌더/provider 호출
- `backend/app/api/routes/meta.py` — `/llm` 삭제, `/chat_modes` 추가(C1)
- `backend/app/config.py` — C4 항목 제거, `llm_provider: Literal["claude_agent"]`, `anthropic_api_key` 유지+주석
- `backend/requirements.txt` — `openai` 제거, `claude-agent-sdk` 추가(`httpx`는 TestClient 의존으로 유지)
- `backend/tests/test_discussion_sse.py` — 오버라이드 섹션을 mode 계약으로 교체(하트비트 테스트 무변경)
- `backend/tests/test_contracts.py` — `test_meta_llm_contract` → `test_meta_chat_modes_contract`
- `.env.example` — LLM 섹션 재작성(구독 인증 기본 + 팀 배포 시 ANTHROPIC_API_KEY 주석)
- `.gitignore` — `.chat_tmp/` 추가

`backend/app/api/routes/discussion.py`, `backend/app/api/deps.py`, `backend/app/llm/__init__.py`(빈 파일)는 무변경.

### U2 — frontend-coder (스코프: `frontend/src/`)

**수정**
- `frontend/src/api/types.ts` — `LlmMeta` 삭제, `ChatMode`/`ChatModeInfo`/`ChatModesMeta` 추가
- `frontend/src/api/client.ts` — `getLlmMeta` → `getChatModes` (`GET /api/meta/chat_modes`, 정적 메타 캐시 유지)
- `frontend/src/state/chatStore.ts` — `model`/`reasoningEffort` → `mode: ChatMode | null` + `setMode`
- `frontend/src/discussion/useChatStream.ts` — 요청 바디 `{messages, context, mode}` (mode null이면 미전송 또는 null 전송 — 서버 quick 폴백)
- `frontend/src/discussion/DiscussionPanel.tsx` — 드롭다운 제거 → 세그먼트 2버튼 + 안내 캡션, tool 칩 한국어 병기 매핑
- `frontend/src/styles.css` — `.llm-controls`/`.llm-hint` 제거 → `.mode-controls`/`.mode-seg`/`.mode-hint` 신설(기존 디자인 토큰 준수)

## 5. 코더 실행 프롬프트

### 5.1 backend-coder 프롬프트 (전문)

(§보고서와 동일 — 아래 원문을 그대로 전달한다)

```
[작업] Discussion 채팅 백엔드를 OpenAI API에서 Claude Agent SDK로 전면 전환 (파일럿)

## 배경
전기로(EAF) 공정 분석 대시보드 프로젝트다(레이어: api → services → (data|llm) → domain,
역방향 금지, CLAUDE.md 설계 원칙 준수). Discussion 채팅(POST /api/discussion, SSE)은
현재 OpenAI Responses API(openai_provider.py) 기반이며, 이를 claude-agent-sdk의
query() 하네스로 교체한다. OpenAI 경로는 전면 폐기한다(롤백은 git으로 가능하므로
호환 코드를 남기지 말 것). 대화 이력은 휘발성(서버 미저장, 매 요청 프론트가 전송) 유지.

인증: 이 PC의 Claude Code CLI 로그인(구독) 자격증명을 SDK가 자동 상속한다.
.env에 ANTHROPIC_API_KEY 불필요. 코드/로그 어디에도 자격증명을 출력하지 말 것.

먼저 읽어라: CLAUDE.md, backend/app/llm/ 전체, backend/app/services/discussion_service.py,
backend/app/api/routes/discussion.py, backend/app/api/routes/meta.py, backend/app/config.py,
backend/tests/test_discussion_sse.py, backend/tests/test_contracts.py, DOMAIN_INFO.md.

## SDK 사용법 (공식 문서 확인 완료 — 이대로 구현)
- 설치: requirements.txt에 claude-agent-sdk 추가(pip 패키지, CLI 번들). openai 제거.
  httpx는 FastAPI TestClient 의존이므로 유지.
- 매 요청 1회: `from claude_agent_sdk import query, ClaudeAgentOptions` →
  `async for message in query(prompt=<유저 프롬프트>, options=<옵션>)`.
- 스트리밍: options에 include_partial_messages=True. 이때
  `claude_agent_sdk.types.StreamEvent`(우리 app.llm.base.StreamEvent와 이름 충돌 —
  반드시 `as SdkStreamEvent` 별칭 임포트)가 원시 이벤트를 담아 온다:
  - message.event["type"] == "content_block_delta" 이고 event["delta"]["type"] ==
    "text_delta" → 본문 토큰 event["delta"]["text"]
  - "content_block_start" 이고 event["content_block"]["type"] == "tool_use" →
    도구 시작, 이름 event["content_block"]["name"] (Read/Bash/WebSearch 등),
    id event["content_block"]["id"]
  - "thinking_delta"/"input_json_delta"/기타 미지 이벤트는 무시(스트림 견고성)
- 완결 AssistantMessage도 함께 yield된다 — 그 안의 TextBlock을 다시 방출하면
  텍스트가 2배가 된다. 본문은 델타로만 방출하고 AssistantMessage는 무시하라.
- 도구 실행 완료: UserMessage 안의 ToolResultBlock(tool_use_id로 매칭)이 오면
  TOOL_RESULT를 방출한다. 만약 사용 중인 SDK 버전의 query() 스트림에서 UserMessage/
  ToolResultBlock이 관측되지 않으면, tool_use 블록의 content_block_stop 시점에
  TOOL_RESULT를 방출하는 폴백으로 구현하고 코드 주석에 근거를 남겨라.
- ResultMessage 수신 → DONE 방출 후 종료(subtype이 error면 ERROR 방출 후 종료).
- 예외(스폰 실패/인증 없음 등) → ERROR 이벤트(메시지 300자 절단) 방출 후 종료.
  스트림을 예외로 깨뜨리지 마라. asyncio.CancelledError(클라이언트 중단)는 그대로
  전파하되 finally에서 SDK 제너레이터가 정리되도록 하라(서브프로세스 잔존 방지).
- 권한 잠금(공식 패턴): allowed_tools(사전 승인) + permission_mode="dontAsk" —
  목록 밖 도구/명령은 프롬프트 없이 즉시 거부된다. disallowed_tools=["*"]는 모든
  도구 정의를 컨텍스트에서 제거한다(quick용). bare name("Write")은 해당 도구를
  컨텍스트에서 제거한다. can_use_tool 콜백/훅은 사용하지 않는다.
- setting_sources=[] 필수 — 생략하면 프로젝트 CLAUDE.md(개발 에이전트 운영 규칙)가
  자동 주입되어 채팅 페르소나를 오염시킨다.
- env={"CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1"} — 세션 트랜스크립트 디스크 기록 억제.
  settings.anthropic_api_key가 비어있지 않으면 env["ANTHROPIC_API_KEY"]에 추가
  (팀 배포 전환 경로).
- system_prompt는 커스텀 문자열(기본 프롬프트 완전 대체). 문자열은 CLI 인자로
  전달되어 Windows 인자 길이 제한(~32K자)이 있으므로, 렌더링 결과가 16,000자를
  초과하면 임시 파일에 쓰고 {"type": "file", "path": <경로>} 형태로 전달했다가
  finally에서 삭제하는 헬퍼를 넣어라.

## 계약 (프론트와 병렬 작업 중 — 임의 변경 절대 금지)

C1. GET /api/meta/chat_modes (신규):
{
  "modes": [
    {"id": "quick", "label_ko": "빠른 대화",
     "description_ko": "수 초 안에 답합니다. 일반 질문이나 화면 내용의 간단한 확인에 적합합니다."},
    {"id": "deep", "label_ko": "심화 분석",
     "description_ko": "데이터와 문서를 직접 확인하며 답합니다. 정확하지만 수 분까지 걸릴 수 있습니다."}
  ],
  "default_mode": "quick"
}
항목 필드는 {id, label_ko, description_ko} 정확히 3개, 순서 quick → deep, 문구 원문 그대로.
GET /api/meta/llm 라우트는 삭제한다(404가 되어야 함).

C2. DiscussionRequest: {"messages": [...], "context": {...}|null, "mode": "quick"|"deep"|null}
- model/reasoning_effort 필드 삭제. mode 누락/null/목록 밖 값 → "quick" 폴백(400 아님).
- context(DashboardContext) 스키마 무변경.

C3. SSE 응답 무변경: StreamEvent 스키마({type, text, tool_name, url, title},
type 6종 text_delta/tool_call/tool_result/citation/done/error), data: 프레이밍,
15초 하트비트(": ping") 전부 그대로. routes/discussion.py는 수정하지 않는다.
tool_call/tool_result의 tool_name은 SDK 도구명 원문(Read/Bash 등)을 넣는다.
citation은 이 provider에서 방출하지 않아도 된다(출처는 본문 마크다운 링크로 —
스키마와 enum은 유지).

C5. LLMProvider ABC 유지, 시그니처만 변경:
    def stream_chat(self, system: str, messages: list[ChatMessage],
                    mode: str | None = None) -> AsyncIterator[StreamEvent]
create_provider(): settings.llm_provider == "claude_agent" → ClaudeAgentProvider.

C6. 모드 선언 수치(backend/app/llm/modes.py가 유일 선언 지점 — 다른 파일에 모델명·
도구 목록·턴 수 하드코딩 금지):
- quick: model="claude-haiku-4-5", allowed_tools=(), disallowed_tools=("*",),
  max_turns=1, thinking={"type": "disabled"}
- deep: model="claude-opus-5",
  allowed_tools=("Read", "Grep", "Glob", "WebSearch", "WebFetch",
                 "Bash(.venv/Scripts/python.exe *)", "Bash(.venv\\Scripts\\python.exe *)"),
  disallowed_tools=("Write", "Edit", "NotebookEdit", "Task", "TodoWrite"),
  max_turns=25, thinking 미지정(SDK 기본)
- 공통 옵션: cwd=PROJECT_ROOT(app.config), permission_mode="dontAsk",
  setting_sources=[], include_partial_messages=True, env 위 참조
- VENV_PYTHON = ".venv/Scripts/python.exe" 상수를 Bash 허용 패턴과 시스템 프롬프트
  지침 문구 양쪽의 유일 출처로 사용하라.

## 파일별 작업

[삭제 — git rm 상당, 흔적 없이]
- backend/app/llm/openai_provider.py
- backend/app/llm/anthropic_provider.py
- backend/app/llm/options.py
- backend/app/llm/tools/ 디렉토리 전체(4파일)
- backend/scripts/smoke_openai.py
- backend/tests/test_openai_tools.py

[신규] backend/app/llm/modes.py
- @dataclass(frozen=True) ChatModeSpec: id, label_ko, description_ko, model,
  allowed_tools: tuple[str, ...], disallowed_tools: tuple[str, ...], max_turns: int,
  thinking_disabled: bool
- CHAT_MODES: list[ChatModeSpec] (C6 수치·C1 라벨 문구), DEFAULT_MODE_ID = "quick"
- resolve_mode(mode_id: str | None) -> ChatModeSpec  # 누락/무효 → quick
- as_dicts() -> list[dict]  # C1의 modes 배열 형태 {id, label_ko, description_ko}
- VENV_PYTHON 상수. llm 계층 선언이므로 config/서비스에 의존하지 않는다
  (기존 options.py의 선언 스타일을 따르라).

[신규] backend/app/llm/claude_agent_provider.py — ClaudeAgentProvider(LLMProvider)
- __init__(settings: Settings)
- stream_chat(system, messages, mode=None):
  1) spec = modes.resolve_mode(mode)
  2) prompt = _render_prompt(messages): 마지막 user 메시지를 "# 이번 질문" 블록으로,
     그 이전 메시지들이 있으면 "# 이전 대화 이력" 블록에 "[사용자] ..."/"[어시스턴트] ..."
     줄로 렌더링(이력 없으면 이력 블록 생략). messages가 비면 ERROR 방출 후 종료.
  3) options = _build_options(system, spec): 위 C6/공통 옵션 규칙.
     thinking_disabled=True면 thinking={"type": "disabled"} 전달.
  4) query() 스트림을 위 "SDK 사용법" 규칙대로 StreamEvent로 정규화.
- _render_prompt/_build_options는 테스트 가능하게 분리(모듈 함수 또는 메서드).
- claude_agent_sdk 임포트는 이 파일에만 존재해야 한다(레이어 격리).

[수정] backend/app/llm/base.py
- stream_chat 시그니처를 C5로. docstring에서 OpenAI/options.py 언급 제거.
- create_provider(): "claude_agent" 분기만 남기고 openai/anthropic 분기 제거.

[수정] backend/app/llm/context_builder.py
- DashboardContext 무변경. DOMAIN_INFO.md 로딩 유지(두 모드 공통 포함).
- PERSONA 유지하되 "학술 검색(search_scholar)" 문구를 "웹 검색(WebSearch)/웹 문서
  확인(WebFetch)"으로 교체.
- 상수 추가(아래 원문 그대로 — 특히 확인 질문 문장은 한 글자도 바꾸지 마라):

COMPUTE_POLICY = """\
# 연산 정책 (반드시 준수)
- 이 채팅 세션은 가볍게 유지한다. 헤비한 개발성 코드 실행은 금지한다.
- 값 확인·트렌드 확인은 데이터 읽기만으로 대응한다. 집계(합계/평균) 요청은 가벼운
  코드 실행을 허용한다. 간단한 선형회귀(회귀식·R² 산출) 수준까지 허용한다.
- 그 이상의 명시적으로 헤비한 연산(다변량 모델링, 대량 반복 계산, 전체 heat 전수
  시뮬레이션 등)이 필요한 요청이면, 실행 전에 반드시 사용자에게 다음과 같이 묻고
  진행 의사를 응답받은 후에만 진행한다:
  "이 작업은 내부적으로 스크립트 작성·계산·검증을 거쳐야 하므로 응답이 상당히
  오래 걸릴 수 있습니다. 오래 걸리더라도 객관적으로 확인된 결론을 원하시면
  진행하겠습니다. 진행할까요?"
- 코드/스크립트 파일이 필요하면 프로젝트 루트의 .chat_tmp/ 아래에만 생성한다
  (파이썬 코드로 생성). 프로젝트 소스 파일은 절대 수정하지 않는다.
"""

- deep 전용 "# 프로젝트 탐색 가이드" 상수(취지 유지, VENV_PYTHON 상수 삽입):
  작업 디렉토리=프로젝트 루트 / SPEC.md·docs/ / backend/app/domain·data(모델·태그·
  스펙 정의 코드) / data/dummy/heats.parquet(heat 정적 데이터 ~500건)·
  additions.parquet(부원료 투입)·timeseries/<heat_id>.parquet(1초 시계열) /
  파이썬 실행은 반드시 `{VENV_PYTHON} ...`로만(다른 명령은 권한 정책상 거부됨) /
  웹·문헌은 WebSearch/WebFetch 사용, 본문에 출처 링크.
- quick 전용 "# 응답 지침" 상수: 도구 없이 도메인 지식+화면 컨텍스트만으로 즉답,
  실데이터 조회·계산이 필요하면 추측하지 말고 "심화 분석 모드로 전환해 다시 질문해
  달라"고 한 문장 안내.
- build_system_prompt(ctx: DashboardContext | None, mode: ChatModeSpec) -> str:
  [PERSONA, 도메인지식, 컨텍스트, 모드별 블록] 순서로 "\n\n---\n\n" 결합(기존 방식).

[수정] backend/app/services/discussion_service.py
- DiscussionRequest: model/reasoning_effort 삭제, mode: str | None = None 추가(C2).
- stream(): spec = modes.resolve_mode(req.mode) → system = builder.build_system_prompt(
  req.context, spec) → provider.stream_chat(system, req.messages, mode=spec.id).

[수정] backend/app/api/routes/meta.py
- llm_options() 라우트 삭제, from app.llm import options 제거.
- chat_modes() 신규: C1 그대로 {"modes": modes.as_dicts(), "default_mode":
  modes.DEFAULT_MODE_ID}.

[수정] backend/app/config.py
- 삭제: openai_api_key, llm_model, llm_reasoning_effort, llm_verbosity,
  semantic_scholar_api_key.
- llm_provider: Literal["claude_agent"] = "claude_agent" (ABC/factory 유지 원칙 —
  향후 provider 추가 시 Literal 확장).
- anthropic_api_key: str = "" 유지 + 주석: "파일럿은 미설정 — 이 PC의 Claude Code
  CLI 로그인(구독) 자격증명을 SDK가 상속한다. 팀 배포 시 이 값만 설정하면 API 키
  인증으로 전환된다."

[수정] backend/requirements.txt
- openai 제거, claude-agent-sdk 추가. httpx 유지(TestClient 의존 주석).
- "향후 Claude 전환 시 활성화 # anthropic" 주석 블록 제거.

[수정] .env.example — LLM 섹션 재작성:
- OPENAI_API_KEY/LLM_MODEL/LLM_REASONING_EFFORT/LLM_VERBOSITY/SEMANTIC_SCHOLAR_API_KEY
  제거, LLM_PROVIDER=claude_agent로.
- 주석: 파일럿은 키 불필요(Claude Code CLI 로그인 상속). 팀 배포 시
  # ANTHROPIC_API_KEY=sk-ant-... 만 설정하면 전환.

[수정] .gitignore — "# Discussion 심화 모드가 생성하는 임시 분석 스크립트" 주석과
함께 .chat_tmp/ 추가.

[신규] backend/scripts/smoke_claude_agent.py (수동 실행 전용 — 작성만 하고 절대
실행하지 마라. 구독 사용량을 소모하므로 verifier가 quick/deep 각 1회만 실행한다)
- 사용법: .venv/Scripts/python.exe scripts/smoke_claude_agent.py quick|deep
  (backend에서 실행, smoke_openai.py의 sys.path 방식을 따르라)
- create_provider()로 provider를 만들어 stream_chat 실호출.
- quick: 컨텍스트 없이 "전기로 조업에서 용락(meltdown) 판단이 왜 중요한지 두 문장
  으로 답하라." / deep: "heat A171400의 active_power 평균값을 실제 데이터에서 직접
  확인해서 답하라. 데이터는 data/dummy 아래 parquet이다."
- 측정·출력: 첫 text_delta까지 TTFB(초), 총 소요시간, 이벤트 시퀀스, tool_call별
  tool_name, 본문 앞 120자. 성공 판정: quick = text_delta 존재+done 종료 / deep =
  추가로 tool_call ≥ 1. exit code 0/1. 자격증명·환경변수 값은 절대 출력 금지.

[수정] backend/tests/test_discussion_sse.py
- 하트비트 테스트 2건 무변경. "요청 단위 모델/effort 오버라이드" 섹션을 mode 계약
  테스트로 교체: mode="deep" 파싱 / 누락 시 None / 목록 밖 값("turbo")도 200이고
  modes.resolve_mode가 quick으로 폴백 / resolve_mode(None)·("")·("deep") 동작.

[수정] backend/tests/test_contracts.py
- test_meta_llm_contract 삭제 → test_meta_chat_modes_contract: 200, 최상위 키
  {"modes", "default_mode"}, ids == ["quick", "deep"], 각 항목 키 {id, label_ko,
  description_ko}이며 값 비어있지 않음, default_mode == "quick", body["modes"] ==
  modes.as_dicts(). 나머지 테스트 무변경.

[신규] backend/tests/test_chat_modes.py
- CHAT_MODES: id 순서 ["quick", "deep"], 모델이 정확히 "claude-haiku-4-5"/
  "claude-opus-5", quick은 allowed_tools 빈 튜플+disallowed ("*",)+max_turns 1+
  thinking_disabled True, deep은 allowed_tools에 Read/Grep/Glob/WebSearch/WebFetch와
  VENV_PYTHON 기반 Bash 패턴 2건 포함·bare "Bash" 미포함, disallowed에 Write/Edit 포함.
- resolve_mode 폴백 3케이스, as_dicts 직렬화 형태.

[신규] backend/tests/test_claude_agent_provider.py (SDK 실호출 없음 — provider 모듈의
query를 monkeypatch한 가짜 async generator로 대체)
- text_delta 정규화: content_block_delta/text_delta → TEXT_DELTA(text 일치)
- tool_use content_block_start → TOOL_CALL(tool_name="Read" 등)
- 가짜 AssistantMessage(TextBlock 포함)를 섞어도 본문이 중복 방출되지 않음
- ResultMessage → 마지막 이벤트가 DONE
- query가 예외를 던지면 ERROR 이벤트 후 정상 종료(예외 전파 없음)
- _render_prompt: 3메시지(u/a/u) → "# 이전 대화 이력"에 앞 2개, "# 이번 질문"에
  마지막 user content; 1메시지 → 이력 블록 없음; 빈 목록 → ERROR
- _build_options: quick → model/haiku·disallowed ("*")·max_turns 1·
  permission_mode "dontAsk"·setting_sources []·include_partial_messages True·
  env에 CLAUDE_CODE_SKIP_PROMPT_HISTORY / deep → model/opus·allowed에 Bash 패턴 포함
- 시스템 프롬프트 길이 폴백 헬퍼: 16,000자 초과 시 file 형태 반환 검증(파일 생성/정리)

## 완료 확인 (직접 실행)
- .venv/Scripts/python.exe -m pytest backend/tests  → 전체 통과
- 실호출·스모크·서버 기동 확인은 하지 마라(verifier 담당).
- rg -i "openai" backend/app backend/tests backend/scripts → 0건이 되게 하라.
- .env는 읽지도 출력하지도 마라.

## 스코프 경계
backend/, requirements.txt, .env.example, .gitignore만 수정. frontend/·docs/·CLAUDE.md·
SPEC.md·데이터 파일은 건드리지 않는다. 요구에 없는 리팩터링 금지.
```

### 5.2 frontend-coder 프롬프트 (전문)

```
[작업] Discussion 채팅 UI: 모델/추론강도 드롭다운 폐기 → 모드 2지선택(빠른 대화/심화 분석) 전환

## 배경
전기로(EAF) 공정 분석 대시보드(React/Vite/TS + zustand)다. 백엔드 LLM이 OpenAI에서
Claude Agent SDK로 교체되어(별도 에이전트가 병렬 작업 중), 채팅 옵션이 "모델+추론
강도 드롭다운 2개"에서 "모드 세그먼트 2버튼"으로 바뀐다. SSE 스트림 이벤트 스키마와
파싱 로직(하트비트 포함), 대기 인디케이터, 중단 버튼은 그대로 유지한다.

먼저 읽어라: frontend/src/discussion/DiscussionPanel.tsx, frontend/src/discussion/
useChatStream.ts, frontend/src/state/chatStore.ts, frontend/src/api/types.ts,
frontend/src/api/client.ts, frontend/src/styles.css의 .llm-controls 부근(598~630행 부근).

## 계약 (백엔드와 병렬 작업 중 — 임의 변경 절대 금지)

C1. GET /api/meta/chat_modes (신규, 기존 GET /api/meta/llm 대체):
{
  "modes": [
    {"id": "quick", "label_ko": "빠른 대화",
     "description_ko": "수 초 안에 답합니다. 일반 질문이나 화면 내용의 간단한 확인에 적합합니다."},
    {"id": "deep", "label_ko": "심화 분석",
     "description_ko": "데이터와 문서를 직접 확인하며 답합니다. 정확하지만 수 분까지 걸릴 수 있습니다."}
  ],
  "default_mode": "quick"
}

C2. POST /api/discussion 요청 바디: {"messages": [...], "context": {...}, "mode":
"quick"|"deep"|null}. model/reasoning_effort 필드는 보내지 않는다. mode가 null이면
서버가 quick으로 처리한다.

C3. SSE 응답 무변경: StreamEvent {type, text, tool_name, url, title} (type 6종),
"data: {...}\n\n" 프레이밍, ": ping" 하트비트. useChatStream의 파싱 로직은 수정하지
않는다(요청 바디 부분만 변경). citation 이벤트는 드물어지지만 렌더링은 유지한다.
tool_call/tool_result의 tool_name에는 이제 Claude Code 도구명(Read, Grep, Glob,
Bash, WebSearch, WebFetch)이 온다.

## 파일별 작업

[수정] frontend/src/api/types.ts
- LlmMeta 인터페이스 삭제.
- 추가:
  export type ChatMode = "quick" | "deep";
  export interface ChatModeInfo { id: ChatMode; label_ko: string; description_ko: string; }
  export interface ChatModesMeta { modes: ChatModeInfo[]; default_mode: ChatMode; }
- 나머지 타입(StreamEvent 포함) 무변경.

[수정] frontend/src/api/client.ts
- getLlmMeta 삭제 → getChatModes: () => getMeta<ChatModesMeta>("/api/meta/chat_modes")
  (정적 메타 캐시 getMeta 방식 유지).

[수정] frontend/src/state/chatStore.ts
- model/reasoningEffort/setModel/setReasoningEffort 삭제.
- mode: ChatMode | null (null = 서버 기본값 quick, 휘발성) + setMode(mode: ChatMode)
  추가. 나머지(스트리밍/tool 이력/인용) 무변경.

[수정] frontend/src/discussion/useChatStream.ts
- 요청 바디를 { messages, context: toPayload(), mode: state.mode } 로 변경
  (model/reasoning_effort 제거). 파서·중단·오류 처리 무변경.

[수정] frontend/src/discussion/DiscussionPanel.tsx
- LlmMeta/드롭다운/llm-controls 블록 전부 제거.
- api.getChatModes()를 마운트 시 1회 호출(기존 getLlmMeta useEffect 패턴 유지 —
  실패 시 조용히 무시하고 컨트롤 숨김, 채팅은 서버 기본값으로 동작). 성공 시
  chatStore.mode가 null이면 default_mode로 설정.
- 헤더에 모드 세그먼트: 버튼 2개(라디오그룹 시맨틱, aria-pressed 또는 role="radio"),
  각 버튼 라벨은 meta의 label_ko. 선택 모드는 액센트 표시. 스트리밍 중에도 변경
  가능(다음 전송부터 적용 — 기존 드롭다운과 동일 동작).
- 세그먼트 아래 캡션: 선택된 모드의 description_ko + " · 다음 전송부터 적용".
  비전공자 대상 문구이므로 meta 문구를 가공 없이 그대로 표시한다.
- tool 칩 한국어 병기: 컴포넌트 상단에 선언 상수
  const TOOL_LABELS: Record<string, string> = {
    Read: "파일 읽기 (Read)", Grep: "본문 검색 (Grep)", Glob: "파일 탐색 (Glob)",
    Bash: "파이썬 분석 (Bash)", WebSearch: "웹 검색 (WebSearch)",
    WebFetch: "웹 문서 확인 (WebFetch)",
  };
  표시 헬퍼: TOOL_LABELS[name] ?? name (미지 도구는 원문 그대로).
  진행 칩 "…실행 중", 완료 칩 "…완료", 대기 인디케이터의 activeTool 문구에도 동일
  헬퍼 적용(기존 "조회 중/조회 완료" 문구는 "실행 중/완료"로).
- 대기 인디케이터(경과 초·SLOW_HINT)·중단 버튼·조건부 자동 스크롤·마크다운 렌더링
  무변경.

[수정] frontend/src/styles.css
- .llm-controls, .llm-controls select, .llm-controls select:hover, .llm-hint 제거.
- .mode-controls(헤더 둘째 줄 전체 폭, 우측 정렬), .mode-seg(버튼 그룹: 헤어라인
  보더, 소형), .mode-seg button(캡션 크기, 선택 시 액센트 var(--accent) 계열 표시),
  .mode-hint(기존 .llm-hint에 준하는 우측 정렬 캡션) 신설. 기존 디자인 토큰(CSS
  변수: --border, --accent, --fs-caption 등)만 사용하고 새 색상 하드코딩·그림자
  사용 금지(프로젝트 디자인 규칙).

## 완료 확인 (직접 실행)
- cd frontend && npm run build → 성공(타입 오류 0).
- rg -i "openai|LlmMeta|reasoningEffort|reasoning_effort|meta/llm" frontend/src → 0건.

## 스코프 경계
frontend/src만 수정. package.json 의존성 추가 금지. 백엔드·docs·데이터 파일은
건드리지 않는다. UI 텍스트는 한국어(기술 용어 영문 병기). 요구에 없는 리팩터링 금지.
```

## 6. verifier 체크리스트

전제: 코드 수정 없이 검증·리포트만. `.env` 열람/출력 금지. **F 섹션 실호출은 quick/deep 각 정확히 1회만**(구독 사용량 소모).

**A. 백엔드 테스트/단위**
- [ ] A1 `.venv/Scripts/python.exe -m pytest backend/tests` 전체 통과
- [ ] A2 `test_chat_modes.py`: 모델 id 정확 일치(`claude-haiku-4-5`/`claude-opus-5`), quick 도구 0(disallowed `("*",)`, max_turns 1), deep allowed_tools에 Read/Grep/Glob/WebSearch/WebFetch + `.venv` 파이썬 Bash 패턴 2건(슬래시/역슬래시), bare `"Bash"` 미포함, resolve_mode 폴백(None/""/무효 → quick)
- [ ] A3 `test_claude_agent_provider.py`(SDK 실호출 없음): text_delta/tool_call 정규화, AssistantMessage 텍스트 중복 미방출, ResultMessage→DONE, 예외→ERROR(스트림 미파괴), 이력 렌더링(`# 이전 대화 이력`/`# 이번 질문`), 옵션 구성(permission_mode="dontAsk", setting_sources=[], include_partial_messages=True, CLAUDE_CODE_SKIP_PROMPT_HISTORY)
- [ ] A4 `test_discussion_sse.py`: 하트비트 테스트 2건 원형 유지·통과, mode 파싱(누락→None, 무효값 200+quick 폴백)

**B. API 계약**
- [ ] B1 `GET /api/meta/chat_modes` 응답이 C1 원문과 일치(키 3개, 순서 quick→deep, default_mode "quick", 라벨/설명 문구 그대로)
- [ ] B2 `GET /api/meta/llm` → 404
- [ ] B3 `DiscussionRequest`에 model/reasoning_effort 필드 부재, mode 필드 존재(pydantic 모델 확인)
- [ ] B4 StreamEvent 스키마 무변경: `backend/app/llm/base.py`의 6종 enum·5필드 == `frontend/src/api/types.ts`의 StreamEventType/StreamEvent
- [ ] B5 `frontend/src/api/types.ts`의 ChatModesMeta ↔ C1 응답 형태 일치, useChatStream 요청 바디가 C2와 일치

**C. 폐기 잔재 (grep)**
- [ ] C1 `rg -i "openai"` → backend/app, backend/tests, backend/scripts, frontend/src에서 0건
- [ ] C2 `rg "reasoning_effort|reasoningEffort|LlmMeta|meta/llm|search_scholar|semantic_scholar"` → 위 코드 경로에서 0건
- [ ] C3 삭제 파일 부재: `llm/openai_provider.py`, `llm/anthropic_provider.py`, `llm/options.py`, `llm/tools/`(디렉토리째), `scripts/smoke_openai.py`, `tests/test_openai_tools.py`
- [ ] C4 requirements.txt: `openai` 없음, `claude-agent-sdk` 있음, `httpx` 유지(TestClient 의존)
- [ ] C5 config.py: openai_api_key/llm_model/llm_reasoning_effort/llm_verbosity/semantic_scholar_api_key 부재, `llm_provider: Literal["claude_agent"]`, anthropic_api_key 유지+구독/팀배포 주석
- [ ] C6 `.gitignore`에 `.chat_tmp/`, `.env.example`에 OPENAI 항목 부재+구독 인증 주석

**D. 설계 원칙 (CLAUDE.md)**
- [ ] D1 `LLMProvider` ABC + `create_provider` factory 경유 유지, `claude_agent_sdk` 임포트가 `llm/claude_agent_provider.py` 1개 파일에만 존재(스모크 스크립트는 create_provider 경유 — 직접 임포트 없음)
- [ ] D2 모델명/도구 목록/턴 수의 유일 선언: `rg "claude-haiku-4-5|claude-opus-5"` 결과가 `llm/modes.py`와 테스트 파일에만 존재
- [ ] D3 연산 정책 원문 포함: `rg "진행할까요" backend/app` → context_builder.py 1건(확인 질문 문장 원문 유지)
- [ ] D4 레이어 방향: routes/services에서 SDK·모드 수치 직접 참조 없음(모드는 `llm/modes.py` 경유)

**E. 프론트**
- [ ] E1 `cd frontend && npm run build` 성공
- [ ] E2 DiscussionPanel: 드롭다운(select) 부재, 세그먼트 2버튼 + description_ko 캡션("다음 전송부터 적용" 포함), meta 실패 시 조용한 폴백 유지
- [ ] E3 chatStore: mode/setMode 존재, model/reasoningEffort 부재
- [ ] E4 tool 칩: TOOL_LABELS 매핑(Read/Grep/Glob/Bash/WebSearch/WebFetch 한국어 병기) + 미지 도구 원문 폴백
- [ ] E5 대기 인디케이터(경과 초/지연 안내)·중단 버튼·SSE 파서(": ping" 무시) 코드 무변경 확인

**F. 실호출 스모크 (각 정확히 1회 — 재실행 금지)**
- [ ] F1 quick 1회: `cd backend && ../.venv/Scripts/python.exe scripts/smoke_claude_agent.py quick` → exit 0, text_delta+done, **TTFB 실측값 기록**. 판정: TTFB ≤ 15초 PASS(수 초 목표 대비 실측치를 리포트에 명시)
- [ ] F2 deep 1회: `... smoke_claude_agent.py deep` → exit 0, tool_call ≥ 1(Read 또는 Bash 관측), done 종료, **총 소요시간 기록**
- [ ] F3 스모크 출력에 자격증명/키 문자열 없음
- [ ] F4 스모크 후 `git status`가 소스 변경 없음(.chat_tmp/ 밖 신규 파일 없음), 잔존 `claude`/`node` 고아 프로세스 없음(작업관리자 또는 `tasklist` 확인)

## 7. planner 판단 사항 (요구사항 범위 내 결정)

1. **학술 검색(search_scholar·Semantic Scholar) 완전 폐기**: tools/ 삭제 지시의 파생. 문헌 확인은 deep 모드의 WebSearch/WebFetch가 담당. `semantic_scholar_api_key` 설정도 함께 제거.
2. **DOMAIN_INFO.md는 두 모드 모두 시스템 프롬프트에 직접 포함**(현재 ~5KB): quick은 도구가 없어 유일한 도메인 근거이고, TTFB 영향 미미. 파일이 커질 경우 대비 16,000자 초과 시 SystemPromptFile 폴백 헬퍼 포함.
3. **Bash 제한 메커니즘 = `allowed_tools` 패턴 + `permission_mode="dontAsk"`** (공식 문서의 locked-down 권장 패턴). `can_use_tool` 콜백/훅 미사용 — 미승인 명령은 프롬프트 없이 즉시 거부되고, 시스템 프롬프트에 `.venv/Scripts/python.exe` 사용 규칙을 명시해 매칭을 유도.
4. **CITATION 이벤트는 파일럿에서 미방출 허용**: SDK WebSearch는 출처를 별도 이벤트로 주지 않음. 스키마·프론트 렌더링은 유지하고 출처는 본문 마크다운 링크로.
5. **tool_result 방출 시점**: UserMessage/ToolResultBlock 매칭(정확) 기본, SDK 버전에 따라 미관측 시 content_block_stop 폴백 — 코더에게 검증 지시 포함.
6. **세션 트랜스크립트 억제**: `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` (stateless 서버 위생 — 요청마다 `~/.claude/projects/`에 jsonl이 쌓이는 것 방지).

**사용자 확인 필요 질문: 없음** (인터뷰 확정 사항으로 충분).

## 8. 후속 (main 세션)

- 검증 PASS 후 `docs/WORKLOG.md` 갱신(전환 요약 + 스모크 실측 TTFB/소요시간 기록, P2/P5의 OpenAI·AnthropicProvider·search_scholar 관련 항목 정리).
- 사용자 브라우저 실사용 확인 권장: quick 1문답 + deep 1문답(모드 세그먼트/칩/캡션 확인).
