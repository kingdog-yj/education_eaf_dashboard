// KPI 요약: 일/주/월 생산량·원단위·수율 요약 카드.
import { useEffect, useState } from "react";
import { api } from "../api/client";

type Period = "day" | "week" | "month";

export function KpiSummaryView() {
  const [period, setPeriod] = useState<Period>("day");
  const [cards, setCards] = useState<unknown[]>([]);

  useEffect(() => {
    api
      .getKpiSummary(period)
      .then((r) => setCards(r.cards))
      .catch(console.error);
  }, [period]);

  return (
    <div className="view">
      <div className="view-toolbar">
        {(["day", "week", "month"] as Period[]).map((p) => (
          <button
            key={p}
            className={p === period ? "active" : ""}
            onClick={() => setPeriod(p)}
          >
            {p === "day" ? "일" : p === "week" ? "주" : "월"}
          </button>
        ))}
      </div>
      {cards.length === 0 ? (
        <p className="placeholder">
          데이터가 없습니다. 더미데이터 생성 후 KPI 요약 카드가 표시됩니다.
        </p>
      ) : (
        <div className="kpi-cards">{/* 카드 렌더링: 집계 구현 후 */}</div>
      )}
    </div>
  );
}
