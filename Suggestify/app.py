import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import datetime
import warnings
from html import escape
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Suggestify | Ody",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════
# DESIGN TOKENS — MODERN GLASSMORPHISM
# ══════════════════════════════════════════════════════════════════
BG        = "#050505"
SURFACE   = "rgba(18, 18, 18, 0.85)"
CARD      = "rgba(28, 28, 28, 0.75)"
CARD_HOVER= "rgba(45, 45, 45, 0.85)"
BORDER    = "rgba(255, 255, 255, 0.08)"
BORDER_HL = "rgba(255, 255, 255, 0.15)"
GREEN     = "#1DB954"
GREEN_DIM = "#169C46"
GREEN_GLOW= "rgba(29, 185, 84, 0.35)"
GREEN_XLO = "rgba(29, 185, 84, 0.08)"
TEXT      = "#FFFFFF"
TEXT_MID  = "#B3B3B3"
TEXT_DIM  = "#727272"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ─── BASE RESET ─── */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: {BG} !important;
    color: {TEXT} !important;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{
    padding: 0.5rem 2rem 4rem !important;
    max-width: 100% !important;
}}

/* ─── PAGE TRANSITIONS ─── */
@keyframes fadeSlideIn {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}
@keyframes pulseGlow {{
    0%, 100% {{ box-shadow: 0 0 20px {GREEN_GLOW}; }}
    50% {{ box-shadow: 0 0 35px {GREEN_GLOW}, 0 0 60px rgba(29,185,84,0.15); }}
}}

.animate-in {{
    animation: fadeSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}}

/* ─── STICKY NAVBAR ─── */
.navbar {{
    position: sticky;
    top: 0;
    z-index: 1000;
    background: rgba(5, 5, 5, 0.92);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border-bottom: 1px solid {BORDER};
    padding: 0.75rem 0;
    margin: 0 -2rem 1.5rem -2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}}

.navbar-content {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    flex-wrap: wrap;
}}

.nav-brand {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: {TEXT};
}}
.nav-brand span {{ font-size: 1.8rem; }}

/* ─── KPI CARDS — Glass Effect ─── */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0 2rem;
    animation: fadeSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}}

.kpi-card {{
    background: {CARD};
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}}
.kpi-card::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, {GREEN} 0%, transparent 100%);
}}
.kpi-card:hover {{
    transform: translateY(-4px);
    border-color: {BORDER_HL};
    box-shadow: 0 12px 40px rgba(0,0,0,0.4);
}}

.kpi-icon {{
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
    filter: grayscale(30%);
}}
.kpi-title {{
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: {TEXT_DIM};
    margin-bottom: 0.4rem;
}}
.kpi-value {{
    font-size: 2.2rem;
    font-weight: 800;
    color: {TEXT};
    line-height: 1;
    letter-spacing: -0.03em;
}}
.kpi-unit {{
    font-size: 0.9rem;
    color: {TEXT_MID};
    margin-left: 4px;
    font-weight: 500;
}}

/* ─── SECTION HEADERS ─── */
.section-header {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 1.25rem;
    font-weight: 700;
    color: {TEXT};
    margin: 2.5rem 0 1.25rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid {BORDER};
    animation: fadeSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}}
.section-header .icon {{
    font-size: 1.1rem;
    opacity: 0.9;
}}

/* ─── LIST ITEM — Modern Cards ─── */
.list-item {{
    display: flex;
    align-items: center;
    background: {CARD};
    backdrop-filter: blur(10px);
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 1rem 1.5rem;
    margin-bottom: 0.6rem;
    transition: background 0.25s ease, border-color 0.25s ease,
                transform 0.25s ease, box-shadow 0.25s ease;
}}

/* CLEAN NATIVE CLICKABLE LINKS */
a.custom-link {{
    text-decoration: none !important;
    color: inherit !important;
    display: block;
    margin-bottom: 0.6rem;
}}
a.custom-link .list-item {{
    margin-bottom: 0 !important; /* Margin is handled by the <a> wrapper */
}}
a.custom-link:hover .list-item {{
    background: {CARD_HOVER};
    border-color: {BORDER_HL};
    transform: translateX(6px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
}}
a.custom-link:hover .item-arrow {{
    transform: translateX(4px);
    color: {GREEN};
}}

.item-rank {{
    font-size: 1.1rem;
    font-weight: 800;
    color: {TEXT_DIM};
    width: 50px;
    min-width: 50px;
    text-align: center;
}}
.item-rank.gold {{ color: #FFD700; }}
.item-rank.silver {{ color: #C0C0C0; }}
.item-rank.bronze {{ color: #CD7F32; }}

.item-art {{
    width: 52px;
    height: 52px;
    border-radius: 8px;
    background: linear-gradient(135deg, {GREEN_XLO} 0%, rgba(0,0,0,0.3) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    margin-right: 1rem;
    flex-shrink: 0;
    overflow: hidden;
}}

.item-info {{
    flex: 1;
    min-width: 0;
}}
.item-title {{
    font-size: 1rem;
    font-weight: 600;
    color: {TEXT};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 0.15rem;
}}
.item-subtitle {{
    font-size: 0.85rem;
    color: {TEXT_MID};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.item-stats {{
    display: flex;
    gap: 2rem;
    align-items: center;
    margin-left: auto;
    padding-left: 1rem;
}}
.stat {{
    text-align: right;
}}
.stat-value {{
    font-size: 1.15rem;
    font-weight: 700;
    color: {TEXT};
    line-height: 1.1;
}}
.stat-value.green {{ color: {GREEN}; }}
.stat-label {{
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {TEXT_DIM};
}}

.item-arrow {{
    color: {TEXT_DIM};
    font-size: 1.2rem;
    margin-left: 1rem;
    transition: transform 0.2s ease, color 0.2s ease;
}}

/* ─── BACK BUTTON ─── */
.back-btn {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.6rem 1.2rem;
    background: rgba(255,255,255,0.05);
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_MID};
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 1.5rem;
}}

/* ─── DETAIL PAGE HEADER ─── */
.detail-header {{
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 1.5rem;
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 20px;
    margin-bottom: 2rem;
    animation: fadeSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}}
.detail-art {{
    width: 120px;
    height: 120px;
    border-radius: 12px;
    background: linear-gradient(135deg, {GREEN_DIM} 0%, {GREEN_XLO} 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 3rem;
    flex-shrink: 0;
    overflow: hidden;
}}
.detail-info {{ flex: 1; }}
.detail-type {{
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: {GREEN};
    margin-bottom: 0.3rem;
}}
.detail-title {{
    font-size: 2rem;
    font-weight: 800;
    color: {TEXT};
    letter-spacing: -0.03em;
    margin-bottom: 0.25rem;
}}
.detail-subtitle {{
    font-size: 1rem;
    color: {TEXT_MID};
}}
.detail-stats {{
    display: flex;
    gap: 2rem;
}}
.detail-stat {{
    text-align: center;
    padding: 1rem 1.5rem;
    background: rgba(0,0,0,0.3);
    border-radius: 12px;
}}
.detail-stat-value {{
    font-size: 1.8rem;
    font-weight: 800;
    color: {TEXT};
}}
.detail-stat-label {{
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    color: {TEXT_DIM};
    letter-spacing: 0.05em;
}}

/* ─── CHARTS CONTAINER ─── */
.chart-container {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    animation: fadeIn 0.5s ease forwards;
}}
.chart-title {{
    font-size: 0.85rem;
    font-weight: 700;
    color: {TEXT};
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}}

/* ─── WRAPPED BANNER ─── */
.wrapped-banner {{
    background: linear-gradient(135deg, rgba(29,185,84,0.2) 0%, rgba(29,185,84,0.05) 50%, rgba(0,0,0,0) 100%);
    border: 1px solid {GREEN};
    border-radius: 20px;
    padding: 2rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    animation: fadeSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}}
.wrapped-banner::before {{
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 50%;
    height: 200%;
    background: radial-gradient(ellipse, {GREEN_GLOW} 0%, transparent 70%);
    animation: pulseGlow 3s infinite;
}}
.wrapped-title {{
    font-size: 2.5rem;
    font-weight: 900;
    background: linear-gradient(135deg, {GREEN} 0%, #1ed760 50%, {GREEN} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
}}
.wrapped-subtitle {{
    font-size: 1.1rem;
    color: {TEXT_MID};
}}

/* ─── EMPTY STATE ─── */
.empty-state {{
    text-align: center;
    padding: 4rem 2rem;
    color: {TEXT_DIM};
}}
.empty-state .icon {{
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}}

/* ─── STREAMLIT OVERRIDES FOR INPUTS ─── */
div[data-baseweb="select"] > div,
div[data-testid="stDateInput"] input {{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px !important;
    color: {TEXT} !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 0.75rem !important;
    transition: all 0.2s ease !important;
}}
div.row-widget.stRadio {{ display: none !important; }}

div[data-testid="stTextInput"] input {{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid {BORDER} !important;
    border-radius: 12px !important;
    padding: 0.8rem 1rem !important;
    font-size: 0.95rem !important;
}}
div[data-testid="stTextInput"] input::placeholder {{
    color: {TEXT_DIM} !important;
}}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════
CONNECTION_STRING = "postgresql://postgres:secret@localhost:5432/spotify_db"

@st.cache_resource
def get_engine():
    return create_engine(CONNECTION_STRING, pool_pre_ping=True, pool_size=5)

@st.cache_data(ttl=300, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})

@st.cache_data(ttl=600, show_spinner=False)
def get_date_bounds() -> tuple[datetime.date, datetime.date]:
    df = run_query("SELECT MIN(played_at)::date AS mn, MAX(played_at)::date AS mx FROM streams;")
    if df.empty or pd.isnull(df["mn"].iloc[0]):
        return datetime.date(2023, 1, 1), datetime.date.today()
    return df["mn"].iloc[0], df["mx"].iloc[0]


# ══════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ══════════════════════════════════════════════════════════════════

def get_rank_class(rank: int) -> str:
    if rank == 1: return "gold"
    if rank == 2: return "silver"
    if rank == 3: return "bronze"
    return ""

def get_item_icon(link_type: str) -> str:
    icons = {"song": "🎵", "artist": "🎤", "album": "💿"}
    return icons.get(link_type, "🎵")

def render_list_v2(df: pd.DataFrame, title_col: str, sub_col: str, streams_col: str, hours_col: str,
                   id_col: str = None, link_type: str = None, image_col: str = "image_url",
                   rank_col: str = None):
    """
    Modern list renderer using pure HTML <a> tags.
    Target "_top" bypasses the iframe container and opens in the SAME browser tab smoothly!
    """
    current_tab = st.query_params.get("tab", "overview")

    for i, row in df.iterrows():
        rank = int(row[rank_col]) if (rank_col and rank_col in row.index) else (i + 1)
        rank_class = get_rank_class(rank)
        title = escape(str(row[title_col]))[:60]
        subtitle = escape(str(row[sub_col]))[:50]
        streams = f"{int(row[streams_col]):,}"
        hours = f"{float(row[hours_col]):.1f}"
        can_navigate = link_type and id_col and id_col in row.index

        image_url = row.get(image_col) if image_col in row else None
        if image_url and pd.notnull(image_url) and str(image_url).startswith("http"):
            radius = "50%" if link_type == "artist" else "8px"
            art_html = f'<img src="{image_url}" style="width:100%; height:100%; object-fit:cover; border-radius:{radius};">'
        else:
            art_html = get_item_icon(link_type) if link_type else "🎵"

        card_html = f'''
        <div class="list-item">
            <div class="item-rank {rank_class}">{rank}</div>
            <div class="item-art">{art_html}</div>
            <div class="item-info">
                <div class="item-title">{title}</div>
                <div class="item-subtitle">{subtitle}</div>
            </div>
            <div class="item-stats">
                <div class="stat">
                    <div class="stat-value">{streams}</div>
                    <div class="stat-label">Streams</div>
                </div>
                <div class="stat">
                    <div class="stat-value green">{hours}h</div>
                    <div class="stat-label">Time</div>
                </div>
            </div>
            {"<div class='item-arrow'>→</div>" if can_navigate else ""}
        </div>
        '''

        if can_navigate:
            item_id = str(row[id_col])
            href = f"?tab={current_tab}&view={link_type}&id={item_id}"
            st.markdown(f'<a href="{href}" class="custom-link" target="_top">{card_html}</a>', unsafe_allow_html=True)
        else:
            st.markdown(card_html, unsafe_allow_html=True)


def render_kpi_grid(kpis: list[dict]):
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        unit_html = f'<span class="kpi-unit">{kpi.get("unit", "")}</span>' if kpi.get("unit") else ""
        col.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-icon">{kpi["icon"]}</div>
            <div class="kpi-title">{kpi["title"]}</div>
            <div class="kpi-value">{kpi["value"]}{unit_html}</div>
        </div>
        ''', unsafe_allow_html=True)


def render_detail_header(type_label: str, title: str, subtitle: str, icon: str, stats: list[dict], image_url: str = None):
    stats_html = "".join([
        f'<div class="detail-stat"><div class="detail-stat-value">{s["value"]}</div><div class="detail-stat-label">{s["label"]}</div></div>'
        for s in stats
    ])
    if image_url and pd.notnull(image_url) and str(image_url).startswith("http"):
        art_html = f'<img src="{image_url}" style="width:100%; height:100%; object-fit:cover;">'
    else:
        art_html = icon

    st.markdown(f'''
    <div class="detail-header">
        <div class="detail-art">{art_html}</div>
        <div class="detail-info">
            <div class="detail-type">{type_label}</div>
            <div class="detail-title">{escape(title)}</div>
            <div class="detail-subtitle">{escape(subtitle)}</div>
        </div>
        <div class="detail-stats">{stats_html}</div>
    </div>
    ''', unsafe_allow_html=True)


# ── Plotly Helpers ──
_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=TEXT_DIM, size=12),
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)", zeroline=False),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)", zeroline=False),
    margin=dict(t=30, b=40, l=50, r=20),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="#1C1C1C", bordercolor="rgba(255,255,255,0.1)", font=dict(color=TEXT, size=13))
)

def themed(fig: go.Figure, **extra) -> go.Figure:
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_layout(**extra)
    return fig

def chart_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["stream_count"],
        name="Streams", mode="lines+markers",
        line=dict(color=GREEN, width=3, shape='spline'),
        marker=dict(size=7, color=GREEN, line=dict(width=2, color=BG)),
        fill="tozeroy", fillcolor=GREEN_XLO
    ))
    fig.add_trace(go.Bar(
        x=df["period"], y=df["hours_played"],
        name="Hours", marker_color="rgba(29,185,84,0.2)",
        yaxis="y2"
    ))
    return themed(fig,
        yaxis=dict(title=dict(text="Streams", font=dict(color=TEXT_MID))),
        yaxis2=dict(title=dict(text="Hours", font=dict(color=TEXT_MID)), overlaying="y", side="right", showgrid=False),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center")
    )

def chart_heatmap(df: pd.DataFrame) -> go.Figure:
    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = df.pivot(index="dow", columns="hour", values="stream_count").reindex(index=range(1, 8), columns=range(24)).fillna(0)
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}" for h in range(24)],
        y=DOW,
        colorscale=[[0, BG], [0.15, "rgba(29,185,84,0.1)"], [0.4, GREEN_DIM], [1, GREEN]],
        hoverongaps=False,
        hovertemplate="<b>%{y}</b> at <b>%{x}:00</b><br>%{z} streams<extra></extra>"
    ))
    return themed(fig, xaxis_title="Hour", yaxis_title="", margin=dict(t=20, b=50, l=60, r=20))

def chart_bar(x, y, xlabel: str) -> go.Figure:
    max_val = max(y) if y else 0
    colors = [GREEN if v == max_val else "rgba(29,185,84,0.35)" for v in y]
    fig = go.Figure(go.Bar(
        x=x, y=y,
        marker_color=colors,
        marker_line=dict(width=0),
        hovertemplate="<b>%{x}</b><br>%{y:,} streams<extra></extra>"
    ))
    return themed(fig, xaxis_title=xlabel, yaxis_title="Streams", bargap=0.25)


# ══════════════════════════════════════════════════════════════════
# NAVIGATION HANDLING
# ══════════════════════════════════════════════════════════════════

def get_current_view() -> dict:
    params = st.query_params
    return {
        "type": params.get("view", None),
        "id": params.get("id", None),
        "tab": params.get("tab", "overview")
    }

def go_back():
    current = get_current_view()
    st.query_params.clear()
    if current.get("type") == "song":
        st.query_params["tab"] = "tracks"
    elif current.get("type") == "artist":
        st.query_params["tab"] = "artists"
    elif current.get("type") == "album":
        st.query_params["tab"] = "albums"


# ══════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════

min_date, max_date = get_date_bounds()
if "start_date" not in st.session_state:
    st.session_state.start_date = min_date
if "end_date" not in st.session_state:
    st.session_state.end_date = max_date

# Safe assignment for the date_preset selection
if "date_preset" not in st.session_state:
    st.session_state.date_preset = "all"

preset_options = {
    "all": "♾️ All Time",
    "wrapped": "🎁 Wrapped",
    "month": "📅 Month",
    "week": "📅 Week"
}

# Provide safe fallback in case st.session_state.date_preset gets out of sync
safe_preset = st.session_state.date_preset if st.session_state.date_preset in preset_options else "all"

view_state = get_current_view()
current_tab = view_state["tab"]
detail_type = view_state["type"]
detail_id = view_state["id"]

# ─── NAVBAR ───
st.markdown('<div class="navbar"><div class="navbar-content">', unsafe_allow_html=True)
st.markdown('<div class="nav-brand"><span>🎧</span>Suggestify</div>', unsafe_allow_html=True)

nav_col, date_col = st.columns([3, 2])

with nav_col:
    tabs = [
        ("overview", "📊 Overview"),
        ("tracks", "🎵 Tracks"),
        ("artists", "🎤 Artists"),
        ("albums", "💿 Albums"),
        ("habits", "🕐 Habits"),
    ]
    cols = st.columns(len(tabs))
    for i, (tab_id, tab_label) in enumerate(tabs):
        with cols[i]:
            is_active = (current_tab == tab_id) and not detail_type
            if st.button(
                tab_label,
                key=f"nav_{tab_id}",
                type="primary" if is_active else "secondary",
                use_container_width=True
            ):
                st.query_params.clear()
                st.query_params["tab"] = tab_id
                st.rerun()

with date_col:
    preset_col, d1_col, d2_col = st.columns([1.4, 1, 1])

    with preset_col:
        selected_preset = st.selectbox(
            "Period",
            options=list(preset_options.keys()),
            format_func=lambda x: preset_options[x],
            index=list(preset_options.keys()).index(safe_preset),
            label_visibility="collapsed",
            key="preset_select"
        )
        if selected_preset != st.session_state.date_preset:
            st.session_state.date_preset = selected_preset
            if selected_preset == "all":
                st.session_state.start_date = min_date
                st.session_state.end_date = max_date
            elif selected_preset == "wrapped":
                st.session_state.start_date = datetime.date(max_date.year, 1, 1)
                st.session_state.end_date = max_date
            elif selected_preset == "month":
                st.session_state.start_date = max_date - datetime.timedelta(days=30)
                st.session_state.end_date = max_date
            elif selected_preset == "week":
                st.session_state.start_date = max_date - datetime.timedelta(days=7)
                st.session_state.end_date = max_date
            st.rerun()

    with d1_col:
        new_start = st.date_input("From", value=st.session_state.start_date,
            min_value=min_date, max_value=max_date, label_visibility="collapsed", key="start_input")

    with d2_col:
        new_end = st.date_input("To", value=st.session_state.end_date,
            min_value=min_date, max_value=max_date, label_visibility="collapsed", key="end_input")

    if new_start != st.session_state.start_date or new_end != st.session_state.end_date:
        if new_start <= new_end:
            st.session_state.start_date = new_start
            st.session_state.end_date = new_end
            st.session_state.date_preset = "custom"
            st.rerun()

st.markdown('</div></div>', unsafe_allow_html=True)

F = {"start_date": st.session_state.start_date, "end_date": st.session_state.end_date}


# ══════════════════════════════════════════════════════════════════
# DETAIL VIEWS
# ══════════════════════════════════════════════════════════════════

if detail_type and detail_id:

    if st.button("← Back", key="back_btn"):
        go_back()
        st.rerun()

    if detail_type == "song":
        song_info = run_query("""
            SELECT so.title, COALESCE(a.name, 'Unknown') as artist, so.image_url,
                   COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 2) as hours,
                   MIN(s.played_at) as first_play
            FROM songs so
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            LEFT JOIN streams s ON s.song_id = so.id AND s.played_at::date BETWEEN :start_date AND :end_date
            WHERE so.id = :id
            GROUP BY so.id, so.title, a.name, so.image_url
        """, {"id": detail_id, **F})

        if not song_info.empty:
            row = song_info.iloc[0]
            render_detail_header(
                type_label="Track", title=str(row["title"]),
                subtitle=f"by {row['artist']}", icon="🎵",
                stats=[
                    {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                    {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            if pd.notnull(row['first_play']):
                st.info(f"✨ **First played:** {row['first_play'].strftime('%B %d, %Y')}")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<div class="chart-container"><div class="chart-title">📈 Listening Timeline</div>', unsafe_allow_html=True)
                df_t = run_query("""
                    SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count,
                           ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played
                    FROM streams WHERE song_id = :id AND played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY 1 ORDER BY 1
                """, {"id": detail_id, **F})
                if not df_t.empty:
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

            with c2:
                st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
                df_h = run_query("""
                    SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count
                    FROM streams WHERE song_id = :id AND played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY 1 ORDER BY 1
                """, {"id": detail_id, **F})
                if not df_h.empty:
                    st.plotly_chart(
                        chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "artist":
        art_info = run_query("""
            SELECT a.name, a.image_url, COUNT(s.id) as streams,
                   ROUND(SUM(s.ms_played)/3600000.0, 2) as hours,
                   COUNT(DISTINCT s.song_id) as unique_tracks
            FROM artists a
            LEFT JOIN song_artists sa ON sa.artist_id = a.id
            LEFT JOIN streams s ON s.song_id = sa.song_id AND s.played_at::date BETWEEN :start_date AND :end_date
            WHERE a.id = :id
            GROUP BY a.id, a.name, a.image_url
        """, {"id": detail_id, **F})

        if not art_info.empty:
            row = art_info.iloc[0]
            artist_name = str(row["name"])
            
            render_detail_header(
                type_label="Artist", title=artist_name,
                subtitle=f"{int(row['unique_tracks'] or 0)} tracks played", icon="🎤",
                stats=[
                    {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                    {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            # --- Changed Layout: 3 Columns for Artist View ---
            c1, c2, c3 = st.columns([1.1, 1.1, 1])
            
            with c1:
                st.markdown('<div class="section-header"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
                df_tracks = run_query("""
                    SELECT so.id AS song_id, so.title as song_title, 'Track' as sub, so.image_url,
                           COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 3) as hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid AND s.played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY so.id, so.title, so.image_url ORDER BY streams DESC LIMIT 7
                """, {"aid": detail_id, **F})
                
                if not df_tracks.empty:
                    render_list_v2(df_tracks, "song_title", "sub", "streams", "hours_played", "song_id", "song")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("See Full List →", key=f"btn_full_tracks_{detail_id}", use_container_width=True):
                        st.query_params.clear()
                        st.query_params["tab"] = "tracks"
                        # Set session state so it's picked up by the input key on next render
                        st.session_state["search_tracks"] = artist_name
                        st.rerun()

            with c2:
                st.markdown('<div class="section-header"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)
                df_albums = run_query("""
                    SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                           MAX(so.image_url) AS image_url,
                           COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                    LEFT JOIN albums al ON al.id = so.album_id
                    WHERE sa.artist_id = :aid AND s.played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY al.id, al.title ORDER BY streams DESC LIMIT 7
                """, {"aid": detail_id, **F})
                
                if not df_albums.empty:
                    df_albums["subtitle"] = "Album"
                    render_list_v2(df_albums, "album_title", "subtitle", "streams", "hours_played", "album_id", "album")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("See Full List →", key=f"btn_full_albums_{detail_id}", use_container_width=True):
                        st.query_params.clear()
                        st.query_params["tab"] = "albums"
                        # Set session state so it's picked up by the input key on next render
                        st.session_state["search_albums"] = artist_name
                        st.rerun()

            with c3:
                st.markdown('<div class="chart-container"><div class="chart-title">📈 Timeline</div>', unsafe_allow_html=True)
                df_t = run_query("""
                    SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count,
                           ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played
                    FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid AND played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY 1 ORDER BY 1
                """, {"aid": detail_id, **F})
                if not df_t.empty:
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
                df_h = run_query("""
                    SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count
                    FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid AND played_at::date BETWEEN :start_date AND :end_date
                    GROUP BY 1 ORDER BY 1
                """, {"aid": detail_id, **F})
                if not df_h.empty:
                    st.plotly_chart(
                        chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "album":
        alb_info = run_query("""
            SELECT al.title, MAX(so.image_url) as image_url, COUNT(s.id) as streams,
                   ROUND(SUM(s.ms_played)/3600000.0, 2) as hours,
                   COUNT(DISTINCT s.song_id) as track_count
            FROM albums al
            LEFT JOIN songs so ON so.album_id = al.id
            LEFT JOIN streams s ON s.song_id = so.id AND s.played_at::date BETWEEN :start_date AND :end_date
            WHERE al.id = :id
            GROUP BY al.id, al.title
        """, {"id": detail_id, **F})

        if not alb_info.empty:
            row = alb_info.iloc[0]
            render_detail_header(
                type_label="Album",
                title=str(row["title"]) if row["title"] else "Unknown Album",
                subtitle=f"{int(row['track_count'] or 0)} tracks played", icon="💿",
                stats=[
                    {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                    {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            st.markdown('<div class="section-header"><span class="icon">🎵</span>Album Tracks</div>', unsafe_allow_html=True)
            df_tracks = run_query("""
                SELECT so.id AS song_id, so.title AS song_title,
                       COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                       COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE so.album_id = :aid AND s.played_at::date BETWEEN :start_date AND :end_date
                GROUP BY so.id, so.title, a.name, so.image_url ORDER BY streams DESC
            """, {"aid": detail_id, **F})
            if not df_tracks.empty:
                render_list_v2(df_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song")
            else:
                st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found in this period</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# TAB VIEWS
# ══════════════════════════════════════════════════════════════════

elif current_tab == "overview":

    if st.session_state.date_preset == "wrapped":
        st.markdown(f'''
        <div class="wrapped-banner">
            <div class="wrapped-title">🎁 Your {max_date.year} Wrapped</div>
            <div class="wrapped-subtitle">Your year in music so far • {st.session_state.start_date.strftime("%b %d")} — {st.session_state.end_date.strftime("%b %d, %Y")}</div>
        </div>
        ''', unsafe_allow_html=True)

    df_kpi = run_query("""
        SELECT
            ROUND(SUM(s.ms_played) / 3600000.0, 1) AS total_hours,
            COUNT(DISTINCT sa.artist_id) AS unique_artists,
            COUNT(DISTINCT s.song_id) AS unique_songs,
            COUNT(s.id) AS total_streams
        FROM streams s
        JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        WHERE s.played_at::date BETWEEN :start_date AND :end_date;
    """, F)

    if not df_kpi.empty:
        row = df_kpi.iloc[0]
        render_kpi_grid([
            {"icon": "⏱️", "title": "Listening Time", "value": f"{float(row['total_hours'] or 0):,.1f}", "unit": "hrs"},
            {"icon": "🎵", "title": "Total Streams", "value": f"{int(row['total_streams'] or 0):,}"},
            {"icon": "🎤", "title": "Unique Artists", "value": f"{int(row['unique_artists'] or 0):,}"},
            {"icon": "🎶", "title": "Unique Songs", "value": f"{int(row['unique_songs'] or 0):,}"},
        ])

    st.markdown('<div class="section-header"><span class="icon">📈</span>Listening Trend</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    df_trend = run_query("""
        SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count,
               ROUND(SUM(ms_played) / 3600000.0, 2) AS hours_played
        FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date
        GROUP BY 1 ORDER BY 1;
    """, F)
    if not df_trend.empty:
        st.plotly_chart(chart_trend(df_trend), use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-header"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
        df_top_tracks = run_query("""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
            GROUP BY so.id, so.title, a.name, so.image_url ORDER BY streams DESC LIMIT 5;
        """, F)
        if not df_top_tracks.empty:
            render_list_v2(df_top_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song")

    with c2:
        st.markdown('<div class="section-header"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)
        df_top_artists = run_query("""
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url, COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
            GROUP BY a.id, a.name, a.image_url ORDER BY streams DESC LIMIT 5;
        """, F)
        if not df_top_artists.empty:
            df_top_artists["subtitle"] = "Artist"
            render_list_v2(df_top_artists, "artist_name", "subtitle", "streams", "hours_played", "artist_id", "artist")


elif current_tab == "tracks":
    st.markdown('<div class="section-header"><span class="icon">🎵</span>Track Explorer</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search tracks...", placeholder="e.g. Starboy, Red Moon...", label_visibility="collapsed", key="search_tracks")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200, 500], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_songs = run_query("""
            WITH ranked AS (
                SELECT so.id AS song_id, so.title AS song_title,
                       COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                       COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played,
                       ROW_NUMBER() OVER (ORDER BY COUNT(s.id) DESC) AS global_rank
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :start_date AND :end_date
                GROUP BY so.id, so.title, a.name, so.image_url
            )
            SELECT * FROM ranked
            WHERE song_title ILIKE :search OR main_artist ILIKE :search
            ORDER BY global_rank
            LIMIT :limit;
        """, query_params)
    else:
        df_songs = run_query("""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY COUNT(s.id) DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
            GROUP BY so.id, so.title, a.name, so.image_url
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)

    if not df_songs.empty:
        render_list_v2(df_songs, "song_title", "main_artist", "streams", "hours_played",
                       "song_id", "song", rank_col="global_rank")
    else:
        st.markdown('<div class="empty-state"><div class="icon">🔍</div>No tracks found</div>', unsafe_allow_html=True)


elif current_tab == "artists":
    st.markdown('<div class="section-header"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search artists...", placeholder="e.g. Drake, Nicki Minaj...", label_visibility="collapsed", key="search_artists")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_artists = run_query("""
            WITH ranked AS (
                SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                       COUNT(s.id) AS streams,
                       ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                       ROW_NUMBER() OVER (ORDER BY SUM(s.ms_played) DESC) AS global_rank
                FROM streams s
                JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :start_date AND :end_date
                GROUP BY a.id, a.name, a.image_url
            )
            SELECT * FROM ranked
            WHERE artist_name ILIKE :search
            ORDER BY global_rank
            LIMIT :limit;
        """, query_params)
    else:
        df_artists = run_query("""
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY SUM(s.ms_played) DESC) AS global_rank
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
            GROUP BY a.id, a.name, a.image_url
            ORDER BY hours_played DESC LIMIT :limit;
        """, query_params)

    if not df_artists.empty:
        df_artists["subtitle"] = "Artist"
        render_list_v2(df_artists, "artist_name", "subtitle", "streams", "hours_played",
                       "artist_id", "artist", rank_col="global_rank")
    else:
        st.markdown('<div class="empty-state"><div class="icon">🎤</div>No artists found</div>', unsafe_allow_html=True)


elif current_tab == "albums":
    st.markdown('<div class="section-header"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search albums...", placeholder="e.g. Take Care, UTOPIA...", label_visibility="collapsed", key="search_albums")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_albums = run_query("""
            WITH ranked AS (
                SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                       MAX(so.image_url) AS image_url,
                       COUNT(s.id) AS streams,
                       ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                       ROW_NUMBER() OVER (ORDER BY SUM(s.ms_played) DESC) AS global_rank
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                LEFT JOIN albums al ON al.id = so.album_id
                WHERE s.played_at::date BETWEEN :start_date AND :end_date
                GROUP BY al.id, al.title
            )
            SELECT * FROM ranked
            WHERE album_title ILIKE :search
            ORDER BY global_rank
            LIMIT :limit;
        """, query_params)
    else:
        df_albums = run_query("""
            SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY SUM(s.ms_played) DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
            GROUP BY al.id, al.title
            ORDER BY hours_played DESC LIMIT :limit;
        """, query_params)

    if not df_albums.empty:
        df_albums["subtitle"] = "Album"
        render_list_v2(df_albums, "album_title", "subtitle", "streams", "hours_played",
                       "album_id", "album", rank_col="global_rank")
    else:
        st.markdown('<div class="empty-state"><div class="icon">💿</div>No albums found</div>', unsafe_allow_html=True)


elif current_tab == "habits":
    st.markdown('<div class="section-header"><span class="icon">🕐</span>Listening Habits</div>', unsafe_allow_html=True)

    st.markdown('<div class="chart-container"><div class="chart-title">📊 Activity Heatmap (Day × Hour)</div>', unsafe_allow_html=True)
    df_heatmap = run_query("""
        SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, EXTRACT(HOUR FROM played_at)::INT AS hour,
               COUNT(*) AS stream_count
        FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date
        GROUP BY 1, 2;
    """, F)
    if not df_heatmap.empty:
        st.plotly_chart(chart_heatmap(df_heatmap), use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container"><div class="chart-title">⏰ Peak Hours</div>', unsafe_allow_html=True)
        df_hours = run_query("""
            SELECT EXTRACT(HOUR FROM played_at)::INT AS hour, COUNT(*) AS stream_count
            FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date
            GROUP BY 1 ORDER BY 1;
        """, F)
        if not df_hours.empty:
            st.plotly_chart(
                chart_bar(df_hours["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_hours["stream_count"].tolist(), "Hour"),
                use_container_width=True, config={"displayModeBar": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container"><div class="chart-title">📅 Active Days</div>', unsafe_allow_html=True)
        df_days = run_query("""
            SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, COUNT(*) AS stream_count
            FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date
            GROUP BY 1 ORDER BY 1;
        """, F)
        if not df_days.empty:
            dow_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
            st.plotly_chart(
                chart_bar(df_days["dow"].map(dow_map).tolist(), df_days["stream_count"].tolist(), "Day"),
                use_container_width=True, config={"displayModeBar": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)