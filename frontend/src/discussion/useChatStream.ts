// POST /api/discussion 의 SSE 스트림을 파싱해 chatStore에 반영하는 훅.
import { useCallback } from "react";
import type { StreamEvent } from "../api/types";
import { useChatStore } from "../state/chatStore";
import { useDashboardContext } from "../state/dashboardContext";

export function useChatStream() {
  const chat = useChatStore();
  const toPayload = useDashboardContext((s) => s.toPayload);

  const send = useCallback(
    async (content: string) => {
      chat.addUserMessage(content);
      const messages = [
        ...useChatStore.getState().messages, // addUserMessage 반영 후 최신 이력
      ];

      try {
        const resp = await fetch("/api/discussion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages, context: toPayload() }),
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
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) continue;
            handleEvent(JSON.parse(line.slice(5)) as StreamEvent);
          }
        }
      } catch (err) {
        useChatStore
          .getState()
          .appendDelta(`\n\n⚠️ 오류: ${err instanceof Error ? err.message : err}`);
      } finally {
        useChatStore.getState().finishStreaming();
      }
    },
    [toPayload], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return { send };
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
      chat.setActiveTool(null);
      break;
    case "citation":
      chat.addCitation({ url: ev.url, title: ev.title });
      break;
    case "error":
      chat.appendDelta(`\n\n⚠️ ${ev.text}`);
      break;
    case "done":
      break;
  }
}
