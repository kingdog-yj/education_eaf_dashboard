// 실시간 모니터링: /api/live WebSocket 수신 → 차트 append.
// 현재는 연결 상태 확인용 스켈레톤 (백엔드 시뮬레이션 구현 후 차트 연동).
import { useEffect, useRef, useState } from "react";

export function LiveView() {
  const [status, setStatus] = useState<"connecting" | "open" | "closed">(
    "connecting",
  );
  const [lastMessage, setLastMessage] = useState<string>("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/api/live`);
    wsRef.current = ws;
    ws.onopen = () => setStatus("open");
    ws.onclose = () => setStatus("closed");
    ws.onmessage = (e) => setLastMessage(e.data);
    return () => ws.close();
  }, []);

  return (
    <div className="view">
      <p>
        실시간 스트림: <strong>{status}</strong>
      </p>
      <pre className="placeholder">{lastMessage || "수신 대기 중…"}</pre>
      <p className="placeholder">
        더미데이터 생성 후 과거 heat 실시간 재생(시뮬레이션) 차트가 구현됩니다.
      </p>
    </div>
  );
}
