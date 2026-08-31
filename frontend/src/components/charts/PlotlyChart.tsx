// plotly.js 얇은 React wrapper. (react-plotly.js는 React 19 peer 의존성 문제로 미사용)
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";

interface Props {
  data: Plotly.Data[];
  layout?: Partial<Plotly.Layout>;
  style?: React.CSSProperties;
}

export function PlotlyChart({ data, layout, style }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    void Plotly.react(ref.current, data, { autosize: true, ...layout }, {
      responsive: true,
      displaylogo: false,
    });
  }, [data, layout]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) Plotly.purge(el);
    };
  }, []);

  return <div ref={ref} style={{ width: "100%", height: "100%", ...style }} />;
}
