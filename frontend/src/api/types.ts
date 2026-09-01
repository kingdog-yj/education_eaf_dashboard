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
  steel_group: string;
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

// --- 메타/스펙 레지스트리 (백엔드 domain/specs.py · domain/materials.py) ---

/** 지표 스펙. lo/hi가 null이면 밴드 없음(판정 대상 아님). */
export interface MetricSpec {
  id: string;
  label_ko: string;
  unit: string;
  decimals: number;
  lo: number | null;
  hi: number | null;
}

export interface KpiSummaryCard {
  id: string;
  label_ko: string;
  unit: string;
  decimals: number;
  value: number | null;
  prev_value: number | null;
  spec_id: string | null;
}

export interface KpiSummaryResponse {
  period: "day" | "week" | "month";
  bucket_start: string | null;
  bucket_end: string | null;
  prev_bucket_start: string | null;
  cards: KpiSummaryCard[];
}

/** 조업 페이즈 구간(산출 가능한 것만 포함). */
export interface PhaseInterval {
  phase: string;
  label_ko: string;
  start: string;
  end: string;
}

export interface MaterialsMeta {
  scrap_grades: Record<string, string>;
  addition_materials: Record<string, string>;
  steel_groups: Record<string, string>;
}

/** 부원료 투입 이벤트. */
export interface AdditionEvent {
  ts: string;
  material: string;
  label_ko: string;
  amount_kg: number;
}

/** KPI 트렌드 1행 = heat 1건. 지표 키는 SPEC_REGISTRY의 id와 동일. */
export type KpiTrendRow = {
  heat_id: string;
  date: string;
  steel_group: string;
} & Record<string, number | string | null>;

// --- Discussion (백엔드 StreamEvent와 일치) ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/** UI 전용 메시지 타입 — API 계약(ChatMessage)과 분리된다.
 *  durationS 등 부가 필드는 프론트 표시용이며 백엔드로 전송하지 않는다
 *  (useChatStream에서 role/content만 추출해 전송). */
export type UiChatMessage = ChatMessage & { durationS?: number };

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

/** 대화 모드. quick=빠른 대화, deep=심화 분석. */
export type ChatMode = "quick" | "deep";

export interface ChatModeInfo {
  id: ChatMode;
  label_ko: string;
  description_ko: string;
}

/** 대화 모드 선택지 메타. GET /api/meta/chat_modes */
export interface ChatModesMeta {
  modes: ChatModeInfo[];
  default_mode: ChatMode;
}

export interface DashboardContextPayload {
  view: string;
  heat_id: string | null;
  period_start: string | null;
  period_end: string | null;
  visible_tags: string[];
  note: string;
}
