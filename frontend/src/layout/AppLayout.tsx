// 핵심 레이아웃: [좌측 네비] [중앙 대시보드 뷰] [우측 Discussion 패널 상주].
// DiscussionPanel은 뷰 전환과 무관하게 마운트 유지 → 대화 상태 보존 + 컨텍스트 자동 추적.
import { useState } from "react";
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

export function AppLayout() {
  const { view, setView } = useDashboardContext();
  const [chatOpen, setChatOpen] = useState(true);
  const ActiveView =
    VIEWS.find((v) => v.id === view)?.component ?? HeatDetailView;

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <h1>EAF 대시보드</h1>
        {VIEWS.map((v) => (
          <button
            key={v.id}
            className={v.id === view ? "active" : ""}
            onClick={() => setView(v.id)}
          >
            {v.label}
          </button>
        ))}
        <button
          className="chat-toggle"
          onClick={() => setChatOpen((o) => !o)}
          title="Discussion 패널 접기/펼치기"
        >
          💬 {chatOpen ? "패널 닫기" : "Discussion"}
        </button>
      </nav>

      <main className="main-content">
        <ActiveView />
      </main>

      {chatOpen && <DiscussionPanel />}
    </div>
  );
}
