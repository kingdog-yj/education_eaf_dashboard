// Plotly 공통 테마. 디자인 토큰(styles.css :root)과 같은 값을 사용한다.
// 차트 색·폰트를 각 뷰에 흩뿌리지 않기 위한 유일한 선언 지점.
import type * as Plotly from "plotly.js";

export const CHART = {
  fontFamily:
    'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif',
  textBody: "#333333",
  textMuted: "#475569",
  grid: "rgba(0,0,0,0.06)",
  gridStrong: "rgba(0,0,0,0.1)",
  accent: "#0078d4",
  accentTint: "rgba(0,120,212,0.08)",
  danger: "#d13438",
  /** 페이즈 음영 교대 톤 (중립 회색) */
  phaseShade: ["rgba(0,0,0,0.03)", "rgba(0,0,0,0.06)"],
  colorway: ["#0078d4", "#038387", "#8764b8"],
} as const;

/** 모든 x/y 축에 적용할 기본값. */
export const axisDefaults: Partial<Plotly.LayoutAxis> = {
  gridcolor: CHART.grid,
  linecolor: CHART.gridStrong,
  zeroline: false,
  ticks: "outside",
  tickcolor: CHART.gridStrong,
  ticklen: 4,
  tickfont: { size: 11, color: CHART.textMuted },
  automargin: true,
};

export const baseLayout: Partial<Plotly.Layout> = {
  font: { family: CHART.fontFamily, color: CHART.textBody, size: 12 },
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "rgba(0,0,0,0)",
  colorway: [...CHART.colorway],
  margin: { l: 56, r: 16, t: 32, b: 40 },
  hovermode: "closest",
  hoverlabel: { font: { family: CHART.fontFamily, size: 12 } },
  legend: {
    orientation: "h",
    yanchor: "bottom",
    y: 1.02,
    x: 0,
    font: { size: 12 },
  },
};

const AXIS_KEY = /^[xy]axis\d*$/;

/** 테마 기본값에 호출부 layout을 병합(중첩 키는 얕은 병합). */
export function mergeLayout(
  layout?: Partial<Plotly.Layout>,
): Partial<Plotly.Layout> {
  const src = (layout ?? {}) as Record<string, unknown>;
  const merged: Record<string, unknown> = { ...baseLayout, ...src };

  for (const key of ["font", "margin", "legend", "hoverlabel"] as const) {
    const base = baseLayout[key] as Record<string, unknown> | undefined;
    const over = src[key] as Record<string, unknown> | undefined;
    if (base || over) merged[key] = { ...base, ...over };
  }

  // 축은 개수를 알 수 없으므로(서브플롯 동적 생성) 키 패턴으로 처리
  const axisKeys = new Set(Object.keys(merged).filter((k) => AXIS_KEY.test(k)));
  axisKeys.add("xaxis");
  axisKeys.add("yaxis");
  for (const key of axisKeys) {
    merged[key] = {
      ...axisDefaults,
      ...((merged[key] as Record<string, unknown>) ?? {}),
    };
  }

  return merged as Partial<Plotly.Layout>;
}
