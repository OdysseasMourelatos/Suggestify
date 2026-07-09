import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
import datetime
import warnings
import os
from html import escape
warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Suggestify",
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

# ══════════════════════════════════════════════════════════════════
# LOAD EXTERNAL CSS
# ══════════════════════════════════════════════════════════════════
def load_css():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    css_path = os.path.join(os.path.dirname(current_dir), "static", "styles.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
            
        tokens = {
            "VAR_CARD_HOVER": CARD_HOVER,
            "VAR_GREEN_GLOW": GREEN_GLOW,
            "VAR_BORDER_HL": BORDER_HL,
            "VAR_GREEN_DIM": GREEN_DIM,
            "VAR_GREEN_XLO": GREEN_XLO,
            "VAR_TEXT_MID": TEXT_MID,
            "VAR_TEXT_DIM": TEXT_DIM,
            "VAR_SURFACE": SURFACE,
            "VAR_BORDER": BORDER,
            "VAR_GREEN": GREEN,
            "VAR_CARD": CARD,
            "VAR_TEXT": TEXT,
            "VAR_BG": BG,
        }
        
        for key, val in tokens.items():
            css = css.replace(key, val)
            
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css()

# ══════════════════════════════════════════════════════════════════
# EXTRA UX TRANSITIONS
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@keyframes fadeSlideUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}

.list-item {{ transition: transform 0.22s ease, background 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease; }}
.list-item:hover {{ transform: translateX(5px); background: rgba(255,255,255,0.045); border-color: rgba(29,185,84,0.35); box-shadow: 0 6px 22px rgba(0,0,0,0.28); }}
.item-art {{ transition: transform 0.25s ease; }}
.list-item:hover .item-art {{ transform: scale(1.07); }}
.item-arrow {{ transition: transform 0.25s ease, color 0.25s ease; display: inline-block; }}
.list-item:hover .item-arrow {{ transform: translateX(5px); color: {GREEN}; }}
.stat-value {{ transition: color 0.2s ease; }}

.kpi-card {{ transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease; animation: fadeSlideUp 0.5s ease both; }}
.kpi-card:hover {{ transform: translateY(-5px); box-shadow: 0 12px 30px rgba(29,185,84,0.14); border-color: rgba(29,185,84,0.3); }}
.kpi-icon {{ transition: transform 0.3s ease; display: inline-block; }}
.kpi-card:hover .kpi-icon {{ transform: scale(1.18) rotate(-4deg); }}

.section-header {{ position: relative; animation: fadeIn 0.4s ease both; }}
.chart-container {{ animation: fadeSlideUp 0.45s ease both; transition: border-color 0.25s ease, box-shadow 0.25s ease; }}
.chart-container:hover {{ border-color: rgba(29,185,84,0.18); }}
.detail-header {{ animation: fadeSlideUp 0.4s ease both; }}
.detail-art {{ transition: transform 0.3s ease; }}
.detail-header:hover .detail-art {{ transform: scale(1.03); }}
.detail-stat {{ transition: transform 0.2s ease; }}
.detail-stat:hover {{ transform: translateY(-2px); }}

.wrapped-banner {{ animation: fadeSlideUp 0.5s ease both; }}
.empty-state {{ animation: fadeIn 0.4s ease both; }}

div[data-testid="stButton"] button {{ transition: all 0.2s ease !important; }}
div[data-testid="stButton"] button[kind="secondary"]:hover {{ background: rgba(29,185,84,0.08) !important; color: {GREEN} !important; transform: translateY(-1px) !important; border-color: rgba(29,185,84,0.3) !important; }}
div[data-testid="stButton"] button[kind="primary"]:hover {{ transform: translateY(-1px) !important; box-shadow: 0 6px 18px rgba(29,185,84,0.3) !important; }}

div[data-testid="stTextInput"] input, div[data-baseweb="select"] > div, div[data-testid="stDateInput"] input {{ transition: border-color 0.2s ease, box-shadow 0.2s ease !important; }}
div[data-testid="stTextInput"] input:focus, div[data-testid="stDateInput"] input:focus {{ border-color: {GREEN} !important; box-shadow: 0 0 0 2px {GREEN_XLO} !important; }}

.custom-link {{ text-decoration: none !important; display: block; }}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════
CONNECTION_STRING = os.environ.get("DATABASE_URL", "postgresql://postgres:dKPJjO2jZtkmwjYh@db.pxpplxyszvrzubdqykmw.supabase.co:5432/postgres")
@st.cache_resource
def get_engine():
    return create_engine(CONNECTION_STRING, pool_pre_ping=True, pool_size=5)

@st.cache_data(ttl=3600, show_spinner=False)
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
    icons = {"song": "🎵", "artist": "🎤", "album": "💿", "genre": "🎸"}
    return icons.get(link_type, "🎵")

def render_list_v2(df: pd.DataFrame, title_col: str, sub_col: str, streams_col: str, hours_col: str,
                   id_col: str = None, link_type: str = None, image_col: str = "image_url",
                   rank_col: str = None, reveal_top_n: int = 0,
                   reveal_delay_base: float = 0.5, reveal_delay_step: float = 0.2):
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

        reveal_style = ""
        if reveal_top_n > 0 and rank <= reveal_top_n:
            delay = reveal_delay_base + (rank - 1) * reveal_delay_step
            reveal_style = f'style="animation-delay: {delay:.1f}s;"'

        reveal_class = "list-item-reveal" if reveal_style else ""

        card_html = f'''
        <div class="list-item {reveal_class}" {reveal_style}>
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
            params = st.query_params
            current_view = params.get("view", "")
            current_id = params.get("id", "")
            
            href = f"?tab={current_tab}&view={link_type}&id={item_id}"
            if current_view and current_id: href += f"&pview={current_view}&pid={current_id}"
            if params.get("preset"): href += f"&preset={params.get('preset')}"
            if params.get("start"): href += f"&start={params.get('start')}"
            if params.get("end"): href += f"&end={params.get('end')}"

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

def chart_multi_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    colors = [GREEN, "#1ed760", "#A8E4A0", TEXT_MID, TEXT_DIM]
    for idx, track in enumerate(df["track_title"].unique()):
        track_df = df[df["track_title"] == track]
        fig.add_trace(go.Scatter(
            x=track_df["period"], 
            y=track_df["stream_count"],
            name=track, 
            mode="lines",
            line=dict(width=2.5, shape='spline', color=colors[idx % len(colors)]),
        ))
    return themed(fig, 
        yaxis=dict(title=dict(text="Streams", font=dict(color=TEXT_MID))),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center")
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
    params = st.query_params
    pview = params.get("pview")
    pid = params.get("pid")
    tab = params.get("tab", "overview")
    preset = params.get("preset")
    start = params.get("start")
    end = params.get("end")

    st.query_params.clear()
    st.query_params["tab"] = tab
    if pview and pid:
        st.query_params["view"] = pview
        st.query_params["id"] = pid
    if preset: st.query_params["preset"] = preset
    if start: st.query_params["start"] = start
    if end: st.query_params["end"] = end
    
# ══════════════════════════════════════════════════════════════════
# MAIN APP & STATE MANAGEMENT (CALLBACKS)
# ══════════════════════════════════════════════════════════════════
min_date, max_date = get_date_bounds()

def get_parsed_date(date_str, default_date):
    if not date_str: return default_date
    try: return datetime.date.fromisoformat(date_str)
    except: return default_date

params = st.query_params

if "start_date" not in st.session_state:
    st.session_state.start_date = get_parsed_date(params.get("start"), min_date)
    st.session_state.end_date = get_parsed_date(params.get("end"), max_date)
    url_preset = params.get("preset", "all")
    st.session_state.date_preset = url_preset if url_preset in ["all", "wrapped", "month", "week"] else None

def update_dates_from_preset():
    sel = st.session_state.date_preset
    if sel == "all":
        st.session_state.start_date = min_date
        st.session_state.end_date = max_date
    elif sel == "wrapped":
        st.session_state.start_date = datetime.date(max_date.year, 1, 1)
        st.session_state.end_date = max_date
    elif sel == "month":
        st.session_state.start_date = max_date - datetime.timedelta(days=30)
        st.session_state.end_date = max_date
    elif sel == "week":
        st.session_state.start_date = max_date - datetime.timedelta(days=7)
        st.session_state.end_date = max_date
        
    st.query_params["preset"] = sel
    st.query_params["start"] = st.session_state.start_date.isoformat()
    st.query_params["end"] = st.session_state.end_date.isoformat()

def mark_manual():
    st.session_state.date_preset = None
    st.query_params["preset"] = "manual"
    st.query_params["start"] = st.session_state.start_date.isoformat()
    st.query_params["end"] = st.session_state.end_date.isoformat()

preset_options = {
    "all": "♾️ All Time",
    "wrapped": "🎁 Wrapped",
    "month": "📅 Month",
    "week": "📅 Week"
}

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
        ("genres", "🎸 Genres"),
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
                curr_preset = st.query_params.get("preset")
                curr_start = st.query_params.get("start")
                curr_end = st.query_params.get("end")
                
                st.query_params.clear()
                st.query_params["tab"] = tab_id
                
                if curr_preset: st.query_params["preset"] = curr_preset
                if curr_start: st.query_params["start"] = curr_start
                if curr_end: st.query_params["end"] = curr_end
                
                st.rerun()
try:
    users_df = run_query("SELECT id, username FROM users ORDER BY username")
    user_dict = dict(zip(users_df['username'], users_df['id']))
except:
    user_dict = {"Ody": 1} 

with date_col:
    selected_username = st.selectbox("👤 User", options=list(user_dict.keys()), label_visibility="collapsed")
    selected_user_id = user_dict.get(selected_username, 1)
    
    preset_col, d1_col, d2_col = st.columns([1.4, 1, 1])

    with preset_col:
        st.selectbox(
            "Period",
            options=list(preset_options.keys()),
            format_func=lambda x: preset_options[x],
            placeholder="⚙️ Manual",
            label_visibility="collapsed",
            key="date_preset",
            on_change=update_dates_from_preset
        )

    with d1_col:
        st.date_input("From", min_value=min_date, max_value=max_date, 
                      label_visibility="collapsed", key="start_date", on_change=mark_manual)

    with d2_col:
        st.date_input("To", min_value=min_date, max_value=max_date, 
                      label_visibility="collapsed", key="end_date", on_change=mark_manual)

st.markdown('</div></div>', unsafe_allow_html=True)

# Κλειδώνουμε τα φίλτρα για τα queries (Με το USER_ID)
F = {
    "start_date": st.session_state.start_date, 
    "end_date": st.session_state.end_date,
    "user_id": selected_user_id
}

# ══════════════════════════════════════════════════════════════════
# DETAIL VIEWS
# ══════════════════════════════════════════════════════════════════

if detail_type and detail_id:

    if st.button("← Back", key="back_btn"):
        go_back()
        st.rerun()

    if detail_type == "song":
        song_info = run_query("""
        WITH song_streams AS (
            SELECT song_id, COUNT(*) as streams, ROUND(SUM(ms_played)/3600000.0, 2) as hours
            FROM streams
            WHERE played_at::date BETWEEN :start_date AND :end_date
              AND user_id = :user_id
            GROUP BY song_id
        ),
        ranked AS (
            SELECT song_id, streams, hours,
                RANK() OVER (ORDER BY streams DESC, hours DESC) as global_rank
            FROM song_streams
        )
        SELECT so.title, COALESCE(a.name, 'Unknown') as artist, so.image_url,
            COALESCE(r.streams, 0) as streams,
            COALESCE(r.hours, 0) as hours,
            r.global_rank,
            MIN(s.played_at) as first_play
        FROM songs so
        LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
        LEFT JOIN artists a ON a.id = sa.artist_id
        LEFT JOIN ranked r ON r.song_id = so.id
        LEFT JOIN streams s ON s.song_id = so.id 
             AND s.played_at::date BETWEEN :start_date AND :end_date 
             AND s.user_id = :user_id
        WHERE so.id = :id
        GROUP BY so.id, so.title, a.name, so.image_url, r.streams, r.hours, r.global_rank
    """, {"id": detail_id, **F})

        if not song_info.empty:
            row = song_info.iloc[0]
            rank_display = f"#{int(row['global_rank'])}" if pd.notnull(row.get('global_rank')) else "—"
            render_detail_header(
                type_label="Track", title=str(row["title"]),
                subtitle=f"by {row['artist']}", icon="🎵",
                stats=[
                    {"value": rank_display, "label": "Song Rank"},
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
                    FROM streams 
                    WHERE song_id = :id 
                      AND played_at::date BETWEEN :start_date AND :end_date
                      AND user_id = :user_id
                    GROUP BY 1 ORDER BY 1
                """, {"id": detail_id, **F})
                if not df_t.empty:
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

            with c2:
                st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
                df_h = run_query("""
                    SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count
                    FROM streams 
                    WHERE song_id = :id 
                      AND played_at::date BETWEEN :start_date AND :end_date
                      AND user_id = :user_id
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
        WITH artist_streams AS (
            SELECT sa.artist_id, COUNT(*) as streams, ROUND(SUM(s.ms_played)/3600000.0, 2) as hours
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY sa.artist_id
        ),
        ranked AS (
            SELECT artist_id, streams, hours,
                RANK() OVER (ORDER BY streams DESC) as global_rank
            FROM artist_streams
        )
        SELECT a.name, a.image_url,
            COALESCE(r.streams, 0) as streams,
            COALESCE(r.hours, 0) as hours,
            r.global_rank,
            COUNT(DISTINCT s.song_id) as unique_tracks
        FROM artists a
        LEFT JOIN song_artists sa ON sa.artist_id = a.id
        LEFT JOIN streams s ON s.song_id = sa.song_id 
             AND s.played_at::date BETWEEN :start_date AND :end_date
             AND s.user_id = :user_id
        LEFT JOIN ranked r ON r.artist_id = a.id
        WHERE a.id = :id
        GROUP BY a.id, a.name, a.image_url, r.streams, r.hours, r.global_rank
    """, {"id": detail_id, **F})
        if not art_info.empty:
            row = art_info.iloc[0]
            artist_name = str(row["name"])
            rank_display = f"#{int(row['global_rank'])}" if pd.notnull(row.get('global_rank')) else "—"
            render_detail_header(
                type_label="Artist", title=artist_name,
                subtitle=f"{int(row['unique_tracks'] or 0)} tracks played", icon="🎤",
                stats=[
                    {"value": rank_display, "label": "Artist Rank"},
                    {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                    {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            c1, c2, c3 = st.columns([1.1, 1.1, 1])
            
            with c1:
                st.markdown('<div class="section-header"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
                df_tracks = run_query("""
                    SELECT so.id AS song_id, so.title as song_title, 'Track' as sub, so.image_url,
                           COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 3) as hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY so.id, so.title, so.image_url ORDER BY streams DESC LIMIT 10
                """, {"aid": detail_id, **F})
                
                if not df_tracks.empty:
                    render_list_v2(df_tracks, "song_title", "sub", "streams", "hours_played", "song_id", "song")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("See Full List →", key=f"btn_full_tracks_{detail_id}", use_container_width=True):
                        st.query_params.clear()
                        st.query_params["tab"] = "tracks"
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
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY al.id, al.title ORDER BY streams DESC LIMIT 10
                """, {"aid": detail_id, **F})
                
                if not df_albums.empty:
                    df_albums["subtitle"] = "Album"
                    render_list_v2(df_albums, "album_title", "subtitle", "streams", "hours_played", "album_id", "album")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("See Full List →", key=f"btn_full_albums_{detail_id}", use_container_width=True):
                        st.query_params.clear()
                        st.query_params["tab"] = "albums"
                        st.session_state["search_albums"] = artist_name
                        st.rerun()

            with c3:
                st.markdown('<div class="chart-container"><div class="chart-title">📈 Timeline</div>', unsafe_allow_html=True)
                df_t = run_query("""
                    SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count,
                           ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played
                    FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1
                """, {"aid": detail_id, **F})
                if not df_t.empty:
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
                df_h = run_query("""
                    SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count
                    FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1
                """, {"aid": detail_id, **F})
                if not df_h.empty:
                    st.plotly_chart(
                        chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-container"><div class="chart-title">📅 Active Days</div>', unsafe_allow_html=True)
                df_days = run_query("""
                    SELECT EXTRACT(ISODOW FROM s.played_at)::INT AS dow, COUNT(*) AS stream_count
                    FROM streams s
                    JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1;
                """, {"aid": detail_id, **F})
                if not df_days.empty:
                    dow_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
                    st.plotly_chart(
                        chart_bar(df_days["dow"].map(dow_map).tolist(), df_days["stream_count"].tolist(), "Day"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "album":
        alb_info = run_query("""
        WITH AlbumPrimaryArtists AS (
            SELECT a.name, COUNT(DISTINCT so.id) as track_cnt
            FROM songs so
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE so.album_id = :id
            GROUP BY a.name
        ),
        TopAlbumArtists AS (
            SELECT STRING_AGG(name, ', ') as artist_names
            FROM AlbumPrimaryArtists
            WHERE track_cnt = (SELECT MAX(track_cnt) FROM AlbumPrimaryArtists)
        ),
        album_streams AS (
            SELECT so.album_id, COUNT(*) as streams, ROUND(SUM(s.ms_played)/3600000.0, 2) as hours
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND so.album_id IS NOT NULL
            GROUP BY so.album_id
        ),
        ranked AS (
            SELECT album_id, RANK() OVER (ORDER BY streams DESC) as global_rank
            FROM album_streams
        )
        SELECT al.title, MAX(so.image_url) as image_url,
            COALESCE(ars.streams, 0) as streams,
            COALESCE(ars.hours, 0) as hours,
            COUNT(DISTINCT s.song_id) as track_count,
            (SELECT artist_names FROM TopAlbumArtists) as artist_name,
            r.global_rank
        FROM albums al
        LEFT JOIN songs so ON so.album_id = al.id
        LEFT JOIN streams s ON s.song_id = so.id 
             AND s.played_at::date BETWEEN :start_date AND :end_date
             AND s.user_id = :user_id
        LEFT JOIN album_streams ars ON ars.album_id = al.id
        LEFT JOIN ranked r ON r.album_id = al.id
        WHERE al.id = :id
        GROUP BY al.id, al.title, ars.streams, ars.hours, r.global_rank
    """, {"id": detail_id, **F})
        if not alb_info.empty:
            row = alb_info.iloc[0]
            artist_name = row["artist_name"] if pd.notnull(row["artist_name"]) else "Unknown Artist"
            rank_display = f"#{int(row['global_rank'])}" if pd.notnull(row.get('global_rank')) else "—"
            render_detail_header(
                type_label="Album",
                title=str(row["title"]) if row["title"] else "Unknown Album",
                subtitle=f"by {artist_name} • {int(row['track_count'] or 0)} tracks played", 
                icon="💿",
                stats=[
                    {"value": rank_display, "label": "Album Rank"},
                    {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                    {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            c_left, c_right = st.columns([1.2, 1.0])
            
            with c_left:
                st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Album Tracks</div>', unsafe_allow_html=True)
                df_tracks = run_query("""
                    SELECT so.id AS song_id, so.title AS song_title,
                           COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                           COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                    LEFT JOIN artists a ON a.id = sa.artist_id
                    WHERE so.album_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY so.id, so.title, a.name, so.image_url ORDER BY streams DESC
                """, {"aid": detail_id, **F})
                
                if not df_tracks.empty:
                    render_list_v2(df_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song")
                else:
                    st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found in this period</div>', unsafe_allow_html=True)
                    
            with c_right:
                st.markdown('<div class="chart-container" style="margin-top: 0;"><div class="chart-title">📈 Top 5 Tracks Evolution</div>', unsafe_allow_html=True)
                df_album_trend = run_query("""
                    WITH top_tracks AS (
                        SELECT so.id, so.title
                        FROM streams s
                        JOIN songs so ON so.id = s.song_id
                        WHERE so.album_id = :aid 
                          AND s.played_at::date BETWEEN :start_date AND :end_date
                          AND s.user_id = :user_id
                        GROUP BY so.id, so.title
                        ORDER BY COUNT(*) DESC
                        LIMIT 5
                    )
                    SELECT DATE_TRUNC('month', s.played_at) AS period, t.title AS track_title, COUNT(*) AS stream_count
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN top_tracks t ON t.id = so.id
                    WHERE s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                """, {"aid": detail_id, **F})
                
                if not df_album_trend.empty:
                    st.plotly_chart(chart_multi_trend(df_album_trend), use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-container"><div class="chart-title">⏰ Peak Hours</div>', unsafe_allow_html=True)
                df_hours = run_query("""
                    SELECT EXTRACT(HOUR FROM s.played_at)::INT AS hour, COUNT(*) AS stream_count
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    WHERE so.album_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1;
                """, {"aid": detail_id, **F})
                if not df_hours.empty:
                    st.plotly_chart(
                        chart_bar(df_hours["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_hours["stream_count"].tolist(), "Hour"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="chart-container"><div class="chart-title">📅 Active Days</div>', unsafe_allow_html=True)
                df_days = run_query("""
                    SELECT EXTRACT(ISODOW FROM s.played_at)::INT AS dow, COUNT(*) AS stream_count
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    WHERE so.album_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1;
                """, {"aid": detail_id, **F})
                if not df_days.empty:
                    dow_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
                    st.plotly_chart(
                        chart_bar(df_days["dow"].map(dow_map).tolist(), df_days["stream_count"].tolist(), "Day"),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "genre":
            genre_info = run_query("""
                SELECT g.name, COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 2) as hours,
                       COUNT(DISTINCT sa.artist_id) as unique_artists
                FROM genres g
                JOIN album_genres ag ON ag.genre_id = g.id
                JOIN songs so ON so.album_id = ag.album_id
                JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                JOIN streams s ON s.song_id = so.id 
                     AND s.played_at::date BETWEEN :start_date AND :end_date
                     AND s.user_id = :user_id
                WHERE g.id = :id
                GROUP BY g.name
            """, {"id": detail_id, **F})

            if not genre_info.empty:
                row = genre_info.iloc[0]
                genre_name = str(row["name"]).title()

                render_detail_header(
                    type_label="Genre", title=genre_name,
                    subtitle=f"{int(row['unique_artists'] or 0)} artists in your library", icon="🎸",
                    stats=[
                        {"value": f"{int(row['streams'] or 0):,}", "label": "Streams"},
                        {"value": f"{float(row['hours'] or 0):.1f}h", "label": "Listened"},
                    ]
                )

                c_left, c_right = st.columns(2)

                with c_left:
                    st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)
                    df_g_artists = run_query("""
                        SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
                        FROM streams s
                        JOIN songs so ON so.id = s.song_id
                        JOIN album_genres ag ON ag.album_id = so.album_id
                        JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                        JOIN artists a ON a.id = sa.artist_id
                        WHERE ag.genre_id = :id 
                          AND s.played_at::date BETWEEN :start_date AND :end_date
                          AND s.user_id = :user_id
                        GROUP BY a.id, a.name, a.image_url ORDER BY streams DESC LIMIT 10
                    """, {"id": detail_id, **F})

                    if not df_g_artists.empty:
                        df_g_artists["sub"] = "Artist"
                        render_list_v2(df_g_artists, "artist_name", "sub", "streams", "hours_played", "artist_id", "artist")
                    else:
                        st.markdown('<div class="empty-state"><div class="icon">📭</div>No artists found</div>', unsafe_allow_html=True)

                with c_right:
                    st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
                    df_g_tracks = run_query("""
                        SELECT so.id AS song_id, so.title AS song_title, a.name AS main_artist, so.image_url,
                               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
                        FROM streams s
                        JOIN songs so ON so.id = s.song_id
                        JOIN album_genres ag ON ag.album_id = so.album_id
                        JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                        JOIN artists a ON a.id = sa.artist_id
                        WHERE ag.genre_id = :id 
                          AND s.played_at::date BETWEEN :start_date AND :end_date
                          AND s.user_id = :user_id
                        GROUP BY so.id, so.title, a.name, so.image_url ORDER BY streams DESC LIMIT 10
                    """, {"id": detail_id, **F})

                    if not df_g_tracks.empty:
                        render_list_v2(df_g_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song")
                    else:
                        st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found</div>', unsafe_allow_html=True)

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
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id;
    """, F)

    if not df_kpi.empty:
        row = df_kpi.iloc[0]
        render_kpi_grid([
            {"icon": "⏱️", "title": "Listening Time", "value": f"{float(row['total_hours'] or 0):,.1f}", "unit": "hrs"},
            {"icon": "🎵", "title": "Total Streams", "value": f"{int(row['total_streams'] or 0):,}"},
            {"icon": "🎤", "title": "Unique Artists", "value": f"{int(row['unique_artists'] or 0):,}"},
            {"icon": "🎶", "title": "Unique Songs", "value": f"{int(row['unique_songs'] or 0):,}"},
        ])

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
              AND s.user_id = :user_id
            GROUP BY so.id, so.title, a.name, so.image_url ORDER BY streams DESC LIMIT 5;
        """, F)
        if not df_top_tracks.empty:
            render_list_v2(df_top_tracks, "song_title", "main_artist", "streams", "hours_played",
                           "song_id", "song", reveal_top_n=5)

    with c2:
        st.markdown('<div class="section-header"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)
        df_top_artists = run_query("""
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url, COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY a.id, a.name, a.image_url ORDER BY streams DESC LIMIT 5;
        """, F)
        if not df_top_artists.empty:
            df_top_artists["subtitle"] = "Artist"
            render_list_v2(df_top_artists, "artist_name", "subtitle", "streams", "hours_played",
                           "artist_id", "artist", reveal_top_n=5)

    st.markdown('<div class="section-header"><span class="icon">📈</span>Listening Trend</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    df_trend = run_query("""
        SELECT DATE_TRUNC('month', s.played_at) AS period, COUNT(*) AS stream_count,
               ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
        FROM streams s 
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
        GROUP BY 1 ORDER BY 1;
    """, F)
    if not df_trend.empty:
        st.plotly_chart(chart_trend(df_trend), use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

elif current_tab == "tracks":
    st.markdown('<div class="section-header"><span class="icon">🎵</span>Track Explorer</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search tracks...", placeholder="e.g. Starboy, Red Moon...", label_visibility="collapsed", key="search_tracks")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200, 500], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_songs = run_query("""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND (so.title ILIKE :search OR a.name ILIKE :search)
            GROUP BY so.id, so.title, a.name, so.image_url
            ORDER BY streams DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_songs.empty:
            render_list_v2(df_songs, "song_title", "main_artist", "streams", "hours_played",
               "song_id", "song", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🔍</div>No tracks found</div>', unsafe_allow_html=True)

    else:
        df_songs = run_query("""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY COUNT(s.id) DESC, SUM(s.ms_played) DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY so.id, so.title, a.name, so.image_url
            ORDER BY streams DESC, hours_played DESC LIMIT :limit;
        """, query_params)

        if not df_songs.empty:
           render_list_v2(df_songs, "song_title", "main_artist", "streams", "hours_played",
               "song_id", "song", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
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
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND a.name ILIKE :search
            GROUP BY a.id, a.name, a.image_url
            ORDER BY streams DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_artists.empty:
            df_artists["subtitle"] = "Artist"
            render_list_v2(df_artists, "artist_name", "subtitle", "streams", "hours_played",
               "artist_id", "artist", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🎤</div>No artists found</div>', unsafe_allow_html=True)

    else:
        df_artists = run_query("""
        SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
            COUNT(s.id) AS streams,
            ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
            ROW_NUMBER() OVER (ORDER BY COUNT(s.id) DESC) AS global_rank
        FROM streams s
        JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        JOIN artists a ON a.id = sa.artist_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
        GROUP BY a.id, a.name, a.image_url
        ORDER BY streams DESC LIMIT :limit;
    """, query_params)

        if not df_artists.empty:
            df_artists["subtitle"] = "Artist"
            render_list_v2(df_artists, "artist_name", "subtitle", "streams", "hours_played",
               "artist_id", "artist", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🎤</div>No artists found</div>', unsafe_allow_html=True)


elif current_tab == "albums":
    st.markdown('<div class="section-header"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search albums...", placeholder="e.g. Take Care, UTOPIA...", label_visibility="collapsed", key="search_albums")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    base_query = """
        WITH TrueAlbumArtists AS (
            SELECT album_id, STRING_AGG(name, ', ') as artist_name
            FROM (
                SELECT so.album_id, a.name,
                       RANK() OVER(PARTITION BY so.album_id ORDER BY COUNT(DISTINCT so.id) DESC) as rnk
                FROM songs so
                JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE so.album_id IS NOT NULL
                GROUP BY so.album_id, a.name
            ) ranked
            WHERE rnk = 1
            GROUP BY album_id
        )
    """

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_albums = run_query(base_query + """
            SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                   COALESCE(aa.artist_name, 'Unknown Artist') AS artist_name,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            LEFT JOIN TrueAlbumArtists aa ON aa.album_id = al.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND al.title ILIKE :search
            GROUP BY al.id, al.title, aa.artist_name
            ORDER BY streams DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_albums.empty:
            render_list_v2(df_albums, "album_title", "artist_name", "streams", "hours_played",
               "album_id", "album", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)

        else:
            st.markdown('<div class="empty-state"><div class="icon">💿</div>No albums found</div>', unsafe_allow_html=True)

    else:
        df_albums = run_query(base_query + """
            SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                   COALESCE(aa.artist_name, 'Unknown Artist') AS artist_name,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY COUNT(s.id) DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            LEFT JOIN TrueAlbumArtists aa ON aa.album_id = al.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY al.id, al.title, aa.artist_name
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)

        if not df_albums.empty:
            render_list_v2(df_albums, "album_title", "artist_name", "streams", "hours_played",
               "album_id", "album", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
        else:
            st.markdown('<div class="empty-state"><div class="icon">💿</div>No albums found</div>', unsafe_allow_html=True)
            
elif current_tab == "habits":
    st.markdown('<div class="section-header"><span class="icon">🕐</span>Listening Habits</div>', unsafe_allow_html=True)

    st.markdown('<div class="chart-container"><div class="chart-title">📊 Activity Heatmap (Day × Hour)</div>', unsafe_allow_html=True)
    df_heatmap = run_query("""
        SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, EXTRACT(HOUR FROM played_at)::INT AS hour,
               COUNT(*) AS stream_count
        FROM streams 
        WHERE played_at::date BETWEEN :start_date AND :end_date
          AND user_id = :user_id
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
            FROM streams 
            WHERE played_at::date BETWEEN :start_date AND :end_date
              AND user_id = :user_id
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
            FROM streams 
            WHERE played_at::date BETWEEN :start_date AND :end_date
              AND user_id = :user_id
            GROUP BY 1 ORDER BY 1;
        """, F)
        if not df_days.empty:
            dow_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
            st.plotly_chart(
                chart_bar(df_days["dow"].map(dow_map).tolist(), df_days["stream_count"].tolist(), "Day"),
                use_container_width=True, config={"displayModeBar": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)

elif current_tab == "genres":
    st.markdown('<div class="section-header"><span class="icon">🎸</span>Top Genres</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search genres...", placeholder="e.g. Rap, Pop...", label_visibility="collapsed", key="search_genres")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    base_genre_query = """
        SELECT g.id AS genre_id, INITCAP(g.name) AS genre_name, 
               COUNT(DISTINCT sa.artist_id) || ' Artists' AS subtitle,
               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
        FROM streams s
        JOIN songs so ON so.id = s.song_id
        JOIN album_genres ag ON ag.album_id = so.album_id
        JOIN genres g ON g.id = ag.genre_id
        JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
    """

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_genres = run_query(base_genre_query + """
            AND g.name ILIKE :search
            GROUP BY g.id, g.name
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)
    else:
        df_genres = run_query(base_genre_query + """
            GROUP BY g.id, g.name
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)

    if not df_genres.empty:
        render_list_v2(df_genres, "genre_name", "subtitle", "streams", "hours_played",
               "genre_id", "genre", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
    else:
        st.markdown('<div class="empty-state"><div class="icon">🎸</div>No genres found</div>', unsafe_allow_html=True)