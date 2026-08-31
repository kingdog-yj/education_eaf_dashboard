// KPI 요약: 일/주/월 버킷 집계 카드. 카드 구성은 응답 선언(cards)을 그대로 따른다.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { KpiSummaryResponse, MetricSpec } from "../api/types";
import { KpiCard } from "../components/KpiCard";
import { formatDate, formatValue, toSpecMap } from "../lib/metrics";

type Period = "day" | "week" | "month";

const PERIODS: { id: Period; label: string }[] = [
  { id: "day", label: "일" },
  { id: "week", label: "주" },
  { id: "month", label: "월" },
];

/** 값>0이면 이탈로 보는 카운터 카드(응답에 spec_id가 없는 유일한 판정 대상). */
const COUNTER_DANGER_ID = "out_of_spec_count";

export function KpiSummaryView() {
  const [period, setPeriod] = useState<Period>("day");
  const [summary, setSummary] = useState<KpiSummaryResponse | null>(null);
  const [specs, setSpecs] = useState<MetricSpec[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSpecs().then(setSpecs).catch(console.error);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getKpiSummary(period)
      .then((r) => !cancelled && setSummary(r))
      .catch(() => !cancelled && setSummary(null))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [period]);

  const specMap = useMemo(() => toSpecMap(specs), [specs]);
  const cards = summary?.cards ?? [];
  const periodLabel = PERIODS.find((p) => p.id === period)?.label ?? "";

  return (
    <div className="view">
      <header className="view-header">
        <div>
          <div className="view-title">KPI 요약</div>
          <div className="view-subtitle">
            {summary?.bucket_start
              ? `집계 기간 ${formatDate(summary.bucket_start)} ~ ${formatDate(summary.bucket_end)} · 데이터 최신 ${periodLabel} 기준`
              : "데이터의 최신 heat이 속한 버킷을 집계합니다."}
          </div>
        </div>
        <div className="view-toolbar">
          <div className="field">
            <span>집계 단위</span>
            <div className="segmented" role="group" aria-label="집계 단위">
              {PERIODS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={p.id === period ? "active" : ""}
                  aria-pressed={p.id === period}
                  onClick={() => setPeriod(p.id)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      {cards.length === 0 ? (
        <p className="empty-state">
          {loading
            ? "요약을 불러오는 중…"
            : "집계할 heat 데이터가 없습니다. 더미데이터 생성 후 표시됩니다."}
        </p>
      ) : (
        <div className="kpi-grid">
          {cards.map((c) => {
            const spec = c.spec_id ? specMap.get(c.spec_id) : null;
            return (
              <KpiCard
                key={c.id}
                label={c.label_ko}
                value={c.value}
                unit={c.unit}
                decimals={c.decimals}
                spec={spec}
                danger={c.id === COUNTER_DANGER_ID && (c.value ?? 0) > 0}
                meta={
                  <span>
                    직전 {periodLabel}{" "}
                    {formatValue(c.prev_value, c.decimals)}
                    {c.prev_value != null && c.value != null
                      ? ` (${diffText(c.value - c.prev_value, c.decimals)})`
                      : ""}
                  </span>
                }
              />
            );
          })}
        </div>
      )}

      {summary?.prev_bucket_start && (
        <p className="card-note">
          직전 버킷 시작: {formatDate(summary.prev_bucket_start)} · 증감은
          수치 차이만 표시하며 좋고 나쁨을 판단하지 않습니다.
        </p>
      )}
    </div>
  );
}

function diffText(delta: number, decimals: number): string {
  if (Math.abs(delta) < 10 ** -decimals / 2) return "변화 없음";
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${formatValue(Math.abs(delta), decimals)}`;
}
