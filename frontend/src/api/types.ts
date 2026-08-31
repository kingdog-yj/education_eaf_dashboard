// 백엔드 domain/models.py · llm/base.py와 스키마를 일치시킬 것

export interface HeatEvents {
  power_on: string;
  meltdown: string | null;
  tap_start: string | null;
  tap_end: string | null;
}

export interface HeatSummary {
  heat_id: string;
  date: string;
  shift: string;
  events: HeatEvents;
  tap_weight_t: number | null;
  energy_kwh_per_t: number | null;
}

export interface Heat {
  summary: HeatSummary;
  charge: {
    baskets: Record<string, number>[];
    total_charge_t: number;
    hot_heel_t: number;
  };
  kpi: Record<string, number | null>;
  eop: { tap_temp_c: number | null; composition_pct: Record<string, number> };
  slag: {
    composition_pct: Record<string, number>;
    basicity: number | null;
    additions_kg: Record<string, number>;
  };
}

export interface TimeseriesSeries {
  tag_id: string;
  unit: string;
  points: { ts: string; value: number }[];
}

export interface HeatTimeseries {
  heat_id: string;
  series: TimeseriesSeries[];
  downsample_s: number | null;
}

export interface TagMeta {
  id: string;
  group: "electrical" | "chemical" | "thermal";
  unit: string;
  label_ko: string;
  sample_period_s: number;
  cumulative: boolean;
}

export interface PhaseMeta {
  id: string;
  label_ko: string;
}

// --- Discussion (백엔드 StreamEvent와 일치) ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type StreamEventType =
  | "text_delta"
  | "tool_call"
  | "tool_result"
  | "citation"
  | "done"
  | "error";

export interface StreamEvent {
  type: StreamEventType;
  text: string;
  tool_name: string;
  url: string;
  title: string;
}

export interface DashboardContextPayload {
  view: string;
  heat_id: string | null;
  period_start: string | null;
  period_end: string | null;
  visible_tags: string[];
  note: string;
}
