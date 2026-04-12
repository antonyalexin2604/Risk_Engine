"""
PROMETHEUS Dashboard — Refined Global Styling
Aesthetic: Institutional Light · Warm whites · Deep slate · Eye-soothing typography

FILE PATH: dashboard/styling.py
"""

import streamlit as st


def apply_global_styling():
    """
    Apply refined, eye-soothing styling to the PROMETHEUS dashboard.

    Uses the slate colour palette from app.py (not pure black) and
    proportional, non-bold font sizes so nothing overlaps.

    Usage in app.py (MUST be first thing after imports):
        from styling import apply_global_styling
        apply_global_styling()
    """

    st.markdown("""
    <style>
        /* ── Base reset: slate body text, normal weight ── */
        body, p, li, a {
            color: #334155 !important;
            font-weight: 400 !important;
            font-size: 0.875rem !important;
            line-height: 1.55 !important;
        }

        span, div {
            font-weight: inherit !important;
        }

        /* ── Headings ── */
        h1 { color: #0f172a !important; font-weight: 500 !important; font-size: 1.75rem !important; line-height: 1.15 !important; }
        h2 { color: #0f172a !important; font-weight: 500 !important; font-size: 1.35rem !important; line-height: 1.2  !important; }
        h3 { color: #1e293b !important; font-weight: 500 !important; font-size: 1.10rem !important; line-height: 1.25 !important; }
        h4, h5, h6 { color: #334155 !important; font-weight: 500 !important; }

        /* ── Streamlit markdown ── */
        .stMarkdown p, .stMarkdown span, .stMarkdown li {
            color: #475569 !important;
            font-weight: 400 !important;
            font-size: 0.875rem !important;
        }

        /* ── Metrics ── */
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            color: #64748b !important;
            font-weight: 500 !important;
            font-size: 0.75rem !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            color: #0f172a !important;
            font-weight: 600 !important;
            font-size: 1.55rem !important;
            font-family: 'JetBrains Mono', monospace !important;
        }

        [data-testid="stMetricDelta"],
        [data-testid="stMetricDelta"] * {
            font-weight: 400 !important;
            font-size: 0.80rem !important;
        }

        /* ── DataFrames ── */
        [data-testid="stDataFrameResizable"] thead th,
        .stDataFrame thead th {
            background-color: #f1ede6 !important;
            color: #334155 !important;
            font-weight: 600 !important;
            font-size: 0.75rem !important;
            border-bottom: 1px solid #dedad1 !important;
        }

        [data-testid="stDataFrameResizable"] tbody td,
        .stDataFrame tbody td {
            color: #475569 !important;
            font-weight: 400 !important;
            font-size: 0.8rem !important;
        }

        [data-testid="stDataFrameResizable"] tbody th,
        .stDataFrame tbody th {
            color: #475569 !important;
            font-weight: 500 !important;
            font-size: 0.8rem !important;
        }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            color: #334155 !important;
        }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] li {
            color: #475569 !important;
            font-weight: 400 !important;
            font-size: 0.85rem !important;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #0f172a !important;
            font-weight: 500 !important;
        }

        /* ── Tabs ── */
        .stTabs [data-baseweb="tab"] {
            color: #475569 !important;
            font-weight: 500 !important;
            font-size: 0.85rem !important;
        }
        .stTabs [aria-selected="true"] {
            color: #0f172a !important;
            font-weight: 600 !important;
            border-bottom: 2px solid #991b1b !important;
        }

        /* ── Buttons ── */
        .stButton > button,
        .stDownloadButton > button {
            font-weight: 500 !important;
            font-size: 0.85rem !important;
        }

        /* ── Input / widget labels ── */
        .stSelectbox label,
        .stMultiSelect label,
        .stTextInput label,
        .stNumberInput label,
        .stDateInput label,
        .stRadio label {
            color: #64748b !important;
            font-weight: 500 !important;
            font-size: 0.73rem !important;
            text-transform: uppercase;
            letter-spacing: 0.07em;
        }

        /* ── Expanders ── */
        .streamlit-expanderHeader {
            color: #334155 !important;
            font-weight: 500 !important;
            font-size: 0.88rem !important;
        }

        /* ── Alerts / banners ── */
        .stAlert, .stAlert p, .stAlert span {
            font-weight: 400 !important;
            font-size: 0.85rem !important;
        }

        /* ── Captions ── */
        .stCaption, .stCaption *,
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #94a3b8 !important;
            font-weight: 400 !important;
            font-size: 0.75rem !important;
        }

    </style>
    """, unsafe_allow_html=True)


def apply_plotly_theme(fig):
    """
    Apply refined light theme to Plotly figures, matching the dashboard palette.

    Call this on any Plotly figure that needs the standard styling:
        fig = apply_plotly_theme(fig)
        st.plotly_chart(fig)
    """
    fig.update_layout(
        font=dict(
            family="JetBrains Mono, Inter, sans-serif",
            size=10,
            color="#64748b",
        ),
        title_font=dict(
            size=13,
            color="#334155",
            family="Inter, sans-serif",
        ),
        xaxis=dict(
            title_font=dict(size=11, color="#64748b", family="Inter, sans-serif"),
            tickfont=dict(size=9, color="#94a3b8", family="JetBrains Mono, monospace"),
            gridcolor="#dedad1",
            linecolor="#dedad1",
            linewidth=1,
        ),
        yaxis=dict(
            title_font=dict(size=11, color="#64748b", family="Inter, sans-serif"),
            tickfont=dict(size=9, color="#94a3b8", family="JetBrains Mono, monospace"),
            gridcolor="#dedad1",
            linecolor="#dedad1",
            linewidth=1,
        ),
        legend=dict(
            font=dict(size=10, color="#475569", family="JetBrains Mono, monospace"),
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#dedad1",
            borderwidth=1,
        ),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f7f6f3",
    )
    return fig


# Palette aligned with the app.py colour constants
CHART_COLORS = {
    'categorical': [
        '#1e40af',  # blue
        '#3730a3',  # indigo
        '#0f766e',  # teal
        '#166534',  # green
        '#92400e',  # amber
        '#991b1b',  # crimson
        '#64748b',  # slate
    ],
    'reds':   ['#991b1b', '#c53030', '#ef4444', '#fca5a5'],
    'blues':  ['#1e3a8a', '#1e40af', '#3b82f6', '#93c5fd'],
    'greens': ['#14532d', '#166534', '#22c55e', '#86efac'],
}


def get_dark_colors(palette='categorical'):
    """Return chart colour palette aligned with the dashboard theme."""
    return CHART_COLORS.get(palette, CHART_COLORS['categorical'])
