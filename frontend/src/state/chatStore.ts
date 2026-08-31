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
  citations: Citation[];
  isStreaming: boolean;
  addUserMessage: (content: string) => void;
  appendDelta: (delta: string) => void;
  setActiveTool: (name: string | null) => void;
  addCitation: (c: Citation) => void;
  finishStreaming: () => void;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streamingText: "",
  activeTool: null,
  citations: [],
  isStreaming: false,
  addUserMessage: (content) =>
    set((s) => ({
      messages: [...s.messages, { role: "user", content }],
      streamingText: "",
      citations: [],
      isStreaming: true,
    })),
  appendDelta: (delta) =>
    set((s) => ({ streamingText: s.streamingText + delta })),
  setActiveTool: (activeTool) => set({ activeTool }),
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
    set({ messages: [], streamingText: "", citations: [], isStreaming: false }),
}));
