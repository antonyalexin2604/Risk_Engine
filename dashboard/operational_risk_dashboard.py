"""
PROMETHEUS Risk Platform
Operational Risk Dashboard — FIXED VERSION

FILE PATH: dashboard/operational_risk_dashboard.py

FIXES:
1. DateTime conversion error resolved
2. Font visibility improved with stronger CSS
3. All charts with high-contrast styling
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.engines.operational_risk import (
    BusinessIndicatorInput,
    compute_sma_capital,
    analyze_losses_by_event_type,
    analyze_losses_by_business_line,
    BASEL_EVENT_TYPES,
    BASEL_BUSINESS_LINES,
)
from backend.data_sources.loss_event_database import get_loss_event_database


# ═════════════════════════════════════════════════════════════════════════════
# LIGHT THEME — Institutional palette aligned with main PROMETHEUS dashboard
# ═════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:wght@400;600&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --cream:       #fafaf8;
  --white:       #ffffff;
  --stone-100:   #eeebe5;
  --stone-200:   #dedad1;
  --slate-400:   #94a3b8;
  --slate-500:   #64748b;
  --slate-600:   #475569;
  --slate-700:   #334155;
  --slate-900:   #0f172a;
  --crimson:     #991b1b;
  --blue:        #1e40af;
  --teal:        #0f766e;
  --green:       #166534;
  --amber:       #92400e;
  --border:      #dedad1;
  --shadow-sm:   0 1px 3px rgba(15,23,42,0.07), 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md:   0 4px 14px rgba(15,23,42,0.09), 0 2px 4px rgba(15,23,42,0.04);
}

/* ── Global ── */
.stApp { background: var(--cream) !important; font-family: 'Inter', sans-serif; }
.main .block-container { padding: 1.8rem 2.2rem 3rem !important; max-width: 100% !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--white) !important;
  border-right: 1px solid var(--border) !important;
  box-shadow: 2px 0 8px rgba(15,23,42,0.04) !important;
}
section[data-testid="stSidebar"] * {
  color: var(--slate-600) !important;
  font-weight: 400 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
  color: var(--slate-900) !important;
  font-weight: 500 !important;
}

/* ── Text ── */
h1, h2, h3 { color: var(--slate-900) !important; font-weight: 400 !important; }
h4, h5, h6 { color: var(--slate-700) !important; font-weight: 500 !important; }
p, li       { color: var(--slate-600) !important; font-weight: 400 !important; }
label       { color: var(--slate-500) !important; font-weight: 400 !important; }
span, div   { font-weight: inherit !important; }
.stMarkdown p, .stMarkdown span, .stMarkdown li {
  color: var(--slate-600) !important; font-weight: 400 !important;
}

/* ── Metrics ── */
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
  color: var(--slate-900) !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-weight: 600 !important;
  font-size: 1.55rem !important;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] * {
  color: var(--slate-500) !important;
  font-size: 0.75rem !important;
  font-weight: 500 !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] * {
  font-weight: 400 !important;
  font-size: 0.80rem !important;
}

/* ── DataFrames ── */
.stDataFrame { border-radius: 10px !important; overflow: hidden; }
[data-testid="stDataFrameResizable"] thead th,
.stDataFrame thead th {
  background-color: #f1ede6 !important;
  color: var(--slate-700) !important;
  font-weight: 600 !important;
  font-size: 0.75rem !important;
  border-bottom: 1px solid var(--border) !important;
}
[data-testid="stDataFrameResizable"] tbody td,
.stDataFrame tbody td {
  color: var(--slate-600) !important;
  font-weight: 400 !important;
  font-size: 0.80rem !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab"] {
  color: var(--slate-500) !important;
  font-weight: 500 !important;
  font-size: 0.85rem !important;
}
.stTabs [aria-selected="true"] {
  color: var(--slate-900) !important;
  font-weight: 600 !important;
  border-bottom: 2px solid var(--crimson) !important;
}

/* ── Buttons ── */
.stButton > button {
  background: var(--slate-900) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  font-size: 0.85rem !important;
  padding: 0.5rem 1.4rem !important;
  box-shadow: var(--shadow-sm) !important;
}
.stButton > button:hover { background: var(--slate-700) !important; }
.stDownloadButton > button {
  background: var(--white) !important;
  border: 1.5px solid var(--stone-200) !important;
  color: var(--slate-700) !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  font-size: 0.85rem !important;
}

/* ── Input labels ── */
.stSelectbox label, .stMultiSelect label, .stTextInput label,
.stNumberInput label, .stDateInput label, .stRadio label {
  color: var(--slate-500) !important;
  font-weight: 500 !important;
  font-size: 0.73rem !important;
  text-transform: uppercase;
  letter-spacing: 0.07em;
}
.stSelectbox > div > div {
  background: var(--white) !important;
  border: 1px solid var(--border) !important;
  color: var(--slate-700) !important;
  border-radius: 8px !important;
}

/* ── Alerts ── */
.stAlert { border-radius: 8px !important; border-left-width: 3px !important;
  font-weight: 400 !important; font-size: 0.85rem !important; }

/* ── Captions ── */
.stCaption, [data-testid="stCaptionContainer"],
.stCaption *, [data-testid="stCaptionContainer"] * {
  color: var(--slate-400) !important;
  font-weight: 400 !important;
  font-size: 0.75rem !important;
}

/* ── Dividers ── */
hr { border-color: var(--stone-200) !important; margin: 1rem 0 !important; }

/* ── Page header ── */
.op-title {
  font-family: 'DM Serif Display', serif;
  font-size: 2.1rem; font-weight: 400;
  color: var(--slate-900); line-height: 1.05; margin-bottom: 0;
  letter-spacing: -0.01em;
}
.op-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem; color: var(--slate-500);
  letter-spacing: 0.11em; text-transform: uppercase; margin-bottom: 1.8rem;
  font-weight: 300;
}

/* ── Section dividers ── */
.sh { display:flex; align-items:center; gap:14px; margin:28px 0 14px; }
.sh-line { flex:1; height:1px; background:var(--stone-200); }
.sh-text { font-family:'JetBrains Mono',monospace; font-size:0.63rem; font-weight:400;
  color:var(--slate-400); letter-spacing:0.16em; text-transform:uppercase; white-space:nowrap; }
</style>
""", unsafe_allow_html=True)


def apply_light_theme(fig, h=360):
    """Apply refined institutional light theme to Plotly figures (matches main dashboard PLOT())."""
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f7f6f3",
        font=dict(family="JetBrains Mono, Inter, sans-serif", size=10, color="#64748b"),
        title_font=dict(size=12, color="#334155", family="Inter, sans-serif"),
        xaxis=dict(
            title_font=dict(size=11, color="#64748b", family="Inter, sans-serif"),
            tickfont=dict(size=9, color="#94a3b8", family="JetBrains Mono, monospace"),
            gridcolor="#dedad1", linecolor="#dedad1", linewidth=1, zeroline=False,
        ),
        yaxis=dict(
            title_font=dict(size=11, color="#64748b", family="Inter, sans-serif"),
            tickfont=dict(size=9, color="#94a3b8", family="JetBrains Mono, monospace"),
            gridcolor="#dedad1", linecolor="#dedad1", linewidth=1, zeroline=False,
        ),
        legend=dict(
            font=dict(size=10, color="#475569", family="JetBrains Mono, monospace"),
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#dedad1", borderwidth=1,
        ),
        hoverlabel=dict(
            bgcolor="#ffffff", font_color="#334155",
            font_family="JetBrains Mono", font_size=11, bordercolor="#dedad1",
        ),
        height=h,
        margin=dict(l=24, r=24, t=10, b=24),
    )
    return fig


def get_loss_timeline_fixed(loss_events):
    """
    Create timeline DataFrame with PROPER datetime conversion.
    
    FIXES: datetime accessor error by ensuring dates are datetime objects.
    """
    if not loss_events:
        return pd.DataFrame()
    
    data = []
    for e in loss_events:
        # Convert date objects to datetime for pandas
        booking_date = e.booking_date
        if isinstance(booking_date, date) and not isinstance(booking_date, datetime):
            booking_date = datetime.combine(booking_date, datetime.min.time())
        
        data.append({
            "date": booking_date,
            "event_id": e.event_id,
            "event_type": BASEL_EVENT_TYPES.get(e.event_type, e.event_type),
            "business_line": BASEL_BUSINESS_LINES.get(e.business_line, e.business_line),
            "net_loss": e.net_loss_amount,
            "gross_loss": e.gross_loss_amount,
        })
    
    df = pd.DataFrame(data)
    
    # CRITICAL: Ensure date column is datetime
    df["date"] = pd.to_datetime(df["date"])
    
    df = df.sort_values("date")
    
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Operational Risk — PROMETHEUS",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown('<div class="op-title">Operational Risk</div>', unsafe_allow_html=True)
st.markdown('<div class="op-sub">Basel III SMA (OPE25) · BIC × ILM · Business Indicator Component</div>',
            unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Load Data with Error Handling
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_business_indicator_data():
    """Load BI data from file or use defaults."""
    try:
        import json
        bi_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "backend/data_sources/business_indicator_data.json"
        )
        
        if os.path.exists(bi_file):
            with open(bi_file, 'r') as f:
                data = json.load(f)
            
            bi_inputs = []
            for bi_dict in data.get("business_indicators", []):
                bi = BusinessIndicatorInput(
                    year=bi_dict["year"],
                    interest_income=bi_dict.get("interest_income", 0.0),
                    interest_expense=bi_dict.get("interest_expense", 0.0),
                    dividend_income=bi_dict.get("dividend_income", 0.0),
                    services_income=bi_dict.get("services_income", 0.0),
                    services_expense=bi_dict.get("services_expense", 0.0),
                    financial_income=bi_dict.get("financial_income", 0.0),
                    financial_expense=bi_dict.get("financial_expense", 0.0),
                    other_operating_income=bi_dict.get("other_operating_income", 0.0),
                    trading_book_pnl=bi_dict.get("trading_book_pnl", 0.0),
                    banking_book_pnl=bi_dict.get("banking_book_pnl", 0.0),
                )
                bi_inputs.append(bi)
            
            return bi_inputs
    except Exception as e:
        st.warning(f"Could not load BI data from file: {e}. Using default data.")
    
    # Default data
    return [
        BusinessIndicatorInput(
            year=2023, interest_income=800, interest_expense=400, dividend_income=80,
            services_income=500, services_expense=150, financial_income=250,
            financial_expense=100, other_operating_income=150, trading_book_pnl=300,
            banking_book_pnl=250,
        ),
        BusinessIndicatorInput(
            year=2024, interest_income=850, interest_expense=425, dividend_income=85,
            services_income=525, services_expense=160, financial_income=265,
            financial_expense=105, other_operating_income=160, trading_book_pnl=320,
            banking_book_pnl=265,
        ),
        BusinessIndicatorInput(
            year=2025, interest_income=900, interest_expense=450, dividend_income=90,
            services_income=550, services_expense=170, financial_income=280,
            financial_expense=110, other_operating_income=170, trading_book_pnl=340,
            banking_book_pnl=280,
        ),
    ]


@st.cache_data
def load_loss_events():
    """Load loss events with error handling."""
    try:
        db = get_loss_event_database()
        events = db.get_all_events()
        return events
    except Exception as e:
        st.error(f"Error loading loss events: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.markdown(
    '<div style="font-family:\'DM Serif Display\',serif;font-size:1.2rem;'
    'color:#0f172a;letter-spacing:0.01em;margin-bottom:2px">⬡ PROMETHEUS</div>'
    '<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.58rem;'
    'color:#94a3b8;letter-spacing:0.19em;text-transform:uppercase;margin-bottom:14px">'
    'Operational Risk · OPE25</div>',
    unsafe_allow_html=True,
)

if st.sidebar.button("↺  Recalculate", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

# Load data with error handling
try:
    bi_inputs = load_business_indicator_data()
    loss_events = load_loss_events()
    
    st.sidebar.metric("📊 Loss Events", len(loss_events))
    
    if loss_events:
        db = get_loss_event_database()
        stats = db.get_summary_statistics()
        st.sidebar.metric("📅 Years Covered", stats["year_range"])
        st.sidebar.metric("💰 Total Net Losses", f"EUR {stats['total_net_loss']:.1f}M")
        st.sidebar.metric("📈 Avg Loss", f"EUR {stats['avg_net_loss']:.2f}M")

except Exception as e:
    st.sidebar.error(f"Error loading data: {e}")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Main Content
# ─────────────────────────────────────────────────────────────────────────────

if not loss_events:
    st.warning(
        "⚠️ **No loss events in database.** "
        "Run `operational_loss_generator.py` to generate synthetic data."
    )
    st.info("""
    **Steps to generate data:**
    ```bash
    cd backend/data_generators
    python operational_loss_generator.py
    mv loss_events.json ../data_sources/loss_events.json
    ```
    """)
    st.stop()

# Compute SMA Capital
try:
    sma_result = compute_sma_capital(bi_inputs, loss_events)
except Exception as e:
    st.error(f"Error computing SMA capital: {e}")
    st.stop()

# ── KPI card helper (matches app.py) ─────────────────────────────────────────
def _kpi(col, sup, val, lbl, tag, tag_cls="t-ok"):
    with col:
        st.markdown(
            f'<div style="background:#fff;border:1px solid #dedad1;border-radius:12px;'
            f'padding:20px 20px 16px;box-shadow:0 1px 3px rgba(15,23,42,0.07);'
            f'position:relative;overflow:hidden;">'
            f'<div style="position:absolute;top:0;left:0;right:0;height:2px;'
            f'background:linear-gradient(90deg,#991b1b 0%,rgba(153,27,27,0.12) 65%,transparent 100%);'
            f'border-radius:12px 12px 0 0;"></div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:0.60rem;font-weight:500;'
            f'letter-spacing:0.15em;text-transform:uppercase;color:#94a3b8;margin-bottom:5px">{sup}</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:1.62rem;font-weight:600;'
            f'color:#0f172a;line-height:1.05;margin-bottom:4px">{val}</div>'
            f'<div style="font-family:Inter,sans-serif;font-size:0.78rem;color:#64748b;'
            f'margin-bottom:8px;font-weight:400">{lbl}</div>'
            f'<span style="display:inline-block;font-family:JetBrains Mono,monospace;font-size:0.64rem;'
            f'font-weight:500;padding:2px 8px;border-radius:5px;letter-spacing:0.03em;'
            + {
                "t-ok":   "background:rgba(22,101,52,0.065);color:#166534;border:1px solid rgba(22,101,52,0.14)",
                "t-warn": "background:rgba(146,64,14,0.065);color:#92400e;border:1px solid rgba(146,64,14,0.14)",
                "t-bad":  "background:rgba(153,27,27,0.055);color:#991b1b;border:1px solid rgba(153,27,27,0.14)",
                "t-blue": "background:rgba(30,64,175,0.055);color:#1e40af;border:1px solid rgba(30,64,175,0.14)",
                "t-stone":"background:#eeebe5;color:#475569;border:1px solid #dedad1",
            }.get(tag_cls, "background:#eeebe5;color:#475569;border:1px solid #dedad1")
            + f'">{tag}</span></div>',
            unsafe_allow_html=True)

def _sec(label):
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:14px;margin:28px 0 14px">'
        f'<div style="flex:1;height:1px;background:#dedad1"></div>'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:0.63rem;font-weight:400;'
        f'color:#94a3b8;letter-spacing:0.16em;text-transform:uppercase;white-space:nowrap">{label}</div>'
        f'<div style="flex:1;height:1px;background:#dedad1"></div></div>',
        unsafe_allow_html=True)

# ── KPI row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
_kpi(c1, "Business Indicator",  f"EUR {sma_result.business_indicator:,.0f}M",
     "3-year average BI", "OPE25.15", "t-blue")
_kpi(c2, "BIC",                 f"EUR {sma_result.bic:,.1f}M",
     "Business Indicator Component", "OPE25.20", "t-blue")
_kpi(c3, "ILM",                 f"{sma_result.ilm:.3f}",
     "Internal Loss Multiplier", "Capped 1.0",
     "t-ok" if sma_result.ilm < 1 else "t-warn")
_kpi(c4, "Op Risk Capital",     f"EUR {sma_result.operational_risk_capital:,.1f}M",
     "BIC × ILM", "OPE25", "t-blue")

st.markdown("")
r1, r2, r3 = st.columns(3)
_kpi(r1, "Op Risk RWA",   f"EUR {sma_result.rwa_operational:,.0f}M",
     "Capital × 12.5", "RBC20.9", "t-blue")
_kpi(r2, "Loss Component",f"EUR {sma_result.loss_component:,.1f}M",
     "15 × Avg Annual Losses", "OPE25.12", "t-stone")
_kpi(r3, "Loss Years",    f"{sma_result.years_of_loss_data}",
     "Years of loss data",
     "10 req for LC" if sma_result.years_of_loss_data < 10 else "✓ Sufficient",
     "t-warn" if sma_result.years_of_loss_data < 10 else "t-ok")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "SMA Breakdown",
    "Loss Analysis",
    "Loss Timeline",
    "Event Details",
])

# ── CHART COLOURS (institutional palette) ─────────────────────────────────────
_COLS = ["#1e40af","#0f766e","#92400e","#991b1b","#78350f","#166534","#3730a3"]

# ═════════════════════════════════════════════════════════════════════════════
# Tab 1: SMA Breakdown
# ═════════════════════════════════════════════════════════════════════════════

with tab1:
    _sec("BUSINESS INDICATOR COMPONENT (BIC) — TIERED APPROACH")
    st.markdown(
        f'<p style="font-family:JetBrains Mono,monospace;font-size:0.72rem;'
        f'color:#64748b">3-year average BI: <strong style="color:#0f172a">'
        f'EUR {sma_result.business_indicator:,.1f}M</strong></p>',
        unsafe_allow_html=True)

    bi_bn = sma_result.business_indicator / 1000
    tier_data = []
    tiers = [
        ("Tier 1", 0, 1,          0.12),
        ("Tier 2", 1, 3,          0.15),
        ("Tier 3", 3, 10,         0.18),
        ("Tier 4", 10, 30,        0.21),
        ("Tier 5", 30, float('inf'), 0.23),
    ]
    for tier_name, lower, upper, coef in tiers:
        if bi_bn > lower:
            mb = min(bi_bn, upper) - lower
            tier_data.append({
                "Tier": tier_name,
                "Range (EUR bn)": f"{lower}–{upper if upper != float('inf') else '∞'}",
                "Coefficient": f"{coef:.0%}",
                "Marginal BI (bn)": f"{mb:.2f}",
                "Marginal BIC (M)": f"{mb * coef * 1000:.1f}",
            })
    st.dataframe(pd.DataFrame(tier_data), use_container_width=True, hide_index=True)

    _sec("OPERATIONAL RISK CAPITAL WATERFALL")
    capital_breakdown = pd.DataFrame({
        "Component": ["BIC", "× ILM", "= Op Risk Capital", "× 12.5", "= Op Risk RWA"],
        "Value": [
            f"EUR {sma_result.bic:,.1f}M",
            f"{sma_result.ilm:.3f}",
            f"EUR {sma_result.operational_risk_capital:,.1f}M",
            "12.5×",
            f"EUR {sma_result.rwa_operational:,.0f}M",
        ],
    })
    st.dataframe(capital_breakdown, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# Tab 2: Loss Analysis
# ═════════════════════════════════════════════════════════════════════════════

with tab2:
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        _sec("BY EVENT TYPE")
        event_type_df = analyze_losses_by_event_type(loss_events)
        if not event_type_df.empty:
            fig = px.bar(
                event_type_df,
                x="event_type", y="total_net_loss",
                labels={"total_net_loss": "Net Loss (EUR M)", "event_type": "Event Type"},
                text="total_net_loss",
            )
            fig = apply_light_theme(fig, h=380)
            fig.update_traces(
                marker_color="#991b1b",
                marker_line_color="#dedad1", marker_line_width=1,
                texttemplate="EUR %{text:.1f}M", textposition="outside",
                textfont=dict(size=10, color="#64748b", family="JetBrains Mono"),
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(event_type_df, use_container_width=True, hide_index=True)

    with col_chart2:
        _sec("BY BUSINESS LINE")
        business_line_df = analyze_losses_by_business_line(loss_events)
        if not business_line_df.empty:
            fig = px.pie(
                business_line_df,
                values="total_net_loss", names="business_line",
            )
            fig = apply_light_theme(fig, h=380)
            fig.update_traces(
                textinfo="percent+label",
                textfont=dict(size=10, color="#334155", family="JetBrains Mono"),
                marker=dict(
                    colors=_COLS[:len(business_line_df)],
                    line=dict(color="#ffffff", width=2),
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(business_line_df, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# Tab 3: Loss Timeline
# ═════════════════════════════════════════════════════════════════════════════

with tab3:
    try:
        timeline_df = get_loss_timeline_fixed(loss_events)

        if not timeline_df.empty:
            _sec("ANNUAL AGGREGATE OPERATIONAL LOSSES")
            annual_losses = (
                timeline_df.groupby(timeline_df["date"].dt.year)["net_loss"]
                .sum().reset_index()
            )
            annual_losses.columns = ["Year", "Net Loss (EUR M)"]

            fig = px.bar(
                annual_losses, x="Year", y="Net Loss (EUR M)",
                text="Net Loss (EUR M)",
            )
            fig = apply_light_theme(fig, h=340)
            fig.update_traces(
                marker_color="#991b1b",
                marker_line_color="#dedad1", marker_line_width=1,
                texttemplate="EUR %{text:.1f}M", textposition="outside",
                textfont=dict(size=10, color="#64748b", family="JetBrains Mono"),
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            _sec("INDIVIDUAL LOSS EVENTS — SCATTER")
            fig_scatter = px.scatter(
                timeline_df,
                x="date", y="net_loss",
                color="event_type", size="gross_loss",
                hover_data=["event_id", "business_line"],
                labels={"net_loss": "Net Loss (EUR M)", "date": "Date"},
                color_discrete_sequence=_COLS,
            )
            fig_scatter = apply_light_theme(fig_scatter, h=380)
            fig_scatter.update_traces(
                marker=dict(line=dict(width=1, color="#ffffff"), sizemin=5)
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    except Exception as e:
        st.error(f"Error loading timeline data: {e}")
        st.info("Check that loss event data is available and properly formatted.")


# ═════════════════════════════════════════════════════════════════════════════
# Tab 4: Event Details
# ═════════════════════════════════════════════════════════════════════════════

with tab4:
    _sec("LOSS EVENT DATABASE")
    try:
        timeline_df = get_loss_timeline_fixed(loss_events)

        col_filter1, col_filter2, col_filter3 = st.columns(3)
        with col_filter1:
            filter_event_type = st.multiselect(
                "Event Type",
                options=["All"] + list(BASEL_EVENT_TYPES.values()),
                default="All",
            )
        with col_filter2:
            filter_business_line = st.multiselect(
                "Business Line",
                options=["All"] + list(BASEL_BUSINESS_LINES.values()),
                default="All",
            )
        with col_filter3:
            min_loss = st.number_input("Min Loss (EUR M)", min_value=0.0, value=0.0, step=0.1)

        filtered_df = timeline_df.copy()
        if "All" not in filter_event_type:
            filtered_df = filtered_df[filtered_df["event_type"].isin(filter_event_type)]
        if "All" not in filter_business_line:
            filtered_df = filtered_df[filtered_df["business_line"].isin(filter_business_line)]
        if min_loss > 0:
            filtered_df = filtered_df[filtered_df["net_loss"] >= min_loss]

        st.caption(f"Showing {len(filtered_df)} of {len(timeline_df)} events")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

        csv = filtered_df.to_csv(index=False)
        st.download_button("⬇  Download CSV", csv, "operational_loss_events.csv", "text/csv")

    except Exception as e:
        st.error(f"Error displaying event details: {e}")


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="margin-top:3rem;padding-top:1rem;border-top:1px solid #dedad1;'
    'display:flex;justify-content:space-between;align-items:center">'
    '<span style="font-family:DM Serif Display,serif;color:#c9c2b6;font-size:1rem">⬡ PROMETHEUS</span>'
    '<span style="font-family:JetBrains Mono,monospace;font-size:0.63rem;color:#c9c2b6;letter-spacing:0.08em">'
    'OPE25 · Basel III SMA · CONFIDENTIAL'
    '</span></div>',
    unsafe_allow_html=True)

