import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────
# CONFIG & THEME
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Spotify Analytics",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Palette
BG        = "#0D0D0D"
SURFACE   = "#161616"
CARD      = "#1E1E1E"
BORDER    = "#2A2A2A"
GREEN     = "#1DB954"
GREEN_DIM = "#14833B"
TEXT      = "#FFFFFF"
TEXT_MID  = "#B3B3B3"
TEXT_DIM  = "#6B6B6B"

PLOTLY_TEMPLATE = dict(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=TEXT_MID),
        title=dict(font=dict(color=TEXT, size=15)),
        xaxis=dict(gridcolor=BORDER, linecolor=BORDER, zerolinecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, linecolor=BORDER, zerolinecolor=BORDER),
        colorway=[GREEN, "#1ED760", "#148A3E", "#0F6B30", "#0A4D22"],
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER),
        margin=dict(t=40, b=40, l=40, r=20),
    )
)

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  html, body, [class*="css"] {{
      font-family: 'Inter', sans-serif;
      background-color: {BG};
      color: {TEXT};
  }}

  /* hide streamlit chrome */
  #MainMenu, footer, header {{ visibility: hidden; }}
  .block-container {{ padding: 2rem 2.5rem 4rem; max-width: 1400px; }}

  /* tabs */
  div[data-baseweb="tab-list"] {{
      background: {SURFACE};
      border-radius: 10px;
      padding: 4px;
      gap: 2px;
      border: 1px solid {BORDER};
  }}
  div[data-baseweb="tab"] {{
      border-radius: 8px !important;
      padding: 0.5rem 1.4rem !important;
      color: {TEXT_DIM} !important;
      font-weight: 500;
      font-size: 0.875rem;
  }}
  div[aria-selected="true"][data-baseweb="tab"] {{
      background: {GREEN} !important;
      color: {BG} !important;
  }}

  /* KPI cards */
  .kpi-card {{
      background: {CARD};
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 1.4rem 1.6rem;
      position: relative;
      overflow: hidden;
  }}
  .kpi-card::before {{
      content: '';
      position: absolute;
      top: 0; left: 0;
      width: 3px; height: 100%;
      background: {GREEN};
      border-radius: 12px 0 0 12px;
  }}
  .kpi-label {{
      color: {TEXT_DIM};
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 0.4rem;
  }}
  .kpi-value {{
      color: {TEXT};
      font-size: 2rem;
      font-weight: 700;
      line-height: 1.1;
  }}
  .kpi-unit {{
      color: {TEXT_MID};
      font-size: 0.85rem;
      font-weight: 400;
      margin-left: 4px;
  }}

  /* section headers */
  .section-title {{
      color: {TEXT};
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      margin: 2rem 0 1rem;
      padding-bottom: 0.6rem;
      border-bottom: 1px solid {BORDER};
  }}

  /* data tables */
  div[data-testid="stDataFrame"] thead tr th {{
      background: {SURFACE} !important;
      color: {TEXT_DIM} !important;
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
  }}
  div[data-testid="stDataFrame"] tbody tr:hover td {{
      background: {CARD} !important;
  }}

  /* selectbox */
  div[data-baseweb="select"] > div {{
      background: {CARD} !important;
      border-color: {BORDER} !important;
      color: {TEXT} !important;
      border-radius: 8px !important;
  }}

  /* page title */
  .page-header {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.75rem;
  }}
  .page-title {{
      font-size: 1.6rem;
      font-weight: 700;
      color: {TEXT};
      letter-spacing: -0.01em;
  }}
  .page-dot {{
      color: {GREEN};
      font-size: 1.6rem;
  }}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# DB CONNECTION (cached)
# ──────────────────────────────────────────────
CONNECTION_STRING = "postgresql://postgres:secret@localhost:5432/spotify_db"

@st.cache_resource
def get_engine():
    return create_engine(CONNECTION_STRING, pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


# ──────────────────────────────────────────────
# SQL QUERIES
# ──────────────────────────────────────────────

SQL_KPIS = """
SELECT
    ROUND(SUM(ms_played) / 3600000.0, 1)  AS total_hours,
    COUNT(DISTINCT s.song_id)              AS unique_songs,
    COUNT(DISTINCT sa.artist_id)           AS unique_artists
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id
WHERE sa.is_feature = FALSE;
"""

SQL_STREAMS_OVER_TIME = """
SELECT
    DATE_TRUNC('month', played_at) AS period,
    COUNT(*)                        AS stream_count,
    ROUND(SUM(ms_played) / 3600000.0, 2) AS hours_played
FROM streams
GROUP BY 1
ORDER BY 1;
"""

SQL_TOP_ARTISTS = """
SELECT
    a.name                                       AS artist,
    COUNT(s.id)                                  AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 2)      AS hours_played
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
JOIN artists a       ON a.id = sa.artist_id
GROUP BY a.id, a.name
ORDER BY hours_played DESC
LIMIT 10;
"""

SQL_ALL_ARTISTS = """
SELECT DISTINCT a.id, a.name
FROM artists a
JOIN song_artists sa ON sa.artist_id = a.id
ORDER BY a.name;
"""

SQL_ARTIST_TOP_SONGS = """
SELECT
    so.title                                         AS song,
    COUNT(s.id)                                      AS stream_count,
    ROUND(SUM(s.ms_played) / 3600000.0, 3)          AS hours_played
FROM streams s
JOIN songs so        ON so.id = s.song_id
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.artist_id = :artist_id
GROUP BY so.id, so.title
ORDER BY stream_count DESC
LIMIT 10;
"""

SQL_ARTIST_PEAK_HOURS = """
SELECT
    EXTRACT(HOUR FROM played_at)::INT AS hour,
    COUNT(*)                           AS stream_count
FROM streams s
JOIN song_artists sa ON sa.song_id = s.song_id AND sa.artist_id = :artist_id
GROUP BY 1
ORDER BY 1;
"""

SQL_HEATMAP = """
SELECT
    EXTRACT(ISODOW FROM played_at)::INT  AS dow,
    EXTRACT(HOUR   FROM played_at)::INT  AS hour,
    COUNT(*)                              AS stream_count
FROM streams
GROUP BY 1, 2
ORDER BY 1, 2;
"""

SQL_HOURLY = """
SELECT
    EXTRACT(HOUR FROM played_at)::INT AS hour,
    COUNT(*)                           AS stream_count
FROM streams
GROUP BY 1
ORDER BY 1;
"""

SQL_DOW = """
SELECT
    EXTRACT(ISODOW FROM played_at)::INT AS dow,
    COUNT(*)                             AS stream_count
FROM streams
GROUP BY 1
ORDER BY 1;
"""


# ──────────────────────────────────────────────
# CHART HELPERS
# ──────────────────────────────────────────────

def apply_theme(fig):
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def streams_trend_chart(df: pd.DataFrame) -> go.Figure:
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["stream_count"],
        name="Streams",
        mode="lines+markers",
        line=dict(color=GREEN, width=2.5),
        marker=dict(size=5, color=GREEN),
        fill="tozeroy",
        fillcolor=f"rgba(29,185,84,0.10)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Streams: %{y:,}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["period"], y=df["hours_played"],
        name="Hours",
        marker_color=f"rgba(29,185,84,0.25)",
        yaxis="y2",
        hovertemplate="<b>%{x|%b %Y}</b><br>Hours: %{y:.1f}<extra></extra>",
    ))
    fig.update_layout(
        yaxis=dict(title="Streams"),
        yaxis2=dict(title="Hours Played", overlaying="y", side="right", showgrid=False),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
    )
    return apply_theme(fig)


def top_artists_chart(df: pd.DataFrame) -> go.Figure:
    df_sorted = df.sort_values("hours_played")
    fig = go.Figure(go.Bar(
        x=df_sorted["hours_played"],
        y=df_sorted["artist"],
        orientation="h",
        marker=dict(
            color=df_sorted["hours_played"],
            colorscale=[[0, GREEN_DIM], [1, GREEN]],
            showscale=False,
        ),
        text=df_sorted["hours_played"].apply(lambda v: f"{v:.1f}h"),
        textposition="outside",
        textfont=dict(color=TEXT_MID, size=11),
        hovertemplate="<b>%{y}</b><br>Hours: %{x:.2f}<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Hours Played", yaxis_title="")
    return apply_theme(fig)


def heatmap_chart(df: pd.DataFrame) -> go.Figure:
    DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = (
        df.pivot(index="dow", columns="hour", values="stream_count")
          .reindex(index=range(1, 8), columns=range(24))
          .fillna(0)
    )
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}:00" for h in range(24)],
        y=DOW_LABELS,
        colorscale=[[0, BG], [0.3, GREEN_DIM], [1, GREEN]],
        showscale=True,
        hovertemplate="<b>%{y}</b> at <b>%{x}</b><br>Streams: %{z:,}<extra></extra>",
        colorbar=dict(tickfont=dict(color=TEXT_DIM), len=0.8),
    ))
    fig.update_layout(xaxis_title="Hour of Day", yaxis_title="")
    return apply_theme(fig)


def hour_bar_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=df["hour"].apply(lambda h: f"{h:02d}:00"),
        y=df["stream_count"],
        marker_color=[GREEN if v == df["stream_count"].max() else f"rgba(29,185,84,0.45)"
                      for v in df["stream_count"]],
        hovertemplate="<b>%{x}</b><br>Streams: %{y:,}<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Hour of Day", yaxis_title="Streams",
                      bargap=0.15)
    return apply_theme(fig)


def dow_bar_chart(df: pd.DataFrame) -> go.Figure:
    DAYS = {1:"Mon",2:"Tue",3:"Wed",4:"Thu",5:"Fri",6:"Sat",7:"Sun"}
    df["day_name"] = df["dow"].map(DAYS)
    fig = go.Figure(go.Bar(
        x=df["day_name"],
        y=df["stream_count"],
        marker_color=[GREEN if v == df["stream_count"].max() else f"rgba(29,185,84,0.45)"
                      for v in df["stream_count"]],
        hovertemplate="<b>%{x}</b><br>Streams: %{y:,}<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Day of Week", yaxis_title="Streams",
                      bargap=0.2)
    return apply_theme(fig)


def artist_hours_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=df["hour"].apply(lambda h: f"{h:02d}:00"),
        y=df["stream_count"],
        marker_color=[GREEN if v == df["stream_count"].max() else f"rgba(29,185,84,0.45)"
                      for v in df["stream_count"]],
        hovertemplate="<b>%{x}</b><br>Streams: %{y:,}<extra></extra>",
    ))
    fig.update_layout(xaxis_title="Hour of Day", yaxis_title="Streams",
                      bargap=0.15)
    return apply_theme(fig)


# ──────────────────────────────────────────────
# PAGE HEADER
# ──────────────────────────────────────────────

st.markdown("""
<div class="page-header">
  <span style="font-size:1.8rem;">🎧</span>
  <span class="page-title">Spotify Analytics</span>
  <span class="page-dot">·</span>
  <span style="color:#6B6B6B;font-size:0.85rem;margin-top:4px;">Streaming Intelligence Dashboard</span>
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────

tab_overview, tab_artists, tab_habits = st.tabs(
    ["📊  Overview", "🎤  Artist Analytics", "🕐  Listening Habits"]
)


# ╔══════════════════════════════════════╗
# ║           TAB 1 – OVERVIEW           ║
# ╚══════════════════════════════════════╝
with tab_overview:

    with st.spinner("Loading overview…"):
        df_kpi  = run_query(SQL_KPIS)
        df_time = run_query(SQL_STREAMS_OVER_TIME)

    # KPI row
    total_hours    = float(df_kpi["total_hours"].iloc[0])
    unique_songs   = int(df_kpi["unique_songs"].iloc[0])
    unique_artists = int(df_kpi["unique_artists"].iloc[0])

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Total Listening Time</div>
            <div class="kpi-value">{total_hours:,.1f}<span class="kpi-unit">hrs</span></div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Unique Artists</div>
            <div class="kpi-value">{unique_artists:,}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Unique Songs</div>
            <div class="kpi-value">{unique_songs:,}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-title">Streaming Trend Over Time</div>',
                unsafe_allow_html=True)
    st.plotly_chart(
        streams_trend_chart(df_time),
        use_container_width=True, config={"displayModeBar": False}
    )


# ╔══════════════════════════════════════╗
# ║       TAB 2 – ARTIST ANALYTICS       ║
# ╚══════════════════════════════════════╝
with tab_artists:

    # ── Top 10 Artists ──────────────────
    st.markdown('<div class="section-title">Top 10 Artists by Listening Time</div>',
                unsafe_allow_html=True)

    with st.spinner("Loading artist data…"):
        df_top = run_query(SQL_TOP_ARTISTS)

    col_tbl, col_chart = st.columns([1, 1.6], gap="large")

    with col_tbl:
        display_df = df_top.copy()
        display_df.index = range(1, len(display_df) + 1)
        display_df.columns = ["Artist", "Streams", "Hours Played"]
        st.dataframe(
            display_df,
            use_container_width=True,
            height=380,
        )

    with col_chart:
        st.plotly_chart(
            top_artists_chart(df_top),
            use_container_width=True, config={"displayModeBar": False}
        )

    # ── Per-Artist Drill-down ────────────
    st.markdown('<div class="section-title">Artist Deep-Dive</div>',
                unsafe_allow_html=True)

    with st.spinner("Loading artist list…"):
        df_all_artists = run_query(SQL_ALL_ARTISTS)

    artist_map  = dict(zip(df_all_artists["name"], df_all_artists["id"]))
    artist_name = st.selectbox(
        "Select an artist",
        options=list(artist_map.keys()),
        label_visibility="collapsed",
    )
    artist_id = int(artist_map[artist_name])

    with st.spinner(f"Loading data for {artist_name}…"):
        df_songs = run_query(SQL_ARTIST_TOP_SONGS, {"artist_id": artist_id})
        df_ah    = run_query(SQL_ARTIST_PEAK_HOURS, {"artist_id": artist_id})

    dd_left, dd_right = st.columns([1.2, 1], gap="large")

    with dd_left:
        st.markdown(f"**Top Songs · {artist_name}**")
        display_songs = df_songs.copy()
        display_songs.index = range(1, len(display_songs) + 1)
        display_songs.columns = ["Song", "Streams", "Hours"]
        st.dataframe(display_songs, use_container_width=True, height=340)

    with dd_right:
        st.markdown(f"**Peak Listening Hours · {artist_name}**")
        st.plotly_chart(
            artist_hours_chart(df_ah),
            use_container_width=True, config={"displayModeBar": False}
        )


# ╔══════════════════════════════════════╗
# ║       TAB 3 – LISTENING HABITS       ║
# ╚══════════════════════════════════════╝
with tab_habits:

    with st.spinner("Loading habits data…"):
        df_heatmap = run_query(SQL_HEATMAP)
        df_hourly  = run_query(SQL_HOURLY)
        df_dow     = run_query(SQL_DOW)

    st.markdown('<div class="section-title">Activity Heatmap — Hour × Day</div>',
                unsafe_allow_html=True)
    st.plotly_chart(
        heatmap_chart(df_heatmap),
        use_container_width=True, config={"displayModeBar": False}
    )

    col_h, col_d = st.columns(2, gap="large")
    with col_h:
        st.markdown('<div class="section-title">Peak Hours of the Day</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(
            hour_bar_chart(df_hourly),
            use_container_width=True, config={"displayModeBar": False}
        )
    with col_d:
        st.markdown('<div class="section-title">Most Active Days of the Week</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(
            dow_bar_chart(df_dow),
            use_container_width=True, config={"displayModeBar": False}
        )
