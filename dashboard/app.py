"""
PROMETHEUS Risk Platform — Premium Light Dashboard
Aesthetic: Refined Institutional Light · Warm whites · Deep slate · Crimson accents
Typography: DM Serif Display (titles) · JetBrains Mono (numbers) · Inter (body)
"""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
from datetime import date

from backend.main import PrometheusRunner
from backend.data_sources.persistence import (
    read_capital_history, read_rwa_by_month, read_rwa_by_year,
    read_portfolio_trend, read_mtm_history_for_portfolio,
)

st.set_page_config(
    page_title="PROMETHEUS · Risk Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:wght@400;600;700&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --cream:        #fafaf8;
  --white:      #ffffff;
  --stone-50:     #f7f6f3;
  --stone-100:    #eeebe5;
  --stone-200:    #dedad1;
  --stone-300:    #c9c2b6;
  --slate-500:  #64748b;
  --slate-600:  #475569;
  --slate-700:  #334155;
  --slate-900:  #0f172a;
  --crimson:      #991b1b;
  --crimson-lt:   #c53030;
  --crimson-bg:   rgba(153,27,27,0.055);
  --blue:         #1e40af;
  --blue-lt:    #3b82f6;
  --blue-bg:      rgba(30,64,175,0.055);
  --green:        #166534;
  --green-bg:     rgba(22,101,52,0.065);
  --amber:        #92400e;
  --amber-bg:     rgba(146,64,14,0.065);
  --teal:       #0f766e;
  --indigo:       #3730a3
  --teal-bg:      rgba(15,118,110,0.065);
  --gold:         #78350f;
  --border:       #dedad1
  --border-light: #eeebe5;
  --shadow-xs:    0 1px 2px rgba(15,23,42,0.04)
  --shadow-sm:    0 1px 3px rgba(15,23,42,0.07), 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md:    0 4px 14px rgba(15,23,42,0.09), 0 2px 4px rgba(15,23,42,0.04);
}

/* ── Global ── */
.stApp { background: var(--cream) !important; font-family: 'Nunito Sans', sans-serif; }
.main .block-container { padding: 1.8rem 2.2rem 3rem !important; max-width: 100% !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--white) !important;
  border-right: 1px solid var(--border) !important;
  box-shadow: 2px 0 8px rgba(15,23,42,0.04) !important;
}
section[data-testid="stSidebar"] .block-container { padding: 1.6rem 1.2rem !important; }

/* ── Text ── */
h1,h2,h3 { color: var(--slate-900) !important; }
p,li      { color: var(--slate-600) !important; }
label     { color: var(--slate-600) !important; }
.stCaption, [data-testid="stCaptionContainer"] { color: var(--slate-500) !important; }

/* ── Native widgets ── */
.stSelectbox label, .stRadio label, .stDateInput label {
  color: var(--slate-500) !important; font-size: 0.73rem !important;
  text-transform: uppercase; letter-spacing: 0.07em; font-weight: 500;
}
.stSelectbox > div > div {
  background: var(--white) !important; border: 1px solid var(--border) !important;
  color: var(--slate-700) !important; border-radius: 8px !important;
  box-shadow: var(--shadow-sm) !important;
}
.stDateInput input {
  background: var(--white) !important; border: 1px solid var(--border) !important;
  color: var(--slate-700) !important; border-radius: 8px !important;
}
.stRadio div[role="radiogroup"] label { color: var(--slate-600) !important; font-size: 0.86rem !important; }
.stButton > button {
  background: var(--slate-900) !important; color: #fff !important;
  border: none !important; border-radius: 8px !important;
  font-family: 'Nunito Sans', sans-serif !important; font-weight: 500 !important;
  letter-spacing: 0.02em !important; padding: 0.5rem 1.4rem !important;
  box-shadow: var(--shadow-sm) !important; transition: all 0.15s !important;
}
.stButton > button:hover { background: var(--slate-700) !important; }
.stDownloadButton > button {
  background: var(--white) !important; border: 1.5px solid var(--slate-300) !important;
  color: var(--slate-700) !important; border-radius: 8px !important;
}

/* ── Metrics ── */
[data-testid="stMetricValue"] { color: var(--slate-900) !important; font-family: 'JetBrains Mono', monospace !important; }
[data-testid="stMetricLabel"] { color: var(--slate-500) !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.05em; }

/* ── Dividers ── */
hr { border-color: var(--stone-200) !important; margin: 1rem 0 !important; }

/* ── Info/Success/Error banners ── */
.stAlert { border-radius: 8px !important; border-left-width: 3px !important; }

/* ── Dataframe ── */
.stDataFrame { border-radius: 10px !important; overflow: hidden; }
[data-testid="stDataFrameResizable"] { border-radius: 10px !important; }

/* ── Spinner accent ── */
.stSpinner > div { border-top-color: var(--crimson) !important; }

/* ── Custom Components ── */
.wordmark {
  font-family: 'DM Serif Display', serif;
  font-size: 1.52rem; font-weight: 400;
  color: var(--slate-900); letter-spacing: 0.01em; line-height: 1.1;
}
.wordmark span { color: var(--crimson); font-style: italic; }
.submark {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem; color: var(--stone-400);
  letter-spacing: 0.19em; text-transform: uppercase; margin-top: 0;
  font-weight: 300;
}

.page-title {
  font-family: 'DM Serif Display', serif;
  font-size: 2.1rem; font-weight: 400;
  color: var(--slate-900); line-height: 1.05; margin-bottom: 0;
  letter-spacing: -0.01em;
}
.page-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem; color: var(--slate-500);
  letter-spacing: 0.11em; text-transform: uppercase; margin-bottom: 1.8rem;
  font-weight: 300;
}

/* KPI card */
.kpi {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 20px 16px;
  box-shadow: var(--shadow-sm);
  position: relative; overflow: hidden;
  transition: box-shadow 0.18s ease, transform 0.18s ease;
}
.kpi:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
.kpi::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--crimson) 0%, rgba(153,27,27,0.12) 65%, transparent 100%);
  border-radius: 12px 12px 0 0;
}
.kpi-sup  { font-family:'JetBrains Mono',monospace; font-size:0.60rem; font-weight:500; letter-spacing:0.15em; text-transform:uppercase; color:var(--slate-400); margin-bottom:5px; }
.kpi-val  { font-family:'JetBrains Mono',monospace; font-size:1.82rem; font-weight:600; color:var(--slate-900); line-height:1.05; margin-bottom:4px; letter-spacing:-0.01em; }
.kpi-lbl  { font-family:'Nunito Sans',sans-serif; font-size:0.78rem; color:var(--slate-500); margin-bottom:8px; font-weight:400; line-height:1.4; }
.kpi-tag  { display:inline-block; font-family:'JetBrains Mono',monospace; font-size:0.64rem; font-weight:500; padding:2px 8px; border-radius:5px; letter-spacing:0.03em; }
.t-ok     { background:var(--green-bg);  color:var(--green);   border:1px solid rgba(22,101,52,0.14); }
.t-warn   { background:var(--amber-bg);  color:var(--amber);   border:1px solid rgba(146,64,14,0.14); }
.t-bad    { background:var(--crimson-bg);color:var(--crimson); border:1px solid rgba(153,27,27,0.14); }
.t-blue   { background:var(--blue-bg);   color:var(--blue);    border:1px solid rgba(30,64,175,0.14); }
.t-teal   { background:var(--teal-bg);   color:var(--teal);    border:1px solid rgba(15,118,110,0.14); }
.t-stone  { background:var(--stone-100); color:var(--slate-600);border:1px solid var(--border); }

/* Section header */
.sh { display:flex; align-items:center; gap:14px; margin:28px 0 14px; }
.sh-line { flex:1; height:1px; background:var(--stone-200); }
.sh-text { font-family:'JetBrains Mono',monospace; font-size:0.63rem; font-weight:400; color:var(--slate-400); letter-spacing:0.16em; text-transform:uppercase; white-space:nowrap; }

/* Limit row */
.lrow {
  display:grid; grid-template-columns:210px 1fr 80px 80px 80px 90px;
  gap:10px; align-items:center;
  padding:10px 14px;
  background:var(--white); border:1px solid var(--border);
  border-radius:8px; margin-bottom:6px;
  box-shadow:var(--shadow-sm);
}
.ln  { font-size:0.83rem; font-weight:500; color:var(--slate-700); }
.lt  { font-family:'JetBrains Mono',monospace; font-size:0.62rem; color:var(--slate-400); margin-top:2px; }
.lv  { font-family:'JetBrains Mono',monospace; font-size:0.80rem; color:var(--slate-600); text-align:right; }

/* Regulatory tag sidebar */
.reg-row { display:flex; justify-content:space-between; padding:5px 8px;
  font-size:0.75rem; border-bottom:1px solid var(--stone-100); }

/* Floor banner */
.floor-ok {
  background: var(--green-bg); border:1px solid rgba(22,101,52,0.18);
  border-radius:10px; padding:12px 18px; font-size:0.82rem; color:var(--green);
  font-family:'Nunito Sans',sans-serif; font-weight:500;
}
.floor-warn {
  background: var(--crimson-bg); border:1px solid rgba(153,27,27,0.18);
  border-radius:10px; padding:12px 18px; font-size:0.82rem; color:var(--crimson);
  font-family:'Nunito Sans',sans-serif; font-weight:500;
}
</style>
""", unsafe_allow_html=True)

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "blue":    "#1e40af",
    "indigo":  "#3730a3",
    "teal":    "#0f766e",
    "green":   "#166534",
    "amber":   "#92400e",
    "red":     "#991b1b",
    "crimson": "#7f1d1d",
    "slate":   "#64748b",
    "gold":    "#78350f",
}
CHART_COLS = [C["blue"], C["indigo"], C["teal"], C["gold"], C["amber"], C["green"], C["slate"]]

def PLOT(h=360, t=10):
    return dict(
        paper_bgcolor="#ffffff", plot_bgcolor="#f7f6f3",
        font_color="#64748b", font_family="JetBrains Mono", font_size=10,
        height=h, margin=dict(l=24, r=24, t=t, b=24),
        xaxis=dict(gridcolor="#dedad1", linecolor="#dedad1", tickcolor="#dedad1", zeroline=False,
                   tickfont=dict(family="JetBrains Mono", size=9)),
        yaxis=dict(gridcolor="#dedad1", linecolor="#dedad1", tickcolor="#dedad1", zeroline=False,
                   tickfont=dict(family="JetBrains Mono", size=9)),
        hoverlabel=dict(bgcolor="#ffffff", font_color="#334155",
                        font_family="JetBrains Mono", font_size=11, bordercolor="#dedad1"),
    )

def LEG(orientation="h", y=1.08, x=0):
    return dict(bgcolor="rgba(0,0,0,0)", font_size=10,
                orientation=orientation, y=y, x=x)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_bn(v):
    v = float(v)
    if abs(v) >= 1e9: return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"
def fmt_pct(v): return f"{float(v)*100:.2f}%"

def sec(label):
    st.markdown(
        f'<div class="sh"><div class="sh-line"></div>'
        f'<div class="sh-text">{label}</div>'
        f'<div class="sh-line"></div></div>', unsafe_allow_html=True)

def kpi(col, sup, val, lbl, tag, tag_cls="t-ok"):
    with col:
        st.markdown(
            f'<div class="kpi"><div class="kpi-sup">{sup}</div>'
            f'<div class="kpi-val">{val}</div><div class="kpi-lbl">{lbl}</div>'
            f'<span class="kpi-tag {tag_cls}">{tag}</span></div>',
            unsafe_allow_html=True)

# ── Gauge — light ─────────────────────────────────────────────────────────────
def gauge(value, minimum, label):
    pct  = value * 100; minp = minimum * 100; hi = max(pct * 1.6, minp * 2.8)
    col  = C["green"] if pct >= minp * 1.15 else (C["amber"] if pct >= minp else C["red"])
    fig  = go.Figure(go.Indicator(
        mode="gauge+number", value=pct,
        number={"suffix": "%", "font": {"size": 28, "color": col, "family": "JetBrains Mono"}},
        title={"text": label, "font": {"size": 11, "color": "#64748b", "family": "Inter"}},
        gauge={
            "axis": {"range": [0, hi], "tickcolor": "#cfc8bd", "tickfont": {"color": "#cfc8bd", "size": 9}},
            "bar":  {"color": col, "thickness": 0.20},
            "bgcolor": "#f8f7f4", "bordercolor": "#e4dfd7",
            "steps": [
                {"range": [0, minp],        "color": "rgba(185,28,28,0.07)"},
                {"range": [minp, minp*1.5],  "color": "rgba(180,83,9,0.06)"},
                {"range": [minp*1.5, hi],    "color": "rgba(21,128,61,0.07)"},
            ],
            "threshold": {"line": {"color": C["red"], "width": 1.5}, "thickness": 0.75, "value": minp},
        }
    ))
    fig.update_layout(height=195, margin=dict(l=8, r=8, t=30, b=5),
                      paper_bgcolor="#ffffff", font_color="#64748b")
    return fig

@st.cache_data(ttl=300, show_spinner=False)
def load_data(d):
    return PrometheusRunner(sa_cva_approved=True).run_daily(date.fromisoformat(d))

@st.cache_data(ttl=300, show_spinner=False)
def load_history(days=90):
    return read_capital_history(days)

@st.cache_data(ttl=300, show_spinner=False)
def load_rwa_by_month():
    return read_rwa_by_month(years=2)

@st.cache_data(ttl=300, show_spinner=False)
def load_rwa_by_year():
    return read_rwa_by_year()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="wordmark">⬡ PROMET<span>H</span>EUS</div>', unsafe_allow_html=True)
    st.markdown('<div class="submark">Basel III/IV · Risk Intelligence</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    run_date = st.date_input("Valuation Date", value=date.today(), max_value=date.today())
    st.markdown(
        f'<div style="font-family:JetBrains Mono;font-size:0.65rem;color:#94a3b8;'
        f'margin-top:-8px;margin-bottom:14px">{run_date.strftime("%d %b %Y")}</div>',
        unsafe_allow_html=True)

    page = st.radio("", [
        "Capital Dashboard", "Derivative Portfolios", "Banking Book",
        "Market Risk (FRTB)", "IMM Exposure Profiles",
        "CVA Risk", "CCP Exposure", "Operational Risk",
        "Risk Limits", "Backtesting", "Reports",
        "Market Calibration",
    ], label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="font-family:JetBrains Mono;font-size:0.62rem;color:#94a3b8;'
        'letter-spacing:0.12em;text-transform:uppercase;padding:0 8px;'
        'margin-bottom:8px">Regulatory Basis</div>',
        unsafe_allow_html=True)
    for code, desc in [
        ("CRE52","SA-CCR"),("CRE53","IMM / MC"),("CRE31","A-IRB"),
        ("MAR21-33","FRTB SBM+IMA"),("MAR50","CVA Risk"),
        ("CRE54","CCP Exposure"),("RBC20","Capital Agg."),
    ]:
        st.markdown(
            f'<div class="reg-row">'
            f'<span style="font-family:JetBrains Mono;color:{C["crimson"]};'
            f'font-size:0.68rem;font-weight:500">{code}</span>'
            f'<span style="color:#94a3b8;font-size:0.75rem">{desc}</span></div>',
            unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────────────────────────
with st.spinner(""):
    data = load_data(run_date.isoformat())

cap = data["capital_summary"]; bt  = data["backtesting"]
drv = data["derivative"];      bbk = data["banking_book"]
cva = data.get("cva", {});     ccp = data.get("ccp", {})

# ══════════════════════════════════════════════════════════════════════════════
# 1 · CAPITAL DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Capital Dashboard":
    st.markdown('<div class="page-title">Capital Dashboard</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-sub">RBC20 · Five-Part RWA · {run_date.strftime("%d %b %Y")}</div>',
                unsafe_allow_html=True)

    zone = bt.get("traffic_light", "GREEN")
    ztag = {"GREEN":"t-ok","AMBER":"t-warn","RED":"t-bad"}.get(zone,"t-ok")
    c1,c2,c3,c4,c5 = st.columns(5)
    kpi(c1,"CET1 Ratio",     fmt_pct(cap["cet1_ratio"]),      "Common Equity Tier 1",   "≥ 4.5% min", "t-ok" if cap["cet1_ratio"]>0.07 else "t-bad")
    kpi(c2,"Tier 1 Ratio",   fmt_pct(cap["tier1_ratio"]),     "Tier 1 Capital",          "≥ 6.0% min", "t-ok" if cap["tier1_ratio"]>0.08 else "t-bad")
    kpi(c3,"Total Capital",  fmt_pct(cap["total_cap_ratio"]),  "Total Capital Ratio",     "≥ 8.0% min", "t-ok" if cap["total_cap_ratio"]>0.10 else "t-bad")
    kpi(c4,"Total RWA",      fmt_bn(cap["rwa_total"]),         "Risk-Weighted Assets",    "5-Part RBC20","t-blue")
    kpi(c5,"Backtesting",
        {"GREEN":"● GREEN","AMBER":"● AMBER","RED":"● RED"}.get(zone,"● GREEN"),
        "MAR99 Traffic Light", f"{bt.get('exceptions',0)} exceptions", ztag)

    st.markdown("")
    g1,g2,g3 = st.columns(3)
    with g1: st.plotly_chart(gauge(cap["cet1_ratio"],0.045,"CET1 Ratio"))
    with g2: st.plotly_chart(gauge(cap["tier1_ratio"],0.060,"Tier 1 Ratio"))
    with g3: st.plotly_chart(gauge(cap["total_cap_ratio"],0.080,"Total Capital"))

    sec("RISK-WEIGHTED ASSETS — FIVE-PART BREAKDOWN (RBC20.9)")
    comps = ["Credit (A-IRB)","CCR (SA-CCR/IMM)","Market (FRTB)","CVA (MAR50)","CCP (CRE54)"]
    vals  = [cap["rwa_credit"],cap["rwa_ccr"],cap["rwa_market"],
             cap.get("rwa_cva",0),cap.get("rwa_ccp",0)]
    left, right = st.columns(2)
    with left:
        fig_pie = go.Figure(go.Pie(
            labels=comps, values=vals,
            marker=dict(colors=CHART_COLS, line=dict(color="#ffffff", width=2)),
            hole=0.50,
            textinfo="percent",
            textfont=dict(family="JetBrains Mono", size=10),
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            customdata=[fmt_bn(v) for v in vals],
        ))
        fig_pie.add_annotation(
            text=fmt_bn(sum(vals)), x=0.5, y=0.5, showarrow=False,
            font=dict(family="JetBrains Mono", size=15, color="#0f172a"))
        fig_pie.update_layout(**PLOT(340, 10), showlegend=True,
                               legend=LEG("v", 0.5, 1.02))
        st.plotly_chart(fig_pie)
    with right:
        vbar = [v/1e6 for v in vals]
        fig_bar = go.Figure(go.Bar(
            y=comps, x=vbar, orientation="h",
            marker=dict(color=CHART_COLS, opacity=0.85),
            text=[f"  {fmt_bn(v)}" for v in vals],
            textposition="outside",
            textfont=dict(family="JetBrains Mono", size=10, color="#64748b"),
            cliponaxis=False,
        ))
        fig_bar.update_layout(**PLOT(340, 10), xaxis_title="USD Millions")
        fig_bar.update_xaxes(range=[0, max(vbar)*1.30])
        st.plotly_chart(fig_bar)

    sec("CAPITAL STACK")
    sc1,sc2,sc3,sc4 = st.columns(4)
    for col,acc,val,ratio,minr,colour in [
        (sc1,"CET1 Capital",   cap["cet1_capital"],   cap["cet1_ratio"],     0.045, C["blue"]),
        (sc2,"Tier 1 Capital", cap["tier1_capital"],   cap["tier1_ratio"],    0.060, C["indigo"]),
        (sc3,"Total Capital",  cap["total_capital"],   cap["total_cap_ratio"],0.080, C["teal"]),
        (sc4,"Min Req (8%)",   cap["rwa_total"]*0.08, None, None, C["red"]),
    ]:
        rt  = f" · {ratio*100:.1f}%" if ratio else ""
        mn  = f"Min {minr*100:.1f}%" if minr else "Regulatory floor"
        cls = ("t-ok" if ratio and ratio>=minr else ("t-bad" if ratio else "t-warn"))
        with col:
            st.markdown(
                f'<div class="kpi" style="border-top:2px solid {colour}">'
                f'<div class="kpi-sup">{acc}</div>'
                f'<div class="kpi-val" style="color:{colour}">{fmt_bn(val)}</div>'
                f'<div class="kpi-lbl">{acc}{rt}</div>'
                f'<span class="kpi-tag {cls}">{mn}</span></div>',
                unsafe_allow_html=True)

    st.markdown("")
    floor_rwa = cap.get("rwa_floor", cap.get("rwa_sa_based", cap["rwa_total"])*0.725)
    pre_floor = cap.get("rwa_total_pre_floor", cap["rwa_total"])
    if cap.get("floor_triggered"):
        st.markdown(
            f'<div class="floor-warn">⚠  Output Floor Triggered (RBC20.11) — '
            f'Pre-floor {fmt_bn(pre_floor)} &lt; Floor {fmt_bn(floor_rwa)}</div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="floor-ok">✓  Output Floor not triggered — '
            f'Pre-floor {fmt_bn(pre_floor)} ≥ Floor {fmt_bn(floor_rwa)}'
            f'<span style="color:{C["teal"]};margin-left:14px;'
            f'font-family:JetBrains Mono;font-size:0.68rem">'
            f'CVA excluded from floor base · CAP10 FAQ1</span></div>',
            unsafe_allow_html=True)

    # ── 90-day historical trends ───────────────────────────────────────────────
    hist_df = load_history(90)
    if not hist_df.empty:
        hist_df["run_date"] = pd.to_datetime(hist_df["run_date"])
        hist_df = hist_df.sort_values("run_date")
        sec("RWA TREND — 90 TRADING DAYS")
        fig_trend = go.Figure()
        _rwa_series = [("rwa_credit","Credit",C["blue"]),("rwa_ccr","CCR",C["teal"]),
                       ("rwa_market","Market",C["gold"]),("rwa_cva","CVA",C["amber"]),
                       ("rwa_ccp","CCP",C["slate"])]
        for col,label,colour in _rwa_series:
            if col in hist_df.columns:
                fig_trend.add_trace(go.Scatter(x=hist_df["run_date"],y=hist_df[col]/1e6,
                    name=label,stackgroup="rwa",mode="none",fillcolor=colour,opacity=0.80))
        if "rwa_total" in hist_df.columns:
            fig_trend.add_trace(go.Scatter(x=hist_df["run_date"],y=hist_df["rwa_total"]/1e6,
                name="Total",line=dict(color=C["crimson"],width=1.5,dash="dot")))
        fig_trend.update_layout(**PLOT(320,10),yaxis_title="USD Millions",legend=LEG())
        st.plotly_chart(fig_trend)
        if "cet1_ratio" in hist_df.columns:
            fig_c = go.Figure()
            fig_c.add_trace(go.Scatter(x=hist_df["run_date"],y=hist_df["cet1_ratio"]*100,
                name="CET1",line=dict(color=C["blue"],width=2),
                fill="tozeroy",fillcolor="rgba(30,64,175,0.07)"))
            fig_c.add_hline(y=4.5,line_dash="dash",line_color=C["red"],annotation_text="Min 4.5%")
            fig_c.update_layout(**PLOT(200,10),yaxis_title="CET1 %",legend=LEG())
            st.plotly_chart(fig_c)
        sec("RWA BY YEAR / MONTH")
        monthly = load_rwa_by_month()
        if not monthly.empty:
            _m = monthly.copy()
            for c in ["avg_rwa_total","max_rwa_total"]:
                if c in _m.columns: _m[c] = _m[c].apply(fmt_bn)
            if "avg_cet1_ratio" in _m.columns:
                _m["avg_cet1_ratio"] = _m["avg_cet1_ratio"].apply(lambda x: f"{float(x)*100:.2f}%")
            _m.columns = [c.replace("_"," ").title() for c in _m.columns]
            st.dataframe(_m, width="stretch", hide_index=True)
        yearly = load_rwa_by_year()
        if not yearly.empty:
            _y = yearly.copy()
            for c in ["avg_rwa_total","min_rwa_total","max_rwa_total"]:
                if c in _y.columns: _y[c] = _y[c].apply(fmt_bn)
            for c in ["avg_cet1_ratio","min_cet1_ratio"]:
                if c in _y.columns: _y[c] = _y[c].apply(lambda x: f"{float(x)*100:.2f}%")
            _y.columns = [c.replace("_"," ").title() for c in _y.columns]
            sec("ANNUAL SUMMARY"); st.dataframe(_y, width="stretch", hide_index=True)
    else:
        sec("HISTORICAL TRENDS")
        st.info("No historical data yet. Run the platform on multiple days to populate time-series.")

# ══════════════════════════════════════════════════════════════════════════════
# 2 · DERIVATIVE PORTFOLIOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Derivative Portfolios":
    st.markdown('<div class="page-title">Derivative Portfolios</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">SA-CCR (CRE52) · IMM (CRE53) · Fallback Routing</div>',
                unsafe_allow_html=True)

    pid  = st.selectbox("Portfolio",[p["portfolio_id"] for p in drv],label_visibility="collapsed")
    port = next(p for p in drv if p["portfolio_id"]==pid)
    imm  = port.get("imm") or {}
    c1,c2,c3,c4,c5 = st.columns(5)
    kpi(c1,"Gross Notional",  fmt_bn(port["gross_notional"]),          "Total notional",       "Pre-netting",   "t-stone")
    kpi(c2,"SA-CCR EAD",      fmt_bn(port["saccr"]["ead"]),            "Exposure at Default",  "CRE52 α=1.4",   "t-blue")
    ead_gross = imm.get("ead_imm", 0)
    ead_csa   = imm.get("ead_imm_csa", ead_gross)
    csa_red   = imm.get("csa_reduction_pct", 0)
    kpi(c3,"IMM EAD (Gross)", fmt_bn(ead_gross),                       "Before CSA benefit",   "CRE53 uncoll.", "t-stone")
    kpi(c4,"IMM EAD (CSA)",   fmt_bn(ead_csa),                         "After CSA: VM+IM+MPOR","CRE53.22",      "t-ok" if csa_red>10 else "t-stone")
    kpi(c5,"CCR RWA",         fmt_bn(port["rwa_ccr"]),                 "Credit RWA (CCR)",     "CRE51.13",      "t-blue")

    sec("SA-CCR ADD-ON BY ASSET CLASS")
    addons={"Interest Rate":port["saccr"]["addon_ir"],"FX":port["saccr"]["addon_fx"],
            "Credit":port["saccr"]["addon_credit"],"Equity":port["saccr"]["addon_equity"],
            "Commodity":port["saccr"]["addon_commodity"]}
    fig_add = go.Figure(go.Bar(
        x=list(addons.keys()), y=[v/1e6 for v in addons.values()],
        marker=dict(color=CHART_COLS[:5], opacity=0.85),
        text=[f"${v/1e6:.2f}M" for v in addons.values()],
        textposition="outside", textfont=dict(family="JetBrains Mono",size=10,color="#64748b")))
    fig_add.update_layout(**PLOT(280,10), yaxis_title="USD Millions")
    st.plotly_chart(fig_add)

    # ── CSA Benefit Summary ──────────────────────────────────────────────────
    if imm:
        vm_r  = imm.get("vm_received",  0)
        im_p  = imm.get("im_posted",    0)
        rc_c  = imm.get("rc_csa",       0)
        mpor_s= imm.get("mpor_scale",   1.0)
        sec("CSA BENEFIT DECOMPOSITION — CRE53.22")
        cb1,cb2,cb3,cb4 = st.columns(4)
        kpi(cb1,"VM Received",    fmt_bn(vm_r),          "Variation Margin",      "Daily call",       "t-ok")
        kpi(cb2,"IM Posted",      fmt_bn(im_p),          "Initial Margin (SIMM)", "Segregated",        "t-ok")
        kpi(cb3,"RC after CSA",   fmt_bn(rc_c),          "Net current exposure",  "CRE52.18 formula",  "t-blue" if rc_c>0 else "t-ok")
        kpi(cb4,"EAD Reduction",  f"{csa_red:.1f}%",     "Gross→CSA benefit",     "MPOR scale: {:.3f}".format(mpor_s), "t-ok" if csa_red>20 else "t-warn")
        st.markdown("")

    # ── MTM day-on-day ──────────────────────────────────────────────────────
    _mtm_hist = read_mtm_history_for_portfolio(pid, days=7)
    if not _mtm_hist.empty and len(_mtm_hist["run_date"].unique()) > 1:
        sec("TRADE MTM — DAY-ON-DAY")
        _mtm_hist["run_date"] = pd.to_datetime(_mtm_hist["run_date"])
        _pivot = _mtm_hist.pivot_table(index="trade_id",columns="run_date",values="mtm",aggfunc="sum")
        _pivot = _pivot.sort_index(axis=1)
        if len(_pivot.columns) >= 2:
            _ld,_pd_ = _pivot.columns[-1],_pivot.columns[-2]
            _pivot["delta"] = _pivot[_ld] - _pivot[_pd_]
            _disp = _pivot[[_ld,_pd_,"delta"]].reset_index()
            _disp.columns = ["Trade",f"Today {_ld.date()}",f"Prior {_pd_.date()}","Δ MTM (1d)"]
            for c in [f"Today {_ld.date()}",f"Prior {_pd_.date()}","Δ MTM (1d)"]:
                _disp[c] = _disp[c].apply(fmt_bn)
            st.dataframe(_disp, width="stretch", hide_index=True)
    # ── EAD/RWA 30-day trend ─────────────────────────────────────────────────
    _pt = read_portfolio_trend(pid, days=30)
    if not _pt.empty and len(_pt) > 1:
        sec("EAD / RWA / MTM — 30-DAY TREND")
        _pt["run_date"] = pd.to_datetime(_pt["run_date"]); _pt = _pt.sort_values("run_date")
        _fig = go.Figure()
        _fig.add_trace(go.Scatter(x=_pt["run_date"],y=_pt["ead"]/1e6,name="EAD",
            line=dict(color=C["blue"],width=2)))
        _fig.add_trace(go.Scatter(x=_pt["run_date"],y=_pt["rwa"]/1e6,name="RWA",
            line=dict(color=C["crimson"],width=2,dash="dot")))
        if "mtm_net" in _pt.columns:
            _fig.add_trace(go.Scatter(x=_pt["run_date"],y=_pt["mtm_net"]/1e6,name="Net MTM",
                line=dict(color=C["teal"],width=1.5)))
        _fig.update_layout(**PLOT(260,10),yaxis_title="USD Millions",legend=LEG())
        st.plotly_chart(_fig)
    # ── SA-CCR Trade Attribution Table ───────────────────────────────────────
    sec("SA-CCR TRADE ATTRIBUTION — FULL DECOMPOSITION")
    st.caption(
        "Complete trade-level SA-CCR breakdown: hedging set, sub-hedging set, "
        "supervisory parameters, notional decomposition, and EAD / RWA allocation."
    )

    # Column ordering and rename map for the attribution table
    _ATTR_COLS = [
        ("portfolio_id",            "Portfolio ID"),
        ("trade_id",                "Trade ID"),
        ("asset_class",             "Asset Class"),
        ("instrument_type",         "Instrument"),
        ("underlying_security_id",  "Underlying / Security ID"),
        ("notional_ccy",            "CCY"),
        ("direction",               "Direction"),
        ("current_mtm",             "Current MTM"),
        ("rc_allocated",            "RC (Trade)"),
        ("rc_portfolio",            "RC (Portfolio)"),
        ("addon_trade",             "Add-On (Trade)"),
        ("addon_portfolio",         "Add-On (Portfolio)"),
        ("pfe_trade",               "PFE (Trade)"),
        ("pfe_portfolio",           "PFE (Portfolio)"),
        ("hedging_set",             "Hedging Set"),
        ("sub_hedging_set",         "Sub-Hedging Set"),
        ("supervisory_duration",    "Supervisory Duration"),
        ("supervisory_factor",      "Supervisory Factor"),
        ("maturity_factor",         "Maturity Factor"),
        ("supervisory_delta",       "Supervisory Delta"),
        ("sign_delta",              "Sign Delta"),
        ("saccr_notional",          "SA-CCR Notional"),
        ("saccr_adjusted_notional", "Adjusted Notional (SD×N)"),
        ("effective_notional",      "Effective Notional"),
        ("ead_trade",               "EAD (Trade)"),
        ("ead_portfolio",           "EAD (Portfolio)"),
        ("risk_weight_pct",         "Risk Weight (%)"),
        ("rwa",                     "RWA"),
        ("ead_calc_type",           "EAD Calc Type"),
    ]
    _MONEY_COLS = {
        "current_mtm","rc_allocated","rc_portfolio","addon_trade","addon_portfolio",
        "pfe_trade","pfe_portfolio","saccr_notional","saccr_adjusted_notional",
        "effective_notional","ead_trade","ead_portfolio","rwa",
    }
    _PCT_COLS   = {"supervisory_factor","maturity_factor","risk_weight_pct"}
    _DEC4_COLS  = {"supervisory_duration","supervisory_delta"}

    attr_rows = []
    # Gather trade_results from selected portfolio only
    _tr = port["saccr"].get("trade_results", {})
    for tid, tr in _tr.items():
        row = {}
        for key, label in _ATTR_COLS:
            val = tr.get(key, "—")
            if val is None:
                val = "—"
            elif key in _MONEY_COLS and isinstance(val, (int,float)):
                val = fmt_bn(val)
            elif key in _PCT_COLS and isinstance(val, (int,float)):
                val = f"{val*100:.4f}%" if val < 1 else f"{val:.1f}%"
            elif key in _DEC4_COLS and isinstance(val, (int,float)):
                val = f"{val:.6f}"
            row[label] = val
        attr_rows.append(row)

    if attr_rows:
        _attr_df = pd.DataFrame(attr_rows)
        # Colour-code EAD Calc Type column
        def _style_calc_type(val):
            if val == "IMM":     return "background-color:#e8f5e9;color:#1a5c2e;font-weight:bold"
            if val == "FALLBACK":return "background-color:#fff3f3;color:#8b2500;font-weight:bold"
            return "background-color:#ebf3fb;color:#2b5797;font-weight:bold"
        styled = _attr_df.style.applymap(_style_calc_type, subset=["EAD Calc Type"])
        st.dataframe(styled, width="stretch", hide_index=True)
        # Download button
        _csv = _attr_df.to_csv(index=False).encode()
        st.download_button(
            f"⬇  Download Attribution — {pid}",
            _csv, f"saccr_attribution_{pid}.csv", "text/csv"
        )
    else:
        st.info("No trade-level data available for this portfolio yet.")

    # ── Hedging Set summary ──────────────────────────────────────────────────
    sec("HEDGING SET SUMMARY")
    _hs_rows = []
    for tid, tr in _tr.items():
        _hs_rows.append({
            "Trade": tid,
            "Asset Class": tr.get("asset_class",""),
            "Instrument": tr.get("instrument_type",""),
            "Hedging Set": tr.get("hedging_set",""),
            "Sub-Hedging Set": tr.get("sub_hedging_set",""),
            "Hedging Set Basis": tr.get("hedging_set_basis",""),
            "EAD Calc Type": tr.get("ead_calc_type",""),
        })
    if _hs_rows:
        st.dataframe(pd.DataFrame(_hs_rows), width="stretch", hide_index=True)

    sec("ALL DERIVATIVE PORTFOLIOS")
    rows=[]
    for p in drv:
        imm_r = p.get("imm") or {}
        imm_gross = imm_r.get("ead_imm", 0)
        imm_csa   = imm_r.get("ead_imm_csa", imm_gross)
        csa_pct   = imm_r.get("csa_reduction_pct", 0)
        rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                     "Trades":p["trade_count"],"Notional":fmt_bn(p["gross_notional"]),
                     "SA-CCR EAD":fmt_bn(p["saccr"]["ead"]),
                     "IMM EAD (Gross)":fmt_bn(imm_gross),
                     "IMM EAD (CSA)":fmt_bn(imm_csa),
                     "CSA Benefit":f"{csa_pct:.1f}%",
                     "CCR RWA":fmt_bn(p["rwa_ccr"]),"Market RWA":fmt_bn(p["rwa_market"])})
    st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# 3 · BANKING BOOK
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Banking Book":
    st.markdown('<div class="page-title">Banking Book</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">A-IRB (CRE30–36) · Vasicek Formula · Double-Default</div>',
                unsafe_allow_html=True)

    pid   = st.selectbox("Portfolio",[p["portfolio_id"] for p in bbk],label_visibility="collapsed")
    pdata = next(p for p in bbk if p["portfolio_id"]==pid)
    rwa_pre = pdata.get("total_rwa_pre_mit", pdata["total_rwa"])
    mit_ben = pdata.get("total_mit_benefit", 0.0)
    mit_red = 100.0*(rwa_pre - pdata["total_rwa"])/rwa_pre if rwa_pre > 0 else 0.0
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    kpi(c1,"Total EAD",     fmt_bn(pdata["total_ead"]), "Exposure at Default", "A-IRB",            "t-blue")
    kpi(c2,"RWA (pre CRM)", fmt_bn(rwa_pre),            "Before mitigants",    "Gross",            "t-stone")
    kpi(c3,"RWA (post CRM)",fmt_bn(pdata["total_rwa"]), "After all CRM",       "CRE31.4",          "t-blue")
    kpi(c4,"CRM Benefit",   fmt_bn(mit_ben),            "RWA saved by CRM",    f"{mit_red:.1f}% reduction","t-ok" if mit_ben>0 else "t-stone")
    kpi(c5,"Expected Loss", fmt_bn(pdata["total_el"]),  "PD × LGD × EAD",     "EL",               "t-warn")
    sf = pdata["el_shortfall"]
    kpi(c6,"EL Shortfall",  fmt_bn(sf),                 "vs Provisions (CRE35)","Shortfall" if sf>0 else "Provisioned","t-bad" if sf>0 else "t-ok")

    # ── CRM benefit decomposition by channel ─────────────────────────────────
    mit_by_type = pdata.get("mitigant_by_type", {})
    if any(v > 0 for v in mit_by_type.values()):
        sec("CRM BENEFIT BY CHANNEL — CRE32")
        m1,m2,m3,m4 = st.columns(4)
        channel_map = [("COLLATERAL","Funded Collateral","Pledged assets → LGD*"),
                       ("GUARANTEE","Guarantees","Guarantor PD substitution"),
                       ("CDS","CDS / Double-Default","DD PD reduction"),
                       ("NETTING","Deposit Netting","EAD offset (retail)")]
        for col_w,(key,label,desc) in zip([m1,m2,m3,m4], channel_map):
            val = mit_by_type.get(key, 0.0)
            pct_s = f"{100*val/rwa_pre:.1f}% RWA saved" if rwa_pre>0 and val>0 else "not active"
            kpi(col_w, label, fmt_bn(val), desc, pct_s, "t-ok" if val>0 else "t-stone")
        # Stacked horizontal bar across all channels
        channels = [(k,l) for k,l,_ in channel_map if mit_by_type.get(k,0)>0]
        if channels:
            c_cols = [C["teal"],C["blue"],C["amber"],C["green"]]
            fig_m = go.Figure()
            for (key,label),colour in zip(channels, c_cols):
                v = mit_by_type.get(key,0)
                fig_m.add_trace(go.Bar(
                    name=label, x=[v/1e6], y=["CRM Benefit"],
                    orientation="h", marker_color=colour, opacity=0.85,
                    text=[f"${v/1e6:.1f}M"], textposition="inside",
                    textfont=dict(family="JetBrains Mono", size=9, color="#fff"),
                ))
            fig_m.update_layout(**PLOT(120,10), barmode="stack",
                                xaxis_title="USD Millions", legend=LEG())
            st.plotly_chart(fig_m)
        st.markdown("")

    sec("EXPOSURE DETAIL — TRADE LEVEL")
    tdf = pd.DataFrame(pdata["airb_trades"])
    tdf["pd"]  = tdf["pd"].map(lambda x: f"{x*100:.3f}%")
    tdf["lgd"] = tdf["lgd"].map(lambda x: f"{x*100:.1f}%")
    if "lgd_pre" in tdf.columns:
        tdf["lgd_pre"] = tdf["lgd_pre"].map(lambda x: f"{x*100:.1f}%")
    for c_ in ["ead","rwa","el"]:
        tdf[c_] = tdf[c_].map(fmt_bn)
    if "rwa_pre_mitigant" in tdf.columns:
        tdf["rwa_pre_mitigant"] = tdf["rwa_pre_mitigant"].map(fmt_bn)
    if "rwa_mit_benefit" in tdf.columns:
        tdf["rwa_mit_benefit"] = tdf["rwa_mit_benefit"].map(fmt_bn)
    tdf["correlation"] = tdf["correlation"].map(lambda x: f"{x:.4f}")
    tdf["capital_k"]   = tdf["capital_k"].map(lambda x: f"{x*100:.3f}%")
    show_cols = ["trade_id","pd","lgd_pre","lgd","ead","rwa_pre_mitigant",
                 "rwa","rwa_mit_benefit","el","mitigant_type","correlation","capital_k"]
    show_cols = [c for c in show_cols if c in tdf.columns]
    tdf = tdf[show_cols]
    rename = {"trade_id":"Trade ID","pd":"PD","lgd_pre":"LGD Gross",
              "lgd":"LGD* Net","ead":"EAD","rwa_pre_mitigant":"RWA (Pre CRM)",
              "rwa":"RWA (Post CRM)","rwa_mit_benefit":"CRM Benefit",
              "el":"EL","mitigant_type":"Channel","correlation":"Corr R","capital_k":"Capital K"}
    tdf.rename(columns={k:v for k,v in rename.items() if k in tdf.columns}, inplace=True)
    st.dataframe(tdf, width="stretch", hide_index=True)

    # ── LGD Model Breakdown (Frye-Jacobs three layers) ─────────────────────
    sec("LGD MODEL BREAKDOWN — THREE-LAYER FRYE-JACOBS ANALYSIS")
    try:
        from backend.data_sources.lgd_calibration import (
            DEFAULT_LGD_MODEL, _TTC_TABLE, LGD_FLOORS_SECURED
        )
        class _MD:
            def __init__(self, si): self._si = si
            def stress_index(self): return self._si
        si_live = cap.get("macro_stress_index", 0.30)
        lgd_rows = []
        for (ac, col), (ttc, rho) in sorted(_TTC_TABLE.items()):
            dt   = DEFAULT_LGD_MODEL.downturn_lgd(ac, col)
            cond = DEFAULT_LGD_MODEL.conditional_lgd(ac, _MD(si_live), col)
            fl   = LGD_FLOORS_SECURED.get(col, 0.25)
            lgd_rows.append({
                "Asset Class":       ac,
                "Collateral":        col,
                "rho_LGD":           f"{rho:.2f}",
                "TTC LGD":           f"{ttc*100:.1f}%",
                "Downturn LGD (P1)": f"{dt*100:.1f}%",
                "Conditional (P2)":  f"{cond*100:.1f}%",
                "CRE32.16 Floor":    f"{fl*100:.0f}%",
                "Floor Binding":     "YES" if dt <= fl + 0.001 else "—",
            })
        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.markdown("**Reference LGD Table** — TTC from Moody's / S&P recovery data, stressed via Frye-Jacobs")
            lgd_df = pd.DataFrame(lgd_rows)
            st.dataframe(lgd_df, width="stretch", hide_index=True)
        with col_r:
            st.markdown("**Frye-Jacobs Downturn Formula (CRE36.83)**")
            st.code(
                "LGD_DT = Phi((Phi_inv(LGD_TTC) + rho_LGD x Phi_inv(0.999))"
                " / sqrt(1 - rho_LGD^2))",
                language=None,
            )
            st.markdown(
                "- **TTC LGD**: long-run default-weighted average (Moody's 2023)\n"
                "- **Downturn LGD (P1)**: 99.9th percentile — Pillar 1 capital\n"
                "- **Conditional (P2)**: macro stress-index conditioned — ICAAP\n"
                "- **rho_LGD**: LGD-systematic correlation (Frye 2000)\n"
                "- **Floor**: CRE32.16 regulatory backstop"
            )
            rhos = [0.10, 0.20, 0.30, 0.40, 0.50]
            dts  = [
                DEFAULT_LGD_MODEL._frye_jacobs_q(0.424, r, DEFAULT_LGD_MODEL._q) * 100
                for r in rhos
            ]
            fig_rho = go.Figure(
                go.Scatter(
                    x=rhos, y=dts, mode="lines+markers",
                    line=dict(color="#2980b9", width=2),
                    hovertemplate="rho=%{x:.2f}  DT-LGD=%{y:.1f}%<extra></extra>",
                )
            )
            fig_rho.update_layout(
                **PLOT(250, 0),
                xaxis_title="rho_LGD",
                yaxis_title="DT-LGD (%)",
                title=dict(text="Sensitivity to rho_LGD (CORP, TTC=42.4%)", font=dict(size=11)),
            )
            st.plotly_chart(fig_rho, use_container_width=True)
    except ImportError:
        st.warning("lgd_calibration.py not found — deploy to backend/data_sources/ to enable.")
    except Exception as _lgd_err:
        st.error(f"LGD model panel error: {_lgd_err}")

    sec("ALL PORTFOLIOS — CRM OVERVIEW")

    bbk_rows = []
    for p in bbk:
        rp  = p.get("total_rwa_pre_mit", p["total_rwa"])
        rb  = p.get("total_mit_benefit", 0.0)
        red = 100.0*(rp - p["total_rwa"])/rp if rp > 0 else 0.0
        by_t = p.get("mitigant_by_type", {})
        bbk_rows.append({
            "Portfolio":      p["portfolio_id"],
            "Counterparty":   p["counterparty"][:20],
            "Exposures":      p["exposure_count"],
            "EAD":            fmt_bn(p["total_ead"]),
            "RWA (Pre CRM)":  fmt_bn(rp),
            "RWA (Post CRM)": fmt_bn(p["total_rwa"]),
            "CRM Benefit":    fmt_bn(rb),
            "RWA Reduction":  f"{red:.1f}%",
            "CRM Coverage":   f"{p.get('mitigant_coverage_pct',0):.0f}%",
            "Collateral":     fmt_bn(by_t.get("COLLATERAL",0)),
            "Guarantee":      fmt_bn(by_t.get("GUARANTEE",0)),
            "CDS":            fmt_bn(by_t.get("CDS",0)),
        })
    st.dataframe(pd.DataFrame(bbk_rows), width="stretch", hide_index=True)

    sec("PD vs CAPITAL K — VASICEK PROFILE")
    all_t=[]
    for p in bbk:
        for t in p["airb_trades"]: all_t.append({**t,"Portfolio":p["portfolio_id"]})
    at_df=pd.DataFrame(all_t)
    fig_sc=go.Figure()
    for i,ptf in enumerate(at_df["Portfolio"].unique()):
        sub=at_df[at_df["Portfolio"]==ptf]
        fig_sc.add_trace(go.Scatter(x=sub["pd"],y=sub["capital_k"],mode="markers",name=ptf,
            marker=dict(size=sub["ead"]/sub["ead"].max()*16+5,opacity=0.75,
                        color=list(C.values())[i%len(C)]),
            hovertemplate="<b>%{text}</b><br>PD:%{x:.3f} K:%{y:.3f}<extra></extra>",
            text=sub["trade_id"]))
    fig_sc.update_layout(**PLOT(400,10),xaxis_title="PD",yaxis_title="Capital K")
    st.plotly_chart(fig_sc)

# ══════════════════════════════════════════════════════════════════════════════
# 4 · MARKET RISK
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Market Risk (FRTB)":
    st.markdown('<div class="page-title">Market Risk — FRTB</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">SBM (MAR21–23) · IMA/ES (MAR31–33) · Capital = max(SBM, 1.5×IMA)</div>',
                unsafe_allow_html=True)

    sec("PORTFOLIO MARKET RISK SUMMARY")
    mrows=[{"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"][:22],
            "SBM Total":fmt_bn(p["frtb"]["sbm_total"]),"ES 10d":fmt_bn(p["frtb"]["es_10d"]),
            "ES Stressed":fmt_bn(p["frtb"]["es_stressed"]),"IMA Total":fmt_bn(p["frtb"]["ima_total"]),
            "Market RWA":fmt_bn(p["frtb"]["rwa_market"])} for p in drv]
    st.dataframe(pd.DataFrame(mrows),width="stretch",hide_index=True)

    sec("SBM COMPONENT BREAKDOWN — DELTA · VEGA · CURVATURE")
    sbm_df=pd.DataFrame([{"Portfolio":p["portfolio_id"],
                           "Delta":p["frtb"]["sbm_delta"]/1e6,
                           "Vega":p["frtb"]["sbm_vega"]/1e6,
                           "Curvature":p["frtb"]["sbm_curvature"]/1e6} for p in drv])
    fig_sbm=go.Figure()
    for comp,col_ in [("Delta",C["blue"]),("Vega",C["indigo"]),("Curvature",C["gold"])]:
        fig_sbm.add_trace(go.Bar(name=comp,x=sbm_df["Portfolio"],y=sbm_df[comp],
                                  marker_color=col_,opacity=0.85))
    fig_sbm.update_layout(**PLOT(360,10),barmode="group",yaxis_title="USD Millions",
                           legend=LEG())
    st.plotly_chart(fig_sbm)

    sec("SBM vs IMA — METHOD COMPARISON")
    cmp_df=pd.DataFrame([{"Portfolio":p["portfolio_id"],
                           "SBM":p["frtb"]["sbm_total"]/1e6,
                           "IMA":p["frtb"]["ima_total"]/1e6} for p in drv])
    fig_cmp=go.Figure()
    for m,col_ in [("SBM",C["blue"]),("IMA",C["teal"])]:
        fig_cmp.add_trace(go.Bar(name=m,x=cmp_df["Portfolio"],y=cmp_df[m],
                                  marker_color=col_,opacity=0.85))
    fig_cmp.update_layout(**PLOT(340,10),barmode="group",yaxis_title="USD Millions",
                           legend=LEG())
    st.plotly_chart(fig_cmp)

# ══════════════════════════════════════════════════════════════════════════════
# 5 · IMM EXPOSURE PROFILES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "IMM Exposure Profiles":
    st.markdown('<div class="page-title">IMM Exposure Profiles</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Monte Carlo EPE/EEPE · CRE53 · 2,000 Scenarios</div>',
                unsafe_allow_html=True)

    imm_ports=[p for p in drv if p.get("imm")]
    if not imm_ports:
        st.info("No IMM-eligible trades found.")
    else:
        pid=st.selectbox("Portfolio",[p["portfolio_id"] for p in imm_ports],label_visibility="collapsed")
        pdata=next(p for p in imm_ports if p["portfolio_id"]==pid)
        imm=pdata["imm"]
        c1,c2,c3,c4=st.columns(4)
        kpi(c1,"EPE",         fmt_bn(imm["epe"]),          "Expected Positive Exposure","Base",       "t-blue")
        kpi(c2,"EEPE",        fmt_bn(imm["eepe"]),         "Effective EPE (regulatory)","Non-decreasing","t-blue")
        kpi(c3,"IMM EAD",     fmt_bn(imm["ead_imm"]),      "1.4 × EEPE",               "CRE53",       "t-stone")
        kpi(c4,"Stressed EAD",fmt_bn(imm["stressed_ead"]), "GFC 2007–09 calibration",  "Stressed",    "t-warn")

        st.markdown(
            f'<div style="font-family:JetBrains Mono;font-size:0.66rem;color:#94a3b8;'
            f'margin-bottom:8px">Scenarios: {imm["scenario_count"]:,} · '
            f'Steps: {imm["time_steps"]} · Runtime: {imm["runtime_seconds"]:.2f}s</div>',
            unsafe_allow_html=True)

        t=imm["time_grid"]; ee=imm["ee_profile"]; eee=imm["eee_profile"]; pfe=imm["pfe_95"]
        # Convert scalar PFE to array (horizontal line across time grid)
        if isinstance(pfe, (int, float)):
            pfe = [pfe] * len(t)
        fig_exp=go.Figure()
        fig_exp.add_trace(go.Scatter(x=t,y=[v/1e6 for v in pfe],name="PFE 95%",
            line=dict(color=C["red"],dash="dot",width=1.5)))
        fig_exp.add_trace(go.Scatter(x=t,y=[v/1e6 for v in eee],name="Effective EE (EEE)",
            line=dict(color=C["gold"],width=2.5),
            fill="tozeroy",fillcolor="rgba(146,64,14,0.05)"))
        fig_exp.add_trace(go.Scatter(x=t,y=[v/1e6 for v in ee],name="Expected Exposure (EE)",
            line=dict(color=C["blue"],width=2.5)))
        fig_exp.update_layout(**PLOT(420,10),
            xaxis_title="Time (years)",yaxis_title="Exposure (USD Millions)",
            legend=LEG("h",-0.15,0))
        st.plotly_chart(fig_exp)

# ══════════════════════════════════════════════════════════════════════════════
# 6 · RISK LIMITS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Risk Limits":
    st.markdown('<div class="page-title">Risk Limits</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Real-time utilisation · Threshold monitoring</div>',
                unsafe_allow_html=True)

    limits=[
        {"n":"CET1 Ratio Minimum",   "t":"Ratio","lv":4.5,  "u":"%","c":cap["cet1_ratio"]*100,       "w":0.95},
        {"n":"Total Capital Ratio",  "t":"Ratio","lv":8.0,  "u":"%","c":cap["total_cap_ratio"]*100,   "w":0.92},
        {"n":"FRTB ES (10d, 97.5%)", "t":"ES",   "lv":100,  "u":"M","c":sum(p["frtb"]["es_10d"] for p in drv)/1e6,"w":0.80},
        {"n":"CCR EAD Total",        "t":"EAD",  "lv":500,  "u":"M","c":sum(p["saccr"]["ead"] for p in drv)/1e6,"w":0.80},
        {"n":"Banking Book RWA",     "t":"RWA",  "lv":1500, "u":"M","c":cap["rwa_credit"]/1e6,         "w":0.80},
        {"n":"CVA RWA",              "t":"CVA",  "lv":50,   "u":"M","c":cap.get("rwa_cva",0)/1e6,     "w":0.80},
    ]

    sec("LIMIT UTILISATION")
    for lim in limits:
        util=lim["c"]/lim["lv"]
        pct_=min(util*100,100)
        status="🔴 BREACH" if util>=1 else ("🟡 WARNING" if util>=lim["w"] else "🟢 OK")
        bar_c=C["red"] if util>=1 else (C["amber"] if util>=lim["w"] else C["green"])
        st.markdown(
            f'<div class="lrow">'
            f'<div><div class="ln">{lim["n"]}</div><div class="lt">{lim["t"]}</div></div>'
            f'<div style="background:var(--stone-100);border-radius:4px;height:5px;overflow:hidden">'
            f'<div style="width:{pct_:.1f}%;height:100%;background:{bar_c};border-radius:4px"></div></div>'
            f'<div class="lv">{lim["c"]:.1f}{lim["u"]}</div>'
            f'<div class="lv" style="color:var(--stone-300)">{lim["lv"]:.0f}{lim["u"]}</div>'
            f'<div class="lv">{util*100:.1f}%</div>'
            f'<div style="font-size:0.82rem;text-align:right">{status}</div></div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 7 · BACKTESTING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Backtesting":
    st.markdown('<div class="page-title">Backtesting</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">MAR99 Traffic-Light Framework · 250 Trading Days</div>',
                unsafe_allow_html=True)

    zone=bt.get("traffic_light","GREEN")
    excpts=bt.get("exceptions",0); window=bt.get("window_days",250)
    ztag={"GREEN":"t-ok","AMBER":"t-warn","RED":"t-bad"}.get(zone,"t-ok")

    c1,c2,c3,c4=st.columns(4)
    kpi(c1,"Zone",       zone,                   "MAR99 Traffic Light",   zone,    ztag)
    kpi(c2,"Exceptions", str(excpts),             "Days VaR exceeded",     f"/{window}",
        "t-ok" if excpts<=4 else ("t-warn" if excpts<=9 else "t-bad"))
    kpi(c3,"Rate",       f"{excpts/window*100:.2f}%","Annualised",         "250-day","t-stone")
    kpi(c4,"Multiplier", {"GREEN":"1.50×","AMBER":"1.70–1.92×","RED":"2.00×"}.get(zone,"1.50×"),
        "IMA capital multiplier","MAR33","t-stone")

    sec("TRAFFIC-LIGHT ZONES — MAR32 TABLE 1")
    st.dataframe(pd.DataFrame({
        "Zone":["🟢 Green","🟡 Amber","🔴 Red"],
        "Exceptions (250d)":["0–4","5–9","10+"],
        "Multiplier":["1.50","1.70–1.92","2.00"],
        "Supervisory Action":["No action","Add-on; regulator review","Model revocation risk"],
        "Active":["← Active" if zone=="GREEN" else "","← Active" if zone=="AMBER" else "","← Active" if zone=="RED" else ""],
    }),width="stretch",hide_index=True)

    sec("P&L vs VaR — 250 TRADING DAY LOOKBACK")

    # Build P&L and VaR series from historical DB if available,
    # else fall back to a deterministic simulation seeded from portfolio EAD
    hist_df = load_history(250)
    if not hist_df.empty and "rwa_market" in hist_df.columns and len(hist_df) >= 20:
        # Use actual historical market RWA changes as a P&L proxy
        # (daily RWA change × -1 approximates desk P&L direction)
        hist_df = hist_df.sort_values("run_date")
        rwa_series = hist_df["rwa_market"].values.astype(float)
        n_hist = len(rwa_series)
        # Daily P&L ≈ -ΔRWA / 12.5 (reverse RWA conversion)
        pnl_hist = -np.diff(rwa_series, prepend=rwa_series[0]) / 12.5
        # VaR ≈ 2.33 × rolling 20-day std of P&L
        var_hist = np.array([
            2.33 * np.std(pnl_hist[max(0,i-20):i+1])
            for i in range(n_hist)
        ])
        days_hist = list(range(1, n_hist+1))
        source_label = f"Historical ({n_hist} days from DB)"
    else:
        # Deterministic simulation seeded from current total EAD
        ead_seed = int(sum(p["saccr"]["ead"] for p in drv) / 1e6) % 10000
        rng2 = np.random.default_rng(ead_seed)
        n_hist = 250
        base_pnl_scale = sum(p["saccr"]["ead"] for p in drv) / 250.0 * 0.002
        pnl_hist = rng2.normal(base_pnl_scale * 0.1, base_pnl_scale, n_hist)
        var_hist  = np.abs(rng2.normal(base_pnl_scale * 0.8, base_pnl_scale * 0.1, n_hist))
        days_hist = list(range(1, n_hist+1))
        source_label = "Simulated (seed from portfolio EAD — populate DB for live data)"

    exc_x = [d for d,p,v in zip(days_hist,pnl_hist,var_hist) if -p > v]
    exc_y = [pnl_hist[d-1]/1e3 for d in exc_x]
    actual_excepts = len(exc_x)

    # Update zone based on actual simulated exceptions
    _zone_actual = "GREEN" if actual_excepts<=4 else ("AMBER" if actual_excepts<=9 else "RED")

    fig_bt=go.Figure()
    fig_bt.add_trace(go.Bar(
        x=days_hist, y=pnl_hist/1e3, name="Daily P&L",
        marker_color=[C["red"] if p<0 else C["blue"] for p in pnl_hist],
        opacity=0.60))
    fig_bt.add_trace(go.Scatter(
        x=days_hist, y=-var_hist/1e3, name="−VaR Boundary",
        line=dict(color=C["amber"],dash="dash",width=1.5)))
    if exc_x:
        fig_bt.add_trace(go.Scatter(
            x=exc_x, y=exc_y, mode="markers", name=f"Exception ({actual_excepts})",
            marker=dict(color=C["red"],size=9,symbol="x-thin",
                        line=dict(width=2.5,color=C["red"]))))
    fig_bt.update_layout(**PLOT(400,10),
        xaxis_title="Trading Day", yaxis_title="P&L (USD 000s)",
        legend=LEG(),
        title=dict(text=source_label,font=dict(size=11,color="#94a3b8"),x=0.02))
    st.plotly_chart(fig_bt)

    # P&L distribution chart
    sec("P&L DISTRIBUTION vs NORMAL")
    fig_dist = go.Figure()
    fig_dist.add_trace(go.Histogram(
        x=pnl_hist/1e3, nbinsx=40, name="Observed P&L",
        marker_color=C["blue"], opacity=0.70,
        histnorm="probability density"))
    # Overlay normal fit
    _mu = float(np.mean(pnl_hist/1e3))
    _sd = float(np.std(pnl_hist/1e3))
    _x_norm = np.linspace(float(np.min(pnl_hist/1e3))*1.3, float(np.max(pnl_hist/1e3))*1.3, 200)
    _y_norm = (1/(_sd*np.sqrt(2*np.pi))) * np.exp(-0.5*((_x_norm-_mu)/_sd)**2)
    fig_dist.add_trace(go.Scatter(
        x=_x_norm, y=_y_norm, name="Normal fit",
        line=dict(color=C["amber"],width=2,dash="dot")))
    fig_dist.update_layout(**PLOT(280,10),
        xaxis_title="Daily P&L (USD 000s)", yaxis_title="Density", legend=LEG())
    st.plotly_chart(fig_dist)

# ══════════════════════════════════════════════════════════════════════════════
# 8 · REPORTS
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# CVA RISK — MAR50
# ══════════════════════════════════════════════════════════════════════════════
elif page == "CVA Risk":
    st.markdown('<div class="page-title">CVA Risk Capital</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">MAR50 · BA-CVA / SA-CVA · Fallback Routing · Hedge Benefit</div>',
                unsafe_allow_html=True)

    method_tag = {"SA_CVA":"t-blue","BA_CVA":"t-warn","CCR_PROXY":"t-bad"}.get(cva.get("method","BA_CVA"),"t-stone")
    sa_rwa = cva.get("by_method",{}).get("SA_CVA",0)
    ba_rwa = cva.get("by_method",{}).get("BA_CVA",0)
    px_rwa = cva.get("by_method",{}).get("CCR_PROXY",0)
    hred   = cva.get("hedge_rwa_reduction",0)

    c1,c2,c3,c4,c5 = st.columns(5)
    kpi(c1,"CVA Method",        cva.get("method","—"),           "Approach in use",        "MAR50",          method_tag)
    kpi(c2,"Total CVA RWA",     fmt_bn(cva.get("total_rwa_cva",0)), "Aggregate charge",    "MAR50.20+",      "t-blue")
    kpi(c3,"SA-CVA RWA",        fmt_bn(sa_rwa),                  "Sensitivity-based",      "Approved desks", "t-blue"   if sa_rwa>0 else "t-stone")
    kpi(c4,"BA-CVA RWA",        fmt_bn(ba_rwa),                  "Basic approach",         "All others",     "t-warn"   if ba_rwa>0 else "t-stone")
    kpi(c5,"Hedge Benefit",     fmt_bn(hred),                    "CVA hedge RWA reduction","MAR50.32",       "t-ok"     if hred>0 else "t-stone")

    # ── Method breakdown donut ─────────────────────────────────────────────
    sec("CVA CAPITAL — SA vs BA vs PROXY SPLIT")
    method_vals = [(k, v) for k, v in cva.get("by_method",{}).items() if v > 0]
    if method_vals:
        left, right = st.columns(2)
        with left:
            fig_donut = go.Figure(go.Pie(
                labels=[m for m,_ in method_vals],
                values=[v for _,v in method_vals],
                hole=0.55,
                marker=dict(colors=[C["blue"],C["amber"],C["red"]][:len(method_vals)],
                            line=dict(color="#ffffff",width=2)),
                textinfo="percent+label",
                textfont=dict(family="JetBrains Mono",size=10),
                hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
                customdata=[fmt_bn(v) for _,v in method_vals],
            ))
            fig_donut.add_annotation(x=0.5,y=0.5,text=fmt_bn(cva.get("total_rwa_cva",0)),
                showarrow=False,font=dict(family="JetBrains Mono",size=14,color="#0f172a"))
            fig_donut.update_layout(**PLOT(300,10),showlegend=True,legend=LEG("v",0.5,1.02))
            st.plotly_chart(fig_donut)
        with right:
            if hred > 0:
                fig_hedge = go.Figure(go.Bar(
                    x=["Pre-Hedge CVA RWA","Hedge Benefit","Post-Hedge CVA RWA"],
                    y=[(cva.get("total_rwa_cva",0)+hred)/1e6, -hred/1e6,
                       cva.get("total_rwa_cva",0)/1e6],
                    marker=dict(color=[C["blue"],C["green"],C["teal"]],opacity=0.85),
                    text=[fmt_bn((cva.get("total_rwa_cva",0)+hred)),fmt_bn(-hred),
                          fmt_bn(cva.get("total_rwa_cva",0))],
                    textposition="outside",
                    textfont=dict(family="JetBrains Mono",size=10),
                ))
                fig_hedge.update_layout(**PLOT(300,10),yaxis_title="USD Millions")
                st.plotly_chart(fig_hedge)
            else:
                st.info("No CVA hedges in current portfolio — hedge benefit is zero.")

    # ── Counterparty-level breakdown ───────────────────────────────────────
    sec("COUNTERPARTY CVA DETAIL — MAR50")
    cpts = cva.get("counterparties",[])
    if cpts:
        cdf = pd.DataFrame(cpts)
        cdf["rwa_cva"]      = cdf["rwa_cva"].apply(fmt_bn)
        cdf["cva_estimate"] = cdf["cva_estimate"].apply(fmt_bn)
        rename = {"counterparty_id":"Counterparty","method":"Method",
                  "rwa_cva":"CVA RWA","cva_estimate":"CVA Estimate",
                  "fallback_trace":"Fallback Trace","has_hedge":"Hedged"}
        cdf.rename(columns={k:v for k,v in rename.items() if k in cdf.columns},inplace=True)
        st.dataframe(cdf,width="stretch",hide_index=True)

    # ── Fallback traces ────────────────────────────────────────────────────
    fallbacks = cva.get("fallback_traces",[])
    if fallbacks:
        sec(f"FALLBACK TRACES — {len(fallbacks)} COUNTERPART(IES) ON BA-CVA")
        for trace in fallbacks[:20]:
            parts = trace.split("|")
            cpty_id = parts[1] if len(parts)>1 else trace
            reason  = parts[2] if len(parts)>2 else "—"
            detail  = parts[3] if len(parts)>3 else ""
            st.markdown(
                f'<div class="lrow" style="grid-template-columns:180px 120px 1fr">'                f'<div><div class="ln">{cpty_id}</div></div>'                f'<div class="kpi-tag t-warn">{reason}</div>'                f'<div class="lt">{detail}</div></div>',
                unsafe_allow_html=True)
    else:
        st.success("All counterparties on SA-CVA — no fallbacks to BA-CVA.")

    sec("REGULATORY CONTEXT — MAR50")
    st.markdown("""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-family:'Nunito Sans',sans-serif;font-size:0.83rem;color:var(--slate-600)">
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">SA-CVA (MAR50.40+)</strong><br>
Requires supervisory approval · Sensitivity-based (like FRTB SBM) · Delta + Vega charges on credit spread sensitivities · Lower capital than BA-CVA for well-hedged books
</div>
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">BA-CVA (MAR50.20–38)</strong><br>
Always available as fallback · EAD × RW × M_eff · Supervisory rho = 50% (floor) · Hedge benefit capped · CCR proxy if aggregate CCR RWA below materiality threshold
</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CCP EXPOSURE — CRE54
# ══════════════════════════════════════════════════════════════════════════════
elif page == "CCP Exposure":
    st.markdown('<div class="page-title">CCP Exposure Capital</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">CRE54 · QCCP / Non-QCCP · Trade Exposure · Default Fund</div>',
                unsafe_allow_html=True)

    positions = ccp.get("positions",[])
    total_rwa_ccp = ccp.get("total_rwa_ccp",0)
    qccp_count    = sum(1 for p in positions if p.get("is_qualifying"))
    nonqccp_count = len(positions) - qccp_count
    total_ead     = sum(p.get("trade_ead",0) for p in positions)
    total_dfc     = sum(p.get("df_contribution",0) for p in positions)

    c1,c2,c3,c4,c5 = st.columns(5)
    kpi(c1,"Total CCP RWA",  fmt_bn(total_rwa_ccp),  "Aggregate CRE54 charge", "CRE54",      "t-blue")
    kpi(c2,"QCCP Positions",  str(qccp_count),         "Qualifying CCPs",        "2% RW",       "t-ok")
    kpi(c3,"Non-QCCP",        str(nonqccp_count),      "Non-qualifying CCPs",    "100% RW",     "t-bad" if nonqccp_count>0 else "t-ok")
    kpi(c4,"Trade EAD",       fmt_bn(total_ead),        "Total cleared exposure", "SA-CCR based","t-stone")
    kpi(c5,"Default Fund",    fmt_bn(total_dfc),        "DFC contributions",      "CRE54.31",   "t-stone")

    sec("CCP POSITIONS — TRADE EXPOSURE AND DEFAULT FUND")
    if positions:
        fig_ccp = go.Figure()
        ccp_names  = [p["ccp_name"] for p in positions]
        rwa_trade  = [p["rwa_trade"]/1e6 for p in positions]
        rwa_dfc    = [p["rwa_dfc"]/1e6   for p in positions]
        fig_ccp.add_trace(go.Bar(name="Trade Exposure RWA",x=ccp_names,y=rwa_trade,
            marker_color=C["blue"],opacity=0.85,
            text=[f"${v:.1f}M" for v in rwa_trade],textposition="inside",
            textfont=dict(family="JetBrains Mono",size=9,color="#fff")))
        fig_ccp.add_trace(go.Bar(name="Default Fund RWA",x=ccp_names,y=rwa_dfc,
            marker_color=C["amber"],opacity=0.85,
            text=[f"${v:.1f}M" for v in rwa_dfc],textposition="inside",
            textfont=dict(family="JetBrains Mono",size=9,color="#fff")))
        fig_ccp.update_layout(**PLOT(300,10),barmode="stack",
            yaxis_title="USD Millions",legend=LEG())
        st.plotly_chart(fig_ccp)

        # Detail table
        rows = []
        for p in positions:
            rw_label = "2% (QCCP)" if p["is_qualifying"] else "100% (Non-QCCP)"
            rows.append({
                "CCP":              p["ccp_name"],
                "Type":             "✓ QCCP" if p["is_qualifying"] else "✗ Non-QCCP",
                "Trade EAD":        fmt_bn(p["trade_ead"]),
                "IM Posted":        fmt_bn(p["im_posted"]),
                "DFC":              fmt_bn(p["df_contribution"]),
                "Trade RW":         rw_label,
                "Trade RWA":        fmt_bn(p["rwa_trade"]),
                "DFC RWA":          fmt_bn(p["rwa_dfc"]),
                "Total RWA":        fmt_bn(p["rwa_total"]),
                "Method":           p["method_note"],
            })
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)

    sec("REGULATORY CONTEXT — CRE54")
    st.markdown("""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;font-family:'Nunito Sans',sans-serif;font-size:0.82rem;color:var(--slate-600)">
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">Trade Exposure</strong><br>
QCCP: 2% risk weight · Non-QCCP: 100% RW · Segregated IM: 0% RW (CRE54.15) · Non-segregated IM: 2% RW
</div>
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">Default Fund</strong><br>
Risk-sensitive: proportional to hypothetical KCCP (CRE54.32) · Simplified: DFC × 1.6% flat rate · Unfunded commitments: 1250% RW (CRE54.42)
</div>
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">Client Clearing</strong><br>
Clearing member acting as intermediary → 2% on client EAD · Exposure treated as trade-level QCCP exposure · No DFC for intermediary role
</div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# OPERATIONAL RISK — OPE25 SMA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Operational Risk":
    st.markdown('<div class="page-title">Operational Risk</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Basel III SMA (OPE25) · BIC × ILM</div>',
                unsafe_allow_html=True)

    try:
        from backend.engines.operational_risk import (
            BusinessIndicatorInput, compute_sma_capital,
            analyze_losses_by_event_type, analyze_losses_by_business_line,
            get_loss_timeline
        )
        from backend.data_sources.loss_event_database import get_loss_event_database
        
        # Load business indicator data
        bi_inputs = [
            BusinessIndicatorInput(
                year=2023, interest_income=800, interest_expense=400,
                dividend_income=80, services_income=500, services_expense=150,
                financial_income=250, financial_expense=100,
                other_operating_income=150, trading_book_pnl=300, banking_book_pnl=250,
            ),
            BusinessIndicatorInput(
                year=2024, interest_income=850, interest_expense=425,
                dividend_income=85, services_income=525, services_expense=160,
                financial_income=265, financial_expense=105,
                other_operating_income=160, trading_book_pnl=320, banking_book_pnl=265,
            ),
            BusinessIndicatorInput(
                year=2025, interest_income=900, interest_expense=450,
                dividend_income=90, services_income=550, services_expense=170,
                financial_income=280, financial_expense=110,
                other_operating_income=170, trading_book_pnl=340, banking_book_pnl=280,
            ),
        ]
        
        # Load loss events
        db = get_loss_event_database()
        loss_events = db.get_all_events()
        
        if not loss_events:
            st.warning(
                "⚠️ **No operational loss events in database.** "
                "Generate sample data or upload historical loss events to see SMA calculation."
            )
            st.info("To generate sample data, run: `python backend/data_generators/03_operational_loss_generator.py`")
        else:
            # Compute SMA Capital
            sma_result = compute_sma_capital(bi_inputs, loss_events)
            
            # Display key metrics
            c1,c2,c3,c4 = st.columns(4)
            kpi(c1, "Business Indicator", fmt_bn(sma_result.business_indicator * 1e6),
                "3-year average BI", "OPE25.15", "t-blue")
            kpi(c2, "BIC", fmt_bn(sma_result.bic * 1e6),
                "Business Indicator Component", "OPE25.20", "t-blue")
            kpi(c3, "ILM", f"{sma_result.ilm:.3f}",
                "Internal Loss Multiplier", "Capped at 1.0", "t-ok" if sma_result.ilm < 1 else "t-warn")
            kpi(c4, "Op Risk Capital", fmt_bn(sma_result.operational_risk_capital * 1e6),
                "BIC × ILM", "OPE25", "t-blue")
            
            st.markdown("")
            r1,r2,r3 = st.columns(3)
            kpi(r1, "Op Risk RWA", fmt_bn(sma_result.rwa_operational * 1e6),
                "Capital × 12.5", "RBC20.9", "t-blue")
            kpi(r2, "Loss Component", fmt_bn(sma_result.loss_component * 1e6),
                "15 × Avg Annual Losses", "OPE25.12", "t-stone")
            kpi(r3, "Loss Years", f"{sma_result.years_of_loss_data}",
                "Years of loss data", "10 req for LC" if sma_result.years_of_loss_data < 10 else "✓ Sufficient", 
                "t-warn" if sma_result.years_of_loss_data < 10 else "t-ok")
            
            # BIC Tier Breakdown
            sec("BUSINESS INDICATOR COMPONENT (BIC) — TIERED APPROACH")
            bi_bn = sma_result.business_indicator / 1000
            tier_data = []
            tiers = [
                ("Tier 1", 0, 1, 0.12),
                ("Tier 2", 1, 3, 0.15),
                ("Tier 3", 3, 10, 0.18),
                ("Tier 4", 10, 30, 0.21),
                ("Tier 5", 30, float('inf'), 0.23),
            ]
            
            for tier_name, lower, upper, coef in tiers:
                if bi_bn > lower:
                    marginal_bi = min(bi_bn, upper) - lower
                    marginal_bic = marginal_bi * coef
                    tier_data.append({
                        "Tier": tier_name,
                        "Range (EUR bn)": f"{lower}-{upper if upper != float('inf') else '∞'}",
                        "Coefficient": f"{coef:.0%}",
                        "Marginal BI (bn)": f"{marginal_bi:.2f}",
                        "Marginal BIC (M)": f"{marginal_bic * 1000:.1f}",
                    })
            
            tier_df = pd.DataFrame(tier_data)
            st.dataframe(tier_df, width="stretch", hide_index=True)
            
            # Loss Analysis
            sec("LOSS ANALYSIS — BY EVENT TYPE & BUSINESS LINE")
            lcol, rcol = st.columns(2)
            
            with lcol:
                event_type_df = analyze_losses_by_event_type(loss_events)
                if not event_type_df.empty:
                    fig_et = go.Figure(go.Bar(
                        x=event_type_df["event_type"],
                        y=event_type_df["total_net_loss"],
                        marker_color=C["red"],
                        opacity=0.85,
                        text=[f"{v:.1f}M" for v in event_type_df["total_net_loss"]],
                        textposition="outside",
                        textfont=dict(family="JetBrains Mono", size=9),
                    ))
                    fig_et.update_layout(**PLOT(280,10), 
                        xaxis_title="Event Type", yaxis_title="Net Loss (EUR M)",
                        showlegend=False)
                    st.plotly_chart(fig_et)
            
            with rcol:
                bl_df = analyze_losses_by_business_line(loss_events)
                if not bl_df.empty:
                    fig_bl = go.Figure(go.Pie(
                        labels=bl_df["business_line"],
                        values=bl_df["total_net_loss"],
                        hole=0.5,
                        marker=dict(colors=[C["red"], C["amber"], C["gold"], C["teal"], C["blue"]]),
                        textinfo="percent+label",
                        textfont=dict(family="JetBrains Mono", size=9),
                    ))
                    fig_bl.update_layout(**PLOT(280,10), showlegend=True, legend=LEG("v",0.5,1.02))
                    st.plotly_chart(fig_bl)
            
            # Timeline
            timeline_df = get_loss_timeline(loss_events)
            if not timeline_df.empty:
                sec("LOSS TIMELINE — ANNUAL AGGREGATION")
                annual_losses = timeline_df.groupby(timeline_df["date"].dt.year)["net_loss"].sum().reset_index()
                annual_losses.columns = ["Year", "Net Loss"]
                
                fig_ann = go.Figure(go.Bar(
                    x=annual_losses["Year"],
                    y=annual_losses["Net Loss"],
                    marker_color=C["red"],
                    opacity=0.85,
                    text=[f"{v:.1f}M" for v in annual_losses["Net Loss"]],
                    textposition="outside",
                    textfont=dict(family="JetBrains Mono", size=10),
                ))
                fig_ann.update_layout(**PLOT(300,10), 
                    xaxis_title="Year", yaxis_title="Net Loss (EUR M)")
                st.plotly_chart(fig_ann)
        
        sec("REGULATORY CONTEXT — OPE25")
        st.markdown("""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-family:'Nunito Sans',sans-serif;font-size:0.83rem;color:var(--slate-600)">
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">Business Indicator Component (BIC)</strong><br>
Five-tier marginal structure · BI = 3-year average of annual business indicators · Tier 1: 0-1bn EUR @ 12% · Tier 5: >30bn EUR @ 23%
</div>
<div style="background:var(--white);border:1px solid var(--border);border-radius:10px;padding:14px 16px">
<strong style="color:var(--slate-800)">Internal Loss Multiplier (ILM)</strong><br>
ILM = min(1, ln(exp(1)-1+(LC/BIC)^0.8)) · LC = 15 × average annual losses · Requires 10+ years of loss data · Defaults to 1.0 if insufficient data
</div>
</div>
""", unsafe_allow_html=True)
        
    except ImportError as e:
        st.error(f"Operational Risk module not available: {e}")
        st.info("Ensure operational_risk.py and loss_event_database.py are deployed to backend/")
    except Exception as e:
        st.error(f"Error loading Operational Risk data: {e}")
        st.info("Check that loss event data is available and properly formatted.")

elif page == "Reports":
    st.markdown('<div class="page-title">Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Regulatory Exports · xlsx · csv · Risk Control Use</div>',
                unsafe_allow_html=True)

    c_l,c_r=st.columns([1,2])
    with c_l:
        sec("REPORT TYPE")
        rtype=st.selectbox("",[
            "Capital Summary (RBC20)",
            "SA-CCR Trade Attribution (all 29 fields)",
            "Derivative Portfolio — SA-CCR Summary",
            "Banking Book — A-IRB Detail",
            "CVA Detail — By Counterparty",
            "CCP Exposure Detail",
            "FRTB Market Risk Summary",
            "Full Daily Risk Pack (multi-sheet Excel)",
        ], label_visibility="collapsed")
        sec("FORMAT")
        fmt=st.radio("",["Excel (.xlsx)","CSV (.csv)"],label_visibility="collapsed")
        date_str=run_date.strftime("%Y%m%d")
    with c_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Generate Report"):
            # ── Helper: build SA-CCR attribution across all portfolios ────────
            def _build_saccr_attribution():
                rows=[]
                for p in drv:
                    for tid,tr in p["saccr"].get("trade_results",{}).items():
                        rows.append({
                            "Portfolio ID":          tr.get("portfolio_id",""),
                            "Trade ID":              tr.get("trade_id",""),
                            "Asset Class":           tr.get("asset_class",""),
                            "Instrument Type":       tr.get("instrument_type",""),
                            "Underlying / Sec ID":   tr.get("underlying_security_id","—") or "—",
                            "Currency":              tr.get("notional_ccy",""),
                            "Direction":             tr.get("direction",0),
                            "Current MTM (USD)":     tr.get("current_mtm",0),
                            "RC Allocated (USD)":    tr.get("rc_allocated",0),
                            "RC Portfolio (USD)":    tr.get("rc_portfolio",0),
                            "Add-On Trade (USD)":    tr.get("addon_trade",0),
                            "Add-On Portfolio (USD)":tr.get("addon_portfolio",0),
                            "PFE Trade (USD)":       tr.get("pfe_trade",0),
                            "PFE Portfolio (USD)":   tr.get("pfe_portfolio",0),
                            "Hedging Set":           tr.get("hedging_set",""),
                            "Sub-Hedging Set":       tr.get("sub_hedging_set",""),
                            "Hedging Set Basis":     tr.get("hedging_set_basis",""),
                            "Supervisory Duration":  tr.get("supervisory_duration",0),
                            "Supervisory Factor":    tr.get("supervisory_factor",0),
                            "Maturity Factor":       tr.get("maturity_factor",0),
                            "Supervisory Delta":     tr.get("supervisory_delta",0),
                            "Sign Delta":            tr.get("sign_delta",0),
                            "SA-CCR Notional":       tr.get("saccr_notional",0),
                            "Adjusted Notional":     tr.get("saccr_adjusted_notional",0),
                            "Effective Notional":    tr.get("effective_notional",0),
                            "EAD (Trade)":           tr.get("ead_trade",0),
                            "EAD (Portfolio)":       tr.get("ead_portfolio",0),
                            "Risk Weight (%)":       tr.get("risk_weight_pct",0),
                            "RWA (USD)":             tr.get("rwa",0),
                            "EAD Calc Type":         tr.get("ead_calc_type","SA_CCR"),
                            "Fallback Trace":        tr.get("fallback_trace","") or "",
                            "Trade Date":            tr.get("trade_date",""),
                            "Maturity Date":         tr.get("maturity_date",""),
                            "Credit Quality":        tr.get("credit_quality",""),
                        })
                return pd.DataFrame(rows)

            multi_sheet = False

            if "SA-CCR Trade Attribution" in rtype:
                df_out = _build_saccr_attribution()

            elif "SA-CCR Summary" in rtype:
                rows=[]
                for p in drv:
                    s=p["saccr"]
                    rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                                 "Trades":p["trade_count"],"Notional (USD)":p["gross_notional"],
                                 "RC (USD)":s["rc"],"PFE Mult":s["pfe_mult"],
                                 "AddOn IR":s["addon_ir"],"AddOn FX":s["addon_fx"],
                                 "AddOn Credit":s["addon_credit"],"AddOn Equity":s["addon_equity"],
                                 "AddOn Commodity":s["addon_commodity"],"AddOn Total":s["addon_agg"],
                                 "EAD (USD)":s["ead"],"CCR RWA (USD)":p["rwa_ccr"]})
                df_out=pd.DataFrame(rows)

            elif "A-IRB" in rtype:
                rows=[]
                for p in bbk:
                    for t in p["airb_trades"]:
                        rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                                     "Trade ID":t["trade_id"],"PD (%)":round(t["pd"]*100,4),
                                     "LGD (%)":round(t["lgd"]*100,2),"EAD (USD)":t["ead"],
                                     "Correlation R":t["correlation"],"Capital K":t["capital_k"],
                                     "RWA (USD)":t["rwa"],"EL (USD)":t["el"]})
                df_out=pd.DataFrame(rows)

            elif "CVA Detail" in rtype:
                rows=[]
                for cpty in cva.get("counterparties",[]):
                    rows.append({"Counterparty":cpty.get("counterparty_id",""),
                                 "CVA Method":cpty.get("method",""),
                                 "CVA RWA (USD)":cpty.get("rwa_cva",0),
                                 "CVA Estimate (USD)":cpty.get("cva_estimate",0),
                                 "Hedged":cpty.get("has_hedge",False),
                                 "Fallback Trace":cpty.get("fallback_trace","") or ""})
                df_out=pd.DataFrame(rows) if rows else pd.DataFrame({"Note":["No CVA counterparty data"]})

            elif "CCP" in rtype:
                rows=[]
                for pos in ccp.get("positions",[]):
                    rows.append({"CCP":pos["ccp_name"],
                                 "Qualifying":pos["is_qualifying"],
                                 "Trade EAD (USD)":pos["trade_ead"],
                                 "IM Posted (USD)":pos["im_posted"],
                                 "DFC (USD)":pos["df_contribution"],
                                 "Trade RW":pos["trade_rw"],
                                 "Trade RWA (USD)":pos["rwa_trade"],
                                 "DFC RWA (USD)":pos["rwa_dfc"],
                                 "Total RWA (USD)":pos["rwa_total"],
                                 "Method":pos["method_note"]})
                df_out=pd.DataFrame(rows) if rows else pd.DataFrame({"Note":["No CCP data"]})

            elif "FRTB" in rtype:
                rows=[]
                for p in drv:
                    frtb=p.get("frtb",{})
                    rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                                 "SBM Delta":frtb.get("sbm_delta",0),"SBM Vega":frtb.get("sbm_vega",0),
                                 "SBM Curvature":frtb.get("sbm_curvature",0),
                                 "SBM Total":frtb.get("sbm_total",0),
                                 "IMA ES (10d)":frtb.get("es_10d",0),
                                 "IMA Total":frtb.get("ima_total",0),
                                 "Market Risk Capital":frtb.get("capital",0),
                                 "Market RWA":frtb.get("rwa_market",0)})
                df_out=pd.DataFrame(rows)

            elif "Full Daily Risk Pack" in rtype:
                multi_sheet = True
                _sheets = {
                    "Capital Summary":   pd.DataFrame([{
                        "Run Date":cap["run_date"],"RWA Credit":cap["rwa_credit"],
                        "RWA CCR":cap["rwa_ccr"],"RWA Market":cap["rwa_market"],
                        "RWA CVA":cap.get("rwa_cva",0),"RWA CCP":cap.get("rwa_ccp",0),
                        "RWA Total":cap["rwa_total"],"Floor Triggered":cap["floor_triggered"],
                        "CET1 Ratio (%)":cap["cet1_ratio"]*100,
                        "Tier1 Ratio (%)":cap["tier1_ratio"]*100,
                        "Total Cap Ratio (%)":cap["total_cap_ratio"]*100,
                        "CVA Method":cap.get("cva_method","")}]),
                    "SA-CCR Attribution": _build_saccr_attribution(),
                    "A-IRB Detail":      pd.DataFrame([
                        {"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                         "Trade ID":t["trade_id"],"PD (%)":round(t["pd"]*100,4),
                         "LGD (%)":round(t["lgd"]*100,2),"EAD":t["ead"],
                         "Corr R":t["correlation"],"Capital K":t["capital_k"],
                         "RWA":t["rwa"],"EL":t["el"]}
                        for p in bbk for t in p["airb_trades"]]),
                    "CVA Detail":        pd.DataFrame([
                        {"Counterparty":c.get("counterparty_id",""),
                         "Method":c.get("method",""),"CVA RWA":c.get("rwa_cva",0),
                         "CVA Estimate":c.get("cva_estimate",0),
                         "Hedged":c.get("has_hedge",False),
                         "Fallback":c.get("fallback_trace","") or ""}
                        for c in cva.get("counterparties",[])]),
                    "CCP Detail":        pd.DataFrame([
                        {"CCP":pos["ccp_name"],"QCCP":pos["is_qualifying"],
                         "Trade EAD":pos["trade_ead"],"IM Posted":pos["im_posted"],
                         "DFC":pos["df_contribution"],"Trade RW":pos["trade_rw"],
                         "Trade RWA":pos["rwa_trade"],"DFC RWA":pos["rwa_dfc"],
                         "Total RWA":pos["rwa_total"]}
                        for pos in ccp.get("positions",[])]),
                }
                df_out = _sheets["Capital Summary"]   # for preview
            else:
                df_out=pd.DataFrame({"Note":["Select a report type and click Generate"]})

            # ── Write output ──────────────────────────────────────────────────
            if "Excel" in fmt or multi_sheet:
                buf=io.BytesIO()
                with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                    if multi_sheet:
                        for sheet_name, sheet_df in _sheets.items():
                            sheet_df.to_excel(w, index=False, sheet_name=sheet_name[:31])
                            ws = w.sheets[sheet_name[:31]]
                            ws.set_column(0, len(sheet_df.columns)-1, 20)
                            # Freeze top row
                            ws.freeze_panes(1, 0)
                            # Header format
                            hdr_fmt = w.book.add_format(
                                {"bold":True,"bg_color":"#1E3A5F","font_color":"#FFFFFF",
                                 "border":1,"font_name":"Arial","font_size":10})
                            for ci, col in enumerate(sheet_df.columns):
                                ws.write(0, ci, col, hdr_fmt)
                    else:
                        df_out.to_excel(w, index=False, sheet_name="Risk Report")
                        ws=w.sheets["Risk Report"]
                        ws.set_column(0, len(df_out.columns)-1, 20)
                        ws.freeze_panes(1, 0)
                        hdr_fmt = w.book.add_format(
                            {"bold":True,"bg_color":"#1E3A5F","font_color":"#FFFFFF",
                             "border":1,"font_name":"Arial","font_size":10})
                        for ci, col in enumerate(df_out.columns):
                            ws.write(0, ci, col, hdr_fmt)
                buf.seek(0)
                fname=f"PROMETHEUS_{date_str}.xlsx"
                st.download_button("⬇  Download Excel", buf, fname,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                fname=f"PROMETHEUS_{date_str}.csv"
                st.download_button("⬇  Download CSV", df_out.to_csv(index=False).encode(),
                    fname, "text/csv")

            sec("PREVIEW")
            st.dataframe(df_out, width="stretch", hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# MARKET CALIBRATION
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Market Calibration":
    st.markdown('<div class="page-title">Market Calibration</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Live Parameters · yfinance · Replaces Hardcoded Scalars</div>',
                unsafe_allow_html=True)

    @st.cache_data(ttl=3600, show_spinner=False)
    def _load_cal():
        try:
            from backend.data_sources.calibration import CalibratedParams, _DEFAULT_CACHE_PATH
            import os
            if os.path.exists(_DEFAULT_CACHE_PATH):
                return CalibratedParams.load(_DEFAULT_CACHE_PATH)
            # Fallback: return defaults
            return CalibratedParams(calibration_date="not-calibrated", data_quality="fallback")
        except Exception as e:
            return None

    cal = _load_cal()

    if cal is None:
        st.warning("Calibration unavailable. Ensure yfinance is installed: pip install yfinance")
    else:
        qual_tag = {"full":"t-ok","partial":"t-warn","fallback":"t-bad","skipped":"t-stone"}.get(
            cal.data_quality, "t-stone")
        c1,c2,c3,c4,c5 = st.columns(5)
        kpi(c1,"As Of",      cal.calibration_date,              "Calibration date",   cal.data_quality, qual_tag)
        kpi(c2,"S&P 500",    f"{cal.eq_spot:,.0f}",             "Last close",         "EQ_US",          "t-stone")
        kpi(c3,"Equity Vol", f"{cal.eq_vol_ewma*100:.2f}%",     "EWMA conditional",   "was 20.00%",     qual_tag)
        kpi(c4,"10Y Rate",   f"{cal.ir_spot_10y*100:.3f}%",     "UST 10Y yield",      "IR_10Y",         "t-stone")
        kpi(c5,"VIX",        f"{cal.vix_level:.1f}",            "CBOE VIX",           "Stress indicator",
            "t-ok" if cal.vix_level<25 else ("t-warn" if cal.vix_level<40 else "t-bad"))

        sec("EQUITY PARAMETERS — S&P 500 DERIVED")
        e1,e2,e3,e4 = st.columns(4)
        kpi(e1,"Hist Vol (1Y)",  f"{cal.eq_vol_hist*100:.2f}%",     "252-day realised",    "was 20.00%",  "t-blue")
        kpi(e2,"EWMA Vol",       f"{cal.eq_vol_ewma*100:.2f}%",     "λ=0.94 conditional",  "IMM input",   "t-blue")
        kpi(e3,"Stressed Vol",   f"{cal.eq_vol_stressed*100:.2f}%", "Worst 21d window",    "was 40.00%",  "t-warn")
        kpi(e4,"Annual Drift",   f"{cal.eq_drift*100:+.2f}%",       "Log-return mean×252", "was +5.00%",
            "t-ok" if cal.eq_drift>0 else "t-bad")

        sec("INTEREST RATE PARAMETERS — ORNSTEIN-UHLENBECK MLE (UST 10Y)")
        r1,r2,r3,r4 = st.columns(4)
        kpi(r1,"OU Kappa (κ)",  f"{cal.ir_kappa:.4f}",         "Mean reversion speed",  "was 0.1000",  "t-blue")
        kpi(r2,"OU Theta (θ)",  f"{cal.ir_theta_10y*100:.3f}%","Long-run target rate",  "was 4.500%",  "t-blue")
        kpi(r3,"IR Vol",         f"{cal.ir_vol_hist*100:.4f}%", "Daily rate std×√252",   "was 1.500%",  "t-stone")
        kpi(r4,"IR Stressed",    f"{cal.ir_vol_stressed*100:.4f}%","Worst 21d window",   "was 3.000%",  "t-warn")

        sec("FX & COMMODITY CALIBRATION")
        f1,f2,f3,f4 = st.columns(4)
        kpi(f1,"EUR/USD Vol", f"{cal.fx_vol_eur*100:.2f}%",
            "EWMA", f"Spot {cal.fx_spot_eur:.4f}", "t-stone")
        kpi(f2,"GBP/USD Vol", f"{cal.fx_vol_gbp*100:.2f}%",
            "EWMA", f"Spot {cal.fx_spot_gbp:.4f}", "t-stone")
        kpi(f3,"Energy Vol",  f"{cal.cmdty_energy_vol*100:.2f}%",
            "EWMA crude oil", f"Spot {cal.cmdty_energy_spot:.1f}", "t-stone")
        kpi(f4,"Metals Vol",  f"{cal.cmdty_metals_vol*100:.2f}%",
            "EWMA gold", f"Spot {cal.cmdty_metals_spot:.1f}", "t-stone")

        sec("PARAMETER COMPARISON — LIVE vs HARDCODED")
        _comp = pd.DataFrame([
            {"Parameter": "Equity drift (μ)",     "Hardcoded": "+5.00%",
             "Calibrated": f"{cal.eq_drift*100:+.2f}%",       "Source": "S&P 500 252d log-return mean"},
            {"Parameter": "Equity vol (σ)",        "Hardcoded": "20.00%",
             "Calibrated": f"{cal.eq_vol_ewma*100:.2f}%",     "Source": "EWMA conditional (λ=0.94)"},
            {"Parameter": "Stressed vol",           "Hardcoded": "40.00%",
             "Calibrated": f"{cal.eq_vol_stressed*100:.2f}%", "Source": "Worst 21-day rolling window"},
            {"Parameter": "IR vol (σ_r)",           "Hardcoded": "1.5000%",
             "Calibrated": f"{cal.ir_vol_hist*100:.4f}%",     "Source": "OU MLE on UST 10Y yield changes"},
            {"Parameter": "Mean reversion (κ)",     "Hardcoded": "0.1000",
             "Calibrated": f"{cal.ir_kappa:.4f}",             "Source": "OU MLE regression Δr = a+b×r+ε"},
            {"Parameter": "Long-run rate (θ)",      "Hardcoded": "4.500%",
             "Calibrated": f"{cal.ir_theta_10y*100:.3f}%",    "Source": "θ = -a/b from OLS regression"},
            {"Parameter": "EUR/USD vol",            "Hardcoded": "8.00%",
             "Calibrated": f"{cal.fx_vol_eur*100:.2f}%",      "Source": "EWMA on EURUSD daily returns"},
            {"Parameter": "Energy commodity vol",   "Hardcoded": "30.00%",
             "Calibrated": f"{cal.cmdty_energy_vol*100:.2f}%","Source": "EWMA on WTI crude CL=F"},
        ])
        st.dataframe(_comp, width="stretch", hide_index=True)

        sec("CROSS-ASSET CORRELATION MATRIX — EWMA PAIRWISE (λ=0.94)")
        _labels = ["EQ","FX","IR","CR","CMDTY","Market"]
        _mat    = cal.correlation_matrix
        fig_corr = go.Figure(go.Heatmap(
            z=_mat, x=_labels, y=_labels,
            colorscale=[[0,"#1e40af"],[0.5,"#f7f6f3"],[1,"#991b1b"]],
            zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in _mat],
            texttemplate="%{text}",
            textfont=dict(family="JetBrains Mono",size=11),
            showscale=True,
        ))
        fig_corr.update_layout(**PLOT(380,10))
        st.plotly_chart(fig_corr)

        if cal.fetch_log:
            sec("DATA FETCH LOG")
            _log_df = pd.DataFrame([{"Factor":k,"Status":v} for k,v in cal.fetch_log.items()])
            st.dataframe(_log_df, width="stretch", hide_index=True)

        st.caption(
            "Calibration refreshes every 8 hours (JSON cache). Live data via yfinance. "
            "Falls back to hardcoded defaults per ticker on any fetch failure. "
            "Correlations via EWMA (λ=0.94, RiskMetrics standard). "
            "Skip calibration in CI: PROMETHEUS_SKIP_CALIBRATION=1."
        )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid var(--stone-200);'
    f'display:flex;justify-content:space-between;align-items:center">'
    f'<span style="font-family:DM Serif Display,serif;color:var(--stone-300);font-size:1rem">⬡ PROMETHEUS</span>'
    f'<span style="font-family:JetBrains Mono;font-size:0.63rem;color:var(--stone-300);letter-spacing:0.08em">'
    f'{run_date.strftime("%d %b %Y")} · CRE52 · CRE53 · CRE31 · MAR21-33 · MAR50 · RBC20 · CONFIDENTIAL'
    f'</span></div>',
    unsafe_allow_html=True)
