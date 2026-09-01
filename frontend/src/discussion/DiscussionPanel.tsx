// 대시보드 우측에 상주하는 Discussion 사이드패널.
// 뷰 전환과 무관하게 상태 유지(AppLayout에 상주), 현재 화면 컨텍스트 자동 주입.
// 레이아웃 컨테이너(<aside>)는 AppLayout이 소유한다 — 여기서는 내용만 렌더.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
// (useEffect: 경과 시간 타이머 · useLayoutEffect: 조건부 자동 스크롤)
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client";
import type { LlmMeta } from "../api/types";
import { useChatStore } from "../state/chatStore";
import { useDashboardContext } from "../state/dashboardContext";
import { useChatStream } from "./useChatStream";

/** 하단에서 이 거리(px) 안쪽이면 새 내용 도착 시 자동으로 따라 내려간다. */
const STICK_THRESHOLD_PX = 80;

const VIEW_LABELS: Record<string, string> = {
  heat_detail: "Heat 상세",
  trend: "트렌드/비교",
  live: "실시간",
  kpi_summary: "KPI 요약",
};

/** 이 시간(초)을 넘기면 지연 안내 문구를 덧붙인다. */
const SLOW_HINT_SEC = 20;

export function DiscussionPanel() {
  const {
    messages,
    streamingText,
    activeTool,
    toolHistory,
    citations,
    isStreaming,
    clear,
  } = useChatStore();
  const model = useChatStore((s) => s.model);
  const reasoningEffort = useChatStore((s) => s.reasoningEffort);
  const setModel = useChatStore((s) => s.setModel);
  const setReasoningEffort = useChatStore((s) => s.setReasoningEffort);
  const [llmMeta, setLlmMeta] = useState<LlmMeta | null>(null);
  const heatId = useDashboardContext((s) => s.heatId);
  const view = useDashboardContext((s) => s.view);
  const { send, abort } = useChatStream();
  const [input, setInput] = useState("");
  const [elapsed, setElapsed] = useState(0);

  // 첫 토큰까지 수십 초가 걸릴 수 있어 경과 시간을 노출한다(무응답 오인 방지).
  useEffect(() => {
    if (!isStreaming) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    setElapsed(0);
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [isStreaming]);

  // 모델·추론 강도 선택지. 백엔드가 아직 /api/meta/llm을 제공하지 않으면
  // 드롭다운을 숨기고 서버 기본값으로만 동작한다(채팅 기능에는 영향 없음).
  useEffect(() => {
    let alive = true;
    api
      .getLlmMeta()
      .then((meta) => {
        if (!alive) return;
        setLlmMeta(meta);
        const s = useChatStore.getState();
        if (s.model === null) s.setModel(meta.default_model);
        if (s.reasoningEffort === null) s.setReasoningEffort(meta.default_effort);
      })
      .catch(() => {
        /* 미지원 백엔드 — 조용히 무시 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const listRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const onScroll = () => {
      stickRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight <= STICK_THRESHOLD_PX;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    const el = listRef.current;
    if (el && stickRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, streamingText, activeTool, toolHistory, citations, elapsed]);

  const submit = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    stickRef.current = true;
    void send(text);
  };

  return (
    <>
      <header className="discussion-header">
        <strong>Discussion</strong>
        <span className="context-badge" title="현재 대화에 자동 주입되는 화면 컨텍스트">
          {VIEW_LABELS[view] ?? view}
          {heatId ? ` · ${heatId}` : ""}
        </span>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={clear}
          title="대화 초기화 (기록은 저장되지 않습니다)"
        >
          초기화
        </button>

        {llmMeta && (
          <div
            className="llm-controls"
            title="모델과 추론 강도(reasoning effort)를 높일수록 분석은 깊어지지만 응답은 느려집니다. 변경은 다음 전송부터 적용됩니다."
          >
            <select
              aria-label="LLM 모델"
              value={model ?? llmMeta.default_model}
              onChange={(e) => setModel(e.target.value)}
            >
              {llmMeta.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label_ko}
                </option>
              ))}
            </select>
            <select
              aria-label="추론 강도 (reasoning effort)"
              value={reasoningEffort ?? llmMeta.default_effort}
              onChange={(e) => setReasoningEffort(e.target.value)}
            >
              {llmMeta.efforts.map((f) => (
                <option key={f.id} value={f.id}>
                  추론 {f.label_ko}
                </option>
              ))}
            </select>
            <span className="llm-hint">
              빠른 응답 ↔ 심층 분석 트레이드오프 · 다음 전송부터 적용
            </span>
          </div>
        )}
      </header>

      <div className="discussion-messages" ref={listRef}>
        {messages.length === 0 && !streamingText && (
          <p className="placeholder">
            현재 보고 있는 화면을 컨텍스트로 전문가 수준의 공정 디스커션을
            시작하세요.
            <br />예: “이 heat의 용락(meltdown) 시점이 늦은 원인을 분석해줘”
          </p>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg msg-user">
              {m.content}
            </div>
          ) : (
            <div key={i} className="msg msg-assistant markdown">
              <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
            </div>
          ),
        )}

        {streamingText && (
          <div className="msg msg-assistant markdown">
            <Markdown remarkPlugins={[remarkGfm]}>{streamingText}</Markdown>
          </div>
        )}

        {/* tool 실행 이력: tool_call→tool_result 간격이 짧아 실행 중 칩만으로는
            화면에 남지 않으므로, 완료된 tool을 누적해 보여준다. */}
        {isStreaming && (toolHistory.length > 0 || activeTool) && (
          <div className="tool-chips">
            {toolHistory.map((name) => (
              <span key={name} className="tool-chip done">
                {name} 조회 완료
              </span>
            ))}
            {activeTool && (
              <span className="tool-chip">
                <span className="spinner" aria-hidden="true" />
                {activeTool} 조회 중…
              </span>
            )}
          </div>
        )}

        {isStreaming && !streamingText && (
          <div className="msg msg-assistant msg-pending" aria-live="polite">
            <span className="dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span>
              {activeTool ? `${activeTool} 조회 중` : "응답 생성 중"}
              <span className="pending-timer"> {elapsed}초 경과</span>
            </span>
            {elapsed >= SLOW_HINT_SEC && (
              <span className="pending-hint">
                첫 응답까지 1분 이상 걸릴 수 있습니다. 중단하려면 아래 중단
                버튼을 누르세요.
              </span>
            )}
          </div>
        )}

        {citations.length > 0 && (
          <div className="citations">
            <div className="citations-title">출처 (citations)</div>
            <ol>
              {citations.map((c, i) => (
                <li key={i}>
                  <a href={c.url} target="_blank" rel="noreferrer">
                    {c.title || c.url}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <footer className="discussion-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="질문 입력 (Enter 전송, Shift+Enter 줄바꿈)"
          rows={3}
        />
        {isStreaming ? (
          <button
            type="button"
            className="btn"
            onClick={abort}
            title="응답 생성을 중단합니다 (지금까지 받은 내용은 유지)"
          >
            중단
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={!input.trim()}
          >
            전송
          </button>
        )}
      </footer>
    </>
  );
}
