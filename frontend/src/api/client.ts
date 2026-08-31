// REST API 클라이언트. 모든 fetch는 여기로 모은다 (엔드포인트 하드코딩 분산 금지).
import type {
  Heat,
  HeatSummary,
  HeatTimeseries,
  PhaseMeta,
  TagMeta,
} from "./types";

async function get<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} → ${resp.status}`);
  return resp.json();
}

export const api = {
  listHeats: (params?: { start?: string; end?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.start) q.set("start", params.start);
    if (params?.end) q.set("end", params.end);
    if (params?.limit) q.set("limit", String(params.limit));
    return get<HeatSummary[]>(`/api/heats?${q}`);
  },
  getHeat: (heatId: string) => get<Heat>(`/api/heats/${heatId}`),
  getTimeseries: (heatId: string, tags?: string[], downsample?: number) => {
    const q = new URLSearchParams();
    if (tags?.length) q.set("tags", tags.join(","));
    if (downsample) q.set("downsample", String(downsample));
    return get<HeatTimeseries>(`/api/heats/${heatId}/timeseries?${q}`);
  },
  getKpiTrend: (start?: string, end?: string) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return get<Record<string, unknown>[]>(`/api/kpi/trend?${q}`);
  },
  getKpiSummary: (period: "day" | "week" | "month") =>
    get<{ period: string; cards: unknown[] }>(`/api/kpi/summary?period=${period}`),
  getTags: () => get<TagMeta[]>("/api/meta/tags"),
  getPhases: () => get<PhaseMeta[]>("/api/meta/phases"),
};
