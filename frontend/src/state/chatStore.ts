// Discussion 대화 상태 — 휘발성(서버 미저장). 브라우저 세션 동안만 유지.
import { create } from "zustand";
import type { ChatMode, UiChatMessage } from "../api/types";

export interface Citation {
  url: string;
  title: string;
}

interface ChatState {
  messages: UiChatMessage[];
  streamingText: string; // 수신 중인 assistant 응답
  /** 현재 응답 스트림 시작 시각(ms). 완료 시 소요시간 산출용. 미진행이면 null. */
  streamStartedAt: number | null;
  activeTool: string | null; // 실행 중인 tool 이름 (UI 표시)
  /** 현재 응답에서 실행 완료된 tool 이름 목록. tool_call→tool_result 간격이
   *  매우 짧아 activeTool만으로는 화면에 남지 않으므로 이력으로 누적한다. */
  toolHistory: string[];
  citations: Citation[];
  isStreaming: boolean;
  /** 선택된 대화 모드. null이면 서버 기본값(quick)을 따른다(휘발성 — 저장하지 않음). */
  mode: ChatMode | null;
  setMode: (mode: ChatMode) => void;
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
  streamStartedAt: null,
  activeTool: null,
  toolHistory: [],
  citations: [],
  isStreaming: false,
  mode: null,
  setMode: (mode) => set({ mode }),
  addUserMessage: (content) =>
    set((s) => ({
      messages: [...s.messages, { role: "user", content }],
      streamingText: "",
      streamStartedAt: Date.now(),
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
    set((s) => {
      // 중단된 응답에도 그 시점까지의 소요시간을 부여한다.
      const durationS =
        s.streamStartedAt !== null
          ? (Date.now() - s.streamStartedAt) / 1000
          : undefined;
      return {
        messages: s.streamingText
          ? [
              ...s.messages,
              {
                role: "assistant" as const,
                content: s.streamingText,
                ...(durationS !== undefined ? { durationS } : {}),
              },
            ]
          : s.messages,
        streamingText: "",
        streamStartedAt: null,
        activeTool: null,
        isStreaming: false,
      };
    }),
  clear: () =>
    set({
      messages: [],
      streamingText: "",
      streamStartedAt: null,
      activeTool: null,
      toolHistory: [],
      citations: [],
      isStreaming: false,
    }),
}));
