// Discussion 대화 상태 — 휘발성(서버 미저장). 브라우저 세션 동안만 유지.
import { create } from "zustand";
import type { ChatMessage } from "../api/types";

export interface Citation {
  url: string;
  title: string;
}

interface ChatState {
  messages: ChatMessage[];
  streamingText: string; // 수신 중인 assistant 응답
  activeTool: string | null; // 실행 중인 tool 이름 (UI 표시)
  /** 현재 응답에서 실행 완료된 tool 이름 목록. tool_call→tool_result 간격이
   *  매우 짧아 activeTool만으로는 화면에 남지 않으므로 이력으로 누적한다. */
  toolHistory: string[];
  citations: Citation[];
  isStreaming: boolean;
  /** 선택된 LLM 모델. null이면 서버 기본값을 따른다(휘발성 — 저장하지 않음). */
  model: string | null;
  /** 선택된 추론 강도(reasoning effort). null이면 서버 기본값. */
  reasoningEffort: string | null;
  setModel: (model: string | null) => void;
  setReasoningEffort: (reasoningEffort: string | null) => void;
  addUserMessage: (content: string) => void;
  appendDelta: (delta: string) => void;
  setActiveTool: (name: string | null) => void;
  completeTool: (name: string) => void;
  addCitation: (c: Citation) => void;
  finishStreaming: () => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingText: "",
  activeTool: null,
  toolHistory: [],
  citations: [],
  isStreaming: false,
  model: null,
  reasoningEffort: null,
  setModel: (model) => set({ model }),
  setReasoningEffort: (reasoningEffort) => set({ reasoningEffort }),
  addUserMessage: (content) =>
    set((s) => ({
      messages: [...s.messages, { role: "user", content }],
      streamingText: "",
      activeTool: null,
      toolHistory: [],
      citations: [],
      isStreaming: true,
    })),
  appendDelta: (delta) =>
    set((s) => ({ streamingText: s.streamingText + delta })),
  setActiveTool: (activeTool) => set({ activeTool }),
  completeTool: (name) =>
    set((s) => ({
      activeTool: null,
      toolHistory: name && !s.toolHistory.includes(name)
        ? [...s.toolHistory, name]
        : s.toolHistory,
    })),
  addCitation: (c) => set((s) => ({ citations: [...s.citations, c] })),
  finishStreaming: () =>
    set((s) => ({
      messages: s.streamingText
        ? [...s.messages, { role: "assistant", content: s.streamingText }]
        : s.messages,
      streamingText: "",
      activeTool: null,
      isStreaming: false,
    })),
  clear: () =>
    set({
      messages: [],
      streamingText: "",
      activeTool: null,
      toolHistory: [],
      citations: [],
      isStreaming: false,
    }),
}));
