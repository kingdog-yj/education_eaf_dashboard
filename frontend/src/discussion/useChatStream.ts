// POST /api/discussion 의 SSE 스트림을 파싱해 chatStore에 반영하는 훅.
import { useCallback, useRef } from "react";
import type { ChatMessage, StreamEvent } from "../api/types";
import { useChatStore } from "../state/chatStore";
import { useDashboardContext } from "../state/dashboardContext";

export function useChatStream() {
  const chat = useChatStore();
  const toPayload = useDashboardContext((s) => s.toPayload);
  const abortRef = useRef<AbortController | null>(null);

  /** 진행 중인 응답을 중단한다. 지금까지 받은 텍스트는 그대로 확정된다. */
  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (content: string) => {
      chat.addUserMessage(content);
      const state = useChatStore.getState(); // addUserMessage 반영 후 최신 상태
      // API 계약(ChatMessage)에 맞춰 role/content만 전송한다.
      // UI 전용 필드(durationS 등)는 백엔드로 나가지 않게 여기서 제거한다.
      const messages: ChatMessage[] = state.messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      // 대화 모드는 전송 시점의 스토어 값을 그대로 보낸다(null=서버 기본값 quick).
      const mode = state.mode;

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const resp = await fetch("/api/discussion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages,
            context: toPayload(),
            mode,
          }),
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) throw new Error(`discussion → ${resp.status}`);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE 프레임: "data: {...}\n\n"
          // (백엔드 keep-alive 주석 프레임 ": ping"은 data가 아니므로 자연히 무시된다)
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) continue;
            handleEvent(JSON.parse(line.slice(5)) as StreamEvent);
          }
        }
      } catch (err) {
        // 사용자가 중단한 경우는 오류가 아니다 — 받은 내용만 확정한다.
        if (!controller.signal.aborted) {
          useChatStore
            .getState()
            .appendDelta(
              `\n\n오류: ${err instanceof Error ? err.message : String(err)}`,
            );
        }
      } finally {
        abortRef.current = null;
        useChatStore.getState().finishStreaming();
      }
    },
    [toPayload], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return { send, abort };
}

function handleEvent(ev: StreamEvent) {
  const chat = useChatStore.getState();
  switch (ev.type) {
    case "text_delta":
      chat.appendDelta(ev.text);
      break;
    case "tool_call":
      chat.setActiveTool(ev.tool_name);
      break;
    case "tool_result":
      chat.completeTool(ev.tool_name || chat.activeTool || "");
      break;
    case "citation":
      chat.addCitation({ url: ev.url, title: ev.title });
      break;
    case "error":
      chat.appendDelta(`\n\n오류: ${ev.text}`);
      break;
    case "done":
      break;
  }
}
