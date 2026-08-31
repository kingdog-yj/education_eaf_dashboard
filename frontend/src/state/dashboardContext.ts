// 대시보드 화면 상태 → Discussion 컨텍스트 자동 주입의 원천.
// 각 뷰는 조작(heat 선택, 기간 변경 등) 시 이 store를 갱신할 의무가 있다.
import { create } from "zustand";
import type { DashboardContextPayload } from "../api/types";

export type ViewId = "heat_detail" | "trend" | "live" | "kpi_summary";

interface DashboardContextState {
  view: ViewId;
  heatId: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  visibleTags: string[];
  setView: (view: ViewId) => void;
  setHeatId: (heatId: string | null) => void;
  setPeriod: (start: string | null, end: string | null) => void;
  setVisibleTags: (tags: string[]) => void;
  toPayload: () => DashboardContextPayload;
}

export const useDashboardContext = create<DashboardContextState>((set, get) => ({
  view: "heat_detail",
  heatId: null,
  periodStart: null,
  periodEnd: null,
  visibleTags: [],
  setView: (view) => set({ view }),
  setHeatId: (heatId) => set({ heatId }),
  setPeriod: (periodStart, periodEnd) => set({ periodStart, periodEnd }),
  setVisibleTags: (visibleTags) => set({ visibleTags }),
  toPayload: () => {
    const s = get();
    return {
      view: s.view,
      heat_id: s.heatId,
      period_start: s.periodStart,
      period_end: s.periodEnd,
      visible_tags: s.visibleTags,
      note: "",
    };
  },
}));
