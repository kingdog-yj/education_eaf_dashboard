// 다수 heat 트렌드/비교: 기간별 KPI 추이.
// TODO(더미데이터 생성 후): KPI 선택 UI, heat 간 시계열 오버레이 비교, 이상 heat 하이라이트.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PlotlyChart } from "../components/charts/PlotlyChart";

export function TrendView() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    api.getKpiTrend().then(setRows).catch(console.error);
  }, []);

  if (rows.length === 0) {
    return (
      <div className="view">
        <p className="placeholder">
          데이터가 없습니다. 더미데이터 생성 후 KPI 트렌드가 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className="view">
      <div className="chart-area">
        <PlotlyChart
          data={[
            {
              x: rows.map((r) => r.date as string),
              y: rows.map((r) => r.kpi_energy_kwh_per_t as number),
              type: "scatter",
              mode: "lines+markers",
              name: "전력원단위 (kWh/t)",
            },
          ]}
          layout={{ title: { text: "KPI 트렌드" } }}
        />
      </div>
    </div>
  );
}
