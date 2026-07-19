import datetime
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from config import *
from charts import themed, chart_multi_trend
from ui import render_list_v2, render_kpi_grid, counter_span

# Second color for "User B" — reuses the red already established as your
# app's secondary accent (see the Quick-Rate toggle in app.py).
ACCENT = "#E53935"
ACCENT_DIM = "rgba(229,57,53,0.35)"


# ═════════════════════════════════════════════════════════════════════════
# Small amount of CSS for the handful of components that genuinely don't
# exist yet in styles.css (hero avatars, battle cards, DNA cards, share
# card). Everything else below reuses your existing classes.
# ═════════════════════════════════════════════════════════════════════════

def _inject_css():
    st.markdown(f"""
    <style>
    .fm-avatars {{ display: flex; align-items: center; justify-content: center; margin-bottom: 10px; }}
    .fm-avatar {{
        width: 60px; height: 60px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.4rem; font-weight: 800; color: #fff;
        border: 3px solid {BG};
        background: linear-gradient(135deg, {GREEN}, {GREEN_DIM});
    }}
    .fm-avatar.b {{ background: linear-gradient(135deg, {ACCENT}, #8f1f1c); margin-left: -16px; }}

    .fm-battle-title {{
        color: {TEXT_MID}; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.06em; margin-bottom: 10px;
    }}
    .fm-battle-side {{ display: flex; justify-content: space-between; align-items: center; padding: 5px 0; }}
    .fm-battle-name {{ color: {TEXT}; font-weight: 600; font-size: 0.9rem; }}
    .fm-battle-val {{ color: {TEXT_MID}; font-weight: 700; font-size: 0.9rem; }}
    .fm-battle-winner .fm-battle-name, .fm-battle-winner .fm-battle-val {{ color: {GREEN}; }}

    .fm-dna-card {{ border-left: 4px solid {GREEN}; }}
    .fm-dna-card.b {{ border-left: 4px solid {ACCENT}; }}
    .fm-dna-name {{ color: {TEXT_MID}; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }}
    .fm-dna-title {{ color: {TEXT}; font-size: 1.3rem; font-weight: 800; margin: 6px 0 4px; }}
    .fm-dna-sub {{ color: {TEXT_DIM}; font-size: 0.85rem; }}

    .fm-subhead {{ color: {TEXT_MID}; font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }}

    .fm-share-card {{
        max-width: 420px; margin: 0 auto; border-radius: 22px; overflow: hidden;
        background: linear-gradient(160deg, {GREEN_XLO} 0%, {BG} 55%, rgba(229,57,53,0.08) 100%);
        border: 1px solid {BORDER}; padding: 26px;
    }}
    .fm-share-top {{ display:flex; justify-content: space-between; align-items:center; margin-bottom: 16px; }}
    .fm-share-brand {{ font-weight: 900; color: {TEXT}; font-size: 1.05rem; }}
    .fm-share-year {{ color: {TEXT_DIM}; font-size: 0.75rem; font-weight: 700; }}
    .fm-share-score {{ text-align:center; margin: 8px 0 16px; }}
    .fm-share-score .num {{ font-size: 3.2rem; font-weight: 900; color: {GREEN}; line-height:1; }}
    .fm-share-score .lbl {{ color: {TEXT_MID}; font-size: 0.85rem; margin-top: 4px; }}
    .fm-share-tag {{ display:inline-block; margin-top:8px; padding: 5px 14px; border-radius:999px; background:{GREEN}; color:#062b12; font-weight:800; font-size:0.8rem; }}
    .fm-share-row {{ display:flex; justify-content:space-between; padding: 9px 0; border-top: 1px solid {BORDER}; }}
    .fm-share-k {{ color: {TEXT_DIM}; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .fm-share-v {{ color: {TEXT}; font-size: 0.84rem; font-weight: 700; text-align: right; max-width: 60%; }}
    </style>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════
# DATA LAYER — same query patterns already used throughout app.py
# ═════════════════════════════════════════════════════════════════════════

def _F(user_id, start_date, end_date):
    return {"user_id": user_id, "start_date": start_date, "end_date": end_date}


def _kpis(run_query, F):
    df = run_query("""
        SELECT
            COUNT(s.id) AS total_streams,
            ROUND(COALESCE(SUM(s.ms_played), 0) / 3600000.0, 2) AS total_hours,
            COUNT(DISTINCT sa.artist_id) AS unique_artists,
            COUNT(DISTINCT s.song_id) AS unique_songs
        FROM streams s
        JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
    """, F)
    if df.empty:
        return {"total_streams": 0, "total_hours": 0.0, "unique_artists": 0, "unique_songs": 0}
    r = df.iloc[0]
    return {
        "total_streams": int(r["total_streams"] or 0),
        "total_hours": float(r["total_hours"] or 0),
        "unique_artists": int(r["unique_artists"] or 0),
        "unique_songs": int(r["unique_songs"] or 0),
    }


def _top_artists(run_query, F, limit=200):
    return run_query("""
        SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours
        FROM streams s
        JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        JOIN artists a ON a.id = sa.artist_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
        GROUP BY a.id, a.name, a.image_url
        ORDER BY streams DESC LIMIT :limit
    """, {**F, "limit": limit})


def _top_tracks(run_query, F, limit=100):
    return run_query("""
        WITH TrackArtists AS (
            SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
            FROM song_artists sa JOIN artists a ON a.id = sa.artist_id GROUP BY sa.song_id
        )
        SELECT so.id AS song_id, so.title AS song_title,
               COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours
        FROM streams s
        JOIN songs so ON so.id = s.song_id
        LEFT JOIN TrackArtists ta ON ta.song_id = so.id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
        GROUP BY so.id, so.title, ta.all_artists, so.image_url
        ORDER BY streams DESC LIMIT :limit
    """, {**F, "limit": limit})


def _top_albums(run_query, F, limit=100):
    return run_query("""
        SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
               MAX(so.image_url) AS image_url,
               COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours
        FROM streams s
        JOIN songs so ON so.id = s.song_id
        LEFT JOIN albums al ON al.id = so.album_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
          AND so.album_id IS NOT NULL
        GROUP BY al.id, al.title
        ORDER BY streams DESC LIMIT :limit
    """, {**F, "limit": limit})


def _genres(run_query, F, limit=50):
    return run_query("""
        WITH StreamBase AS (
            SELECT s.id AS stream_id, s.ms_played, so.primary_genre AS song_genre,
                   al.primary_genre AS album_genre, so.album_id
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
        ),
        Unrolled AS (
            SELECT stream_id, ms_played, song_genre AS genre_name FROM StreamBase WHERE song_genre IS NOT NULL
            UNION ALL
            SELECT stream_id, ms_played, album_genre FROM StreamBase WHERE album_genre IS NOT NULL
            UNION ALL
            SELECT sb.stream_id, sb.ms_played, g.name
            FROM StreamBase sb
            JOIN album_genres ag ON ag.album_id = sb.album_id
            JOIN genres g ON g.id = ag.genre_id
        ),
        UniqueStreamGenres AS (
            SELECT DISTINCT stream_id, ms_played, INITCAP(TRIM(genre_name)) AS genre_name
            FROM Unrolled WHERE genre_name IS NOT NULL AND LOWER(genre_name) != 'unknown'
        )
        SELECT genre_name, COUNT(stream_id) AS streams, ROUND(SUM(ms_played) / 3600000.0, 2) AS hours
        FROM UniqueStreamGenres GROUP BY genre_name ORDER BY streams DESC LIMIT :limit
    """, {**F, "limit": limit})


def _hour_dist(run_query, F):
    df = run_query("""
        SELECT EXTRACT(HOUR FROM played_at)::INT AS hour, COUNT(*) AS streams
        FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
        GROUP BY 1
    """, F)
    vec = np.zeros(24)
    for _, r in df.iterrows():
        vec[int(r["hour"])] = r["streams"]
    return vec


def _day_dist(run_query, F):
    df = run_query("""
        SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, COUNT(*) AS streams
        FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
        GROUP BY 1
    """, F)
    vec = np.zeros(7)
    for _, r in df.iterrows():
        vec[int(r["dow"]) - 1] = r["streams"]
    return vec


def _monthly_trend(run_query, F):
    return run_query("""
        SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS streams
        FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
        GROUP BY 1 ORDER BY 1
    """, F)


def _avg_song_age(run_query, F):
    df = run_query("""
        SELECT ROUND(AVG(EXTRACT(YEAR FROM s.played_at) - EXTRACT(YEAR FROM so.release_date))::numeric, 1) AS avg_age
        FROM streams s JOIN songs so ON so.id = s.song_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id
          AND so.release_date IS NOT NULL
    """, F)
    if df.empty or pd.isnull(df.iloc[0]["avg_age"]):
        return 3.0
    return float(df.iloc[0]["avg_age"])


@st.cache_data(show_spinner=False, ttl=600)
def _fetch_all(_run_query, user_id, start_date, end_date):
    """`_run_query` is prefixed with underscore so Streamlit's cache
    doesn't try to hash the function object itself."""
    F = _F(user_id, start_date, end_date)
    return {
        "kpis": _kpis(_run_query, F),
        "artists": _top_artists(_run_query, F),
        "tracks": _top_tracks(_run_query, F),
        "albums": _top_albums(_run_query, F),
        "genres": _genres(_run_query, F),
        "hour_vec": _hour_dist(_run_query, F),
        "day_vec": _day_dist(_run_query, F),
        "trend": _monthly_trend(_run_query, F),
        "avg_song_age": _avg_song_age(_run_query, F),
    }


# ═════════════════════════════════════════════════════════════════════════
# SCORING / ANALYSIS
# ═════════════════════════════════════════════════════════════════════════

def _jaccard(set_a, set_b):
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _cosine(vec_a, vec_b):
    na, nb = np.linalg.norm(vec_a), np.linalg.norm(vec_b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (na * nb))


def compute_compatibility(data_a, data_b, top_n=30):
    artists_a = set(data_a["artists"].head(top_n)["artist_id"]) if not data_a["artists"].empty else set()
    artists_b = set(data_b["artists"].head(top_n)["artist_id"]) if not data_b["artists"].empty else set()
    tracks_a = set(data_a["tracks"].head(top_n)["song_id"]) if not data_a["tracks"].empty else set()
    tracks_b = set(data_b["tracks"].head(top_n)["song_id"]) if not data_b["tracks"].empty else set()
    genres_a = set(data_a["genres"]["genre_name"]) if not data_a["genres"].empty else set()
    genres_b = set(data_b["genres"]["genre_name"]) if not data_b["genres"].empty else set()

    sim_artists = _jaccard(artists_a, artists_b)
    sim_tracks = _jaccard(tracks_a, tracks_b)
    sim_genres = _jaccard(genres_a, genres_b)
    sim_hour = _cosine(data_a["hour_vec"], data_b["hour_vec"])
    sim_day = _cosine(data_a["day_vec"], data_b["day_vec"])

    weighted = (sim_artists * 0.30 + sim_tracks * 0.25 + sim_genres * 0.20 +
                sim_hour * 0.15 + sim_day * 0.10)
    score = max(0, min(100, int(round(weighted * 100))))

    if score >= 90:
        label, emoji = "Soulmates", "💞"
    elif score >= 75:
        label, emoji = "Besties", "🤝"
    elif score >= 50:
        label, emoji = "Good Match", "🙂"
    else:
        label, emoji = "Different Worlds", "🌌"

    return {
        "score": score, "label": label, "emoji": emoji,
        "breakdown": {
            "Common Artists": ("🎤", round(sim_artists * 100)),
            "Common Tracks": ("🎵", round(sim_tracks * 100)),
            "Common Genres": ("🎸", round(sim_genres * 100)),
            "Hour Rhythm": ("🕐", round(sim_hour * 100)),
            "Day Rhythm": ("📅", round(sim_day * 100)),
        },
    }


def _merge_totals(df_a, df_b, id_col, name_col):
    """Outer-merge two per-user aggregate frames (artists/tracks/albums)
    into one comparison frame with streams_a/streams_b/hours_a/hours_b
    and a single coalesced image_url."""
    base_cols = [id_col, name_col, "streams", "hours"]
    has_img = "image_url" in df_a.columns or "image_url" in df_b.columns

    a = df_a[base_cols + (["image_url"] if "image_url" in df_a.columns else [])].copy() if not df_a.empty else pd.DataFrame(columns=base_cols + ["image_url"])
    b = df_b[base_cols + (["image_url"] if "image_url" in df_b.columns else [])].copy() if not df_b.empty else pd.DataFrame(columns=base_cols + ["image_url"])

    a = a.rename(columns={"streams": "streams_a", "hours": "hours_a", "image_url": "image_url_a"})
    b = b.rename(columns={"streams": "streams_b", "hours": "hours_b", "image_url": "image_url_b"})

    merged = pd.merge(a, b, on=[id_col, name_col], how="outer")
    for c in ["streams_a", "hours_a", "streams_b", "hours_b"]:
        if c not in merged.columns:
            merged[c] = 0.0
        merged[c] = merged[c].fillna(0)

    if has_img:
        img_a = merged["image_url_a"] if "image_url_a" in merged.columns else None
        img_b = merged["image_url_b"] if "image_url_b" in merged.columns else None
        if img_a is not None and img_b is not None:
            merged["image_url"] = img_a.combine_first(img_b)
        elif img_a is not None:
            merged["image_url"] = img_a
        else:
            merged["image_url"] = img_b
    else:
        merged["image_url"] = None

    merged["combined_streams"] = merged["streams_a"] + merged["streams_b"]
    merged["combined_hours"] = merged["hours_a"] + merged["hours_b"]
    return merged


def shared_and_collision(data_a, data_b, entity, top_n=8):
    """entity in {'artists','tracks','albums'} ->
    (shared_df, a_only_df, b_only_df, id_col, name_col)"""
    id_map = {"artists": "artist_id", "tracks": "song_id", "albums": "album_id"}
    name_map = {"artists": "artist_name", "tracks": "song_title", "albums": "album_title"}
    id_col, name_col = id_map[entity], name_map[entity]

    merged = _merge_totals(data_a[entity], data_b[entity], id_col, name_col)

    shared = merged[(merged["streams_a"] > 0) & (merged["streams_b"] > 0)] \
        .sort_values("combined_streams", ascending=False).head(top_n).reset_index(drop=True)
    a_only = merged[(merged["streams_a"] > 0) & (merged["streams_b"] == 0)] \
        .sort_values("streams_a", ascending=False).head(top_n).reset_index(drop=True)
    b_only = merged[(merged["streams_b"] > 0) & (merged["streams_a"] == 0)] \
        .sort_values("streams_b", ascending=False).head(top_n).reset_index(drop=True)

    return shared, a_only, b_only, id_col, name_col


def generate_music_dna(data, username):
    hours_vec = data["hour_vec"]
    total = hours_vec.sum() or 1
    night_pct = (hours_vec[21:24].sum() + hours_vec[0:5].sum()) / total
    morning_pct = hours_vec[5:12].sum() / total

    artists = data["artists"]
    total_streams = artists["streams"].sum() if not artists.empty else 0
    top3_share = (artists.head(3)["streams"].sum() / total_streams) if total_streams else 0

    avg_age = data["avg_song_age"]

    if night_pct >= 0.35:
        time_word = "Night Owl"
    elif morning_pct >= 0.35:
        time_word = "Early Bird"
    else:
        time_word = "All-Day"

    if top3_share >= 0.5:
        style_word = "Loyalist"
    elif top3_share <= 0.22:
        style_word = "Explorer"
    else:
        style_word = "Curator"

    if avg_age >= 8:
        era_word = "Nostalgic"
    elif avg_age <= 2:
        era_word = "Trendsetter"
    else:
        era_word = "Balanced"

    top_genre = data["genres"].iloc[0]["genre_name"] if not data["genres"].empty else "Music"

    return {
        "title": f"{time_word} {style_word}",
        "subtitle": f"{era_word} • Mostly {top_genre}",
        "username": username,
    }


# ═════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ═════════════════════════════════════════════════════════════════════════

def _prep_for_list(df, id_col, name_col, streams_col, hours_col, sub_text, link_type):
    """Shape a merged comparison frame for render_list_v2: adds a
    constant 'sub' column, a positional rank, and passes the right
    streams/hours columns through under generic names."""
    if df.empty:
        return df
    out = df.copy().reset_index(drop=True)
    out["sub"] = sub_text
    out["rank"] = out.index + 1
    out["streams_disp"] = out[streams_col]
    out["hours_disp"] = out[hours_col]
    return out


def _render_compare_lists(shared, a_only, b_only, id_col, name_col, name_a, name_b, link_type):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="fm-subhead">🤝 Shared</div>', unsafe_allow_html=True)
        s = _prep_for_list(shared, id_col, name_col, "combined_streams", "combined_hours",
                            "Loved by both of you", link_type)
        if s is not None and not s.empty:
            render_list_v2(s, name_col, "sub", "streams_disp", "hours_disp",
                            id_col, link_type, rank_col="rank",
                            reveal_top_n=len(s), reveal_delay_base=0.05, reveal_delay_step=0.05)
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>No overlap yet</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="fm-subhead" style="color:{GREEN};">{escape(name_a)} only</div>', unsafe_allow_html=True)
        s = _prep_for_list(a_only, id_col, name_col, "streams_a", "hours_a",
                            f"Not on {escape(name_b)}'s radar", link_type)
        if s is not None and not s.empty:
            render_list_v2(s, name_col, "sub", "streams_disp", "hours_disp",
                            id_col, link_type, rank_col="rank",
                            reveal_top_n=len(s), reveal_delay_base=0.05, reveal_delay_step=0.05)
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing exclusive</div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="fm-subhead" style="color:{ACCENT};">{escape(name_b)} only</div>', unsafe_allow_html=True)
        s = _prep_for_list(b_only, id_col, name_col, "streams_b", "hours_b",
                            f"Not on {escape(name_a)}'s radar", link_type)
        if s is not None and not s.empty:
            render_list_v2(s, name_col, "sub", "streams_disp", "hours_disp",
                            id_col, link_type, rank_col="rank",
                            reveal_top_n=len(s), reveal_delay_base=0.05, reveal_delay_step=0.05)
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing exclusive</div>', unsafe_allow_html=True)


def _venn_figure(shared_n, a_only_n, b_only_n, name_a, name_b):
    fig = go.Figure()
    fig.add_shape(type="circle", x0=0, y0=0, x1=6, y1=6,
                  fillcolor=GREEN, opacity=0.35, line=dict(color=GREEN, width=2))
    fig.add_shape(type="circle", x0=3.4, y0=0, x1=9.4, y1=6,
                  fillcolor=ACCENT, opacity=0.35, line=dict(color=ACCENT, width=2))
    fig.add_annotation(x=1.8, y=3, text=f"<b>{a_only_n}</b><br>{escape(name_a)} only", showarrow=False,
                        font=dict(color=TEXT, size=13))
    fig.add_annotation(x=7.6, y=3, text=f"<b>{b_only_n}</b><br>{escape(name_b)} only", showarrow=False,
                        font=dict(color=TEXT, size=13))
    fig.add_annotation(x=4.7, y=3, text=f"<b>{shared_n}</b><br>Shared", showarrow=False,
                        font=dict(color=TEXT, size=14))
    fig.update_xaxes(visible=False, range=[-0.5, 9.9], fixedrange=True)
    fig.update_yaxes(visible=False, range=[-0.5, 6.5], scaleanchor="x", scaleratio=1, fixedrange=True)
    return themed(fig, height=320, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))


def _rhythm_bar_figure(vec_a, vec_b, labels, name_a, name_b):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=vec_a, name=name_a, marker_color=GREEN))
    fig.add_trace(go.Bar(x=labels, y=vec_b, name=name_b, marker_color=ACCENT))
    return themed(fig, barmode="group", height=300,
                  legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"))


def _render_battle_card(title, val_a, val_b, name_a, name_b, unit="", icon="🏆"):
    a_wins = val_a >= val_b
    st.markdown(f"""
    <div class="kpi-card">
        <div class="fm-battle-title">{icon} {escape(title)}</div>
        <div class="fm-battle-side {'fm-battle-winner' if a_wins else ''}">
            <span class="fm-battle-name">{'👑 ' if a_wins else ''}{escape(name_a)}</span>
            <span class="fm-battle-val">{val_a:,.1f}{unit}</span>
        </div>
        <div class="fm-battle-side {'fm-battle-winner' if not a_wins else ''}">
            <span class="fm-battle-name">{'👑 ' if not a_wins else ''}{escape(name_b)}</span>
            <span class="fm-battle-val">{val_b:,.1f}{unit}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_share_card(name_a, name_b, compat, shared_artist, shared_track):
    tag = f"{compat['emoji']} {compat['label']}"
    html_card = f"""
    <div class="fm-share-card" id="fm-share-card">
        <div class="fm-share-top">
            <div class="fm-share-brand">🎧 Suggestify</div>
            <div class="fm-share-year">FRIENDS MATCH</div>
        </div>
        <div class="fm-avatars">
            <div class="fm-avatar">{escape(name_a[:1].upper())}</div>
            <div class="fm-avatar b">{escape(name_b[:1].upper())}</div>
        </div>
        <div style="text-align:center; color:{TEXT_MID}; font-size:0.9rem;">{escape(name_a)} &amp; {escape(name_b)}</div>
        <div class="fm-share-score">
            <div class="num">{compat['score']}%</div>
            <div class="lbl">Music Compatibility</div>
            <div class="fm-share-tag">{escape(tag)}</div>
        </div>
        <div class="fm-share-row"><span class="fm-share-k">Top Shared Artist</span><span class="fm-share-v">{escape(shared_artist)}</span></div>
        <div class="fm-share-row"><span class="fm-share-k">Top Shared Song</span><span class="fm-share-v">{escape(shared_track)}</span></div>
    </div>
    <div style="text-align:center; margin-top:14px;">
        <button onclick="fmDownload()" style="
            background:{GREEN}; color:#062b12; border:none; border-radius:999px;
            padding:10px 22px; font-weight:800; cursor:pointer; font-size:0.85rem;">
            ⬇️ Save as PNG
        </button>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script>
    function fmDownload() {{
        const node = document.getElementById('fm-share-card');
        html2canvas(node, {{backgroundColor: null, scale: 2}}).then(canvas => {{
            const link = document.createElement('a');
            link.download = 'suggestify_friends_match.png';
            link.href = canvas.toDataURL('image/png');
            link.click();
        }});
    }}
    </script>
    """
    components.html(html_card, height=560, scrolling=False)


# ═════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════

def render_friends_match_tab(run_query, user_dict, min_date, max_date, default_user_id=None):
    _inject_css()

    st.markdown('<div class="section-header"><span class="icon">🎉</span>Friends Match</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="color:{TEXT_MID};margin-bottom:18px;">'
                'Pick two friends and see how compatible your music taste really is.</div>',
                unsafe_allow_html=True)

    usernames = list(user_dict.keys())
    if len(usernames) < 2:
        st.info("You need at least two users in the database to run a Friends Match. 🙂")
        return

    default_a_idx = 0
    if default_user_id is not None:
        for i, u in enumerate(usernames):
            if user_dict[u] == default_user_id:
                default_a_idx = i
                break

    col_a, col_vs, col_b = st.columns([2, 0.4, 2])
    with col_a:
        name_a = st.selectbox("User A", usernames, index=default_a_idx, key="fm_user_a")
    with col_vs:
        st.markdown('<div style="text-align:center;font-size:1.6rem;margin-top:28px;">⚔️</div>', unsafe_allow_html=True)
    with col_b:
        remaining = [u for u in usernames if u != name_a] or usernames
        name_b = st.selectbox("User B", remaining, index=0, key="fm_user_b")

    col_range, col_btn = st.columns([3, 1])
    with col_range:
        preset = st.selectbox("Compare over", ["All Time", "This Year", "Last 30 Days"], key="fm_range")
    with col_btn:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        compare_clicked = st.button("💥 Compare", use_container_width=True, type="primary")

    if preset == "All Time":
        start_date, end_date = min_date, max_date
    elif preset == "This Year":
        start_date, end_date = datetime.date(max_date.year, 1, 1), max_date
    else:
        start_date, end_date = max_date - datetime.timedelta(days=30), max_date

    cache_key = f"fm_result_{name_a}_{name_b}_{start_date}_{end_date}"

    if compare_clicked or cache_key in st.session_state:
        if name_a == name_b:
            st.warning("Pick two different people to compare. 😄")
            return

        if cache_key not in st.session_state:
            with st.spinner("Crunching listening data…"):
                data_a = _fetch_all(run_query, user_dict[name_a], start_date, end_date)
                data_b = _fetch_all(run_query, user_dict[name_b], start_date, end_date)
                st.session_state[cache_key] = (data_a, data_b)

        data_a, data_b = st.session_state[cache_key]
        _render_results(name_a, name_b, data_a, data_b)


def _render_results(name_a, name_b, data_a, data_b):
    compat = compute_compatibility(data_a, data_b)

    # ── Section 1: Match Score (reuses .wrapped-banner) ─────────────────
    st.markdown(f"""
    <div class="wrapped-banner">
        <div class="fm-avatars">
            <div class="fm-avatar">{escape(name_a[:1].upper())}</div>
            <div class="fm-avatar b">{escape(name_b[:1].upper())}</div>
        </div>
        <div style="text-align:center; color:{TEXT_MID}; font-weight:700; margin-bottom:4px;">❤️ Music Compatibility</div>
        <div class="wrapped-title" style="text-align:center; font-size:3.2rem;">{compat['score']}%</div>
        <div class="wrapped-subtitle" style="text-align:center;">{escape(name_a)} &amp; {escape(name_b)}</div>
        <div style="text-align:center; margin-top:10px;">
            <span style="display:inline-block; padding:6px 18px; border-radius:999px; font-weight:800;
                         font-size:0.9rem; background:{GREEN}; color:#062b12;">
                {compat['emoji']} {compat['label']}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    render_kpi_grid([
        {"icon": icon, "title": label, "raw": val, "suffix": "%"}
        for label, (icon, val) in compat["breakdown"].items()
    ])

    # ── Section 2: Who Wins ──────────────────────────────────────────────
    st.markdown('<div class="section-header"><span class="icon">🏆</span>Who Wins?</div>', unsafe_allow_html=True)
    battle_cols = st.columns(4)
    battles = [
        ("More Streams", data_a["kpis"]["total_streams"], data_b["kpis"]["total_streams"], "", "🔥"),
        ("More Listening Hours", data_a["kpis"]["total_hours"], data_b["kpis"]["total_hours"], "h", "⏱️"),
        ("More Unique Artists", data_a["kpis"]["unique_artists"], data_b["kpis"]["unique_artists"], "", "🎤"),
        ("More Unique Songs", data_a["kpis"]["unique_songs"], data_b["kpis"]["unique_songs"], "", "🎶"),
    ]
    for col, (title, va, vb, unit, icon) in zip(battle_cols, battles):
        with col:
            _render_battle_card(title, va, vb, name_a, name_b, unit, icon)

    # ── Section 3: Music DNA ─────────────────────────────────────────────
    dna_a = generate_music_dna(data_a, name_a)
    dna_b = generate_music_dna(data_b, name_b)
    st.markdown('<div class="section-header"><span class="icon">🧬</span>Music DNA</div>', unsafe_allow_html=True)
    dcol1, dcol2 = st.columns(2)
    with dcol1:
        st.markdown(f"""
        <div class="kpi-card fm-dna-card">
            <div class="fm-dna-name">{escape(name_a)}</div>
            <div class="fm-dna-title">{escape(dna_a['title'])}</div>
            <div class="fm-dna-sub">{escape(dna_a['subtitle'])}</div>
        </div>
        """, unsafe_allow_html=True)
    with dcol2:
        st.markdown(f"""
        <div class="kpi-card fm-dna-card b">
            <div class="fm-dna-name">{escape(name_b)}</div>
            <div class="fm-dna-title">{escape(dna_b['title'])}</div>
            <div class="fm-dna-sub">{escape(dna_b['subtitle'])}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Section 4: Shared Obsessions (clickable, via render_list_v2) ────
    st.markdown('<div class="section-header"><span class="icon">🎯</span>Shared Obsessions — Artists</div>', unsafe_allow_html=True)
    shared_art, a_only_art, b_only_art, art_id_col, art_name_col = shared_and_collision(data_a, data_b, "artists")
    _render_compare_lists(shared_art, a_only_art, b_only_art, art_id_col, art_name_col, name_a, name_b, "artist")

    st.markdown('<div class="section-header"><span class="icon">🎵</span>Shared Obsessions — Tracks</div>', unsafe_allow_html=True)
    shared_trk, a_only_trk, b_only_trk, trk_id_col, trk_name_col = shared_and_collision(data_a, data_b, "tracks")
    _render_compare_lists(shared_trk, a_only_trk, b_only_trk, trk_id_col, trk_name_col, name_a, name_b, "song")

    st.markdown('<div class="section-header"><span class="icon">💿</span>Shared Obsessions — Albums</div>', unsafe_allow_html=True)
    shared_alb, a_only_alb, b_only_alb, alb_id_col, alb_name_col = shared_and_collision(data_a, data_b, "albums")
    _render_compare_lists(shared_alb, a_only_alb, b_only_alb, alb_id_col, alb_name_col, name_a, name_b, "album")

    # ── Section 6: Timeline Comparison (reuses chart_multi_trend) ───────
    st.markdown('<div class="section-header"><span class="icon">📈</span>Listening Timeline</div>', unsafe_allow_html=True)
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    ta = data_a["trend"].rename(columns={"streams": "stream_count"}).copy()
    tb = data_b["trend"].rename(columns={"streams": "stream_count"}).copy()
    ta["track_title"] = name_a
    tb["track_title"] = name_b
    trend_combined = pd.concat([ta, tb], ignore_index=True)
    if not trend_combined.empty:
        st.plotly_chart(chart_multi_trend(trend_combined), use_container_width=True,
                         config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
    else:
        st.markdown('<div class="empty-state"><div class="icon">📭</div>No data for this period</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Section 7: Daily Rhythm ──────────────────────────────────────────
    st.markdown('<div class="section-header"><span class="icon">🕐</span>Daily Rhythm</div>', unsafe_allow_html=True)
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown('<div class="chart-container"><div class="chart-title">Hour of Day</div>', unsafe_allow_html=True)
        hour_labels = [f"{h:02d}:00" for h in range(24)]
        st.plotly_chart(_rhythm_bar_figure(data_a["hour_vec"], data_b["hour_vec"], hour_labels, name_a, name_b),
                         use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        st.markdown('</div>', unsafe_allow_html=True)
    with rc2:
        st.markdown('<div class="chart-container"><div class="chart-title">Day of Week</div>', unsafe_allow_html=True)
        dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        st.plotly_chart(_rhythm_bar_figure(data_a["day_vec"], data_b["day_vec"], dow_labels, name_a, name_b),
                         use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        st.markdown('</div>', unsafe_allow_html=True)

    fav_hour_a = int(np.argmax(data_a["hour_vec"])) if data_a["hour_vec"].sum() else None
    fav_hour_b = int(np.argmax(data_b["hour_vec"])) if data_b["hour_vec"].sum() else None
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    fav_day_a = dow_names[int(np.argmax(data_a["day_vec"]))] if data_a["day_vec"].sum() else "—"
    fav_day_b = dow_names[int(np.argmax(data_b["day_vec"]))] if data_b["day_vec"].sum() else "—"
    st.markdown(f"""
    <div style="display:flex;gap:24px;margin-top:6px;flex-wrap:wrap;color:{TEXT_MID};font-size:0.85rem;">
        <div>🎧 <b style="color:{GREEN}">{escape(name_a)}</b> peaks at
            <b style="color:{TEXT}">{f'{fav_hour_a:02d}:00' if fav_hour_a is not None else '—'}</b>
            on <b style="color:{TEXT}">{escape(fav_day_a)}</b></div>
        <div>🎧 <b style="color:{ACCENT}">{escape(name_b)}</b> peaks at
            <b style="color:{TEXT}">{f'{fav_hour_b:02d}:00' if fav_hour_b is not None else '—'}</b>
            on <b style="color:{TEXT}">{escape(fav_day_b)}</b></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Section 8: Taste Venn Diagram ────────────────────────────────────
    st.markdown('<div class="section-header"><span class="icon">🎨</span>Taste Venn Diagram (Artists)</div>', unsafe_allow_html=True)
    full_a = set(data_a["artists"]["artist_id"]) if not data_a["artists"].empty else set()
    full_b = set(data_b["artists"]["artist_id"]) if not data_b["artists"].empty else set()
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.plotly_chart(_venn_figure(len(full_a & full_b), len(full_a - full_b), len(full_b - full_a), name_a, name_b),
                     use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Section 9: Steal Their Taste (also clickable via render_list_v2) ─
    st.markdown('<div class="section-header"><span class="icon">🕵️</span>If You Stole Their Taste</div>', unsafe_allow_html=True)
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        st.markdown(f'<div class="fm-subhead">Based on the overlap, {escape(name_a)} would probably enjoy</div>', unsafe_allow_html=True)
        reco_a = _prep_for_list(b_only_art.head(5), art_id_col, art_name_col, "streams_b", "hours_b",
                                 f"{escape(name_b)} listens to this a lot", "artist")
        if reco_a is not None and not reco_a.empty:
            render_list_v2(reco_a, art_name_col, "sub", "streams_disp", "hours_disp",
                            art_id_col, "artist", rank_col="rank")
        else:
            st.markdown(f'<div class="empty-state"><div class="icon">📭</div>Already covers everything {escape(name_b)}\'s into!</div>', unsafe_allow_html=True)
    with rcol2:
        st.markdown(f'<div class="fm-subhead">Based on the overlap, {escape(name_b)} would probably enjoy</div>', unsafe_allow_html=True)
        reco_b = _prep_for_list(a_only_art.head(5), art_id_col, art_name_col, "streams_a", "hours_a",
                                 f"{escape(name_a)} listens to this a lot", "artist")
        if reco_b is not None and not reco_b.empty:
            render_list_v2(reco_b, art_name_col, "sub", "streams_disp", "hours_disp",
                            art_id_col, "artist", rank_col="rank")
        else:
            st.markdown(f'<div class="empty-state"><div class="icon">📭</div>Already covers everything {escape(name_a)}\'s into!</div>', unsafe_allow_html=True)

    # ── Section 10: Share Card ───────────────────────────────────────────
    st.markdown('<div class="section-header"><span class="icon">📸</span>Share Card</div>', unsafe_allow_html=True)
    top_shared_artist = shared_art.iloc[0][art_name_col] if not shared_art.empty else "None yet"
    top_shared_track = shared_trk.iloc[0][trk_name_col] if not shared_trk.empty else "None yet"
    _render_share_card(name_a, name_b, compat, top_shared_artist, top_shared_track)