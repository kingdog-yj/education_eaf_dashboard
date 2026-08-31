// 지표 카드. 스펙 밴드가 있으면 값의 밴드 내 위치를 레일로 함께 보여준다.
import type { MetricSpec } from "../api/types";
import {
  bandPosition,
  bandText,
  formatValue,
  hasBand,
  isOutOfSpec,
} from "../lib/metrics";

interface Props {
  label: string;
  value: number | null;
  unit: string;
  decimals: number;
  /** 판정에 사용할 스펙(없으면 판정하지 않음). */
  spec?: MetricSpec | null;
  /** 스펙 판정과 무관하게 이탈색을 강제(예: 스펙 이탈 heat 수 > 0). */
  danger?: boolean;
  /** 보조 정보(예: 직전 대비). */
  meta?: React.ReactNode;
}

export function KpiCard({
  label,
  value,
  unit,
  decimals,
  spec,
  danger,
  meta,
}: Props) {
  const out = danger || isOutOfSpec(value, spec);
  const pos = bandPosition(value, spec);
  const band = bandText(spec);

  return (
    <div className={`kpi-card${out ? " out-of-spec" : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {formatValue(value, decimals)}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {hasBand(spec) && (
        <div
          className="spec-rail"
          title={band ?? undefined}
          aria-label={band ?? undefined}
        >
          <div className="spec-rail-band" />
          {pos != null && (
            <div
              className={`spec-rail-tick${out ? " out" : ""}`}
              style={{ left: `${pos * 100}%` }}
            />
          )}
        </div>
      )}
      {(meta || band) && (
        <div className="kpi-meta">
          {meta}
          {band && <span>{band}</span>}
        </div>
      )}
    </div>
  );
}
