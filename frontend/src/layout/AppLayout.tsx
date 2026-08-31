// 핵심 레이아웃: [좌측 네비] [중앙 대시보드 뷰] [우측 Discussion 패널 상주].
// DiscussionPanel은 뷰 전환과 무관하게 마운트 유지 → 대화 상태 보존 + 컨텍스트 자동 추적.
import { useCallback, useEffect, useRef, useState } from "react";
import { DiscussionPanel } from "../discussion/DiscussionPanel";
import { useDashboardContext, type ViewId } from "../state/dashboardContext";
import { HeatDetailView } from "../views/HeatDetailView";
import { KpiSummaryView } from "../views/KpiSummaryView";
import { LiveView } from "../views/LiveView";
import { TrendView } from "../views/TrendView";

const VIEWS: { id: ViewId; label: string; component: React.ComponentType }[] = [
  { id: "heat_detail", label: "Heat 상세", component: HeatDetailView },
  { id: "trend", label: "트렌드/비교", component: TrendView },
  { id: "live", label: "실시간", component: LiveView },
  { id: "kpi_summary", label: "KPI 요약", component: KpiSummaryView },
];

// 패널 폭 규칙: 기본 25vw, 20~50vw 범위. 좁은 화면에서 채팅이 붕괴되지 않도록 px 하한도 둔다.
const DEFAULT_RATIO = 0.25;
const MIN_RATIO = 0.2;
const MAX_RATIO = 0.5;
const MIN_PX = 280;

function clampWidth(px: number): number {
  const vw = window.innerWidth;
  const min = Math.min(Math.max(vw * MIN_RATIO, MIN_PX), vw * MAX_RATIO);
  return Math.round(Math.min(Math.max(px, min), vw * MAX_RATIO));
}

export function AppLayout() {
  const { view, setView } = useDashboardContext();
  const [chatOpen, setChatOpen] = useState(true);
  // 폭은 AppLayout 로컬 상태 — 뷰 전환에는 유지되고, 새로고침 시 기본값으로 돌아간다(영속화 없음).
  const [panelWidth, setPanelWidth] = useState(() =>
    clampWidth(window.innerWidth * DEFAULT_RATIO),
  );
  const [dragging, setDragging] = useState(false);
  const draggingRef = useRef(false);

  const ActiveView =
    VIEWS.find((v) => v.id === view)?.component ?? HeatDetailView;

  useEffect(() => {
    const onResize = () => setPanelWidth((w) => clampWidth(w));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    setDragging(true);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    setPanelWidth(clampWidth(window.innerWidth - e.clientX));
  }, []);

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setDragging(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  }, []);

  return (
    <div className={`app-layout${dragging ? " resizing" : ""}`}>
      <nav className="sidebar">
        <div className="sidebar-brand">
          <strong>EAF 대시보드</strong>
          <span>Electric Arc Furnace</span>
        </div>
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            className={`nav-item${v.id === view ? " active" : ""}`}
            aria-current={v.id === view ? "page" : undefined}
            onClick={() => setView(v.id)}
          >
            {v.label}
          </button>
        ))}
        <div className="sidebar-spacer" />
        <div className="sidebar-foot">
          <button
            type="button"
            className="nav-item"
            onClick={() => setChatOpen((o) => !o)}
            aria-pressed={chatOpen}
            title="Discussion 패널 접기/펼치기"
          >
            {chatOpen ? "패널 닫기" : "Discussion 열기"}
          </button>
        </div>
      </nav>

      <main className="main-content">
        <ActiveView />
      </main>

      {chatOpen && (
        <>
          <div
            className={`resize-handle${dragging ? " dragging" : ""}`}
            role="separator"
            aria-orientation="vertical"
            aria-label="Discussion 패널 폭 조절"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          />
          <aside className="discussion-panel" style={{ width: panelWidth }}>
            <DiscussionPanel />
          </aside>
        </>
      )}
    </div>
  );
}
