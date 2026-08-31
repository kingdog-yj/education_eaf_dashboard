// 대시보드 우측에 상주하는 Discussion 사이드패널.
// 뷰 전환과 무관하게 상태 유지(AppLayout에 상주), 현재 화면 컨텍스트 자동 주입.
import { useState } from "react";
import { useChatStore } from "../state/chatStore";
import { useDashboardContext } from "../state/dashboardContext";
import { useChatStream } from "./useChatStream";

export function DiscussionPanel() {
  const { messages, streamingText, activeTool, citations, isStreaming, clear } =
    useChatStore();
  const heatId = useDashboardContext((s) => s.heatId);
  const view = useDashboardContext((s) => s.view);
  const { send } = useChatStream();
  const [input, setInput] = useState("");

  const submit = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    void send(text);
  };

  return (
    <aside className="discussion-panel">
      <header className="discussion-header">
        <strong>Discussion</strong>
        <span className="context-badge">
          {view}
          {heatId ? ` · ${heatId}` : ""}
        </span>
        <button onClick={clear} title="대화 초기화 (기록은 저장되지 않습니다)">
          초기화
        </button>
      </header>

      <div className="discussion-messages">
        {messages.length === 0 && !streamingText && (
          <p className="placeholder">
            현재 보고 있는 화면을 컨텍스트로 전문가 수준의 공정 디스커션을
            시작하세요.
            <br />예: "이 heat의 용락 시점이 늦은 원인을 분석해줘"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            {m.content}
          </div>
        ))}
        {streamingText && <div className="msg msg-assistant">{streamingText}</div>}
        {activeTool && <div className="tool-indicator">🔧 {activeTool} 실행 중…</div>}
        {citations.length > 0 && (
          <div className="citations">
            {citations.map((c, i) => (
              <a key={i} href={c.url} target="_blank" rel="noreferrer">
                [{i + 1}] {c.title || c.url}
              </a>
            ))}
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
        <button onClick={submit} disabled={isStreaming}>
          전송
        </button>
      </footer>
    </aside>
  );
}
