// 단일 heat 상세: heat 선택 → 시계열 멀티트랙 차트 + 정적 정보 패널.
// TODO(더미데이터 생성 후): 페이즈 구간 음영, 용락 이벤트 수직선, 그룹별 서브플롯.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Heat, HeatSummary, HeatTimeseries } from "../api/types";
import { PlotlyChart } from "../components/charts/PlotlyChart";
import { useDashboardContext } from "../state/dashboardContext";

export function HeatDetailView() {
  const { heatId, setHeatId, setVisibleTags } = useDashboardContext();
  const [heats, setHeats] = useState<HeatSummary[]>([]);
  const [heat, setHeat] = useState<Heat | null>(null);
  const [ts, setTs] = useState<HeatTimeseries | null>(null);

  useEffect(() => {
    api.listHeats({ limit: 50 }).then(setHeats).catch(console.error);
  }, []);

  useEffect(() => {
    if (!heatId) return;
    api.getHeat(heatId).then(setHeat).catch(console.error);
    api
      .getTimeseries(heatId, undefined, 10)
      .then((t) => {
        setTs(t);
        setVisibleTags(t.series.map((s) => s.tag_id));
      })
      .catch(console.error);
  }, [heatId, setVisibleTags]);

  return (
    <div className="view">
      <div className="view-toolbar">
        <label>
          Heat:{" "}
          <select
            value={heatId ?? ""}
            onChange={(e) => setHeatId(e.target.value || null)}
          >
            <option value="">선택…</option>
            {heats.map((h) => (
              <option key={h.heat_id} value={h.heat_id}>
                {h.heat_id}
              </option>
            ))}
          </select>
        </label>
      </div>

      {heats.length === 0 && (
        <p className="placeholder">
          데이터가 없습니다. 더미데이터 생성 후 heat 목록이 표시됩니다.
        </p>
      )}

      {ts && (
        <div className="chart-area">
          <PlotlyChart
            data={ts.series.map((s) => ({
              x: s.points.map((p) => p.ts),
              y: s.points.map((p) => p.value),
              name: `${s.tag_id} (${s.unit})`,
              type: "scatter",
              mode: "lines",
            }))}
            layout={{ title: { text: `Heat ${ts.heat_id} 시계열` } }}
          />
        </div>
      )}

      {heat && (
        <div className="static-panels">
          <section>
            <h3>KPI</h3>
            <pre>{JSON.stringify(heat.kpi, null, 2)}</pre>
          </section>
          <section>
            <h3>종점 (EOP)</h3>
            <pre>{JSON.stringify(heat.eop, null, 2)}</pre>
          </section>
          <section>
            <h3>슬래그</h3>
            <pre>{JSON.stringify(heat.slag, null, 2)}</pre>
          </section>
          <section>
            <h3>장입</h3>
            <pre>{JSON.stringify(heat.charge, null, 2)}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
