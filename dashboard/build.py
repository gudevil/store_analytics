"""Build the static HTML dashboard from the local DuckDB.

    python build.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go

ROOT       = Path(__file__).resolve().parent
REPO_ROOT  = ROOT.parent
DB_PATH    = REPO_ROOT / "analytics.duckdb"
OUT_HTML   = REPO_ROOT / "docs" / "index.html"

C_PRIMARY   = "#2563eb"
C_SECONDARY = "#10b981"
C_NEG       = "#dc2626"
C_MUTED_FG  = "#64748b"
C_GRID      = "#e2e8f0"
CHART_PALETTE = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444",
                 "#0ea5e9", "#84cc16", "#f97316", "#6366f1", "#14b8a6"]


def query_all(con: duckdb.DuckDBPyConnection) -> dict:
    yearly = con.execute("""
        SELECT
            EXTRACT(year FROM order_date)::INT AS yr,
            SUM(sales)                         AS sales,
            SUM(profit)                        AS profit,
            SUM(profit) / NULLIF(SUM(sales), 0) AS margin,
            COUNT(DISTINCT order_id)           AS orders
        FROM main.orders
        GROUP BY 1
        ORDER BY 1
    """).fetchdf().set_index("yr")

    kpi_totals = con.execute("""
        SELECT
            SUM(sales)                          AS sales,
            SUM(profit)                         AS profit,
            SUM(profit) / NULLIF(SUM(sales), 0) AS margin,
            COUNT(DISTINCT order_id)            AS orders
        FROM main.orders
    """).fetchone()

    last_yr = int(yearly.index.max())
    prev_yr = last_yr - 1

    def yoy_delta(col: str) -> float:
        cur = float(yearly.loc[last_yr, col])
        prv = float(yearly.loc[prev_yr, col])
        if prv == 0:
            return 0.0
        if col == "margin":
            return (cur - prv) * 100.0
        return (cur - prv) / prv * 100.0

    hint = f"YoY {last_yr} vs {prev_yr}"
    kpis = [
        {"label": "Sales (Lifetime)",  "value": f"${kpi_totals[0]:,.0f}",
         "delta": yoy_delta("sales"),  "suffix": "%",   "hint": hint},
        {"label": "Profit (Lifetime)", "value": f"${kpi_totals[1]:,.0f}",
         "delta": yoy_delta("profit"), "suffix": "%",   "hint": hint},
        {"label": "Margin (Lifetime)", "value": f"{kpi_totals[2]*100:.1f}%",
         "delta": yoy_delta("margin"), "suffix": " pp", "hint": hint},
        {"label": "Orders (Lifetime)", "value": f"{int(kpi_totals[3]):,}",
         "delta": yoy_delta("orders"), "suffix": "%",   "hint": hint},
    ]

    monthly = con.execute("""
        SELECT date_trunc('month', order_date) AS month,
               SUM(sales)  AS sales,
               SUM(profit) AS profit
        FROM main.orders
        GROUP BY 1
        ORDER BY 1
    """).fetchdf()

    subcat = con.execute("""
        SELECT p.category AS subcategory,
               SUM(o.sales)  AS sales,
               SUM(o.profit) AS profit,
               SUM(o.profit) / NULLIF(SUM(o.sales), 0) AS margin
        FROM main.orders o
        JOIN main.product p ON o.product_id = p.id
        GROUP BY 1
        ORDER BY margin ASC
    """).fetchdf()

    cat_share = con.execute("""
        SELECT p.name AS category, SUM(o.sales) AS sales
        FROM main.orders o
        JOIN main.product p ON o.product_id = p.id
        GROUP BY 1
        ORDER BY sales DESC
    """).fetchdf()

    segment = con.execute("""
        SELECT c.segment      AS segment,
               SUM(o.sales)   AS sales,
               SUM(o.profit)  AS profit,
               SUM(o.profit) / NULLIF(SUM(o.sales), 0) AS margin
        FROM main.orders o
        JOIN main.customer c ON o.customer_id = c.id
        GROUP BY 1
        ORDER BY profit DESC
    """).fetchdf()

    yoy = yearly.reset_index().sort_values("yr").reset_index(drop=True)
    yoy["sales_yoy"]     = yoy["sales"].pct_change() * 100
    yoy["profit_yoy"]    = yoy["profit"].pct_change() * 100
    yoy["orders_yoy"]    = yoy["orders"].pct_change() * 100
    yoy["margin_yoy_pp"] = (yoy["margin"] - yoy["margin"].shift(1)) * 100

    return {
        "kpis": kpis,
        "monthly": monthly,
        "subcat": subcat,
        "cat_share": cat_share,
        "segment": segment,
        "yoy": yoy,
        "last_yr": last_yr,
        "prev_yr": prev_yr,
    }


BASE_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Inter, ui-sans-serif, system-ui, -apple-system, sans-serif",
              color="#0f172a", size=12),
    margin=dict(l=60, r=60, t=20, b=40),
    hoverlabel=dict(bgcolor="white", bordercolor=C_GRID,
                    font_family="Inter, sans-serif", font_size=12),
)
AXIS_CLEAN = dict(showline=False, ticks="", showgrid=True, gridcolor=C_GRID,
                  griddash="dash", zeroline=False, tickfont=dict(color=C_MUTED_FG))
AXIS_X = {**AXIS_CLEAN, "showgrid": False}


def fig_trend_monthly(monthly: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly["month"], y=monthly["sales"], mode="lines", name="Sales",
        line=dict(color=C_PRIMARY, width=2.5, shape="spline", smoothing=0.6),
        fill="tozeroy", fillcolor="rgba(37, 99, 235, 0.10)",
        hovertemplate="<b>%{x}</b><br>Sales: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=monthly["month"], y=monthly["profit"], mode="lines", name="Profit",
        line=dict(color=C_SECONDARY, width=2, shape="spline", smoothing=0.6),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Profit: $%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **BASE_LAYOUT,
        height=300,
        xaxis=AXIS_X,
        yaxis=dict(**AXIS_CLEAN, tickprefix="$", tickformat=",.0f"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickprefix="$", tickformat=",.0f",
                    tickfont=dict(color=C_MUTED_FG), showline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )
    return fig


def fig_subcat_margin(subcat: pd.DataFrame) -> go.Figure:
    df = subcat.copy()
    df["margin_pct"] = df["margin"] * 100
    colors = [C_NEG if m < 0 else C_PRIMARY for m in df["margin_pct"]]
    fig = go.Figure(go.Bar(
        x=df["margin_pct"], y=df["subcategory"], orientation="h",
        marker=dict(color=colors),
        text=[f"{m:+.1f}%" for m in df["margin_pct"]],
        textposition="auto",
        insidetextanchor="end",
        cliponaxis=False,
        insidetextfont=dict(size=11, color="white"),
        outsidetextfont=dict(size=11, color=C_MUTED_FG),
        hovertemplate="<b>%{y}</b><br>Margin: %{x:.1f}%<br>Sales: $%{customdata[0]:,.0f}<br>Profit: $%{customdata[1]:,.0f}<extra></extra>",
        customdata=df[["sales", "profit"]].values,
    ))
    fig.update_layout(
        **{**BASE_LAYOUT, "margin": dict(l=100, r=70, t=8, b=8)},
        height=520,
        xaxis={**AXIS_CLEAN, "ticksuffix": "%", "zeroline": True,
               "zerolinecolor": "#94a3b8", "zerolinewidth": 1},
        yaxis=dict(showline=False, ticks="", showgrid=False,
                   tickfont=dict(color="#0f172a", size=12)),
    )
    return fig


def fig_cat_donut(cat_share: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=cat_share["category"], values=cat_share["sales"],
        hole=0.55, sort=False, direction="clockwise",
        marker=dict(colors=CHART_PALETTE[: len(cat_share)],
                    line=dict(color="white", width=3)),
        textinfo="percent", textposition="inside",
        insidetextorientation="horizontal",
        textfont=dict(color="white", size=13, family="Inter, sans-serif"),
        hovertemplate="<b>%{label}</b><br>Sales: $%{value:,.0f}<br>Share: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        **{**BASE_LAYOUT, "margin": dict(l=8, r=88, t=8, b=8)},
        height=280,
        showlegend=True,
        legend=dict(orientation="v", yanchor="middle", y=0.5,
                    xanchor="left", x=1.02, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color=C_MUTED_FG)),
    )
    return fig


def fig_to_div(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
        config={"displayModeBar": False, "responsive": True},
    )


def kpi_card(kpi: dict) -> str:
    delta = kpi["delta"]
    suffix = kpi.get("suffix", "%")
    if delta > 0.05:
        color, arrow = "text-emerald-600", "&#9650;"
    elif delta < -0.05:
        color, arrow = "text-rose-600", "&#9660;"
    else:
        color, arrow = "text-slate-400", "&#8211;"
    return f"""
    <div class="bg-white border border-slate-200 rounded-xl p-5 flex flex-col gap-3">
      <div class="text-xs font-medium text-slate-500">{html.escape(kpi['label'])}</div>
      <div class="text-3xl font-semibold text-slate-900 tabular-nums tracking-tight">{html.escape(kpi['value'])}</div>
      <div class="flex items-center gap-2 text-xs">
        <span class="{color} font-medium tabular-nums inline-flex items-center gap-1">
          {arrow} {abs(delta):.1f}{suffix}
        </span>
        <span class="text-slate-400">{html.escape(kpi['hint'])}</span>
      </div>
    </div>
    """.strip()


def yoy_summary_body(yoy: pd.DataFrame) -> str:
    def delta_chip(v: float, suffix: str = "%") -> str:
        if pd.isna(v):
            return '<span class="text-slate-300 tabular-nums">&mdash;</span>'
        color = "text-emerald-600" if v >= 0 else "text-rose-600"
        arrow = "&#9650;" if v >= 0 else "&#9660;"
        return f'<span class="{color} tabular-nums text-xs font-medium">{arrow} {abs(v):.1f}{suffix}</span>'

    def value_cell(main_html: str, delta_html: str) -> str:
        return f"""
        <div class="flex flex-col gap-0.5">
          <div class="text-sm text-slate-900 tabular-nums font-medium">{main_html}</div>
          <div>{delta_html}</div>
        </div>
        """.strip()

    header = """
    <div class="grid grid-cols-5 gap-3 text-[10px] uppercase tracking-wide text-slate-400 pb-2 border-b border-slate-100">
      <div>Year</div>
      <div>Sales</div>
      <div>Profit</div>
      <div>Margin</div>
      <div>Orders</div>
    </div>
    """
    rows = []
    for _, r in yoy.iterrows():
        margin_pct = float(r["margin"]) * 100
        rows.append(f"""
        <div class="grid grid-cols-5 gap-3 py-3 border-b border-slate-100 last:border-0 items-start">
          <div class="text-sm font-semibold text-slate-900 tabular-nums">{int(r['yr'])}</div>
          {value_cell(f"${r['sales']:,.0f}",   delta_chip(r['sales_yoy']))}
          {value_cell(f"${r['profit']:,.0f}",  delta_chip(r['profit_yoy']))}
          {value_cell(f"{margin_pct:.1f}%",   delta_chip(r['margin_yoy_pp'], suffix=' pp'))}
          {value_cell(f"{int(r['orders']):,}", delta_chip(r['orders_yoy']))}
        </div>
        """.strip())
    return header + "\n" + "\n".join(rows)


def segment_card_body(segment: pd.DataFrame) -> str:
    seg_order = ["Consumer", "Corporate", "Home Office"]
    df = segment.set_index("segment").reindex(seg_order).reset_index()

    def kv_row(label: str, value_html: str) -> str:
        return f"""
        <div class="flex items-baseline justify-between tabular-nums">
          <div class="text-xs text-slate-400">{label}</div>
          <div class="text-sm text-slate-900">{value_html}</div>
        </div>
        """.strip()

    rows = []
    for _, r in df.iterrows():
        if pd.isna(r["sales"]):
            continue
        margin_pct = float(r["margin"]) * 100
        margin_color = "text-emerald-700" if margin_pct >= 0 else "text-rose-700"
        rows.append(f"""
        <div class="py-3 border-b border-slate-100 last:border-0 flex flex-col gap-1">
          <div class="text-sm font-medium text-slate-800 mb-0.5">{html.escape(str(r['segment']))}</div>
          {kv_row("Sales",  f"${r['sales']:,.0f}")}
          {kv_row("Profit", f"${r['profit']:,.0f}")}
          {kv_row("Margin", f'<span class="{margin_color} font-medium">{margin_pct:.1f}%</span>')}
        </div>
        """.strip())
    return "\n".join(rows)


def build_html(data: dict) -> str:
    last_yr   = data["last_yr"]
    prev_yr   = data["prev_yr"]
    yoy_start = int(data["yoy"]["yr"].min())

    kpi_html      = "\n".join(kpi_card(k) for k in data["kpis"])
    trend_div     = fig_to_div(fig_trend_monthly(data["monthly"]), "trend-chart")
    subcat_div    = fig_to_div(fig_subcat_margin(data["subcat"]), "subcat-chart")
    donut_div     = fig_to_div(fig_cat_donut(data["cat_share"]), "donut-chart")
    segment_html  = segment_card_body(data["segment"])
    yoy_html      = yoy_summary_body(data["yoy"])

    monthly = data["monthly"].copy()
    monthly["month_str"] = pd.to_datetime(monthly["month"]).dt.strftime("%Y-%m-%d")
    trend_payload = {
        "months": monthly["month_str"].tolist(),
        "sales":  [float(x) for x in monthly["sales"]],
        "profit": [float(x) for x in monthly["profit"]],
    }
    trend_payload_json = json.dumps(trend_payload)

    def card(title: str, description: str, body: str, span_class: str = "") -> str:
        return f"""
        <div class="bg-white border border-slate-200 rounded-xl p-5 flex flex-col {span_class}">
          <div class="mb-4">
            <div class="text-sm font-semibold text-slate-900">{html.escape(title)}</div>
            <div class="text-xs text-slate-500 mt-0.5">{html.escape(description)}</div>
          </div>
          <div class="flex-1 min-h-0">{body}</div>
        </div>
        """.strip()

    trend_card = f"""
    <div class="bg-white border border-slate-200 rounded-xl p-5 flex flex-col lg:col-span-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-4">
        <div>
          <div class="text-sm font-semibold text-slate-900" id="trend-title">Sales &amp; Profit Trend</div>
          <div class="text-xs text-slate-500 mt-0.5" id="trend-subtitle">Monthly view across the full {yoy_start} to {last_yr} history. Sales as area, profit as line.</div>
        </div>
        <div class="inline-flex bg-slate-100 rounded-lg p-1 gap-0.5 text-xs self-start flex-shrink-0" role="tablist" aria-label="Chart view">
          <button id="view-timeline" class="view-btn px-3 py-1 rounded-md font-medium text-slate-500 hover:text-slate-900" data-active="true">Full historical</button>
          <button id="view-yoy"      class="view-btn px-3 py-1 rounded-md font-medium text-slate-500 hover:text-slate-900">Latest year overlay</button>
        </div>
      </div>
      <div class="flex-1 min-h-0">{trend_div}</div>
    </div>
    """.strip()

    subcat_card = card(
        "Profit Margin by Subcategory",
        "Lifetime margin per subcategory. Sorted ascending, loss-makers in red.",
        subcat_div, "lg:col-span-2",
    )
    donut_card = card(
        "Sales Share by Category",
        "Lifetime revenue concentration across product categories.",
        donut_div, "lg:col-span-1",
    )
    yoy_card = card(
        "Year on Year Summary",
        "Annual totals with growth vs prior year.",
        yoy_html, "lg:col-span-4",
    )
    segment_card = card(
        "Customer Segments",
        "Lifetime sales, profit, and margin by segment.",
        segment_html, "lg:col-span-1",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Sales Performance Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{ font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif; }}
    body {{ font-family: 'Inter', ui-sans-serif, system-ui, sans-serif; }}
    .tabular-nums {{ font-variant-numeric: tabular-nums; }}
    .view-btn[data-active="true"] {{
      background-color: white;
      color: #0f172a;
      box-shadow: 0 1px 2px rgba(15,23,42,0.08);
    }}
  </style>
</head>
<body class="bg-slate-50 min-h-screen">
  <div class="max-w-7xl mx-auto px-6 py-8">
    <header class="mb-8">
      <div class="flex items-baseline justify-between flex-wrap gap-2">
        <div>
          <h1 class="text-2xl font-semibold text-slate-900 tracking-tight">Sales Performance Dashboard</h1>
          <p class="text-sm text-slate-500 mt-1">Executive view of sales, margin, and category performance. KPI values are lifetime totals ({yoy_start} to {last_yr}). Latest recorded year ({last_yr} &amp; {prev_yr}) used as delta benchmark.</p>
        </div>
        <div class="text-xs text-slate-400 tabular-nums"> </div>
      </div>
    </header>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
      {kpi_html}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {trend_card}
      {subcat_card}
      {donut_card}
      {segment_card}
      {yoy_card}
    </div>

    <footer class="text-xs text-slate-400 mt-8 text-center">
      Built with Plotly and Tailwind.
    </footer>
  </div>

  <script>
    const TREND_DATA    = {trend_payload_json};
    const OVERLAY_YEARS = [{prev_yr}, {last_yr}];

    const chartDiv    = document.getElementById('trend-chart');
    const title       = document.getElementById('trend-title');
    const subtitle    = document.getElementById('trend-subtitle');
    const btnTimeline = document.getElementById('view-timeline');
    const btnYoy      = document.getElementById('view-yoy');

    const LAYOUT_BASE = {{
      plot_bgcolor: 'white',
      paper_bgcolor: 'white',
      font: {{ family: 'Inter, ui-sans-serif, system-ui, sans-serif', color: '#0f172a', size: 12 }},
      hoverlabel: {{ bgcolor: 'white', bordercolor: '#e2e8f0', font: {{ family: 'Inter, sans-serif', size: 12 }} }},
      height: 320,
      showlegend: true,
    }};
    const AXIS_CLEAN = {{ showline: false, ticks: '', showgrid: true, gridcolor: '#e2e8f0', griddash: 'dash', zeroline: false, tickfont: {{ color: '#64748b', size: 11 }} }};
    const MONTH_TICKS = {{
      tickmode: 'array',
      tickvals: [1,2,3,4,5,6,7,8,9,10,11,12],
      ticktext: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    }};

    function layoutTimeline() {{
      return Object.assign({{}}, LAYOUT_BASE, {{
        margin: {{ l: 60, r: 60, t: 20, b: 30 }},
        legend: {{ orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'left', x: 0, bgcolor: 'rgba(0,0,0,0)' }},
        xaxis: Object.assign({{}}, AXIS_CLEAN, {{ showgrid: false }}),
        yaxis: Object.assign({{}}, AXIS_CLEAN, {{ tickprefix: '$', tickformat: ',.0f' }}),
        yaxis2: {{ overlaying: 'y', side: 'right', showgrid: false, tickprefix: '$', tickformat: ',.0f', tickfont: {{ color: '#64748b', size: 11 }}, showline: false }},
      }});
    }}

    function layoutYoY() {{
      return Object.assign({{}}, LAYOUT_BASE, {{
        margin: {{ l: 60, r: 20, t: 40, b: 40 }},
        legend: {{ orientation: 'h', yanchor: 'bottom', y: -0.18, xanchor: 'center', x: 0.5, bgcolor: 'rgba(0,0,0,0)' }},
        xaxis:  Object.assign({{}}, AXIS_CLEAN, MONTH_TICKS, {{ domain: [0.00, 0.46], anchor: 'y',  showgrid: false }}),
        yaxis:  Object.assign({{}}, AXIS_CLEAN, {{ anchor: 'x',  tickprefix: '$', tickformat: ',.0f' }}),
        xaxis2: Object.assign({{}}, AXIS_CLEAN, MONTH_TICKS, {{ domain: [0.54, 1.00], anchor: 'y2', showgrid: false }}),
        yaxis2: Object.assign({{}}, AXIS_CLEAN, {{ anchor: 'x2', tickprefix: '$', tickformat: ',.0f' }}),
        annotations: [
          {{ x: 0.23, y: 1.10, xref: 'paper', yref: 'paper', xanchor: 'center', text: '<b>Sales</b>',  showarrow: false, font: {{ size: 12, color: '#0f172a' }} }},
          {{ x: 0.77, y: 1.10, xref: 'paper', yref: 'paper', xanchor: 'center', text: '<b>Profit</b>', showarrow: false, font: {{ size: 12, color: '#0f172a' }} }},
        ],
      }});
    }}

    function setActive(activeEl, otherEl) {{
      activeEl.setAttribute('data-active', 'true');
      otherEl.removeAttribute('data-active');
    }}

    function renderTimeline() {{
      Plotly.react(chartDiv, [
        {{
          x: TREND_DATA.months, y: TREND_DATA.sales,
          type: 'scatter', mode: 'lines', name: 'Sales',
          line: {{ color: '#2563eb', width: 2.5, shape: 'spline', smoothing: 0.6 }},
          fill: 'tozeroy', fillcolor: 'rgba(37, 99, 235, 0.10)',
          hovertemplate: '<b>%{{x}}</b><br>Sales: $%{{y:,.0f}}<extra></extra>',
        }},
        {{
          x: TREND_DATA.months, y: TREND_DATA.profit,
          type: 'scatter', mode: 'lines', name: 'Profit',
          line: {{ color: '#10b981', width: 2, shape: 'spline', smoothing: 0.6 }},
          yaxis: 'y2',
          hovertemplate: '<b>%{{x}}</b><br>Profit: $%{{y:,.0f}}<extra></extra>',
        }},
      ], layoutTimeline(), {{ displayModeBar: false, responsive: true }});
      title.textContent = 'Sales & Profit Trend';
      subtitle.textContent = 'Full monthly history from ' + TREND_DATA.months[0].slice(0,4) + ' to ' + TREND_DATA.months[TREND_DATA.months.length-1].slice(0,4) + '. Sales as area, profit as line.';
    }}

    function renderYoY() {{
      const perYear = {{}};
      TREND_DATA.months.forEach((m, i) => {{
        const d = new Date(m);
        const yr = d.getUTCFullYear();
        if (!OVERLAY_YEARS.includes(yr)) return;
        const mo = d.getUTCMonth() + 1;
        if (!perYear[yr]) perYear[yr] = {{ months: [], sales: [], profit: [] }};
        perYear[yr].months.push(mo);
        perYear[yr].sales.push(TREND_DATA.sales[i]);
        perYear[yr].profit.push(TREND_DATA.profit[i]);
      }});
      const years = Object.keys(perYear).map(Number).sort();
      const YEAR_COLOURS = {{ prior: '#94a3b8', latest: '#2563eb' }};

      const traces = [];
      years.forEach((yr) => {{
        const isLatest = (yr === years[years.length - 1]);
        const colour   = isLatest ? YEAR_COLOURS.latest : YEAR_COLOURS.prior;
        traces.push({{
          x: perYear[yr].months, y: perYear[yr].sales,
          type: 'scatter', mode: 'lines+markers',
          name: String(yr), legendgroup: String(yr), showlegend: true,
          line: {{ color: colour, width: 2.5, shape: 'spline', smoothing: 0.6 }},
          marker: {{ size: 5 }},
          xaxis: 'x', yaxis: 'y',
          hovertemplate: `<b>${{yr}} · Month %{{x}}</b><br>Sales: $%{{y:,.0f}}<extra></extra>`,
        }});
        traces.push({{
          x: perYear[yr].months, y: perYear[yr].profit,
          type: 'scatter', mode: 'lines+markers',
          name: String(yr), legendgroup: String(yr), showlegend: false,
          line: {{ color: colour, width: 2.5, shape: 'spline', smoothing: 0.6 }},
          marker: {{ size: 5 }},
          xaxis: 'x2', yaxis: 'y2',
          hovertemplate: `<b>${{yr}} · Month %{{x}}</b><br>Profit: $%{{y:,.0f}}<extra></extra>`,
        }});
      }});

      Plotly.react(chartDiv, traces, layoutYoY(), {{ displayModeBar: false, responsive: true }});
      title.textContent = 'Sales & Profit: ' + OVERLAY_YEARS.join(' vs ');
      subtitle.textContent = 'Monthly sales and profit for ' + OVERLAY_YEARS.join(' and ') + ', side-by-side overlays on a shared Jan to Dec axis.';
    }}

    btnTimeline.addEventListener('click', () => {{ setActive(btnTimeline, btnYoy); renderTimeline(); }});
    btnYoy.addEventListener('click',      () => {{ setActive(btnYoy, btnTimeline); renderYoY(); }});

    renderTimeline();
  </script>
</body>
</html>
"""


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found at {DB_PATH}. Run ../load.py first.")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    data = query_all(con)
    con.close()

    html_text = build_html(data)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html_text, encoding="utf-8")

    print(f"Wrote {OUT_HTML}")
    print(f"Size: {OUT_HTML.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
