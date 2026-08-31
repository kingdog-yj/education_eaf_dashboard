// 단일 heat 상세: heat 선택 → 태그별 서브플롯 시계열(페이즈 음영·용락·부원료) + 정적 정보.
import { useEffect, useMemo, useState } from "react";
import type * as Plotly from "plotly.js";
import { api } from "../api/client";
import type {
  AdditionEvent,
  Heat,
  HeatSummary,
  HeatTimeseries,
  MaterialsMeta,
  MetricSpec,
  PhaseInterval,
  TagMeta,
} from "../api/types";
import { KpiCard } from "../components/KpiCard";
import { PlotlyChart } from "../components/charts/PlotlyChart";
import { CHART } from "../components/charts/theme";
import { formatDate, formatValue, isOutOfSpec, toSpecMap } from "../lib/metrics";
import { useDashboardContext } from "../state/dashboardContext";

const SUBPLOT_GAP = 0.06;

export function HeatDetailView() {
  const { heatId, setHeatId, setVisibleTags } = useDashboardContext();
  const [heats, setHeats] = useState<HeatSummary[]>([]);
  const [heat, setHeat] = useState<Heat | null>(null);
  const [ts, setTs] = useState<HeatTimeseries | null>(null);
  const [phases, setPhases] = useState<PhaseInterval[]>([]);
  const [additions, setAdditions] = useState<AdditionEvent[]>([]);
  const [tags, setTags] = useState<TagMeta[]>([]);
  const [specs, setSpecs] = useState<MetricSpec[]>([]);
  const [materials, setMaterials] = useState<MaterialsMeta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listHeats({ limit: 500 })
      .then(setHeats)
      .catch(() => setError("heat 목록을 불러오지 못했습니다."));
    api.getTags().then(setTags).catch(console.error);
    api.getSpecs().then(setSpecs).catch(console.error);
    api.getMaterials().then(setMaterials).catch(console.error);
  }, []);

  useEffect(() => {
    if (!heatId) {
      setHeat(null);
      setTs(null);
      setPhases([]);
      setAdditions([]);
      return;
    }
    let cancelled = false;
    api.getHeat(heatId).then((h) => !cancelled && setHeat(h)).catch(console.error);
    api
      .getTimeseries(heatId, undefined, 10)
      .then((t) => {
        if (cancelled) return;
        setTs(t);
        setVisibleTags(t.series.map((s) => s.tag_id));
      })
      .catch(console.error);
    api
      .getHeatPhases(heatId)
      .then((p) => !cancelled && setPhases(p))
      .catch(() => !cancelled && setPhases([]));
    api
      .getAdditions(heatId)
      .then((a) => !cancelled && setAdditions(a))
      .catch(() => !cancelled && setAdditions([]));
    return () => {
      cancelled = true;
    };
  }, [heatId, setVisibleTags]);

  const specMap = useMemo(() => toSpecMap(specs), [specs]);
  const tagMap = useMemo(() => new Map(tags.map((t) => [t.id, t])), [tags]);
  const heatMap = useMemo(
    () => new Map(heats.map((h) => [h.heat_id, h])),
    [heats],
  );
  const steelGroupLabel = (code: string) =>
    materials?.steel_groups[code] ?? code;

  // --- 차트 구성 (태그 수·id는 응답에서 동적 결정) ---
  const chart = useMemo(() => {
    const series = ts?.series ?? [];
    if (series.length === 0) return null;

    const n = series.length;
    const height = (1 - SUBPLOT_GAP * (n - 1)) / n;
    const axisOf = (i: number) => (i === 0 ? "y" : `y${i + 1}`);

    const data: Plotly.Data[] = series.map((s, i) => {
      const meta = tagMap.get(s.tag_id);
      return {
        x: s.points.map((p) => p.ts),
        y: s.points.map((p) => p.value),
        name: `${meta?.label_ko ?? s.tag_id} (${s.unit})`,
        type: "scatter",
        mode: "lines",
        line: { width: 1.4 },
        xaxis: "x",
        yaxis: axisOf(i),
        hovertemplate: `%{y} ${s.unit}<extra>${meta?.label_ko ?? s.tag_id}</extra>`,
      } as Plotly.Data;
    });

    const layout: Record<string, unknown> = {
      showlegend: false,
      height: Math.max(320, n * 140),
      margin: { l: 72, r: 24, t: 72, b: 44 },
      // x축은 최하단 서브플롯에 앵커 → 눈금이 차트 맨 아래 한 번만 그려진다.
      xaxis: {
        anchor: axisOf(n - 1),
        showspikes: true,
        spikemode: "across",
        spikethickness: 1,
        spikecolor: CHART.gridStrong,
      },
      hovermode: "x unified",
    };

    series.forEach((s, i) => {
      const meta = tagMap.get(s.tag_id);
      const top = 1 - i * (height + SUBPLOT_GAP);
      layout[i === 0 ? "yaxis" : `yaxis${i + 1}`] = {
        domain: [Math.max(0, top - height), top],
        title: {
          text: `${meta?.label_ko ?? s.tag_id}<br>(${s.unit})`,
          font: { size: 11, color: CHART.textMuted },
        },
      };
    });

    // 페이즈 음영 + 용락 + 부원료 (모두 paper 기준 세로 요소)
    const shapes: Partial<Plotly.Shape>[] = [];
    const annotations: Partial<Plotly.Annotations>[] = [];

    // 페이즈 라벨은 구간 중앙에 배치하고 두 줄로 번갈아 놓아 겹침을 피한다.
    const span = phaseSpanMs(phases);
    phases.forEach((p, i) => {
      shapes.push({
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: p.start,
        x1: p.end,
        y0: 0,
        y1: 1,
        fillcolor: CHART.phaseShade[i % CHART.phaseShade.length],
        line: { width: 0 },
        layer: "below",
      });
      const width = Date.parse(p.end) - Date.parse(p.start);
      if (!span || width / span < 0.05) return; // 너무 좁은 구간은 라벨 생략
      annotations.push({
        x: midpoint(p.start, p.end),
        xref: "x",
        yref: "paper",
        y: i % 2 === 0 ? 1.005 : 1.055,
        xanchor: "center",
        yanchor: "bottom",
        text: p.label_ko,
        showarrow: false,
        font: { size: 11, color: CHART.textMuted },
      });
    });

    const meltdown = heat?.summary.events.meltdown;
    if (meltdown) {
      shapes.push({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: meltdown,
        x1: meltdown,
        y0: 0,
        y1: 1,
        line: { color: CHART.accent, width: 1.6, dash: "dash" },
      });
      annotations.push({
        x: meltdown,
        xref: "x",
        yref: "paper",
        y: 1.11,
        xanchor: "center",
        yanchor: "bottom",
        text: "용락 (meltdown)",
        showarrow: false,
        font: { size: 11, color: CHART.accent },
      });
    }

    additions.forEach((a) => {
      shapes.push({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: a.ts,
        x1: a.ts,
        y0: 0,
        y1: 1,
        line: { color: CHART.textMuted, width: 1, dash: "dot" },
        layer: "below",
      });
    });

    // 부원료 hover용 마커는 최상단 서브플롯에 얹는다.
    const topValues = series[0].points.map((p) => p.value);
    if (additions.length > 0 && topValues.length > 0) {
      const yTop = Math.max(...topValues);
      data.push({
        x: additions.map((a) => a.ts),
        y: additions.map(() => yTop),
        type: "scatter",
        mode: "markers",
        name: "부원료 투입",
        xaxis: "x",
        yaxis: "y",
        marker: { symbol: "triangle-down", size: 9, color: CHART.textMuted },
        customdata: additions.map((a) => [a.label_ko, a.amount_kg]),
        hovertemplate: "%{customdata[0]} %{customdata[1]} kg<extra>부원료 투입</extra>",
      } as Plotly.Data);
    }

    layout.shapes = shapes;
    layout.annotations = annotations;
    return { data, layout: layout as Partial<Plotly.Layout> };
  }, [ts, tagMap, phases, additions, heat]);

  const selected = heatId ? heatMap.get(heatId) : undefined;

  return (
    <div className="view">
      <header className="view-header">
        <div>
          <div className="view-title">Heat 상세</div>
          <div className="view-subtitle">
            {selected
              ? `${formatDate(selected.date)} · ${selected.shift} 근무 · ${steelGroupLabel(selected.steel_group)}`
              : "heat 1회 조업 사이클의 시계열과 조업 결과"}
          </div>
        </div>
        <div className="view-toolbar">
          <label className="field">
            <span>Heat 선택</span>
            <select
              value={heatId ?? ""}
              onChange={(e) => setHeatId(e.target.value || null)}
            >
              <option value="">선택…</option>
              {heats.map((h) => (
                <option key={h.heat_id} value={h.heat_id}>
                  {h.heat_id} · {h.date.slice(0, 10)} ·{" "}
                  {steelGroupLabel(h.steel_group)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {error && <p className="empty-state">{error}</p>}

      {!error && heats.length === 0 && (
        <p className="empty-state">
          heat 데이터가 없습니다. 더미데이터를 생성하면 목록이 표시됩니다.
        </p>
      )}

      {heats.length > 0 && !heatId && (
        <p className="empty-state">
          위에서 heat을 선택하면 시계열과 조업 결과가 표시됩니다.
        </p>
      )}

      {chart && (
        <div className="chart-card">
          <PlotlyChart
            data={chart.data}
            layout={chart.layout}
            style={{ height: (chart.layout.height as number) ?? 480 }}
          />
        </div>
      )}

      {heatId && ts && ts.series.length === 0 && (
        <p className="empty-state">이 heat의 시계열 데이터가 없습니다.</p>
      )}

      {heat && (
        <>
          <section className="card">
            <div className="card-title">조업 결과 (KPI)</div>
            <div className="kpi-grid">
              {Object.entries(heat.kpi).map(([key, value]) => {
                const spec = specMap.get(`kpi_${key}`);
                return (
                  <KpiCard
                    key={key}
                    label={spec?.label_ko ?? key}
                    value={value}
                    unit={spec?.unit ?? ""}
                    decimals={spec?.decimals ?? 1}
                    spec={spec}
                  />
                );
              })}
            </div>
          </section>

          <div className="panel-grid">
            <EopPanel heat={heat} specMap={specMap} />
            <SlagPanel heat={heat} materials={materials} />
            <ChargePanel heat={heat} materials={materials} specMap={specMap} />
            <AdditionsPanel additions={additions} />
          </div>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------- 시간 유틸
// 백엔드 타임스탬프는 타임존이 없는 로컬 표기(naive)다.
// Date → 문자열 변환 시 UTC로 밀리지 않도록 로컬 필드로 직접 조립한다.

function toNaiveIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
    `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  );
}

function midpoint(start: string, end: string): string {
  return toNaiveIso(new Date((Date.parse(start) + Date.parse(end)) / 2));
}

/** 전체 페이즈 구간 길이(ms). 좁은 구간 라벨 생략 판단용. */
function phaseSpanMs(phases: PhaseInterval[]): number {
  if (phases.length === 0) return 0;
  const starts = phases.map((p) => Date.parse(p.start));
  const ends = phases.map((p) => Date.parse(p.end));
  return Math.max(...ends) - Math.min(...starts);
}

// --------------------------------------------------------------- 하위 패널

function EopPanel({
  heat,
  specMap,
}: {
  heat: Heat;
  specMap: Map<string, MetricSpec>;
}) {
  const tempSpec = specMap.get("eop_tap_temp_c");
  const comps = Object.entries(heat.eop.composition_pct ?? {});
  return (
    <section className="card">
      <div className="card-title">종점 (EOP)</div>
      <KpiCard
        label={tempSpec?.label_ko ?? "출강 온도"}
        value={heat.eop.tap_temp_c}
        unit={tempSpec?.unit ?? "°C"}
        decimals={tempSpec?.decimals ?? 0}
        spec={tempSpec}
      />
      {comps.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>종점 성분 (composition)</th>
              <th className="num">값 (%)</th>
              <th className="num">판정</th>
            </tr>
          </thead>
          <tbody>
            {comps.map(([el, v]) => {
              const spec = specMap.get(`eop_comp_${el.toLowerCase()}`);
              const out = isOutOfSpec(v, spec);
              return (
                <tr key={el}>
                  <td>{spec?.label_ko ?? el.toUpperCase()}</td>
                  <td className={`num${out ? " val-danger" : ""}`}>
                    {formatValue(v, spec?.decimals ?? 3)}
                  </td>
                  <td className="num">
                    {spec && (spec.lo != null || spec.hi != null) ? (
                      <span className={`badge${out ? " danger" : ""}`}>
                        {out ? "이탈" : "정상"}
                      </span>
                    ) : (
                      <span className="card-note">기준 없음</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function SlagPanel({
  heat,
  materials,
}: {
  heat: Heat;
  materials: MaterialsMeta | null;
}) {
  const comps = Object.entries(heat.slag.composition_pct ?? {});
  const adds = Object.entries(heat.slag.additions_kg ?? {});
  return (
    <section className="card">
      <div className="card-title">슬래그 · 부재료 (slag)</div>
      <table className="data-table">
        <thead>
          <tr>
            <th>항목</th>
            <th className="num">값</th>
          </tr>
        </thead>
        <tbody>
          {comps.map(([k, v]) => (
            <tr key={k}>
              <td>{k}</td>
              <td className="num">{formatValue(v, 2)} %</td>
            </tr>
          ))}
          <tr>
            <td>염기도 (basicity, CaO/SiO₂)</td>
            <td className="num">{formatValue(heat.slag.basicity, 2)}</td>
          </tr>
          {adds.map(([code, kg]) => (
            <tr key={code}>
              <td>{materials?.addition_materials[code] ?? code}</td>
              <td className="num">{formatValue(kg, 0)} kg</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ChargePanel({
  heat,
  materials,
  specMap,
}: {
  heat: Heat;
  materials: MaterialsMeta | null;
  specMap: Map<string, MetricSpec>;
}) {
  const baskets = heat.charge.baskets ?? [];
  const grades = Array.from(
    new Set(baskets.flatMap((b) => Object.keys(b))),
  );
  const totalSpec = specMap.get("charge_total_t");
  const totalOut = isOutOfSpec(heat.charge.total_charge_t, totalSpec);

  return (
    <section className="card">
      <div className="card-title">장입 (charge)</div>
      {baskets.length > 0 ? (
        <table className="data-table">
          <thead>
            <tr>
              <th>바스켓</th>
              {grades.map((g) => (
                <th key={g} className="num">
                  {materials?.scrap_grades[g] ?? g}
                </th>
              ))}
              <th className="num">소계 (t)</th>
            </tr>
          </thead>
          <tbody>
            {baskets.map((b, i) => (
              <tr key={i}>
                <td>{i + 1}차</td>
                {grades.map((g) => (
                  <td key={g} className="num">
                    {formatValue(b[g] ?? null, 1)}
                  </td>
                ))}
                <td className="num">
                  {formatValue(
                    Object.values(b).reduce((a, v) => a + (v ?? 0), 0),
                    1,
                  )}
                </td>
              </tr>
            ))}
            <tr className="total">
              <td>총 장입량 (t)</td>
              <td className="num" colSpan={grades.length}>
                hot heel {formatValue(heat.charge.hot_heel_t, 1)} t
              </td>
              <td className={`num${totalOut ? " val-danger" : ""}`}>
                {formatValue(
                  heat.charge.total_charge_t,
                  totalSpec?.decimals ?? 1,
                )}
              </td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="card-note">장입 상세 데이터가 없습니다.</p>
      )}
    </section>
  );
}

function AdditionsPanel({ additions }: { additions: AdditionEvent[] }) {
  return (
    <section className="card">
      <div className="card-title">부원료 투입 이력 (additions)</div>
      {additions.length === 0 ? (
        <p className="card-note">투입 이벤트가 없습니다.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>시각</th>
              <th>부원료</th>
              <th className="num">투입량 (kg)</th>
            </tr>
          </thead>
          <tbody>
            {additions.map((a, i) => (
              <tr key={i}>
                <td>{a.ts.slice(11, 19)}</td>
                <td>{a.label_ko || a.material}</td>
                <td className="num">{formatValue(a.amount_kg, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
