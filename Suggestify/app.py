import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import datetime
import warnings
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════
# PAGE CONFIG  (must be first Streamlit call)
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Spotify Analytics",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════
BG        = "#0D0D0D"
SURFACE   = "#141414"
CARD      = "#1A1A1A"
CARD2     = "#222222"
BORDER    = "#2C2C2C"
GREEN     = "#1DB954"
GREEN_LO  = "#14833B"
GREEN_XLO = "#0A4D22"
TEXT      = "#FFFFFF"
TEXT_MID  = "#A0A0A0"
TEXT_DIM  = "#555555"

# ══════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800&display=swap');

/* ── reset ─────────────────────────────────── */
html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif !important;
    background-color: {BG} !important;
    color: {TEXT};
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{
    padding: 1.6rem 2.2rem 4rem !important;
    max-width: 1480px !important;
}}

/* ── sidebar ────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: {SURFACE} !important;
    border-right: 1px solid {BORDER};
}}
[data-testid="stSidebar"] .block-container {{
    padding: 1.5rem 1.2rem !important;
}}
.sidebar-logo {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 1.6rem;
    padding-bottom: 1.2rem;
    border-bottom: 1px solid {BORDER};
}}
.sidebar-logo-text {{
    font-size: 1.05rem;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: -0.01em;
}}
.sidebar-section {{
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {TEXT_DIM};
    margin: 1.4rem 0 0.6rem;
}}

/* ── page header ────────────────────────────── */
.page-header {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 1.6rem;
}}
.page-title {{
    font-size: 1.55rem;
    font-weight: 800;
    color: {TEXT};
    letter-spacing: -0.02em;
}}
.page-sub {{
    font-size: 0.82rem;
    color: {TEXT_DIM};
}}

/* ── tabs ───────────────────────────────────── */
div[data-baseweb="tab-list"] {{
    background: {SURFACE} !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 2px !important;
    border: 1px solid {BORDER} !important;
    margin-bottom: 0.2rem;
}}
div[data-baseweb="tab"] {{
    border-radius: 7px !important;
    padding: 0.45rem 1.2rem !important;
    color: {TEXT_DIM} !important;
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    transition: all 0.15s ease !important;
}}
div[aria-selected="true"][data-baseweb="tab"] {{
    background: {GREEN} !important;
    color: {BG} !important;
    font-weight: 600 !important;
}}

/* ── KPI cards ──────────────────────────────── */
.kpi-row {{ display: flex; gap: 1rem; margin-bottom: 1.6rem; }}
.kpi-card {{
    flex: 1;
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    position: relative;
    overflow: hidden;
}}
.kpi-card::after {{
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: linear-gradient(180deg, {GREEN} 0%, {GREEN_LO} 100%);
}}
.kpi-label {{
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {TEXT_DIM};
    margin-bottom: 0.3rem;
}}
.kpi-value {{
    font-size: 2.1rem;
    font-weight: 800;
    color: {TEXT};
    line-height: 1;
    letter-spacing: -0.02em;
}}
.kpi-unit {{
    font-size: 0.85rem;
    font-weight: 400;
    color: {TEXT_MID};
    margin-left: 3px;
}}
.kpi-delta {{
    font-size: 0.75rem;
    color: {GREEN};
    margin-top: 0.3rem;
}}

/* ── section titles ─────────────────────────── */
.section-title {{
    font-size: 0.88rem;
    font-weight: 700;
    color: {TEXT};
    letter-spacing: 0.01em;
    margin: 1.8rem 0 0.9rem;
    padding-bottom: 0.55rem;
    border-bottom: 1px solid {BORDER};
    display: flex;
    align-items: center;
    gap: 0.5rem;
}}
.section-badge {{
    font-size: 0.65rem;
    background: {CARD2};
    color: {TEXT_MID};
    border: 1px solid {BORDER};
    border-radius: 20px;
    padding: 1px 8px;
    font-weight: 500;
    letter-spacing: 0.05em;
}}

/* ── dataframes ─────────────────────────────── */
div[data-testid="stDataFrame"] {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid {BORDER} !important;
}}
div[data-testid="stDataFrame"] thead tr th {{
    background: {CARD2} !important;
    color: {TEXT_DIM} !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    padding: 0.6rem 0.8rem !important;
}}
div[data-testid="stDataFrame"] tbody tr td {{
    background: {CARD} !important;
    color: {TEXT_MID} !important;
    font-size: 0.82rem !important;
    border-bottom: 1px solid {BORDER} !important;
}}
div[data-testid="stDataFrame"] tbody tr:hover td {{
    background: {CARD2} !important;
    color: {TEXT} !important;
}}

/* ── selectbox ──────────────────────────────── */
div[data-baseweb="select"] > div {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}}

/* ── date input ─────────────────────────────── */
div[data-testid="stDateInput"] input {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 8px !important;
    font-size: 0.82rem !important;
}}

/* ── spinner text ───────────────────────────── */
div[data-testid="stSpinner"] p {{ color: {TEXT_MID} !important; }}

/* ── divider ────────────────────────────────── */
hr {{ border-color: {BORDER} !important; margin: 1rem 0; }}
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


# ══════════════════════════════════════════════════════════════════
# DATE RANGE BOOTSTRAP (no date filter here — needed for defaults)
# ══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner=False)
def get_date_bounds() -> tuple[datetime.date, datetime.date]:
    df = run_query("SELECT MIN(played_at)::date AS mn, MAX(played_at)::date AS mx FROM streams;")
    return df["mn"].iloc[0], df["mx"].iloc[0]


# ══════════════════════════════════════════════════════════════════
# SIDEBAR — GLOBAL FILTERS
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <span style="font-size:1.5rem;">🎧</span>
        <span class="sidebar-logo-text">Spotify Analytics</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">📅 Date Range</div>', unsafe_allow_html=True)

    min_date, max_date = get_date_bounds()

    start_date = st.date_input(
        "From", value=min_date, min_value=min_date, max_value=max_date, key="start"
    )
    end_date = st.date_input(
        "To", value=max_date, min_value=min_date, max_value=max_date, key="end"
    )

    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()

    # Human-readable range summary
    delta_days = (end_date - start_date).days
    st.markdown(f"""
    <div style="margin-top:0.8rem;padding:0.7rem;background:{CARD};
                border:1px solid {BORDER};border-radius:8px;font-size:0.75rem;color:{TEXT_MID};">
        <b style="color:{GREEN};">{delta_days:,}</b> days selected<br>
        {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">ℹ️ About</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:0.73rem;color:{TEXT_DIM};line-height:1.6;">
        All metrics filtered by selected date range. Aggregations run directly in PostgreSQL.
        Data refreshes every 5 min.
    </div>
    """, unsafe_allow_html=True)

# Shared filter dict for all parameterised queries
F = {"start_date": start_date, "end_date": end_date}

# ══════════════════════════════════════════════════════════════════
# SQL LIBRARY
# ══════════════════════════════════════════════════════════════════

# ── Overview ────────────────────────────────────────────────────
SQL_KPIS = """
SELECT
    ROUND(SUM(s.ms_played) / 3600000.0, 1)   AS total_hours,
    COUNT(DISTINCT sa.artist_id)              AS unique_artists,
    COUNT(DISTINCT s.song_id)                 AS unique_songs,
    COUNT(s.id)                               AS total_streams
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
WHERE s.played_at::date BETWEEN :start_date AND :end_date;
"""

SQL_TREND = """
SELECT
    DATE_TRUNC('month', played_at)               AS period,
    COUNT(*)                                      AS stream_count,
    ROUND(SUM(ms_played) / 3600000.0, 2)         AS hours_played
FROM streams
WHERE played_at::date BETWEEN :start_date AND :end_date
GROUP BY 1
ORDER BY 1;
"""

# ── Artist Analytics ─────────────────────────────────────────────
SQL_TOP_ARTISTS = """
SELECT
    a.name                                       AS artist,
    COUNT(s.id)                                  AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 2)      AS hours_played
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
JOIN artists a       ON a.id = sa.artist_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY a.id, a.name
ORDER BY hours_played DESC
LIMIT 10;
"""

SQL_ALL_ARTISTS = """
SELECT DISTINCT a.id, a.name
FROM artists a
JOIN song_artists sa ON sa.artist_id = a.id
JOIN streams s       ON s.song_id = sa.song_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
ORDER BY a.name;
"""

SQL_ARTIST_SONGS = """
SELECT
    so.title                                     AS song,
    COUNT(s.id)                                  AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 3)      AS hours_played
FROM streams s
JOIN songs so        ON so.id = s.song_id
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.artist_id = :artist_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY so.id, so.title
ORDER BY stream_count DESC
LIMIT 10;
"""

SQL_ARTIST_HOURS = """
SELECT
    EXTRACT(HOUR FROM s.played_at)::INT          AS hour,
    COUNT(*)                                      AS stream_count
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.artist_id = :artist_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY 1
ORDER BY 1;
"""

# ── Album Analytics ──────────────────────────────────────────────
SQL_TOP_ALBUMS = """
SELECT
    COALESCE(al.title, 'Unknown Album')          AS album,
    COUNT(s.id)                                  AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 2)      AS hours_played
FROM streams s
JOIN songs so  ON so.id = s.song_id
LEFT JOIN albums al ON al.id = so.album_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY al.id, al.title
ORDER BY hours_played DESC
LIMIT 10;
"""

SQL_ALL_ALBUMS = """
SELECT DISTINCT al.id, al.title
FROM albums al
JOIN songs so  ON so.album_id = al.id
JOIN streams s ON s.song_id = so.id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
ORDER BY al.title;
"""

SQL_ALBUM_TRACKS = """
SELECT
    so.title                                     AS song,
    COUNT(s.id)                                  AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 3)      AS hours_played
FROM streams s
JOIN songs so ON so.id = s.song_id
WHERE so.album_id = :album_id
  AND s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY so.id, so.title
ORDER BY hours_played DESC;
"""

# ── Top 100 Songs ────────────────────────────────────────────────
SQL_TOP_SONGS = """
SELECT
    so.title                                         AS song_title,
    COALESCE(
        (SELECT a.name FROM artists a
         JOIN song_artists sa2 ON sa2.artist_id = a.id
         WHERE sa2.song_id = so.id AND sa2.is_feature = FALSE
         ORDER BY a.id LIMIT 1),
        'Unknown'
    )                                                AS main_artist,
    COALESCE(al.title, '—')                          AS album_title,
    COUNT(s.id)                                      AS streams,
    ROUND(SUM(s.ms_played) / 3600000.0, 3)          AS hours_played
FROM streams s
JOIN songs so       ON so.id = s.song_id
LEFT JOIN albums al ON al.id = so.album_id
WHERE s.played_at::date BETWEEN :start_date AND :end_date
GROUP BY so.id, so.title, al.id, al.title
ORDER BY streams DESC
LIMIT 100;
"""

# ── Listening Habits ─────────────────────────────────────────────
SQL_HEATMAP = """
SELECT
    EXTRACT(ISODOW FROM played_at)::INT  AS dow,
    EXTRACT(HOUR   FROM played_at)::INT  AS hour,
    COUNT(*)                              AS stream_count
FROM streams
WHERE played_at::date BETWEEN :start_date AND :end_date
GROUP BY 1, 2
ORDER BY 1, 2;
"""

SQL_HOURLY = """
SELECT
    EXTRACT(HOUR FROM played_at)::INT    AS hour,
    COUNT(*)                              AS stream_count
FROM streams
WHERE played_at::date BETWEEN :start_date AND :end_date
GROUP BY 1 ORDER BY 1;
"""

SQL_DOW = """
SELECT
    EXTRACT(ISODOW FROM played_at)::INT  AS dow,
    COUNT(*)                              AS stream_count
FROM streams
WHERE played_at::date BETWEEN :start_date AND :end_date
GROUP BY 1 ORDER BY 1;
"""


# ══════════════════════════════════════════════════════════════════
# PLOTLY HELPERS
# ══════════════════════════════════════════════════════════════════
_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=TEXT_MID, size=12),
    xaxis=dict(gridcolor=BORDER, linecolor=BORDER, zerolinecolor="rgba(0,0,0,0)"),
    yaxis=dict(gridcolor=BORDER, linecolor=BORDER, zerolinecolor="rgba(0,0,0,0)"),
    margin=dict(t=30, b=36, l=10, r=16),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER, font=dict(size=11)),
    hoverlabel=dict(bgcolor=CARD2, bordercolor=BORDER, font=dict(color=TEXT, size=12)),
)


def themed(fig: go.Figure, **extra) -> go.Figure:
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_layout(**extra)
    return fig


def _highlight(series: pd.Series) -> list[str]:
    mx = series.max()
    return [GREEN if v == mx else "rgba(29,185,84,0.38)" for v in series]


# ── Trend chart ────────────────────────────────────────────────
def chart_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["stream_count"],
        name="Streams",
        mode="lines+markers",
        line=dict(color=GREEN, width=2.5),
        marker=dict(size=4.5, color=GREEN),
        fill="tozeroy", fillcolor="rgba(29,185,84,0.08)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Streams: <b>%{y:,}</b><extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["period"], y=df["hours_played"],
        name="Hours",
        marker_color="rgba(29,185,84,0.22)",
        yaxis="y2",
        hovertemplate="<b>%{x|%b %Y}</b><br>Hours: <b>%{y:.1f}</b><extra></extra>",
    ))
    return themed(fig,
        yaxis=dict(title="Streams", gridcolor=BORDER, linecolor=BORDER),
        yaxis2=dict(title="Hours", overlaying="y", side="right", showgrid=False, linecolor=BORDER),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1, x=0),
    )


# ── Horizontal bar (artists / albums) ─────────────────────────
def chart_hbar(df: pd.DataFrame, y_col: str, x_col: str = "hours_played") -> go.Figure:
    d = df.sort_values(x_col)
    fig = go.Figure(go.Bar(
        x=d[x_col], y=d[y_col],
        orientation="h",
        marker=dict(
            color=d[x_col],
            colorscale=[[0, GREEN_XLO], [0.5, GREEN_LO], [1, GREEN]],
            showscale=False,
        ),
        text=d[x_col].apply(lambda v: f"{v:.1f}h"),
        textposition="outside",
        textfont=dict(color=TEXT_MID, size=10.5),
        hovertemplate=f"<b>%{{y}}</b><br>Hours: %{{x:.2f}}<extra></extra>",
    ))
    return themed(fig, xaxis_title="Hours Played", yaxis_title="", margin=dict(t=30, b=36, l=160, r=60))


# ── Heatmap ────────────────────────────────────────────────────
def chart_heatmap(df: pd.DataFrame) -> go.Figure:
    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = (
        df.pivot(index="dow", columns="hour", values="stream_count")
          .reindex(index=range(1, 8), columns=range(24)).fillna(0)
    )
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}:00" for h in range(24)],
        y=DOW,
        colorscale=[[0, BG], [0.25, GREEN_XLO], [0.65, GREEN_LO], [1, GREEN]],
        showscale=True,
        colorbar=dict(tickfont=dict(color=TEXT_DIM, size=10), len=0.9, thickness=12),
        hovertemplate="<b>%{y}</b> · <b>%{x}</b><br>Streams: <b>%{z:,}</b><extra></extra>",
    ))
    return themed(fig, xaxis_title="Hour of Day", yaxis_title="",
                  margin=dict(t=20, b=40, l=50, r=20))


# ── Simple bar (hours / dow) ───────────────────────────────────
def chart_bar(x, y, xlabel: str) -> go.Figure:
    y_series = pd.Series(y)
    fig = go.Figure(go.Bar(
        x=x, y=y,
        marker_color=_highlight(y_series),
        hovertemplate="<b>%{x}</b><br>Streams: <b>%{y:,}</b><extra></extra>",
    ))
    return themed(fig, xaxis_title=xlabel, yaxis_title="Streams", bargap=0.18)


# ── Artist peak hours ──────────────────────────────────────────
def chart_artist_hours(df: pd.DataFrame) -> go.Figure:
    labels = df["hour"].apply(lambda h: f"{h:02d}:00")
    return chart_bar(labels.tolist(), df["stream_count"].tolist(), "Hour of Day")


# ══════════════════════════════════════════════════════════════════
# PAGE HEADER
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="page-header">
    <span class="page-title">Streaming Analytics</span>
    <span class="page-dot" style="color:{GREEN};font-size:1.55rem;"> · </span>
    <span class="page-sub">{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}</span>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════
T_OV, T_AR, T_AL, T_SO, T_HA = st.tabs([
    "📊  Overview",
    "🎤  Artists",
    "💿  Albums",
    "🎵  Top Songs",
    "🕐  Habits",
])


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 1 — OVERVIEW                                           ║
# ╚══════════════════════════════════════════════════════════════╝
with T_OV:
    with st.spinner("Crunching numbers…"):
        df_kpi   = run_query(SQL_KPIS, F)
        df_trend = run_query(SQL_TREND, F)

    total_hours    = float(df_kpi["total_hours"].iloc[0] or 0)
    unique_artists = int(df_kpi["unique_artists"].iloc[0] or 0)
    unique_songs   = int(df_kpi["unique_songs"].iloc[0] or 0)
    total_streams  = int(df_kpi["total_streams"].iloc[0] or 0)

    k1, k2, k3, k4 = st.columns(4)
    for col, label, val, unit in [
        (k1, "Listening Time",   f"{total_hours:,.1f}",   "hrs"),
        (k2, "Total Streams",    f"{total_streams:,}",     ""),
        (k3, "Unique Artists",   f"{unique_artists:,}",    ""),
        (k4, "Unique Songs",     f"{unique_songs:,}",      ""),
    ]:
        with col:
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{val}<span class="kpi-unit">{unit}</span></div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-title">Streaming Trend</div>', unsafe_allow_html=True)
    st.plotly_chart(chart_trend(df_trend), use_container_width=True, config={"displayModeBar": False})


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 2 — ARTIST ANALYTICS                                   ║
# ╚══════════════════════════════════════════════════════════════╝
with T_AR:
    with st.spinner("Loading artists…"):
        df_top_artists = run_query(SQL_TOP_ARTISTS, F)
        df_all_artists = run_query(SQL_ALL_ARTISTS, F)

    st.markdown('<div class="section-title">Top 10 Artists <span class="section-badge">by hours played · excludes features</span></div>', unsafe_allow_html=True)

    c_tbl, c_chart = st.columns([1, 1.7], gap="large")
    with c_tbl:
        disp = df_top_artists.copy()
        disp.index = range(1, len(disp) + 1)
        disp.columns = ["Artist", "Streams", "Hours"]
        st.dataframe(disp, use_container_width=True, height=360)
    with c_chart:
        st.plotly_chart(chart_hbar(df_top_artists, "artist"), use_container_width=True,
                        config={"displayModeBar": False})

    # ── Deep-dive ──
    st.markdown('<div class="section-title">Artist Deep-Dive</div>', unsafe_allow_html=True)

    if df_all_artists.empty:
        st.info("No artist data for this date range.")
    else:
        artist_map  = dict(zip(df_all_artists["name"], df_all_artists["id"]))
        artist_name = st.selectbox("Artist", list(artist_map.keys()),
                                   label_visibility="collapsed", key="sel_artist")
        artist_id   = int(artist_map[artist_name])
        params_a    = {**F, "artist_id": artist_id}

        with st.spinner(f"Loading {artist_name}…"):
            df_a_songs = run_query(SQL_ARTIST_SONGS, params_a)
            df_a_hours = run_query(SQL_ARTIST_HOURS, params_a)

        dl, dr = st.columns([1.2, 1], gap="large")
        with dl:
            st.markdown(f"**Top Songs · {artist_name}**")
            ds = df_a_songs.copy()
            ds.index = range(1, len(ds) + 1)
            ds.columns = ["Song", "Streams", "Hours"]
            st.dataframe(ds, use_container_width=True, height=320)
        with dr:
            st.markdown(f"**Peak Hours · {artist_name}**")
            if df_a_hours.empty:
                st.info("No hourly data.")
            else:
                st.plotly_chart(chart_artist_hours(df_a_hours), use_container_width=True,
                                config={"displayModeBar": False})


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 3 — ALBUM ANALYTICS                                    ║
# ╚══════════════════════════════════════════════════════════════╝
with T_AL:
    with st.spinner("Loading albums…"):
        df_top_albums = run_query(SQL_TOP_ALBUMS, F)
        df_all_albums = run_query(SQL_ALL_ALBUMS, F)

    st.markdown('<div class="section-title">Top 10 Albums <span class="section-badge">by hours played</span></div>', unsafe_allow_html=True)

    a_tbl, a_chart = st.columns([1, 1.7], gap="large")
    with a_tbl:
        disp_al = df_top_albums.copy()
        disp_al.index = range(1, len(disp_al) + 1)
        disp_al.columns = ["Album", "Streams", "Hours"]
        st.dataframe(disp_al, use_container_width=True, height=360)
    with a_chart:
        st.plotly_chart(chart_hbar(df_top_albums, "album"), use_container_width=True,
                        config={"displayModeBar": False})

    # ── Track breakdown ──
    st.markdown('<div class="section-title">Album Track Breakdown</div>', unsafe_allow_html=True)

    if df_all_albums.empty:
        st.info("No album data for this date range.")
    else:
        album_map     = dict(zip(df_all_albums["title"], df_all_albums["id"]))
        selected_alb  = st.selectbox("Album", list(album_map.keys()),
                                     label_visibility="collapsed", key="sel_album")
        album_id      = int(album_map[selected_alb])
        params_al     = {**F, "album_id": album_id}

        with st.spinner(f"Loading {selected_alb}…"):
            df_tracks = run_query(SQL_ALBUM_TRACKS, params_al)

        if df_tracks.empty:
            st.info("No streams recorded for this album in the selected range.")
        else:
            dt = df_tracks.copy()
            dt.index = range(1, len(dt) + 1)
            dt.columns = ["Song Title", "Streams", "Hours"]
            st.dataframe(dt, use_container_width=True, height=380)


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 4 — TOP 100 SONGS                                      ║
# ╚══════════════════════════════════════════════════════════════╝
with T_SO:
    st.markdown('<div class="section-title">Top 100 Songs <span class="section-badge">sortable · all columns</span></div>', unsafe_allow_html=True)

    with st.spinner("Fetching top 100…"):
        df_songs = run_query(SQL_TOP_SONGS, F)

    if df_songs.empty:
        st.info("No stream data for this date range.")
    else:
        df_songs.index = range(1, len(df_songs) + 1)
        df_songs.columns = ["Song Title", "Main Artist", "Album", "Streams", "Hours Played"]
        st.dataframe(
            df_songs,
            use_container_width=True,
            height=680,
            column_config={
                "Streams":      st.column_config.NumberColumn(format="%d"),
                "Hours Played": st.column_config.NumberColumn(format="%.3f h"),
            },
        )
        st.markdown(
            f'<div style="font-size:0.73rem;color:{TEXT_DIM};margin-top:0.4rem;">'
            f'Showing top {len(df_songs)} songs · sorted by streams · click any column header to re-sort</div>',
            unsafe_allow_html=True
        )


# ╔══════════════════════════════════════════════════════════════╗
# ║  TAB 5 — LISTENING HABITS                                   ║
# ╚══════════════════════════════════════════════════════════════╝
with T_HA:
    with st.spinner("Analysing habits…"):
        df_heatmap = run_query(SQL_HEATMAP, F)
        df_hourly  = run_query(SQL_HOURLY, F)
        df_dow     = run_query(SQL_DOW, F)

    st.markdown('<div class="section-title">Activity Heatmap <span class="section-badge">day × hour</span></div>', unsafe_allow_html=True)
    st.plotly_chart(chart_heatmap(df_heatmap), use_container_width=True,
                    config={"displayModeBar": False})

    h_col, d_col = st.columns(2, gap="large")

    with h_col:
        st.markdown('<div class="section-title">Peak Hours</div>', unsafe_allow_html=True)
        if not df_hourly.empty:
            labels = df_hourly["hour"].apply(lambda h: f"{h:02d}:00").tolist()
            st.plotly_chart(
                chart_bar(labels, df_hourly["stream_count"].tolist(), "Hour of Day"),
                use_container_width=True, config={"displayModeBar": False}
            )

    with d_col:
        st.markdown('<div class="section-title">Most Active Days</div>', unsafe_allow_html=True)
        if not df_dow.empty:
            DAY_MAP = {1:"Mon", 2:"Tue", 3:"Wed", 4:"Thu", 5:"Fri", 6:"Sat", 7:"Sun"}
            labels = df_dow["dow"].map(DAY_MAP).tolist()
            st.plotly_chart(
                chart_bar(labels, df_dow["stream_count"].tolist(), "Day of Week"),
                use_container_width=True, config={"displayModeBar": False}
            )