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
    page_title="Spotify Analytics | Ody",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════
# DESIGN TOKENS & PREMIUM UX CSS
# ══════════════════════════════════════════════════════════════════
BG        = "#0A0A0A"
SURFACE   = "#141414"
CARD      = "#1C1C1C"
CARD_HOVER= "#282828"
BORDER    = "#2C2C2C"
GREEN     = "#1DB954"
GREEN_DIM = "#169C45"
GREEN_XLO = "#083B1A"
TEXT      = "#FFFFFF"
TEXT_MID  = "#E0E0E0"
TEXT_DIM  = "#8A8A8A"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif !important;
    background-color: {BG} !important;
    color: {TEXT} !important;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{
    padding: 1.5rem 2.5rem 4rem !important;
    max-width: 100% !important;
}}

/* TABS (Οριζόντια premium κουμπιά) */
div.row-widget.stRadio > div {{
    flex-direction: row !important;
    gap: 10px !important;
    background: {SURFACE} !important;
    border-radius: 14px !important;
    padding: 8px !important;
    border: 1px solid {BORDER} !important;
    margin-bottom: 2rem !important;
    justify-content: center;
}}

/* Αισθητική επιλεγμένων tab-κουμπιών */
div.row-widget.stRadio label {{
    background: transparent !important;
    border-radius: 10px !important;
    padding: 0.6rem 1.8rem !important;
    color: {TEXT_DIM} !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    border: none !important;
}}

/* KPI CARDS */
.kpi-container {{ display: flex; gap: 1.25rem; margin: 1.5rem 0 2.5rem; }}
.kpi-card {{
    flex: 1; background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px;
    padding: 1.5rem 1.8rem; position: relative; overflow: hidden;
}}
.kpi-card::after {{
    content: ''; position: absolute; top: 0; left: 0;
    width: 4px; height: 100%; background: {GREEN};
}}
.kpi-title {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: {TEXT_DIM}; margin-bottom: 0.5rem; }}
.kpi-val {{ font-size: 2.8rem; font-weight: 800; color: {TEXT}; line-height: 1; letter-spacing: -0.03em; }}
.kpi-unit {{ font-size: 0.95rem; color: {TEXT_MID}; margin-left: 5px; font-weight: 500; }}

/* PREMIUM LIST CARDS */
.list-container {{ display: flex; flex-direction: column; gap: 0.8rem; margin-top: 1rem; }}
.list-item {{ 
    display: flex; align-items: center; justify-content: space-between; 
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; 
    padding: 1.2rem 2rem; transition: all 0.25s ease; width: 100%;
}}
.list-item:hover {{
    background: {CARD_HOVER}; transform: translateY(-2px);
    border-color: {TEXT_DIM}; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}}

/* Πλαίσιο για τριψήφιους αριθμούς */
.item-rank {{ font-size: 1.8rem; font-weight: 800; color: {TEXT_DIM}; width: 95px; min-width: 95px; text-align: center; }}
.item-rank.top-3 {{ color: {GREEN}; }}

.item-main {{ flex: 1; display: flex; flex-direction: column; gap: 0.25rem; margin-left: 0.5rem; }}
.item-title {{ font-size: 1.25rem; font-weight: 700; color: {TEXT}; letter-spacing: -0.02em; }}
.item-subtitle {{ font-size: 1rem; font-weight: 400; color: {TEXT_MID}; }}

.item-stats {{ display: flex; gap: 3rem; align-items: center; text-align: right; }}
.stat-box {{ display: flex; flex-direction: column; }}
.stat-val {{ font-size: 1.6rem; font-weight: 700; color: {TEXT}; line-height: 1.1; }}
.stat-lbl {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; color: {TEXT_DIM}; letter-spacing: 0.05em; }}

/* HEADER & TITLES */
.page-title {{ font-size: 2.8rem; font-weight: 800; color: {TEXT}; letter-spacing: -0.04em; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 1rem; }}
.section-title {{ font-size: 1.35rem; font-weight: 700; color: {TEXT}; margin: 2rem 0 1.5rem; border-bottom: 1px solid {BORDER}; padding-bottom: 0.6rem; display: flex; align-items: center; gap: 0.5rem; }}

/* INPUTS */
div[data-baseweb="select"] > div, div[data-testid="stDateInput"] input, div[data-testid="stTextInput"] input {{ background: {CARD} !important; border-color: {BORDER} !important; color: {TEXT} !important; border-radius: 10px !important; font-size: 0.95rem !important; }}

/* DATE CONTAINER */
.date-container {{ display: flex; gap: 2rem; background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; padding: 1.2rem 2rem; margin-bottom: 2rem; align-items: center; }}
.date-label {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: {TEXT_DIM}; margin-bottom: 0.3rem; }}

/* CUSTOM LINKS */
a.custom-link {{ text-decoration: none !important; color: inherit !important; display: block; width: 100%; }}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# DATABASE & GLOBALS
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
def render_custom_list(df: pd.DataFrame, title_col: str, sub_col: str, streams_col: str, hours_col: str, id_col: str = None, link_type: str = None):
    html = '<div class="list-container">\n'
    for i, row in df.iterrows():
        rank = i + 1
        rank_class = "top-3" if rank <= 3 else ""
        title = escape(str(row[title_col]))
        subtitle = escape(str(row[sub_col]))
        streams = f"{int(row[streams_col]):,}"
        hours = f"{float(row[hours_col]):.1f}"

        card_html = f"""<div class="list-item">
<div class="item-rank {rank_class}">#{rank}</div>
<div class="item-main">
<div class="item-title">{title}</div>
<div class="item-subtitle">{subtitle}</div>
</div>
<div class="item-stats">
<div class="stat-box">
<span class="stat-val">{streams}</span>
<span class="stat-lbl">Streams</span>
</div>
<div class="stat-box" style="width: 80px;">
<span class="stat-val" style="color:{GREEN};">{hours}h</span>
<span class="stat-lbl">Duration</span>
</div>
</div>
</div>
"""
        if link_type and id_col and id_col in row:
            item_id = escape(str(row[id_col]))
            html += f'<a class="custom-link" href="?view_{link_type}={item_id}" target="_self">{card_html}</a>\n'
        else:
            html += card_html + "\n"
            
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ── Plotly Helpers ──
_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=TEXT_DIM, size=12),
    xaxis=dict(gridcolor=BORDER, linecolor=BORDER),
    yaxis=dict(gridcolor=BORDER, linecolor=BORDER),
    margin=dict(t=40, b=40, l=20, r=20),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=BORDER),
    hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(color=TEXT))
)

def themed(fig: go.Figure, **extra) -> go.Figure:
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_layout(**extra)
    return fig

def chart_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["period"], y=df["stream_count"], name="Streams", mode="lines+markers", line=dict(color=GREEN, width=3), marker=dict(size=6, color=GREEN), fill="tozeroy", fillcolor="rgba(30,215,96,0.08)"))
    fig.add_trace(go.Bar(x=df["period"], y=df["hours_played"], name="Hours", marker_color="rgba(30,215,96,0.25)", yaxis="y2"))
    return themed(fig, yaxis=dict(title="Streams"), yaxis2=dict(title="Hours Played", overlaying="y", side="right", showgrid=False), hovermode="x unified", legend=dict(orientation="h", y=1.15, x=0))

def chart_heatmap(df: pd.DataFrame) -> go.Figure:
    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = df.pivot(index="dow", columns="hour", values="stream_count").reindex(index=range(1, 8), columns=range(24)).fillna(0)
    fig = go.Figure(go.Heatmap(z=pivot.values, x=[f"{h:02d}:00" for h in range(24)], y=DOW, colorscale=[[0, BG], [0.25, GREEN_XLO], [0.65, GREEN_DIM], [1, GREEN]]))
    return themed(fig, xaxis_title="Hour of Day", yaxis_title="", margin=dict(t=20, b=40, l=50, r=20))

def chart_bar(x, y, xlabel: str) -> go.Figure:
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=[GREEN if v == max(y) else "rgba(29,185,84,0.38)" for v in y]))
    return themed(fig, xaxis_title=xlabel, yaxis_title="Streams", bargap=0.18)


# ══════════════════════════════════════════════════════════════════
# MAIN RENDER INTERFACE
# ══════════════════════════════════════════════════════════════════
st.markdown('<div class="page-title"><span>🎧</span> Spotify Intelligence</div>', unsafe_allow_html=True)

# 1. State Variables Setup
if "wrapped_view" not in st.session_state:
    st.session_state.wrapped_view = False

min_date, max_date = get_date_bounds()

if "start_date" not in st.session_state:
    st.session_state.start_date = min_date
if "end_date" not in st.session_state:
    st.session_state.end_date = max_date

# 2. Wrapped View Logic
if st.session_state.wrapped_view:
    st.markdown('<div class="page-title" style="color:#1DB954;">🎁 Your Early Spotify Wrapped</div>', unsafe_allow_html=True)
    
    if st.button("🔙 Back to Main Dashboard"):
        st.session_state.wrapped_view = False
        st.rerun()

    # Params for queries in Wrapped mode
    F = {"start_date": st.session_state.start_date, "end_date": st.session_state.end_date}
    opts = {5: "Top 5", 50: "Top 50", 100: "Top 100", 150: "Top 150", 999999: "Full List"}

    # --- Wrapped: Top Songs ---
    st.markdown('<div class="section-title">🎵 Top Songs</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    w_lim_s = col2.selectbox("Show limit", options=list(opts.keys()), format_func=lambda x: opts[x], index=0, key="w_lim_s", label_visibility="collapsed")
    df_ws = run_query(f"""
        SELECT so.id AS song_id, so.title AS song_title, COALESCE(a.name, 'Unknown') AS main_artist, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played 
        FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE LEFT JOIN artists a ON a.id = sa.artist_id 
        WHERE s.played_at::date BETWEEN :start_date AND :end_date 
        GROUP BY so.id, so.title, a.name ORDER BY streams DESC LIMIT :limit;
    """, {**F, "limit": w_lim_s})
    if not df_ws.empty:
        render_custom_list(df_ws, "song_title", "main_artist", "streams", "hours_played", "song_id", "song")
    else:
        st.info("No track data found for this year.")

    # --- Wrapped: Top Artists ---
    st.markdown('<div class="section-title">🎤 Top Artists</div>', unsafe_allow_html=True)
    col3, col4 = st.columns([3, 1])
    w_lim_a = col4.selectbox("Show limit", options=list(opts.keys()), format_func=lambda x: opts[x], index=0, key="w_lim_a", label_visibility="collapsed")
    df_wa = run_query(f"""
        SELECT a.id AS artist_id, a.name AS artist_name, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played 
        FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE JOIN artists a ON a.id = sa.artist_id 
        WHERE s.played_at::date BETWEEN :start_date AND :end_date 
        GROUP BY a.id, a.name ORDER BY streams DESC LIMIT :limit;
    """, {**F, "limit": w_lim_a})
    if not df_wa.empty:
        df_wa["subtitle"] = "Artist"
        render_custom_list(df_wa, "artist_name", "subtitle", "streams", "hours_played", "artist_id", "artist")
    else:
        st.info("No artist data found for this year.")

    # --- Wrapped: Top Albums ---
    st.markdown('<div class="section-title">💿 Top Albums</div>', unsafe_allow_html=True)
    col5, col6 = st.columns([3, 1])
    w_lim_al = col6.selectbox("Show limit", options=list(opts.keys()), format_func=lambda x: opts[x], index=0, key="w_lim_al", label_visibility="collapsed")
    df_wal = run_query(f"""
        SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played 
        FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN albums al ON al.id = so.album_id 
        WHERE s.played_at::date BETWEEN :start_date AND :end_date 
        GROUP BY al.id, al.title ORDER BY streams DESC LIMIT :limit;
    """, {**F, "limit": w_lim_al})
    if not df_wal.empty:
        df_wal["subtitle"] = "Album"
        render_custom_list(df_wal, "album_title", "subtitle", "streams", "hours_played", "album_id", "album")
    else:
        st.info("No album data found for this year.")

# 3. Main Dashboard Logic
else:
    # 3a. Global Controls
    with st.container():
        st.markdown('<div class="date-container">', unsafe_allow_html=True)
        
        c_btn1, c_btn2, col_d1, col_d2 = st.columns([1, 1, 1.5, 1.5])
        
        with c_btn1:
            if st.button("🎁 Early Wrapped", use_container_width=True):
                # Wrapped Logic: From Jan 1st of the max_date's year, up to max_date
                st.session_state.start_date = datetime.date(max_date.year, 1, 1)
                st.session_state.end_date = max_date
                st.session_state.wrapped_view = True
                st.rerun()
                
        with c_btn2:
            if st.button("♾️ All Time", use_container_width=True):
                st.session_state.start_date = min_date
                st.session_state.end_date = max_date
                st.session_state.wrapped_view = False
                st.rerun()

        with col_d1:
            st.markdown('<div class="date-label">📅 From Date</div>', unsafe_allow_html=True)
            start_date_input = st.date_input("From Date", value=st.session_state.start_date, min_value=min_date, max_value=max_date, label_visibility="collapsed")
        with col_d2:
            st.markdown('<div class="date-label">📅 To Date</div>', unsafe_allow_html=True)
            end_date_input = st.date_input("To Date", value=st.session_state.end_date, min_value=min_date, max_value=max_date, label_visibility="collapsed")
        
        if start_date_input > end_date_input:
            st.error("Start date must be before end date.")
            st.stop()
            
        if start_date_input != st.session_state.start_date or end_date_input != st.session_state.end_date:
            st.session_state.start_date = start_date_input
            st.session_state.end_date = end_date_input
            st.session_state.wrapped_view = False # Exit wrapped view if user modifies dates manually
            st.rerun()
            
        st.markdown('</div>', unsafe_allow_html=True)

    F = {"start_date": st.session_state.start_date, "end_date": st.session_state.end_date}

    # 3b. Section Tabs
    selected_tab = st.radio(
        "Select Section",
        options=["📊  Overview", "🎵  Tracks & Search", "🎤  Artists", "💿  Albums", "🕐  Habits"],
        label_visibility="collapsed",
        horizontal=True
    )

    if selected_tab == "📊  Overview":
        df_kpi = run_query("""
            SELECT ROUND(SUM(s.ms_played) / 3600000.0, 1) AS total_hours, COUNT(DISTINCT sa.artist_id) AS unique_artists, COUNT(DISTINCT s.song_id) AS unique_songs, COUNT(s.id) AS total_streams
            FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            WHERE s.played_at::date BETWEEN :start_date AND :end_date;
        """, F)
        
        if not df_kpi.empty:
            t_hours = float(df_kpi["total_hours"].iloc[0] or 0)
            t_streams = int(df_kpi["total_streams"].iloc[0] or 0)
            u_arts = int(df_kpi["unique_artists"].iloc[0] or 0)
            u_songs = int(df_kpi["unique_songs"].iloc[0] or 0)

            st.markdown('<div class="kpi-container">', unsafe_allow_html=True)
            st.markdown(f'''<div class="kpi-card"><div class="kpi-title">Listening Time</div><div class="kpi-val">{t_hours:,.1f}<span class="kpi-unit">hrs</span></div></div>''', unsafe_allow_html=True)
            st.markdown(f'''<div class="kpi-card"><div class="kpi-title">Total Streams</div><div class="kpi-val">{t_streams:,}</div></div>''', unsafe_allow_html=True)
            st.markdown(f'''<div class="kpi-card"><div class="kpi-title">Unique Artists</div><div class="kpi-val">{u_arts:,}</div></div>''', unsafe_allow_html=True)
            st.markdown(f'''<div class="kpi-card"><div class="kpi-title">Unique Songs</div><div class="kpi-val">{u_songs:,}</div></div>''', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">📈 Streaming Trend Over Time</div>', unsafe_allow_html=True)
        df_t = run_query("SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count, ROUND(SUM(ms_played) / 3600000.0, 2) AS hours_played FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1;", F)
        if not df_t.empty:
            st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})

    elif selected_tab == "🎵  Tracks & Search":
        view_song = st.query_params.get("view_song")
        
        if view_song:
            if st.button("🔙 Back to Tracks List"):
                st.query_params.clear()
                st.rerun()
                
            song_info = run_query("SELECT title, (SELECT name FROM artists a JOIN song_artists sa ON sa.artist_id = a.id WHERE sa.song_id = songs.id LIMIT 1) as artist FROM songs WHERE id = :id", {"id": view_song})
            if not song_info.empty:
                st.markdown(f'<div class="section-title">Focus: {escape(song_info["title"].iloc[0])} <span style="font-size:1rem;color:#888;margin-left:10px;">by {escape(str(song_info["artist"].iloc[0]))}</span></div>', unsafe_allow_html=True)
            
            fp = run_query("SELECT MIN(played_at) as fp, COUNT(*) as total_plays FROM streams WHERE song_id = :id AND played_at::date BETWEEN :start_date AND :end_date", {"id": view_song, **F})
            if not fp.empty and pd.notnull(fp['fp'].iloc[0]):
                first_play_str = fp['fp'].iloc[0].strftime("%B %Y")
                st.info(f"✨ **First Time Played in period:** {first_play_str} | **Total Streams in period:** {fp['total_plays'].iloc[0]:,}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Timeline (Plays over time)**")
                df_t = run_query("SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count, ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played FROM streams WHERE song_id = :id AND played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1", {"id": view_song, **F})
                if not df_t.empty: st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                else: st.write("No trend data.")
            with c2:
                st.markdown("**Peak Hours**")
                df_h = run_query("SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count FROM streams WHERE song_id = :id AND played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1", {"id": view_song, **F})
                if not df_h.empty: st.plotly_chart(chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"), use_container_width=True, config={"displayModeBar": False})
                else: st.write("No hours data.")

        else:
            st.markdown('<div class="section-title">🎵 Track Explorer</div>', unsafe_allow_html=True)
            col_search, col_limit = st.columns([3, 1])
            search_term = col_search.text_input("🔍 Search for a song or artist...", placeholder="e.g. Drake, Datura, Starboy...", key="so_search")
            display_limit = col_limit.selectbox("Results to load", options=[50, 100, 150, 250, 500], index=0, key="so_lim")
            
            query_params = {**F, "limit": display_limit}
            search_clause = ""
            if search_term:
                search_clause = "AND (so.title ILIKE :search OR a.name ILIKE :search)"
                query_params["search"] = f"%{search_term}%"

            SQL_SONGS = f"""
            SELECT so.id AS song_id, so.title AS song_title, COALESCE(a.name, 'Unknown') AS main_artist, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played 
            FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE LEFT JOIN artists a ON a.id = sa.artist_id 
            WHERE s.played_at::date BETWEEN :start_date AND :end_date {search_clause}
            GROUP BY so.id, so.title, a.name ORDER BY streams DESC LIMIT :limit;
            """
            
            df_s = run_query(SQL_SONGS, query_params)
            if not df_s.empty:
                render_custom_list(df_s, title_col="song_title", sub_col="main_artist", streams_col="streams", hours_col="hours_played", id_col="song_id", link_type="song")
            else:
                st.info("No records found in this period.")


    elif selected_tab == "🎤  Artists":
        view_artist = st.query_params.get("view_artist")
        
        if view_artist:
            if st.button("🔙 Back to Artists List"):
                st.query_params.clear()
                st.rerun()
                
            art_info = run_query("SELECT name FROM artists WHERE id = :id", {"id": view_artist})
            if not art_info.empty:
                st.markdown(f'<div class="section-title">Focus: {escape(art_info["name"].iloc[0])}</div>', unsafe_allow_html=True)
                
            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown("**Top Tracks for Artist**")
                df_tracks = run_query("SELECT so.id AS song_id, so.title as song_title, 'Track' as sub, COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 3) as hours_played FROM streams s JOIN songs so ON so.id=s.song_id JOIN song_artists sa ON sa.song_id=s.song_id WHERE sa.artist_id=:aid AND s.played_at::date BETWEEN :start_date AND :end_date GROUP BY so.id, so.title ORDER BY streams DESC LIMIT 10", {**F, "aid": view_artist})
                if not df_tracks.empty: render_custom_list(df_tracks, "song_title", "sub", "streams", "hours_played", "song_id", "song")
                
            with c_right:
                st.markdown("**Timeline (Plays over time)**")
                df_t = run_query("SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count, ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id WHERE sa.artist_id = :aid AND played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1", {"aid": view_artist, **F})
                if not df_t.empty: st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                
                st.markdown("**Peak Hours**")
                df_h = run_query("SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id WHERE sa.artist_id = :aid AND played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1", {"aid": view_artist, **F})
                if not df_h.empty: st.plotly_chart(chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"), use_container_width=True, config={"displayModeBar": False})

        else:
            st.markdown('<div class="section-title">🎤 Top Artists</div>', unsafe_allow_html=True)
            col_lim = st.columns([3, 1])[1]
            display_limit = col_lim.selectbox("Results to load", options=[50, 100, 150, 250], index=0, key="art_lim")
            
            df_a = run_query(f"SELECT a.id AS artist_id, a.name AS artist_name, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE JOIN artists a ON a.id = sa.artist_id WHERE s.played_at::date BETWEEN :start_date AND :end_date GROUP BY a.id, a.name ORDER BY hours_played DESC LIMIT {display_limit};", F)
            
            if not df_a.empty:
                df_a["subtitle"] = "Artist Profile"
                render_custom_list(df_a, title_col="artist_name", sub_col="subtitle", streams_col="streams", hours_col="hours_played", id_col="artist_id", link_type="artist")
            else:
                st.info("No records found in this period.")


    elif selected_tab == "💿  Albums":
        view_album = st.query_params.get("view_album")
        
        if view_album:
            if st.button("🔙 Back to Albums List"):
                st.query_params.clear()
                st.rerun()
                
            alb_info = run_query("SELECT title FROM albums WHERE id = :id", {"id": view_album})
            if not alb_info.empty:
                st.markdown(f'<div class="section-title">Album Focus: {escape(alb_info["title"].iloc[0])}</div>', unsafe_allow_html=True)
                
            st.markdown("**Tracks in this Album (Sorted by Streams)**")
            df_tracks = run_query("""
                SELECT so.id AS song_id, so.title AS song_title, COALESCE(a.name, 'Unknown') AS main_artist, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played 
                FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE LEFT JOIN artists a ON a.id = sa.artist_id 
                WHERE so.album_id = :aid AND s.played_at::date BETWEEN :start_date AND :end_date
                GROUP BY so.id, so.title, a.name ORDER BY streams DESC
            """, {**F, "aid": view_album})
            
            if not df_tracks.empty:
                render_custom_list(df_tracks, title_col="song_title", sub_col="main_artist", streams_col="streams", hours_col="hours_played", id_col="song_id", link_type="song")
            else:
                st.info("No track streams found for this album in this period.")

        else:
            st.markdown('<div class="section-title">💿 Top Albums</div>', unsafe_allow_html=True)
            col_lim = st.columns([3, 1])[1]
            display_limit = col_lim.selectbox("Results to load", options=[50, 100, 150, 250], index=0, key="alb_lim")
            
            df_al = run_query(f"SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN albums al ON al.id = so.album_id WHERE s.played_at::date BETWEEN :start_date AND :end_date GROUP BY al.id, al.title ORDER BY hours_played DESC LIMIT {display_limit};", F)
            
            if not df_al.empty:
                df_al["subtitle"] = "Album Record"
                render_custom_list(df_al, title_col="album_title", sub_col="subtitle", streams_col="streams", hours_col="hours_played", id_col="album_id", link_type="album")
            else:
                st.info("No records found in this period.")

    elif selected_tab == "🕐  Habits":
        st.markdown('<div class="section-title">Activity Heatmap (Day × Hour)</div>', unsafe_allow_html=True)
        df_heatmap = run_query("SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, EXTRACT(HOUR FROM played_at)::INT AS hour, COUNT(*) AS stream_count FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date GROUP BY 1, 2;", F)
        if not df_heatmap.empty:
            st.plotly_chart(chart_heatmap(df_heatmap), use_container_width=True, config={"displayModeBar": False})
        
        h_col, d_col = st.columns(2, gap="large")
        with h_col:
            st.markdown('<div class="section-title">Peak Hours</div>', unsafe_allow_html=True)
            df_hr = run_query("SELECT EXTRACT(HOUR FROM played_at)::INT AS hour, COUNT(*) AS stream_count FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1;", F)
            if not df_hr.empty:
                st.plotly_chart(chart_bar(df_hr["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_hr["stream_count"].tolist(), "Hour of Day"), use_container_width=True, config={"displayModeBar": False})
        with d_col:
            st.markdown('<div class="section-title">Most Active Days</div>', unsafe_allow_html=True)
            df_dw = run_query("SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, COUNT(*) AS stream_count FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date GROUP BY 1 ORDER BY 1;", F)
            if not df_dw.empty:
                st.plotly_chart(chart_bar(df_dw["dow"].map({1:"Mon", 2:"Tue", 3:"Wed", 4:"Thu", 5:"Fri", 6:"Sat", 7:"Sun"}).tolist(), df_dw["stream_count"].tolist(), "Day of Week"), use_container_width=True, config={"displayModeBar": False})