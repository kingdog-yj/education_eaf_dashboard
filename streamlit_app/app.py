"""EAF 공정 분석 대시보드 — Streamlit 고정 스냅샷 데모 (단일 파일).

FastAPI+React 원본(c59ffe8)의 데이터/도메인/프롬프트 계층을 그대로 재사용하고,
UI만 Streamlit으로 대체한 1회성 배포용 앱이다. backend/ 코드는 수정하지 않는다.
데이터 접근·모델·집계 로직은 app.services / app.data / app.domain 호출만 한다.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from app.data.file_repository import ParquetHeatRepository  # noqa: E402
from app.data.repository import HeatNotFoundError  # noqa: E402
from app.domain import specs  # noqa: E402
from app.domain.materials import (  # noqa: E402
    ADDITION_MATERIALS,
    SCRAP_GRADES,
    STEEL_GROUPS,
)
from app.domain.tags import TAG_REGISTRY  # noqa: E402
from app.llm.context_builder import ContextBuilder, DashboardContext  # noqa: E402
from app.llm.options import LLM_MODEL_OPTIONS  # noqa: E402
from app.llm.tools.data_tools import (  # noqa: E402
    QueryHeatDetailTool,
    QueryKpiTrendTool,
    QueryTimeseriesStatsTool,
)
from app.services.heat_service import HeatService  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "dummy"

#: 채팅 모델 — 선언 지점은 llm/options.py (모델 id 하드코딩 금지)
CHAT_MODEL = LLM_MODEL_OPTIONS[0].id

#: 사이드바 표시명 → 내부 view id (원본 프론트 dashboardContext와 동일 문자열)
VIEW_OPTIONS: dict[str, str] = {
    "Heat 상세": "heat_detail",
    "트렌드": "trend",
    "KPI 요약": "kpi_summary",
    "실시간 모니터링": "live",
}

#: Heat 상세 상단 카드에 쓸 KpiInfo 필드 (라벨/단위/자릿수는 SPEC_REGISTRY에서 조회)
DETAIL_KPI_FIELDS: list[str] = [
    "energy_kwh_per_t",
    "tap_weight_t",
    "power_on_min",
    "tap_to_tap_min",
]

#: 트렌드 뷰 기본 선택 지표
DEFAULT_TREND_METRIC = "kpi_energy_kwh_per_t"

#: 집계 기간 표시명 → API 값
PERIOD_OPTIONS: dict[str, str] = {"일": "day", "주": "week", "월": "month"}

DEMO_LIMIT_NOTE = (
    "\n\n---\n\n참고: 이 데모는 heat 상세 조회·시계열 통계·KPI 트렌드 조회 tool을 "
    "사용할 수 있다. 특정 heat나 기간, 순번(예: N번째 전 히트) 질문에는 반드시 tool로 "
    "실제 데이터를 조회한 뒤 답하라. 최신·순번 질문은 query_kpi_trend를 인자 없이 "
    "호출해 전체 목록(날짜 오름차순, 마지막이 최신)을 받아 세어라 — start/end는 "
    "자정 기준으로 해석되어 최신 heat이 누락될 수 있다. "
    "웹·학술 검색은 이 데모에서 지원하지 않는다."
)

#: tool 호출 라운드 상한 (무한 루프 방지)
MAX_TOOL_ROUNDS = 5

st.set_page_config(page_title="EAF 공정 분석 대시보드 (스냅샷)", layout="wide")


# -- 데이터 로딩 (backend 재사용) -------------------------------------------


@st.cache_resource
def get_repository() -> ParquetHeatRepository:
    """스냅샷 데모의 유일한 리포지토리 인스턴스.

    get_settings()/create_repository()를 거치지 않고 DATA_DIR을 직접 쓴다
    (이 앱은 .env·config에 의존하지 않는다).
    """
    return ParquetHeatRepository(DATA_DIR)


@st.cache_resource
def get_service() -> HeatService:
    return HeatService(get_repository())


@st.cache_data(show_spinner=False)
def load_heat_ids() -> list[str]:
    return [h.heat_id for h in get_service().list_heats(None, None, 500)]


@st.cache_data(show_spinner=False)
def load_timeseries(heat_id: str, downsample_s: float = 5.0):
    return get_service().get_timeseries(heat_id, None, downsample_s)


@st.cache_data(show_spinner=False)
def load_kpi_trend() -> pd.DataFrame:
    return pd.DataFrame(get_service().get_kpi_trend(None, None))


# -- 표시 헬퍼 --------------------------------------------------------------


def _num(value) -> float | None:
    """결측(None/NaN/비수치)을 None으로 정규화."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _fmt(value, decimals: int = 1, unit: str = "") -> str:
    """수치 → 표시 문자열. 결측은 '-'."""
    f = _num(value)
    if f is None:
        return "-"
    text = f"{f:.{decimals}f}"
    return f"{text} {unit}".strip() if unit else text


def _kv_table(rows: list[tuple[str, str]]) -> pd.DataFrame:
    """(항목, 값) 목록 → 2열 표."""
    return pd.DataFrame(rows, columns=["항목", "값"])


def _dict_rows(
    data: dict, labels: dict[str, str] | None = None, decimals: int = 2, unit: str = ""
) -> list[tuple[str, str]]:
    """dict → (라벨, 값) 행 목록. labels가 있으면 코드 → 한글 라벨로 치환."""
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        label = (labels or {}).get(key, key.upper())
        rows.append((label, _fmt(value, decimals, unit)))
    return rows


# -- 뷰 ---------------------------------------------------------------------


def render_heat_detail() -> str | None:
    """단일 heat 상세. 선택된 heat_id를 반환한다 (채팅 컨텍스트용)."""
    st.subheader("Heat 상세")

    heat_ids = load_heat_ids()
    if not heat_ids:
        st.info("조회 가능한 heat이 없습니다.")
        return None

    heat_id = st.selectbox("Heat 선택", heat_ids)
    if not heat_id:
        return None

    try:
        heat = get_service().get_heat(heat_id)
    except HeatNotFoundError:
        st.warning(f"heat을 찾을 수 없습니다: {heat_id}")
        return None

    group_label = STEEL_GROUPS.get(heat.summary.steel_group, heat.summary.steel_group)
    st.caption(
        f"{heat.summary.date:%Y-%m-%d %H:%M} · 강종 그룹(steel group): "
        f"{group_label or '-'} · 교대(shift): {heat.summary.shift or '-'}"
    )

    # 상단 KPI 카드 4개 (라벨/단위/자릿수는 SPEC_REGISTRY 선언에서)
    for col, field in zip(st.columns(len(DETAIL_KPI_FIELDS)), DETAIL_KPI_FIELDS):
        spec = specs.get(f"kpi_{field}")
        label = f"{spec.label_ko} ({spec.unit})" if spec else field
        decimals = spec.decimals if spec else 1
        col.metric(label, _fmt(getattr(heat.kpi, field, None), decimals))

    # 시계열
    try:
        ts = load_timeseries(heat_id)
    except HeatNotFoundError:
        ts = None
        st.warning(f"시계열 데이터가 없습니다: {heat_id}")

    if ts is not None and ts.series:
        fig = make_subplots(rows=len(ts.series), cols=1, shared_xaxes=True)
        for i, series in enumerate(ts.series, start=1):
            tag = TAG_REGISTRY.get(series.tag_id)
            fig.add_trace(
                go.Scatter(
                    x=[p.ts for p in series.points],
                    y=[p.value for p in series.points],
                    mode="lines",
                    name=f"{tag.label_ko} ({tag.unit})",
                ),
                row=i,
                col=1,
            )
            fig.update_yaxes(title_text=f"{tag.label_ko}<br>{tag.unit}", row=i, col=1)
        fig.update_layout(
            height=220 * len(ts.series),
            margin=dict(l=60, r=20, t=30, b=40),
            showlegend=True,
        )
        st.plotly_chart(fig, width="stretch")

    # 정적 정보
    left, right = st.columns(2)

    with left:
        st.markdown("**KPI**")
        kpi_rows: list[tuple[str, str]] = []
        for field, value in heat.kpi.model_dump().items():
            spec = specs.get(f"kpi_{field}")
            label = f"{spec.label_ko} ({spec.unit})" if spec else field
            kpi_rows.append((label, _fmt(value, spec.decimals if spec else 1)))
        st.dataframe(_kv_table(kpi_rows), width="stretch", hide_index=True)

        st.markdown("**종점 (EOP, end-point)**")
        temp_spec = specs.get("eop_tap_temp_c")
        eop_rows = [
            (
                f"{temp_spec.label_ko} ({temp_spec.unit})"
                if temp_spec
                else "출강 온도 (°C)",
                _fmt(heat.eop.tap_temp_c, temp_spec.decimals if temp_spec else 0),
            )
        ]
        eop_rows += _dict_rows(heat.eop.composition_pct, decimals=3, unit="%")
        st.dataframe(_kv_table(eop_rows), width="stretch", hide_index=True)

    with right:
        st.markdown("**장입 (charge)**")
        charge_spec = specs.get("charge_total_t")
        charge_rows = [
            (
                f"{charge_spec.label_ko} ({charge_spec.unit})"
                if charge_spec
                else "총 장입량 (t)",
                _fmt(heat.charge.total_charge_t, charge_spec.decimals if charge_spec else 1),
            ),
            ("탕류량 (hot heel, t)", _fmt(heat.charge.hot_heel_t, 1)),
        ]
        for idx, basket in enumerate(heat.charge.baskets, start=1):
            for label, value in _dict_rows(basket, SCRAP_GRADES, decimals=1, unit="t"):
                charge_rows.append((f"바스켓 {idx} · {label}", value))
        st.dataframe(_kv_table(charge_rows), width="stretch", hide_index=True)

        st.markdown("**슬래그 (slag)**")
        slag_rows = [("염기도 (basicity, CaO/SiO₂)", _fmt(heat.slag.basicity, 2))]
        slag_rows += _dict_rows(heat.slag.composition_pct, decimals=2, unit="%")
        slag_rows += _dict_rows(
            heat.slag.additions_kg, ADDITION_MATERIALS, decimals=0, unit="kg"
        )
        st.dataframe(_kv_table(slag_rows), width="stretch", hide_index=True)

    return heat_id


def render_trend() -> None:
    """다수 heat 지표 트렌드."""
    st.subheader("트렌드 (trend)")

    metric_ids = specs.ids()
    default_index = (
        metric_ids.index(DEFAULT_TREND_METRIC)
        if DEFAULT_TREND_METRIC in metric_ids
        else 0
    )
    spec = st.selectbox(
        "지표 선택",
        specs.SPEC_REGISTRY,
        index=default_index,
        format_func=lambda s: f"{s.label_ko} ({s.unit})",
    )

    df = load_kpi_trend()
    if df.empty:
        st.info("트렌드 데이터가 없습니다.")
        return
    if spec.id not in df.columns:
        st.info("해당 지표 데이터 없음")
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df[spec.id],
            mode="lines+markers",
            name=f"{spec.label_ko} ({spec.unit})",
        )
    )
    if spec.lo is not None:
        fig.add_hline(y=spec.lo, line_dash="dot", annotation_text=f"하한 {spec.lo}")
    if spec.hi is not None:
        fig.add_hline(y=spec.hi, line_dash="dot", annotation_text=f"상한 {spec.hi}")
    fig.update_layout(
        height=460,
        margin=dict(l=60, r=20, t=30, b=40),
        yaxis_title=f"{spec.label_ko} ({spec.unit})",
        xaxis_title="일시",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(f"대상 heat 수: {len(df)}")


def render_kpi_summary() -> None:
    """일/주/월 KPI 요약 카드."""
    st.subheader("KPI 요약")

    label = st.radio("집계 기간", list(PERIOD_OPTIONS.keys()), horizontal=True)
    period = PERIOD_OPTIONS[label]

    resp = get_service().get_kpi_summary(period)
    if not resp.cards:
        st.info("집계할 데이터가 없습니다.")
        return
    if resp.bucket_start and resp.bucket_end:
        st.caption(
            f"집계 구간: {resp.bucket_start:%Y-%m-%d %H:%M} ~ "
            f"{resp.bucket_end:%Y-%m-%d %H:%M} (직전 구간 대비 증감 표시)"
        )

    cards = list(resp.cards)
    for start in range(0, len(cards), 4):
        for col, card in zip(st.columns(4), cards[start : start + 4]):
            value = _num(card.value)
            prev = _num(card.prev_value)
            delta = None
            if value is not None and prev is not None:
                delta = f"{value - prev:+.{card.decimals}f}"
            col.metric(
                label=f"{card.label_ko} ({card.unit})",
                value="-" if value is None else f"{value:.{card.decimals}f}",
                delta=delta,
            )


def render_live() -> None:
    st.subheader("실시간 모니터링 (live)")
    st.info("실시간 모니터링은 이 스냅샷에 포함되지 않습니다.")


# -- Discussion (채팅) ------------------------------------------------------


def _openai_key() -> str:
    try:
        return st.secrets.get("OPENAI_API_KEY", "") or os.environ.get(
            "OPENAI_API_KEY", ""
        )
    except Exception:  # secrets.toml 자체가 없는 로컬 환경
        return os.environ.get("OPENAI_API_KEY", "")


def _mask_secrets(text: str) -> str:
    """예외 메시지에 섞여 나올 수 있는 API 키 토큰을 가린다."""
    return re.sub(r"sk-[A-Za-z0-9_\-]{4,}", "***", text)


def _heat_note(heat_id: str) -> str:
    """선택된 heat의 핵심 수치 요약 — tool 호출 전 LLM에 주는 화면 컨텍스트 힌트."""
    try:
        heat = get_service().get_heat(heat_id)
    except HeatNotFoundError:
        return ""

    kpi_parts: list[str] = []
    for field, value in heat.kpi.model_dump().items():
        if _num(value) is None:
            continue
        spec = specs.get(f"kpi_{field}")
        label = spec.label_ko if spec else field
        unit = spec.unit if spec else ""
        kpi_parts.append(f"{label} {_fmt(value, spec.decimals if spec else 1, unit)}")

    eop_parts: list[str] = []
    temp_spec = specs.get("eop_tap_temp_c")
    if _num(heat.eop.tap_temp_c) is not None:
        eop_parts.append(
            f"{temp_spec.label_ko if temp_spec else '출강 온도'} "
            f"{_fmt(heat.eop.tap_temp_c, temp_spec.decimals if temp_spec else 0, '°C')}"
        )
    for element, value in heat.eop.composition_pct.items():
        if _num(value) is not None:
            eop_parts.append(f"{element.upper()} {_fmt(value, 3, '%')}")

    slag_parts: list[str] = []
    if _num(heat.slag.basicity) is not None:
        slag_parts.append(f"염기도 {_fmt(heat.slag.basicity, 2)}")
    if _num(heat.charge.total_charge_t) is not None:
        slag_parts.append(f"총 장입량 {_fmt(heat.charge.total_charge_t, 1, 't')}")

    group_label = STEEL_GROUPS.get(heat.summary.steel_group, heat.summary.steel_group)
    lines = [
        f"heat {heat.summary.heat_id} ({heat.summary.date:%Y-%m-%d %H:%M}"
        + (f", 강종 그룹 {group_label}" if group_label else "")
        + ")"
    ]
    if kpi_parts:
        lines.append("KPI: " + ", ".join(kpi_parts))
    if eop_parts:
        lines.append("EOP: " + ", ".join(eop_parts))
    if slag_parts:
        lines.append("기타: " + ", ".join(slag_parts))
    return " / ".join(lines)


@st.cache_resource
def get_chat_tools() -> list:
    """채팅용 데이터 조회 tool 3종 (웹/학술 검색은 이 데모에서 제외).

    create_default_tools()는 get_settings()에 의존하므로 쓰지 않고,
    캐시된 리포지토리를 재사용해 수동 생성한다.
    """
    repo = get_repository()
    return [QueryHeatDetailTool(repo), QueryTimeseriesStatsTool(repo), QueryKpiTrendTool(repo)]


def _tool_schemas() -> list[dict]:
    """DiscussionTool 선언 → OpenAI function-calling 스키마."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            },
        }
        for t in get_chat_tools()
    ]


def _run_tool(name: str, arguments_json: str) -> str:
    """tool 1회 실행. 실패는 예외 대신 JSON 오류 문자열로 LLM에 돌려준다."""
    tools_by_name = {t.name: t for t in get_chat_tools()}
    tool = tools_by_name.get(name)
    if tool is None:
        return json.dumps({"error": f"알 수 없는 tool: {name}"}, ensure_ascii=False)
    try:
        kwargs = json.loads(arguments_json or "{}")
        return asyncio.run(tool.run(**kwargs))
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _chat_completion_loop(client, system_prompt: str, history: list[dict]) -> str:
    """tool 호출 라운드를 돌고 최종 답변 텍스트를 반환."""
    messages = [{"role": "system", "content": system_prompt}, *history]
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=_tool_schemas(),
        )
        choice = resp.choices[0]
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(choice.message.model_dump(exclude_none=True))
            with st.spinner("데이터 조회 중..."):
                for call in choice.message.tool_calls:
                    st.caption(f"🔎 {call.function.name} 조회 중")
                    result = _run_tool(call.function.name, call.function.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
            continue
        return choice.message.content or ""
    return "도구 호출이 너무 많아 답변을 완성하지 못했습니다. 질문을 더 구체적으로 나눠 다시 시도해 주세요."


def render_chat(view_id: str, heat_id: str | None) -> None:
    st.subheader("Discussion")

    key = _openai_key()
    if not key:
        st.info("OPENAI_API_KEY가 설정되지 않아 채팅이 비활성화되어 있습니다.")
        return

    note = _heat_note(heat_id) if view_id == "heat_detail" and heat_id else ""
    ctx = DashboardContext(
        view=view_id,
        heat_id=heat_id,
        visible_tags=(
            [t.id for t in TAG_REGISTRY.all()]
            if view_id == "heat_detail" and heat_id
            else []
        ),
        note=note,
    )
    system_prompt = ContextBuilder().build_system_prompt(ctx) + DEMO_LIMIT_NOTE

    messages = st.session_state.setdefault("messages", [])
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("공정에 대해 질문하세요")
    if not prompt:
        return

    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            from openai import OpenAI

            client = OpenAI(api_key=key)
            answer = _chat_completion_loop(client, system_prompt, list(messages))
            st.markdown(answer)
            messages.append({"role": "assistant", "content": answer})
        except Exception as exc:  # 채팅 실패가 대시보드를 죽이지 않는다
            st.error(f"LLM 호출 실패: {_mask_secrets(str(exc))}")


# -- 엔트리 -----------------------------------------------------------------


def main() -> None:
    st.title("EAF 공정 분석 대시보드")
    st.caption("고정 스냅샷 데모 (c59ffe8) — 최신 버전은 별도 개발 중")

    choice = st.sidebar.radio("뷰 선택", list(VIEW_OPTIONS.keys()))
    view_id = VIEW_OPTIONS[choice]

    heat_id: str | None = None
    if view_id == "heat_detail":
        heat_id = render_heat_detail()
    elif view_id == "trend":
        render_trend()
    elif view_id == "kpi_summary":
        render_kpi_summary()
    else:
        render_live()

    st.divider()
    render_chat(view_id, heat_id)


main()
