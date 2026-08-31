// 대시보드 우측에 상주하는 Discussion 사이드패널.
// 뷰 전환과 무관하게 상태 유지(AppLayout에 상주), 현재 화면 컨텍스트 자동 주입.
// 레이아웃 컨테이너(<aside>)는 AppLayout이 소유한다 — 여기서는 내용만 렌더.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

export function DiscussionPanel() {
  const { messages, streamingText, activeTool, citations, isStreaming, clear } =
    useChatStore();
  const heatId = useDashboardContext((s) => s.heatId);
  const view = useDashboardContext((s) => s.view);
  const { send } = useChatStream();
  const [input, setInput] = useState("");

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
  }, [messages, streamingText, activeTool, citations]);

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

        {activeTool && (
          <div className="tool-chip">
            <span className="spinner" aria-hidden="true" />
            {activeTool} 실행 중…
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
        <button
          type="button"
          className="btn btn-primary"
          onClick={submit}
          disabled={isStreaming || !input.trim()}
        >
          전송
        </button>
      </footer>
    </>
  );
}
