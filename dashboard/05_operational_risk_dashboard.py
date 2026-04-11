"""
PROMETHEUS Risk Platform
Operational Risk Dashboard — SMA Capital Visualization

FILE PATH: dashboard/pages/operational_risk_dashboard.py

Streamlit page for Operational Risk (Basel III SMA) visualization and analysis.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.engines.operational_risk import (
    BusinessIndicatorInput,
    compute_sma_capital,
    analyze_losses_by_event_type,
    analyze_losses_by_business_line,
    get_loss_timeline,
    BASEL_EVENT_TYPES,
    BASEL_BUSINESS_LINES,
)
from backend.data_sources.loss_event_database import get_loss_event_database


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
# Load Data
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_business_indicator_data():
    """Load BI data from file or use defaults."""
    # In production, load from backend/data_sources/business_indicator_data.json
    # For now, use sample data
    return [
        BusinessIndicatorInput(
            year=2023,
            interest_income=800,
            interest_expense=400,
            dividend_income=80,
            services_income=500,
            services_expense=150,
            financial_income=250,
            financial_expense=100,
            other_operating_income=150,
            trading_book_pnl=300,
            banking_book_pnl=250,
        ),
        BusinessIndicatorInput(
            year=2024,
            interest_income=850,
            interest_expense=425,
            dividend_income=85,
            services_income=525,
            services_expense=160,
            financial_income=265,
            financial_expense=105,
            other_operating_income=160,
            trading_book_pnl=320,
            banking_book_pnl=265,
        ),
        BusinessIndicatorInput(
            year=2025,
            interest_income=900,
            interest_expense=450,
            dividend_income=90,
            services_income=550,
            services_expense=170,
            financial_income=280,
            financial_expense=110,
            other_operating_income=170,
            trading_book_pnl=340,
            banking_book_pnl=280,
        ),
    ]


@st.cache_data
def load_loss_events():
    """Load loss events from database."""
    db = get_loss_event_database()
    return db.get_all_events()


# Load data
bi_inputs = load_business_indicator_data()
loss_events = load_loss_events()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — Configuration
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.header("Configuration")

# Calculate SMA
if st.sidebar.button("🔄 Recalculate", type="primary"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.metric("Loss Events in Database", len(loss_events))

# Display database stats
if loss_events:
    db = get_loss_event_database()
    stats = db.get_summary_statistics()
    
    st.sidebar.metric("Years Covered", stats["year_range"])
    st.sidebar.metric("Total Net Losses", f"EUR {stats['total_net_loss']:.1f}M")
    st.sidebar.metric("Avg Loss per Event", f"EUR {stats['avg_net_loss']:.2f}M")


# ─────────────────────────────────────────────────────────────────────────────
# Main Content — SMA Calculation
# ─────────────────────────────────────────────────────────────────────────────

if not loss_events:
    st.warning(
        "⚠️ **No loss events in database.** "
        "Run `operational_loss_generator.py` to generate synthetic data, "
        "or upload historical loss events."
    )
    st.stop()

# Compute SMA Capital
sma_result = compute_sma_capital(bi_inputs, loss_events)

# Display key metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Business Indicator (3yr avg)",
        f"EUR {sma_result.business_indicator:,.0f}M",
    )

with col2:
    st.metric(
        "BIC",
        f"EUR {sma_result.bic:,.1f}M",
    )

with col3:
    st.metric(
        "ILM",
        f"{sma_result.ilm:.3f}",
        help="Internal Loss Multiplier (capped at 1.0)",
    )

with col4:
    st.metric(
        "Op Risk Capital",
        f"EUR {sma_result.operational_risk_capital:,.1f}M",
        help="BIC × ILM",
    )

st.markdown("---")

# Display RWA
col_rwa1, col_rwa2, col_rwa3 = st.columns(3)

with col_rwa1:
    st.metric(
        "Operational Risk RWA",
        f"EUR {sma_result.rwa_operational:,.0f}M",
        help="Capital × 12.5",
    )

with col_rwa2:
    st.metric(
        "Loss Component (LC)",
        f"EUR {sma_result.loss_component:,.1f}M",
        help="15 × Average Annual Losses",
    )

with col_rwa3:
    st.metric(
        "Years of Loss Data",
        f"{sma_result.years_of_loss_data} years",
        delta="10 required for LC" if sma_result.years_of_loss_data < 10 else "✓",
    )

st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Visualization Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 SMA Breakdown",
    "📉 Loss Analysis",
    "📅 Loss Timeline",
    "🔍 Event Details",
])


# ───────────────────────────────────────
# Tab 1: SMA Breakdown
# ───────────────────────────────────────

with tab1:
    st.subheader("SMA Capital Calculation")
    
    # BIC Tier Breakdown
    st.markdown("#### Business Indicator Component (BIC)")
    st.markdown(f"3-year average BI: **EUR {sma_result.business_indicator:,.1f}M**")
    
    # Show tier structure
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
    
    # ILM Calculation
    st.markdown("#### Internal Loss Multiplier (ILM)")
    
    col_ilm1, col_ilm2 = st.columns(2)
    
    with col_ilm1:
        st.markdown(f"""
        - **LC/BIC Ratio**: {(sma_result.loss_component / sma_result.bic):.3f}
        - **ILM (uncapped)**: Calculated via formula
        - **ILM (final)**: {sma_result.ilm:.3f} ✓ Capped at 1.0
        """)
    
    with col_ilm2:
        st.markdown(f"""
        **Formula:**
        ```
        ILM = min(1.0, ln(exp(1) - 1 + (LC/BIC)^0.8))
        ```
        
        **Status:** {"✅ Sufficient loss data (10+ years)" if sma_result.years_of_loss_data >= 10 else "⚠️ Insufficient data → ILM defaulted to 1.0"}
        """)
    
    st.markdown("---")
    
    # Final Capital
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


# ───────────────────────────────────────
# Tab 2: Loss Analysis
# ───────────────────────────────────────

with tab2:
    st.subheader("Historical Loss Analysis")
    
    col_chart1, col_chart2 = st.columns(2)
    
    # Loss by Event Type
    with col_chart1:
        st.markdown("#### By Event Type")
        event_type_df = analyze_losses_by_event_type(loss_events)
        
        if not event_type_df.empty:
            fig_event_type = px.bar(
                event_type_df,
                x="event_type",
                y="total_net_loss",
                color="pct_of_total",
                title="Net Losses by Basel Event Type",
                labels={
                    "total_net_loss": "Net Loss (EUR M)",
                    "event_type": "Event Type",
                    "pct_of_total": "% of Total",
                },
                color_continuous_scale="Reds",
            )
            fig_event_type.update_layout(height=400)
            st.plotly_chart(fig_event_type, use_container_width=True)
            
            st.dataframe(
                event_type_df.style.format({
                    "total_gross_loss": "{:.1f}",
                    "total_net_loss": "{:.1f}",
                    "avg_loss": "{:.2f}",
                    "pct_of_total": "{:.1f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )
    
    # Loss by Business Line
    with col_chart2:
        st.markdown("#### By Business Line")
        business_line_df = analyze_losses_by_business_line(loss_events)
        
        if not business_line_df.empty:
            fig_bl = px.pie(
                business_line_df,
                values="total_net_loss",
                names="business_line",
                title="Net Losses by Business Line",
                color_discrete_sequence=px.colors.sequential.Reds,
            )
            fig_bl.update_layout(height=400)
            st.plotly_chart(fig_bl, use_container_width=True)
            
            st.dataframe(
                business_line_df.style.format({
                    "total_net_loss": "{:.1f}",
                    "avg_loss": "{:.2f}",
                    "pct_of_total": "{:.1f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )


# ───────────────────────────────────────
# Tab 3: Loss Timeline
# ───────────────────────────────────────

with tab3:
    st.subheader("Loss Event Timeline")
    
    timeline_df = get_loss_timeline(loss_events)
    
    if not timeline_df.empty:
        # Annual aggregate losses
        annual_losses = timeline_df.groupby(timeline_df["date"].dt.year)["net_loss"].sum().reset_index()
        annual_losses.columns = ["Year", "Net Loss (EUR M)"]
        
        fig_annual = px.bar(
            annual_losses,
            x="Year",
            y="Net Loss (EUR M)",
            title="Annual Aggregate Operational Losses",
            color="Net Loss (EUR M)",
            color_continuous_scale="Reds",
        )
        fig_annual.update_layout(height=400)
        st.plotly_chart(fig_annual, use_container_width=True)
        
        st.markdown("---")
        
        # Scatter plot of individual losses
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
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        # Statistics
        st.markdown("#### Timeline Statistics")
        
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        
        with stat_col1:
            st.metric("Total Events", len(timeline_df))
        
        with stat_col2:
            st.metric("Max Loss", f"EUR {timeline_df['net_loss'].max():.2f}M")
        
        with stat_col3:
            st.metric("Avg Loss", f"EUR {timeline_df['net_loss'].mean():.2f}M")
        
        with stat_col4:
            years_span = timeline_df['date'].dt.year.max() - timeline_df['date'].dt.year.min() + 1
            st.metric("Years Span", f"{years_span} years")


# ───────────────────────────────────────
# Tab 4: Event Details
# ───────────────────────────────────────

with tab4:
    st.subheader("Loss Event Database")
    
    # Filters
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
        min_loss = st.number_input(
            "Min Loss (EUR M)",
            min_value=0.0,
            value=0.0,
            step=0.1,
        )
    
    # Apply filters
    timeline_df = get_loss_timeline(loss_events)
    filtered_df = timeline_df.copy()
    
    if "All" not in filter_event_type:
        filtered_df = filtered_df[filtered_df["event_type"].isin(filter_event_type)]
    
    if "All" not in filter_business_line:
        filtered_df = filtered_df[filtered_df["business_line"].isin(filter_business_line)]
    
    if min_loss > 0:
        filtered_df = filtered_df[filtered_df["net_loss"] >= min_loss]
    
    # Display filtered events
    st.markdown(f"**Showing {len(filtered_df)} of {len(timeline_df)} events**")
    
    st.dataframe(
        filtered_df.style.format({
            "net_loss": "{:.2f}",
            "gross_loss": "{:.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )
    
    # Download button
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Filtered Events (CSV)",
        data=csv,
        file_name="operational_loss_events.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption("PROMETHEUS Risk Platform | Operational Risk Module | Basel III SMA (OPE25)")
