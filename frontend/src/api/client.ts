// REST API 클라이언트. 모든 fetch는 여기로 모은다 (엔드포인트 하드코딩 분산 금지).
import type {
  AdditionEvent,
  Heat,
  HeatSummary,
  HeatTimeseries,
  KpiSummaryResponse,
  KpiTrendRow,
  LlmMeta,
  MaterialsMeta,
  MetricSpec,
  PhaseInterval,
  PhaseMeta,
  TagMeta,
} from "./types";

async function get<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${url} → ${resp.status}`);
  return resp.json();
}

/** 정적 메타(태그·페이즈·스펙·부재료)는 세션 동안 변하지 않으므로 1회만 조회한다. */
const metaCache = new Map<string, Promise<unknown>>();

function getMeta<T>(url: string): Promise<T> {
  let cached = metaCache.get(url) as Promise<T> | undefined;
  if (!cached) {
    cached = get<T>(url).catch((err) => {
      metaCache.delete(url); // 실패는 캐시하지 않는다(백엔드 기동 전 호출 대비)
      throw err;
    });
    metaCache.set(url, cached);
  }
  return cached;
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
  /** heat별 조업 페이즈 구간 (산출 가능한 것만). */
  getHeatPhases: (heatId: string) =>
    get<PhaseInterval[]>(`/api/heats/${heatId}/phases`),
  /** heat별 부원료 투입 이벤트. */
  getAdditions: (heatId: string) =>
    get<AdditionEvent[]>(`/api/heats/${heatId}/additions`),
  getKpiTrend: (start?: string, end?: string) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    return get<KpiTrendRow[]>(`/api/kpi/trend?${q}`);
  },
  getKpiSummary: (period: "day" | "week" | "month") =>
    get<KpiSummaryResponse>(`/api/kpi/summary?period=${period}`),

  // --- 정적 메타 ---
  getTags: () => getMeta<TagMeta[]>("/api/meta/tags"),
  getPhases: () => getMeta<PhaseMeta[]>("/api/meta/phases"),
  getSpecs: () => getMeta<MetricSpec[]>("/api/meta/specs"),
  getMaterials: () => getMeta<MaterialsMeta>("/api/meta/materials"),
  /** Discussion용 LLM 모델·추론 강도 선택지. 미지원 백엔드에서는 reject된다. */
  getLlmMeta: () => getMeta<LlmMeta>("/api/meta/llm"),
};
