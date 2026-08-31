// plotly.js-dist-min은 자체 타입이 없음 — @types/plotly.js의 타입을 재사용
declare module "plotly.js-dist-min" {
  import * as Plotly from "plotly.js";
  export = Plotly;
}
