"""
PROMETHEUS Risk Platform — Premium Light Dashboard
Aesthetic: Refined Institutional Light · Warm whites · Deep slate · Crimson accents
Typography: Playfair Display (titles) · IBM Plex Mono (numbers) · Inter (body)
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

st.set_page_config(
    page_title="PROMETHEUS · Risk Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --cream:      #fafaf7;
  --white:      #ffffff;
  --stone-50:   #f8f7f4;
  --stone-100:  #f0ede8;
  --stone-200:  #e4dfd7;
  --stone-300:  #cfc8bd;
  --slate-500:  #64748b;
  --slate-600:  #475569;
  --slate-700:  #334155;
  --slate-900:  #0f172a;
  --crimson:    #b91c1c;
  --crimson-lt: #dc2626;
  --crimson-bg: rgba(185,28,28,0.06);
  --blue:       #1d4ed8;
  --blue-lt:    #3b82f6;
  --blue-bg:    rgba(29,78,216,0.06);
  --green:      #15803d;
  --green-bg:   rgba(21,128,61,0.07);
  --amber:      #b45309;
  --amber-bg:   rgba(180,83,9,0.07);
  --teal:       #0f766e;
  --indigo:     #4338ca;
  --gold:       #92400e;
  --border:     #e4dfd7;
  --shadow-sm:  0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md:  0 4px 12px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04);
}

/* ── Global ── */
.stApp { background: var(--stone-50) !important; font-family: 'Inter', sans-serif; }
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
  font-family: 'Inter', sans-serif !important; font-weight: 500 !important;
  letter-spacing: 0.02em !important; padding: 0.5rem 1.4rem !important;
  box-shadow: var(--shadow-sm) !important; transition: all 0.15s !important;
}
.stButton > button:hover { background: var(--slate-700) !important; }
.stDownloadButton > button {
  background: var(--white) !important; border: 1.5px solid var(--slate-300) !important;
  color: var(--slate-700) !important; border-radius: 8px !important;
}

/* ── Metrics ── */
[data-testid="stMetricValue"] { color: var(--slate-900) !important; font-family: 'IBM Plex Mono', monospace !important; }
[data-testid="stMetricLabel"] { color: var(--slate-500) !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.05em; }

/* ── Dividers ── */
hr { border-color: var(--stone-200) !important; margin: 1rem 0 !important; }

/* ── Info/Success/Error banners ── */
.stAlert { border-radius: 8px !important; border-left-width: 3px !important; }

/* ── Custom Components ── */
.wordmark {
  font-family: 'Playfair Display', serif;
  font-size: 1.4rem; font-weight: 700;
  color: var(--slate-900); letter-spacing: 0.02em;
}
.wordmark span { color: var(--crimson); }
.submark {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.62rem; color: var(--slate-500);
  letter-spacing: 0.14em; text-transform: uppercase; margin-top: -3px;
}

.page-title {
  font-family: 'Playfair Display', serif;
  font-size: 1.8rem; font-weight: 700;
  color: var(--slate-900); line-height: 1.15; margin-bottom: 0;
}
.page-sub {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.70rem; color: var(--slate-500);
  letter-spacing: 0.09em; text-transform: uppercase; margin-bottom: 1.5rem;
}

/* KPI card */
.kpi {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 18px 14px;
  box-shadow: var(--shadow-sm);
  position: relative; overflow: hidden;
}
.kpi::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--crimson), transparent);
  opacity: 0.4;
}
.kpi-sup  { font-family:'IBM Plex Mono',monospace; font-size:0.62rem; font-weight:600; letter-spacing:0.12em; text-transform:uppercase; color:var(--slate-400); margin-bottom:5px; }
.kpi-val  { font-family:'IBM Plex Mono',monospace; font-size:1.75rem; font-weight:600; color:var(--slate-900); line-height:1.1; margin-bottom:3px; }
.kpi-lbl  { font-size:0.79rem; color:var(--slate-500); margin-bottom:7px; }
.kpi-tag  { display:inline-block; font-family:'IBM Plex Mono',monospace; font-size:0.64rem; font-weight:500; padding:2px 7px; border-radius:4px; }
.t-ok     { background:var(--green-bg);  color:var(--green); }
.t-warn   { background:var(--amber-bg);  color:var(--amber); }
.t-bad    { background:var(--crimson-bg);color:var(--crimson); }
.t-blue   { background:var(--blue-bg);   color:var(--blue); }
.t-stone  { background:var(--stone-100); color:var(--slate-600); }

/* Section header */
.sh { display:flex; align-items:center; gap:12px; margin:26px 0 13px; }
.sh-line { flex:1; height:1px; background:var(--stone-200); }
.sh-text { font-family:'IBM Plex Mono',monospace; font-size:0.66rem; font-weight:600; color:var(--slate-400); letter-spacing:0.13em; text-transform:uppercase; white-space:nowrap; }

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
.lt  { font-family:'IBM Plex Mono',monospace; font-size:0.62rem; color:var(--slate-400); margin-top:2px; }
.lv  { font-family:'IBM Plex Mono',monospace; font-size:0.80rem; color:var(--slate-600); text-align:right; }

/* Regulatory tag sidebar */
.reg-row { display:flex; justify-content:space-between; padding:5px 8px;
  font-size:0.75rem; border-bottom:1px solid var(--stone-100); }

/* Floor banner */
.floor-ok {
  background: var(--green-bg); border:1px solid rgba(21,128,61,0.18);
  border-radius:8px; padding:11px 16px; font-size:0.83rem; color:var(--green);
}
.floor-warn {
  background: var(--crimson-bg); border:1px solid rgba(185,28,28,0.18);
  border-radius:8px; padding:11px 16px; font-size:0.83rem; color:var(--crimson);
}
</style>
""", unsafe_allow_html=True)

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "blue":   "#1d4ed8",
    "indigo": "#4338ca",
    "teal":   "#0f766e",
    "green":  "#15803d",
    "amber":  "#b45309",
    "red":    "#b91c1c",
    "crimson":"#991b1b",
    "slate":  "#64748b",
    "gold":   "#92400e",
}
CHART_COLS = [C["blue"], C["indigo"], C["teal"], C["gold"], C["amber"], C["slate"]]

def PLOT(h=360, t=10):
    return dict(
        paper_bgcolor="#ffffff", plot_bgcolor="#fafaf7",
        font_color="#64748b", font_family="IBM Plex Mono", font_size=10,
        height=h, margin=dict(l=20, r=20, t=t, b=20),
        xaxis=dict(gridcolor="#e4dfd7", linecolor="#e4dfd7", tickcolor="#e4dfd7", zeroline=False),
        yaxis=dict(gridcolor="#e4dfd7", linecolor="#e4dfd7", tickcolor="#e4dfd7", zeroline=False),
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
        number={"suffix": "%", "font": {"size": 28, "color": col, "family": "IBM Plex Mono"}},
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

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="wordmark">⬡ PROMET<span>H</span>EUS</div>', unsafe_allow_html=True)
    st.markdown('<div class="submark">Basel III/IV · Risk Intelligence</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    run_date = st.date_input("Valuation Date", value=date.today(), max_value=date.today())
    st.markdown(
        f'<div style="font-family:IBM Plex Mono;font-size:0.65rem;color:#94a3b8;'
        f'margin-top:-8px;margin-bottom:14px">{run_date.strftime("%d %b %Y")}</div>',
        unsafe_allow_html=True)

    page = st.radio("", [
        "Capital Dashboard", "Derivative Portfolios", "Banking Book",
        "Market Risk (FRTB)", "IMM Exposure Profiles",
        "Risk Limits", "Backtesting", "Reports",
    ], label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="font-family:IBM Plex Mono;font-size:0.62rem;color:#94a3b8;'
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
            f'<span style="font-family:IBM Plex Mono;color:{C["crimson"]};'
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
            textfont=dict(family="IBM Plex Mono", size=10),
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            customdata=[fmt_bn(v) for v in vals],
        ))
        fig_pie.add_annotation(
            text=fmt_bn(sum(vals)), x=0.5, y=0.5, showarrow=False,
            font=dict(family="IBM Plex Mono", size=15, color="#0f172a"))
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
            textfont=dict(family="IBM Plex Mono", size=10, color="#64748b"),
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
            f'font-family:IBM Plex Mono;font-size:0.68rem">'
            f'CVA excluded from floor base · CAP10 FAQ1</span></div>',
            unsafe_allow_html=True)

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
    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Gross Notional",fmt_bn(port["gross_notional"]),"Total notional",  "Pre-netting", "t-stone")
    kpi(c2,"SA-CCR EAD",    fmt_bn(port["saccr"]["ead"]), "Exposure at Default","CRE52 α=1.4","t-blue")
    kpi(c3,"IMM EAD",       fmt_bn(imm.get("ead_imm",0)), "Internal Models EAD","CRE53 floor","t-stone")
    kpi(c4,"CCR RWA",       fmt_bn(port["rwa_ccr"]),      "Credit RWA (CCR)",  "CRE51.13",   "t-blue")

    sec("SA-CCR ADD-ON BY ASSET CLASS")
    addons={"Interest Rate":port["saccr"]["addon_ir"],"FX":port["saccr"]["addon_fx"],
            "Credit":port["saccr"]["addon_credit"],"Equity":port["saccr"]["addon_equity"],
            "Commodity":port["saccr"]["addon_commodity"]}
    fig_add = go.Figure(go.Bar(
        x=list(addons.keys()), y=[v/1e6 for v in addons.values()],
        marker=dict(color=CHART_COLS[:5], opacity=0.85),
        text=[f"${v/1e6:.2f}M" for v in addons.values()],
        textposition="outside", textfont=dict(family="IBM Plex Mono",size=10,color="#64748b")))
    fig_add.update_layout(**PLOT(280,10), yaxis_title="USD Millions")
    st.plotly_chart(fig_add)

    sec("ALL DERIVATIVE PORTFOLIOS")
    rows=[]
    for p in drv:
        imm_r = p.get("imm") or {}
        rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                     "Trades":p["trade_count"],"Notional":fmt_bn(p["gross_notional"]),
                     "SA-CCR EAD":fmt_bn(p["saccr"]["ead"]),
                     "IMM EAD":fmt_bn(imm_r.get("ead_imm",0)),
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
    c1,c2,c3,c4 = st.columns(4)
    kpi(c1,"Total EAD",    fmt_bn(pdata["total_ead"]),"Exposure at Default","A-IRB","t-blue")
    kpi(c2,"Total RWA",    fmt_bn(pdata["total_rwa"]),"Risk-Weighted Assets","CRE31.4","t-blue")
    kpi(c3,"Expected Loss",fmt_bn(pdata["total_el"]), "PD × LGD × EAD","EL","t-warn")
    sf=pdata["el_shortfall"]
    kpi(c4,"EL Shortfall", fmt_bn(sf),"vs Provisions (CRE35)",
        "Shortfall" if sf>0 else "Provisioned","t-bad" if sf>0 else "t-ok")

    sec("EXPOSURE DETAIL — TRADE LEVEL")
    tdf = pd.DataFrame(pdata["airb_trades"])
    tdf["pd"]         =tdf["pd"].map(lambda x:f"{x*100:.3f}%")
    tdf["lgd"]        =tdf["lgd"].map(lambda x:f"{x*100:.1f}%")
    for c2_ in ["ead","rwa","el"]: tdf[c2_]=tdf[c2_].map(fmt_bn)
    tdf["correlation"]=tdf["correlation"].map(lambda x:f"{x:.4f}")
    tdf["capital_k"]  =tdf["capital_k"].map(lambda x:f"{x*100:.3f}%")
    tdf.columns=["Trade ID","PD","LGD","EAD","RWA","EL","Corr R","Capital K"]
    st.dataframe(tdf, width="stretch", hide_index=True)

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
            f'<div style="font-family:IBM Plex Mono;font-size:0.66rem;color:#94a3b8;'
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

    sec("P&L vs VAR — 250 DAY LOOKBACK")
    rng=np.random.default_rng(42)
    days=list(range(1,251)); pnl=rng.normal(0,50000,250); var=np.abs(rng.normal(50000,10000,250))
    exc_x=[d for d,p,v in zip(days,pnl,var) if -p>v]
    exc_y=[pnl[d-1]/1e3 for d in exc_x]
    fig_bt=go.Figure()
    fig_bt.add_trace(go.Bar(x=days,y=pnl/1e3,name="Daily P&L",
        marker_color=[C["red"] if p<0 else C["blue"] for p in pnl],opacity=0.60))
    fig_bt.add_trace(go.Scatter(x=days,y=-var/1e3,name="−VaR Boundary",
        line=dict(color=C["amber"],dash="dash",width=1.5)))
    fig_bt.add_trace(go.Scatter(x=exc_x,y=exc_y,mode="markers",name="Exception",
        marker=dict(color=C["red"],size=8,symbol="x-thin",line=dict(width=2,color=C["red"]))))
    fig_bt.update_layout(**PLOT(400,10),
        xaxis_title="Trading Day",yaxis_title="P&L (USD 000s)",
        legend=LEG())
    st.plotly_chart(fig_bt)

# ══════════════════════════════════════════════════════════════════════════════
# 8 · REPORTS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Reports":
    st.markdown('<div class="page-title">Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">Regulatory Exports · xlsx · csv · Risk Control Use</div>',
                unsafe_allow_html=True)

    c_l,c_r=st.columns([1,2])
    with c_l:
        sec("REPORT TYPE")
        rtype=st.selectbox("",["Capital Summary (RBC20)","Derivative Portfolio — SA-CCR Detail",
            "Banking Book — A-IRB Detail","FRTB Market Risk Summary","Full Daily Risk Pack"],
            label_visibility="collapsed")
        sec("FORMAT")
        fmt=st.radio("",["Excel (.xlsx)","CSV (.csv)"],label_visibility="collapsed")
        date_str=run_date.strftime("%Y%m%d")
    with c_r:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("Generate Report"):
            if "Capital" in rtype:
                df_out=pd.DataFrame([{"Run Date":cap["run_date"],
                    "RWA Credit":cap["rwa_credit"],"RWA CCR":cap["rwa_ccr"],
                    "RWA Market":cap["rwa_market"],"RWA CVA":cap.get("rwa_cva",0),
                    "RWA CCP":cap.get("rwa_ccp",0),"RWA Total":cap["rwa_total"],
                    "CET1 Ratio (%)":cap["cet1_ratio"]*100,
                    "Total Cap Ratio (%)":cap["total_cap_ratio"]*100,
                    "Floor Triggered":cap["floor_triggered"],
                    "CVA Method":cap.get("cva_method","")}])
            elif "SA-CCR" in rtype:
                rows=[]
                for p in drv:
                    s=p["saccr"]
                    rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                                 "Trades":p["trade_count"],"Notional":p["gross_notional"],
                                 "RC":s["rc"],"PFE Mult":s["pfe_mult"],"AddOn IR":s["addon_ir"],
                                 "AddOn FX":s["addon_fx"],"AddOn Credit":s["addon_credit"],
                                 "AddOn Equity":s["addon_equity"],"AddOn Comm":s["addon_commodity"],
                                 "AddOn Total":s["addon_agg"],"EAD":s["ead"],"CCR RWA":p["rwa_ccr"]})
                df_out=pd.DataFrame(rows)
            elif "A-IRB" in rtype:
                rows=[]
                for p in bbk:
                    for t in p["airb_trades"]:
                        rows.append({"Portfolio":p["portfolio_id"],"Counterparty":p["counterparty"],
                                     "Trade ID":t["trade_id"],"PD (%)":t["pd"]*100,"LGD (%)":t["lgd"]*100,
                                     "EAD":t["ead"],"Corr R":t["correlation"],"Capital K":t["capital_k"],
                                     "RWA":t["rwa"],"EL":t["el"]})
                df_out=pd.DataFrame(rows)
            else:
                rows=[]
                for p in drv: rows.append({"Portfolio":p["portfolio_id"],"Type":"DERIVATIVE",
                    "EAD":p["saccr"]["ead"],"CCR RWA":p["rwa_ccr"],"Market RWA":p["rwa_market"]})
                for p in bbk: rows.append({"Portfolio":p["portfolio_id"],"Type":"BANKING_BOOK",
                    "EAD":p["total_ead"],"Credit RWA":p["total_rwa"]})
                df_out=pd.DataFrame(rows)

            if "Excel" in fmt:
                buf=io.BytesIO()
                with pd.ExcelWriter(buf,engine="xlsxwriter") as w:
                    df_out.to_excel(w,index=False,sheet_name="Risk Report")
                    w.sheets["Risk Report"].set_column(0,len(df_out.columns)-1,20)
                buf.seek(0)
                fname=f"PROMETHEUS_{date_str}.xlsx"
                st.download_button("⬇  Download Excel",buf,fname,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                fname=f"PROMETHEUS_{date_str}.csv"
                st.download_button("⬇  Download CSV",df_out.to_csv(index=False).encode(),fname,"text/csv")
            sec("PREVIEW")
            st.dataframe(df_out,width="stretch",hide_index=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid var(--stone-200);'
    f'display:flex;justify-content:space-between;align-items:center">'
    f'<span style="font-family:Playfair Display,serif;color:var(--stone-300);font-size:1rem">⬡ PROMETHEUS</span>'
    f'<span style="font-family:IBM Plex Mono;font-size:0.63rem;color:var(--stone-300);letter-spacing:0.08em">'
    f'{run_date.strftime("%d %b %Y")} · CRE52 · CRE53 · CRE31 · MAR21-33 · MAR50 · RBC20 · CONFIDENTIAL'
    f'</span></div>',
    unsafe_allow_html=True)
