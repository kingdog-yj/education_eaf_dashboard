// plotly.js 얇은 React wrapper. (react-plotly.js는 React 19 peer 의존성 문제로 미사용)
// 공통 테마(theme.ts)를 기본값으로 병합하므로 호출부는 데이터/차이나는 레이아웃만 넘긴다.
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import { mergeLayout } from "./theme";

interface Props {
  data: Plotly.Data[];
  layout?: Partial<Plotly.Layout>;
  style?: React.CSSProperties;
  /** 데이터 포인트 클릭 (plotly_click). */
  onClick?: (ev: Plotly.PlotMouseEvent) => void;
}

type PlotlyDiv = HTMLDivElement & {
  on?: (event: string, handler: (ev: Plotly.PlotMouseEvent) => void) => void;
  removeAllListeners?: (event: string) => void;
};

export function PlotlyChart({ data, layout, style, onClick }: Props) {
  const ref = useRef<PlotlyDiv>(null);
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;
  const bound = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    void Plotly.react(el, data, mergeLayout(layout), {
      responsive: true,
      displaylogo: false,
    }).then(() => {
      if (bound.current || !el.on) return;
      bound.current = true;
      el.on("plotly_click", (ev) => onClickRef.current?.(ev));
    });
  }, [data, layout]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (!el) return;
      el.removeAllListeners?.("plotly_click");
      bound.current = false;
      Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} style={{ width: "100%", height: "100%", ...style }} />;
}
