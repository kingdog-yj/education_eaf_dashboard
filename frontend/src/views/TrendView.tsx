// 다수 heat 트렌드/비교: 지표 선택 + 기간 필터 + 강종 그룹별 비교 + 스펙 밴드/이탈 강조.
// 포인트 클릭 시 해당 heat 상세로 이동한다.
import { useEffect, useMemo, useState } from "react";
import type * as Plotly from "plotly.js";
import { api } from "../api/client";
import type { KpiTrendRow, MaterialsMeta, MetricSpec } from "../api/types";
import { PlotlyChart } from "../components/charts/PlotlyChart";
import { CHART } from "../components/charts/theme";
import { formatValue, isOutOfSpec, toSpecMap } from "../lib/metrics";
import { useDashboardContext } from "../state/dashboardContext";

const DEFAULT_METRIC = "kpi_energy_kwh_per_t";

export function TrendView() {
  const { periodStart, periodEnd, setPeriod, setHeatId, setView } =
    useDashboardContext();
  const [rows, setRows] = useState<KpiTrendRow[]>([]);
  const [specs, setSpecs] = useState<MetricSpec[]>([]);
  const [materials, setMaterials] = useState<MaterialsMeta | null>(null);
  const [metricId, setMetricId] = useState(DEFAULT_METRIC);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSpecs().then(setSpecs).catch(console.error);
    api.getMaterials().then(setMaterials).catch(console.error);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getKpiTrend(periodStart ?? undefined, periodEnd ?? undefined)
      .then((r) => !cancelled && setRows(r))
      .catch(() => !cancelled && setRows([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [periodStart, periodEnd]);

  const specMap = useMemo(() => toSpecMap(specs), [specs]);
  const spec = specMap.get(metricId) ?? specs[0] ?? null;
  const activeId = spec?.id ?? metricId;

  const groups = useMemo(() => {
    const map = new Map<string, KpiTrendRow[]>();
    for (const r of rows) {
      const g = (r.steel_group as string) || "unknown";
      const list = map.get(g);
      if (list) list.push(r);
      else map.set(g, [r]);
    }
    return map;
  }, [rows]);

  const outOfSpecCount = useMemo(
    () =>
      rows.filter((r) => isOutOfSpec(numeric(r[activeId]), spec)).length,
    [rows, activeId, spec],
  );

  const chart = useMemo(() => {
    if (rows.length === 0 || !spec) return null;

    const data: Plotly.Data[] = [];
    let gi = 0;
    for (const [code, list] of groups) {
      const color = CHART.colorway[gi % CHART.colorway.length];
      gi += 1;
      const values = list.map((r) => numeric(r[activeId]));
      data.push({
        x: list.map((r) => r.date),
        y: values,
        type: "scatter",
        mode: "markers",
        name: materials?.steel_groups[code] ?? code,
        marker: {
          size: 7,
          color: values.map((v) =>
            isOutOfSpec(v, spec) ? CHART.danger : color,
          ),
          line: { width: 0 },
        },
        customdata: list.map((r) => r.heat_id),
        hovertemplate:
          `%{customdata}<br>%{x}<br>%{y:.${spec.decimals}f} ${spec.unit}<extra>` +
          `${materials?.steel_groups[code] ?? code}</extra>`,
      } as Plotly.Data);
    }

    const shapes: Partial<Plotly.Shape>[] = [];
    if (spec.lo != null && spec.hi != null) {
      shapes.push({
        type: "rect",
        xref: "paper",
        yref: "y",
        x0: 0,
        x1: 1,
        y0: spec.lo,
        y1: spec.hi,
        fillcolor: CHART.accentTint,
        line: { width: 0 },
        layer: "below",
      });
    }
    for (const bound of [spec.lo, spec.hi]) {
      if (bound == null) continue;
      shapes.push({
        type: "line",
        xref: "paper",
        yref: "y",
        x0: 0,
        x1: 1,
        y0: bound,
        y1: bound,
        line: { color: CHART.accent, width: 1, dash: "dash" },
        layer: "below",
      });
    }

    const layout: Partial<Plotly.Layout> = {
      shapes,
      yaxis: { title: { text: `${spec.label_ko} (${spec.unit})` } },
      xaxis: { title: { text: "조업일 (date)" } },
      margin: { l: 72, r: 24, t: 48, b: 48 },
    };
    return { data, layout };
  }, [rows, groups, spec, activeId, materials]);

  return (
    <div className="view">
      <header className="view-header">
        <div>
          <div className="view-title">트렌드 / 비교</div>
          <div className="view-subtitle">
            heat {rows.length.toLocaleString("ko-KR")}건
            {spec ? ` · ${spec.label_ko} 기준 이탈 ${outOfSpecCount}건` : ""}
          </div>
        </div>
        <div className="view-toolbar">
          <label className="field">
            <span>지표 (metric)</span>
            <select
              value={activeId}
              onChange={(e) => setMetricId(e.target.value)}
            >
              {specs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label_ko} ({s.unit})
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>시작일</span>
            <input
              type="date"
              value={periodStart ?? ""}
              onChange={(e) => setPeriod(e.target.value || null, periodEnd)}
            />
          </label>
          <label className="field">
            <span>종료일</span>
            <input
              type="date"
              value={periodEnd ?? ""}
              onChange={(e) => setPeriod(periodStart, e.target.value || null)}
            />
          </label>
          {(periodStart || periodEnd) && (
            <button
              type="button"
              className="btn"
              onClick={() => setPeriod(null, null)}
            >
              기간 초기화
            </button>
          )}
        </div>
      </header>

      {rows.length === 0 ? (
        <p className="empty-state">
          {loading
            ? "트렌드를 불러오는 중…"
            : "선택한 기간에 heat 데이터가 없습니다."}
        </p>
      ) : (
        <>
          <div className="chart-card">
            <PlotlyChart
              data={chart?.data ?? []}
              layout={chart?.layout}
              style={{ height: 460 }}
              onClick={(ev) => {
                const hid = ev.points?.[0]?.customdata;
                if (typeof hid !== "string") return;
                setHeatId(hid);
                setView("heat_detail");
              }}
            />
          </div>
          <p className="card-note">
            점을 클릭하면 해당 heat 상세로 이동합니다. 밴드(음영) 밖 값은 스펙
            이탈로 표시됩니다.
          </p>
          {spec && <TrendStats rows={rows} metricId={activeId} spec={spec} />}
        </>
      )}
    </div>
  );
}

function TrendStats({
  rows,
  metricId,
  spec,
}: {
  rows: KpiTrendRow[];
  metricId: string;
  spec: MetricSpec;
}) {
  const values = rows
    .map((r) => numeric(r[metricId]))
    .filter((v): v is number => v != null);
  if (values.length === 0) return null;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const sd = Math.sqrt(
    values.reduce((a, v) => a + (v - mean) ** 2, 0) / values.length,
  );

  return (
    <section className="card">
      <div className="card-title">
        {spec.label_ko} 분포 ({values.length.toLocaleString("ko-KR")} heat)
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th className="num">평균</th>
            <th className="num">표준편차 (σ)</th>
            <th className="num">최소</th>
            <th className="num">최대</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="num">{formatValue(mean, spec.decimals)}</td>
            <td className="num">{formatValue(sd, spec.decimals)}</td>
            <td className="num">{formatValue(min, spec.decimals)}</td>
            <td className="num">{formatValue(max, spec.decimals)}</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

function numeric(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
