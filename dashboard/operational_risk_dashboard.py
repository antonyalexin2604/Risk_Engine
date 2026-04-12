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
# ULTRA-STRONG CSS FOR MAXIMUM VISIBILITY
# ═════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* FORCE ALL TEXT TO BE DARK AND BOLD */
    * {
        color: #000000 !important;
        font-weight: 600 !important;
    }
    
    body, p, span, div, label, .stMarkdown {
        color: #000000 !important;
        font-weight: 600 !important;
    }
    
    /* Headers - Extra Bold */
    h1, h2, h3, h4, h5, h6 {
        color: #000000 !important;
        font-weight: 800 !important;
    }
    
    /* Metrics - Very Large and Bold */
    [data-testid="stMetricLabel"], .stMetric label {
        color: #000000 !important;
        font-weight: 700 !important;
        font-size: 18px !important;
    }
    
    [data-testid="stMetricValue"], .stMetric-value {
        color: #000000 !important;
        font-weight: 900 !important;
        font-size: 40px !important;
    }
    
    /* DataFrames */
    .dataframe, .stDataFrame {
        color: #000000 !important;
    }
    
    .dataframe th {
        background-color: #e0e0e0 !important;
        color: #000000 !important;
        font-weight: 800 !important;
        font-size: 16px !important;
    }
    
    .dataframe td {
        color: #000000 !important;
        font-weight: 600 !important;
        font-size: 15px !important;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] * {
        color: #000000 !important;
        font-weight: 600 !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        color: #000000 !important;
        font-weight: 700 !important;
        font-size: 18px !important;
    }
    
    /* Plotly charts - override default styles */
    .js-plotly-plot .plotly text {
        fill: #000000 !important;
        font-weight: 700 !important;
        font-size: 14px !important;
    }
</style>
""", unsafe_allow_html=True)


def apply_dark_theme(fig):
    """Apply ultra-dark, high-contrast theme to Plotly figures."""
    fig.update_layout(
        font=dict(
            family="Arial Black, Arial, sans-serif",
            size=15,
            color="#000000",
        ),
        title_font=dict(
            size=22,
            color="#000000",
            family="Arial Black",
        ),
        xaxis=dict(
            title_font=dict(size=18, color="#000000"),
            tickfont=dict(size=15, color="#000000", family="Arial Black"),
            gridcolor="#b0b0b0",
            linecolor="#000000",
            linewidth=3,
        ),
        yaxis=dict(
            title_font=dict(size=18, color="#000000"),
            tickfont=dict(size=15, color="#000000", family="Arial Black"),
            gridcolor="#b0b0b0",
            linecolor="#000000",
            linewidth=3,
        ),
        legend=dict(
            font=dict(size=15, color="#000000", family="Arial Black"),
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="#000000",
            borderwidth=3,
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
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
    page_icon="⚠️",
    layout="wide",
)

st.title("⚠️ Operational Risk — Basel III SMA")
st.markdown("**Standardised Measurement Approach** (OPE25) | BIC × ILM")


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

st.sidebar.header("⚙️ Configuration")

if st.sidebar.button("🔄 Recalculate", type="primary"):
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

# Display Metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Business Indicator (3yr avg)", f"EUR {sma_result.business_indicator:,.0f}M")

with col2:
    st.metric("BIC", f"EUR {sma_result.bic:,.1f}M")

with col3:
    st.metric("ILM", f"{sma_result.ilm:.3f}")

with col4:
    st.metric("Op Risk Capital", f"EUR {sma_result.operational_risk_capital:,.1f}M")

st.markdown("---")

col_rwa1, col_rwa2, col_rwa3 = st.columns(3)

with col_rwa1:
    st.metric("🎯 Operational Risk RWA", f"EUR {sma_result.rwa_operational:,.0f}M")

with col_rwa2:
    st.metric("Loss Component (LC)", f"EUR {sma_result.loss_component:,.1f}M")

with col_rwa3:
    st.metric("Years of Loss Data", f"{sma_result.years_of_loss_data} years")

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 SMA Breakdown",
    "📉 Loss Analysis",
    "📅 Loss Timeline",
    "🔍 Event Details",
])


# ═════════════════════════════════════════════════════════════════════════════
# Tab 1: SMA Breakdown
# ═════════════════════════════════════════════════════════════════════════════

with tab1:
    st.subheader("SMA Capital Calculation")
    
    st.markdown("#### Business Indicator Component (BIC)")
    st.markdown(f"**3-year average BI:** EUR {sma_result.business_indicator:,.1f}M")
    
    # BIC tier breakdown
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
    st.dataframe(tier_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("#### Operational Risk Capital & RWA")
    
    capital_breakdown = pd.DataFrame({
        "Component": ["BIC", "× ILM", "= Op Risk Capital", "× 12.5", "= RWA"],
        "Value": [
            f"EUR {sma_result.bic:,.1f}M",
            f"{sma_result.ilm:.3f}",
            f"EUR {sma_result.operational_risk_capital:,.1f}M",
            "12.5",
            f"EUR {sma_result.rwa_operational:,.0f}M",
        ],
    })
    
    st.dataframe(capital_breakdown, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# Tab 2: Loss Analysis
# ═════════════════════════════════════════════════════════════════════════════

with tab2:
    st.subheader("Historical Loss Analysis")
    
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### By Event Type")
        event_type_df = analyze_losses_by_event_type(loss_events)
        
        if not event_type_df.empty:
            fig = px.bar(
                event_type_df,
                x="event_type",
                y="total_net_loss",
                title="Net Losses by Basel Event Type",
                labels={"total_net_loss": "Net Loss (EUR M)", "event_type": "Event Type"},
                text="total_net_loss",
            )
            
            fig = apply_dark_theme(fig)
            
            fig.update_traces(
                marker_color='#8B0000',
                marker_line_color='#000000',
                marker_line_width=2,
                texttemplate='EUR %{text:.1f}M',
                textposition='outside',
                textfont=dict(size=16, color='#000000', family='Arial Black'),
            )
            
            fig.update_layout(height=500, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(event_type_df, use_container_width=True, hide_index=True)
    
    with col_chart2:
        st.markdown("#### By Business Line")
        business_line_df = analyze_losses_by_business_line(loss_events)
        
        if not business_line_df.empty:
            fig = px.pie(
                business_line_df,
                values="total_net_loss",
                names="business_line",
                title="Net Losses by Business Line",
            )
            
            fig = apply_dark_theme(fig)
            
            fig.update_traces(
                textinfo='label+percent+value',
                textfont=dict(size=14, color='white', family='Arial Black'),
                marker=dict(
                    colors=['#8B0000', '#A52A2A', '#B22222', '#DC143C', '#FF0000'],
                    line=dict(color='#000000', width=3)
                ),
            )
            
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(business_line_df, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# Tab 3: Loss Timeline - FIXED
# ═════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Loss Event Timeline")
    
    try:
        # Use FIXED timeline function
        timeline_df = get_loss_timeline_fixed(loss_events)
        
        if not timeline_df.empty:
            # Annual aggregate losses
            annual_losses = timeline_df.groupby(timeline_df["date"].dt.year)["net_loss"].sum().reset_index()
            annual_losses.columns = ["Year", "Net Loss (EUR M)"]
            
            fig = px.bar(
                annual_losses,
                x="Year",
                y="Net Loss (EUR M)",
                title="Annual Aggregate Operational Losses",
                text="Net Loss (EUR M)",
            )
            
            fig = apply_dark_theme(fig)
            
            fig.update_traces(
                marker_color='#8B0000',
                marker_line_color='#000000',
                marker_line_width=2,
                texttemplate='EUR %{text:.1f}M',
                textposition='outside',
                textfont=dict(size=16, color='#000000', family='Arial Black'),
            )
            
            fig.update_layout(height=500, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            st.markdown("#### Individual Loss Events")
            
            fig_scatter = px.scatter(
                timeline_df,
                x="date",
                y="net_loss",
                color="event_type",
                size="gross_loss",
                hover_data=["event_id", "business_line"],
                title="Loss Events Over Time",
                labels={"net_loss": "Net Loss (EUR M)", "date": "Date"},
            )
            
            fig_scatter = apply_dark_theme(fig_scatter)
            
            fig_scatter.update_traces(
                marker=dict(line=dict(width=2, color='#000000'), sizemin=6)
            )
            
            fig_scatter.update_layout(height=500)
            st.plotly_chart(fig_scatter, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error loading Operational Risk data: {e}")
        st.info("Check that loss event data is available and properly formatted.")


# ═════════════════════════════════════════════════════════════════════════════
# Tab 4: Event Details
# ═════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("Loss Event Database")
    
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
        
        # Apply filters
        filtered_df = timeline_df.copy()
        
        if "All" not in filter_event_type:
            filtered_df = filtered_df[filtered_df["event_type"].isin(filter_event_type)]
        
        if "All" not in filter_business_line:
            filtered_df = filtered_df[filtered_df["business_line"].isin(filter_business_line)]
        
        if min_loss > 0:
            filtered_df = filtered_df[filtered_df["net_loss"] >= min_loss]
        
        st.markdown(f"**Showing {len(filtered_df)} of {len(timeline_df)} events**")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        
        # Download
        csv = filtered_df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "operational_loss_events.csv", "text/csv")
        
    except Exception as e:
        st.error(f"Error displaying event details: {e}")


st.markdown("---")
st.caption("PROMETHEUS Risk Platform | Operational Risk Module | Basel III SMA (OPE25)")
