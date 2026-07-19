import datetime
import random
from html import escape

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ─────────────────────────────────────────────────────────────────────────
# Defaults (override via the `colors` dict passed into render_friends_match_tab)
# ─────────────────────────────────────────────────────────────────────────
_DEFAULT_COLORS = {
    "GREEN": "#1DB954",
    "TEXT": "#FFFFFF",
    "TEXT_MID": "#B3B3B3",
    "TEXT_DIM": "#727272",
    "BG": "#121212",
}

ACCENT = "#E53935"   # secondary accent (User B color), matches your quick-rate red
CARD_BG = "rgba(255,255,255,0.04)"
BORDER = "rgba(255,255,255,0.08)"


# ═════════════════════════════════════════════════════════════════════════
# CSS
# ═════════════════════════════════════════════════════════════════════════

def _inject_css(C):
    st.markdown(f"""
    <style>
    @keyframes fm-fade-up {{
        from {{ opacity: 0; transform: translateY(14px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fm-pop {{
        0%   {{ transform: scale(0.85); opacity: 0; }}
        60%  {{ transform: scale(1.04); opacity: 1; }}
        100% {{ transform: scale(1); }}
    }}
    @keyframes fm-pulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(29,185,84,0.35); }}
        50%      {{ box-shadow: 0 0 0 14px rgba(29,185,84,0); }}
    }}
    .fm-section {{
        animation: fm-fade-up 0.5s ease both;
        margin: 28px 0 8px;
    }}
    .fm-section-title {{
        font-size: 1.05rem; font-weight: 800; color: {C['TEXT']};
        display: flex; align-items: center; gap: 8px; margin-bottom: 14px;
        letter-spacing: 0.2px;
    }}
    .fm-hero {{
        background: linear-gradient(135deg, rgba(29,185,84,0.16), rgba(229,57,53,0.10));
        border: 1px solid {BORDER};
        border-radius: 24px;
        padding: 36px 28px;
        text-align: center;
        animation: fm-pop 0.6s ease both;
        position: relative;
        overflow: hidden;
    }}
    .fm-hero-score {{
        font-size: 4.2rem; font-weight: 900; color: {C['GREEN']};
        line-height: 1; margin: 8px 0;
        text-shadow: 0 0 30px rgba(29,185,84,0.45);
    }}
    .fm-hero-label {{
        display: inline-block; margin-top: 6px; padding: 6px 18px;
        border-radius: 999px; font-weight: 800; font-size: 0.95rem;
        background: {C['GREEN']}; color: #062b12;
        animation: fm-pulse 2.4s infinite;
    }}
    .fm-avatars {{ display: flex; align-items: center; justify-content: center; gap: -10px; margin-bottom: 6px; }}
    .fm-avatar {{
        width: 64px; height: 64px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.6rem; font-weight: 800; color: #fff;
        border: 3px solid {C['BG']};
        background: linear-gradient(135deg, {C['GREEN']}, #0d7a37);
    }}
    .fm-avatar.b {{ background: linear-gradient(135deg, {ACCENT}, #8f1f1c); margin-left: -18px; }}
    .fm-vs {{ font-weight: 800; color: {C['TEXT_DIM']}; margin: 0 6px; }}
    .fm-names {{ color: {C['TEXT_MID']}; font-size: 0.95rem; margin-top: 4px; }}

    .fm-battle-row {{ display: flex; gap: 14px; flex-wrap: wrap; }}
    .fm-battle-card {{
        flex: 1 1 220px; background: {CARD_BG}; border: 1px solid {BORDER};
        border-radius: 16px; padding: 16px 18px; animation: fm-fade-up 0.5s ease both;
    }}
    .fm-battle-title {{ color: {C['TEXT_MID']}; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }}
    .fm-battle-side {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 0; }}
    .fm-battle-name {{ color: {C['TEXT']}; font-weight: 600; font-size: 0.92rem; }}
    .fm-battle-val {{ color: {C['TEXT_MID']}; font-weight: 700; font-size: 0.92rem; }}
    .fm-battle-winner .fm-battle-name {{ color: {C['GREEN']}; }}
    .fm-battle-winner .fm-battle-val {{ color: {C['GREEN']}; }}
    .fm-crown {{ margin-right: 6px; }}

    .fm-dna-row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
    .fm-dna-card {{
        flex: 1 1 280px; border-radius: 18px; padding: 22px;
        background: {CARD_BG}; border: 1px solid {BORDER}; animation: fm-fade-up 0.55s ease both;
    }}
    .fm-dna-card.a {{ border-left: 4px solid {C['GREEN']}; }}
    .fm-dna-card.b {{ border-left: 4px solid {ACCENT}; }}
    .fm-dna-name {{ color: {C['TEXT_MID']}; font-size: 0.82rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }}
    .fm-dna-title {{ color: {C['TEXT']}; font-size: 1.35rem; font-weight: 800; margin: 6px 0 4px; }}
    .fm-dna-sub {{ color: {C['TEXT_DIM']}; font-size: 0.88rem; }}

    .fm-list-row {{
        display: flex; align-items: center; gap: 12px; padding: 9px 10px;
        border-radius: 10px; margin-bottom: 4px; background: rgba(255,255,255,0.02);
        animation: fm-fade-up 0.4s ease both;
    }}
    .fm-list-row img, .fm-list-avatar-fallback {{
        width: 42px; height: 42px; border-radius: 8px; object-fit: cover; flex-shrink: 0;
        background: rgba(255,255,255,0.08); display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem;
    }}
    .fm-list-rank {{ color: {C['TEXT_DIM']}; font-weight: 800; font-size: 0.85rem; width: 20px; text-align: center; flex-shrink: 0; }}
    .fm-list-main {{ flex: 1; min-width: 0; }}
    .fm-list-title {{ color: {C['TEXT']}; font-weight: 600; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .fm-list-sub {{ color: {C['TEXT_DIM']}; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .fm-list-stat {{ color: {C['TEXT_MID']}; font-size: 0.82rem; font-weight: 700; flex-shrink: 0; }}
    .fm-list-badge {{
        flex-shrink: 0; font-size: 0.68rem; font-weight: 800; padding: 3px 8px; border-radius: 999px;
    }}
    .fm-list-badge.a {{ background: rgba(29,185,84,0.18); color: {C['GREEN']}; }}
    .fm-list-badge.b {{ background: rgba(229,57,53,0.18); color: {ACCENT}; }}

    .fm-empty {{ color: {C['TEXT_DIM']}; font-size: 0.85rem; padding: 14px 4px; text-align: center; }}

    .fm-share-card {{
        max-width: 420px; margin: 0 auto; border-radius: 22px; overflow: hidden;
        background: linear-gradient(160deg, #0d1f14 0%, #121212 55%, #1c0f0e 100%);
        border: 1px solid {BORDER}; padding: 26px; font-family: inherit;
    }}
    .fm-share-top {{ display:flex; justify-content: space-between; align-items:center; margin-bottom: 18px; }}
    .fm-share-brand {{ font-weight: 900; color: {C['TEXT']}; font-size: 1.05rem; }}
    .fm-share-year {{ color: {C['TEXT_DIM']}; font-size: 0.78rem; font-weight: 700; }}
    .fm-share-score {{ text-align:center; margin: 10px 0 18px; }}
    .fm-share-score .num {{ font-size: 3.4rem; font-weight: 900; color: {C['GREEN']}; line-height:1; }}
    .fm-share-score .lbl {{ color: {C['TEXT_MID']}; font-size: 0.85rem; margin-top: 4px; }}
    .fm-share-tag {{ display:inline-block; margin-top:8px; padding: 5px 14px; border-radius:999px; background:{C['GREEN']}; color:#062b12; font-weight:800; font-size:0.8rem; }}
    .fm-share-row {{ display:flex; justify-content:space-between; padding: 10px 0; border-top: 1px solid {BORDER}; }}
    .fm-share-row:last-child {{ padding-bottom: 0; }}
    .fm-share-k {{ color: {C['TEXT_DIM']}; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.4px; }}
    .fm-share-v {{ color: {C['TEXT']}; font-size: 0.86rem; font-weight: 700; text-align: right; max-width: 60%; }}
    </style>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════
# DATA LAYER
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
    """Cached bundle of everything needed for one user. `_run_query` is
    prefixed with underscore so Streamlit's cache doesn't try to hash it."""
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
    if not set_a and not set_b:
        return 0.0
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

    weighted = (
        sim_artists * 0.30 + sim_tracks * 0.25 + sim_genres * 0.20 +
        sim_hour * 0.15 + sim_day * 0.10
    )
    score = int(round(weighted * 100))
    score = max(0, min(100, score))

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
            "Common Artists": round(sim_artists * 100),
            "Common Tracks": round(sim_tracks * 100),
            "Common Genres": round(sim_genres * 100),
            "Hour Rhythm": round(sim_hour * 100),
            "Day Rhythm": round(sim_day * 100),
        },
    }


def _merge_totals(df_a, df_b, id_col, name_col, extra_cols=()):
    """Outer-merge two per-user aggregate frames into one comparison frame."""
    cols = [id_col, name_col, "streams"] + list(extra_cols)
    a = df_a[cols].rename(columns={"streams": "streams_a"}) if not df_a.empty else pd.DataFrame(columns=cols[:-1] + ["streams_a"])
    b = df_b[cols].rename(columns={"streams": "streams_b"}) if not df_b.empty else pd.DataFrame(columns=cols[:-1] + ["streams_b"])
    merged = pd.merge(a, b, on=[id_col, name_col], how="outer", suffixes=("", "_b2"))
    merged["streams_a"] = merged["streams_a"].fillna(0)
    merged["streams_b"] = merged["streams_b"].fillna(0)
    return merged


def shared_and_collision(data_a, data_b, entity, top_n=8):
    """entity in {'artists','tracks','albums'} -> returns (shared_df, a_only_df, b_only_df)"""
    id_map = {"artists": "artist_id", "tracks": "song_id", "albums": "album_id"}
    name_map = {"artists": "artist_name", "tracks": "song_title", "albums": "album_title"}
    id_col, name_col = id_map[entity], name_map[entity]

    df_a, df_b = data_a[entity], data_b[entity]
    image_col = "image_url" if "image_url" in df_a.columns else None
    extra = (image_col,) if image_col else ()

    merged = _merge_totals(df_a, df_b, id_col, name_col, extra_cols=extra)
    if image_col:
        img_col_final = image_col if image_col in merged.columns else f"{image_col}_b2"
        merged["image_url"] = merged.get(image_col)
        if img_col_final in merged.columns:
            merged["image_url"] = merged["image_url"].fillna(merged.get(img_col_final))

    merged["combined"] = merged["streams_a"] + merged["streams_b"]

    shared = merged[(merged["streams_a"] > 0) & (merged["streams_b"] > 0)] \
        .sort_values("combined", ascending=False).head(top_n)
    a_only = merged[(merged["streams_a"] > 0) & (merged["streams_b"] == 0)] \
        .sort_values("streams_a", ascending=False).head(top_n)
    b_only = merged[(merged["streams_b"] > 0) & (merged["streams_a"] == 0)] \
        .sort_values("streams_b", ascending=False).head(top_n)

    return shared, a_only, b_only, id_col, name_col


def generate_music_dna(data, username):
    hours = data["hour_vec"]
    total = hours.sum() or 1
    night_pct = (hours[21:24].sum() + hours[0:5].sum()) / total
    morning_pct = hours[5:12].sum() / total

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

    title = f"{time_word} {style_word}"
    subtitle = f"{era_word} • Mostly {top_genre}"
    return {"title": title, "subtitle": subtitle, "username": username}


def build_recommendations(other_only_df, id_col, name_col, limit=5):
    if other_only_df.empty:
        return []
    top = other_only_df.sort_values("streams_b" if "streams_b" in other_only_df.columns else "streams_a",
                                     ascending=False).head(limit)
    return top[name_col].tolist()


# ═════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ═════════════════════════════════════════════════════════════════════════

def _list_row(rank, title, sub, stat, image_url=None, badge=None, icon="🎵"):
    img_html = (
        f'<img src="{escape(image_url)}" />' if image_url and pd.notnull(image_url)
        else f'<div class="fm-list-avatar-fallback">{icon}</div>'
    )
    badge_html = ""
    if badge:
        badge_html = f'<span class="fm-list-badge {badge[1]}">{escape(badge[0])}</span>'
    st.markdown(f"""
    <div class="fm-list-row">
        <div class="fm-list-rank">{rank}</div>
        {img_html}
        <div class="fm-list-main">
            <div class="fm-list-title">{escape(str(title))}</div>
            <div class="fm-list-sub">{escape(str(sub))}</div>
        </div>
        {badge_html}
        <div class="fm-list-stat">{stat}</div>
    </div>
    """, unsafe_allow_html=True)


def _render_shared_block(shared, a_only, b_only, id_col, name_col, name_a, name_b, icon):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div style="color:{_DEFAULT_COLORS["TEXT_MID"]};font-weight:700;font-size:0.85rem;margin-bottom:8px;">🤝 Shared</div>', unsafe_allow_html=True)
        if shared.empty:
            st.markdown('<div class="fm-empty">No overlap yet</div>', unsafe_allow_html=True)
        else:
            for i, (_, r) in enumerate(shared.iterrows(), 1):
                _list_row(i, r[name_col], f"{int(r['streams_a'])} vs {int(r['streams_b'])} plays",
                           f"{int(r['combined'])}", r.get("image_url"), icon=icon)
    with col2:
        st.markdown(f'<div style="color:{_DEFAULT_COLORS["GREEN"]};font-weight:700;font-size:0.85rem;margin-bottom:8px;">{escape(name_a)} only</div>', unsafe_allow_html=True)
        if a_only.empty:
            st.markdown('<div class="fm-empty">Nothing exclusive</div>', unsafe_allow_html=True)
        else:
            for i, (_, r) in enumerate(a_only.iterrows(), 1):
                _list_row(i, r[name_col], "Not on their radar", f"{int(r['streams_a'])}",
                           r.get("image_url"), badge=("A", "a"), icon=icon)
    with col3:
        st.markdown(f'<div style="color:{ACCENT};font-weight:700;font-size:0.85rem;margin-bottom:8px;">{escape(name_b)} only</div>', unsafe_allow_html=True)
        if b_only.empty:
            st.markdown('<div class="fm-empty">Nothing exclusive</div>', unsafe_allow_html=True)
        else:
            for i, (_, r) in enumerate(b_only.iterrows(), 1):
                _list_row(i, r[name_col], "Not on their radar", f"{int(r['streams_b'])}",
                           r.get("image_url"), badge=("B", "b"), icon=icon)


def _venn_figure(shared_n, a_only_n, b_only_n, name_a, name_b, C):
    fig = go.Figure()
    fig.add_shape(type="circle", x0=0, y0=0, x1=6, y1=6,
                  fillcolor=C["GREEN"], opacity=0.35, line=dict(color=C["GREEN"], width=2))
    fig.add_shape(type="circle", x0=3.4, y0=0, x1=9.4, y1=6,
                  fillcolor=ACCENT, opacity=0.35, line=dict(color=ACCENT, width=2))
    fig.add_annotation(x=1.8, y=3, text=f"<b>{a_only_n}</b><br>{escape(name_a)} only", showarrow=False,
                        font=dict(color=C["TEXT"], size=13))
    fig.add_annotation(x=7.6, y=3, text=f"<b>{b_only_n}</b><br>{escape(name_b)} only", showarrow=False,
                        font=dict(color=C["TEXT"], size=13))
    fig.add_annotation(x=4.7, y=3, text=f"<b>{shared_n}</b><br>Shared", showarrow=False,
                        font=dict(color=C["TEXT"], size=14))
    fig.update_xaxes(visible=False, range=[-0.5, 9.9])
    fig.update_yaxes(visible=False, range=[-0.5, 6.5], scaleanchor="x", scaleratio=1)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=320, showlegend=False,
    )
    return fig


def _trend_compare_figure(trend_a, trend_b, name_a, name_b, C):
    fig = go.Figure()
    if not trend_a.empty:
        fig.add_trace(go.Scatter(x=trend_a["period"], y=trend_a["streams"], mode="lines+markers",
                                  name=name_a, line=dict(color=C["GREEN"], width=3),
                                  marker=dict(size=6)))
    if not trend_b.empty:
        fig.add_trace(go.Scatter(x=trend_b["period"], y=trend_b["streams"], mode="lines+markers",
                                  name=name_b, line=dict(color=ACCENT, width=3),
                                  marker=dict(size=6)))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C["TEXT_MID"]),
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=40, b=10), height=340,
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
    )
    return fig


def _rhythm_bar_figure(vec_a, vec_b, labels, name_a, name_b, C):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=vec_a, name=name_a, marker_color=C["GREEN"]))
    fig.add_trace(go.Bar(x=labels, y=vec_b, name=name_b, marker_color=ACCENT))
    fig.update_layout(
        barmode="group", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C["TEXT_MID"]), legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=40, b=10), height=300,
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
    )
    return fig


def _render_battle_card(title, val_a, val_b, name_a, name_b, unit="", icon="🏆"):
    a_wins = val_a >= val_b
    winner = name_a if a_wins else name_b
    st.markdown(f"""
    <div class="fm-battle-card">
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


def _render_share_card(name_a, name_b, compat, shared_artist, shared_track, C):
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
        <div class="fm-names">{escape(name_a)} &amp; {escape(name_b)}</div>
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
            background:{C['GREEN']}; color:#062b12; border:none; border-radius:999px;
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

def render_friends_match_tab(run_query, user_dict, min_date, max_date,
                              default_user_id=None, colors=None):
    """
    run_query      : your existing run_query(sql, params) -> DataFrame function
    user_dict      : {username: user_id} exactly like in app.py
    min_date/max_date : global date bounds (datetime.date)
    default_user_id   : pre-select this user as "User A" (e.g. selected_user_id)
    colors         : optional dict with GREEN/TEXT/TEXT_MID/TEXT_DIM/BG overrides
    """
    C = {**_DEFAULT_COLORS, **(colors or {})}
    _inject_css(C)

    st.markdown('<div class="fm-section-title">🎉 Friends Match</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="color:{C["TEXT_MID"]};margin-bottom:18px;">'
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
    default_b_idx = 1 if default_a_idx == 0 else 0

    col_a, col_vs, col_b = st.columns([2, 0.4, 2])
    with col_a:
        name_a = st.selectbox("User A", usernames, index=default_a_idx, key="fm_user_a")
    with col_vs:
        st.markdown(f'<div style="text-align:center;font-size:1.6rem;margin-top:28px;">⚔️</div>', unsafe_allow_html=True)
    with col_b:
        remaining = [u for u in usernames if u != name_a] or usernames
        b_default = remaining[0] if usernames[default_b_idx] not in remaining else usernames[default_b_idx]
        name_b = st.selectbox("User B", remaining, index=remaining.index(b_default) if b_default in remaining else 0, key="fm_user_b")

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
                user_a_id = user_dict[name_a]
                user_b_id = user_dict[name_b]
                data_a = _fetch_all(run_query, user_a_id, start_date, end_date)
                data_b = _fetch_all(run_query, user_b_id, start_date, end_date)
                st.session_state[cache_key] = (data_a, data_b)

        data_a, data_b = st.session_state[cache_key]
        _render_results(name_a, name_b, data_a, data_b, C)


def _render_results(name_a, name_b, data_a, data_b, C):
    compat = compute_compatibility(data_a, data_b)

    # ── Section 1: Match Score ──────────────────────────────────────────
    st.markdown('<div class="fm-section">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="fm-hero">
        <div class="fm-avatars">
            <div class="fm-avatar">{escape(name_a[:1].upper())}</div>
            <div class="fm-avatar b">{escape(name_b[:1].upper())}</div>
        </div>
        <div class="fm-names">{escape(name_a)} &amp; {escape(name_b)}</div>
        <div style="color:{C['TEXT_MID']};font-weight:700;margin-top:10px;">❤️ Music Compatibility</div>
        <div class="fm-hero-score">{compat['score']}%</div>
        <div class="fm-hero-label">{compat['emoji']} {compat['label']}</div>
    </div>
    """, unsafe_allow_html=True)
    bcols = st.columns(5)
    for i, (k, v) in enumerate(compat["breakdown"].items()):
        with bcols[i]:
            st.markdown(f"""
            <div style="text-align:center;margin-top:10px;">
                <div style="color:{C['TEXT']};font-weight:800;font-size:1.1rem;">{v}%</div>
                <div style="color:{C['TEXT_DIM']};font-size:0.72rem;">{escape(k)}</div>
            </div>
            """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Section 2: Who Wins ─────────────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">🏆 Who Wins?</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="fm-battle-row">', unsafe_allow_html=True)
    battle_cols = st.columns(4)
    battles = [
        ("More Streams", data_a["kpis"]["total_streams"], data_b["kpis"]["total_streams"], "", "🔥"),
        ("More Listening Hours", data_a["kpis"]["total_hours"], data_b["kpis"]["total_hours"], "h", "⏱️"),
        ("More Unique Artists", data_a["kpis"]["unique_artists"], data_b["kpis"]["unique_artists"], "", "🎤"),
        ("More Unique Songs", data_a["kpis"]["unique_songs"], data_b["kpis"]["unique_songs"], "", "🎶"),
    ]
    for i, (title, va, vb, unit, icon) in enumerate(battles):
        with battle_cols[i]:
            _render_battle_card(title, va, vb, name_a, name_b, unit, icon)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Section 3: Music DNA ────────────────────────────────────────────
    dna_a = generate_music_dna(data_a, name_a)
    dna_b = generate_music_dna(data_b, name_b)
    st.markdown('<div class="fm-section"><div class="fm-section-title">🧬 Music DNA</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="fm-dna-row">', unsafe_allow_html=True)
    dcol1, dcol2 = st.columns(2)
    with dcol1:
        st.markdown(f"""
        <div class="fm-dna-card a">
            <div class="fm-dna-name">{escape(name_a)}</div>
            <div class="fm-dna-title">{escape(dna_a['title'])}</div>
            <div class="fm-dna-sub">{escape(dna_a['subtitle'])}</div>
        </div>
        """, unsafe_allow_html=True)
    with dcol2:
        st.markdown(f"""
        <div class="fm-dna-card b">
            <div class="fm-dna-name">{escape(name_b)}</div>
            <div class="fm-dna-title">{escape(dna_b['title'])}</div>
            <div class="fm-dna-sub">{escape(dna_b['subtitle'])}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Section 4: Shared Obsessions ────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">🎯 Shared Obsessions — Artists</div></div>', unsafe_allow_html=True)
    shared_art, a_only_art, b_only_art, art_id_col, art_name_col = shared_and_collision(data_a, data_b, "artists")
    _render_shared_block(shared_art, a_only_art, b_only_art, art_id_col, art_name_col, name_a, name_b, "🎤")

    st.markdown('<div class="fm-section"><div class="fm-section-title">🎵 Shared Obsessions — Tracks</div></div>', unsafe_allow_html=True)
    shared_trk, a_only_trk, b_only_trk, trk_id_col, trk_name_col = shared_and_collision(data_a, data_b, "tracks")
    _render_shared_block(shared_trk, a_only_trk, b_only_trk, trk_id_col, trk_name_col, name_a, name_b, "🎵")

    st.markdown('<div class="fm-section"><div class="fm-section-title">💿 Shared Obsessions — Albums</div></div>', unsafe_allow_html=True)
    shared_alb, a_only_alb, b_only_alb, alb_id_col, alb_name_col = shared_and_collision(data_a, data_b, "albums")
    _render_shared_block(shared_alb, a_only_alb, b_only_alb, alb_id_col, alb_name_col, name_a, name_b, "💿")

    # ── Section 6: Timeline Comparison ──────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">📈 Listening Timeline</div></div>', unsafe_allow_html=True)
    st.plotly_chart(_trend_compare_figure(data_a["trend"], data_b["trend"], name_a, name_b, C),
                     use_container_width=True, config={"displayModeBar": False})

    # ── Section 7: Daily Rhythm ─────────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">🕐 Daily Rhythm</div></div>', unsafe_allow_html=True)
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(f'<div style="color:{C["TEXT_MID"]};font-size:0.85rem;margin-bottom:6px;">Hour of day</div>', unsafe_allow_html=True)
        hour_labels = [f"{h:02d}:00" for h in range(24)]
        st.plotly_chart(_rhythm_bar_figure(data_a["hour_vec"], data_b["hour_vec"], hour_labels, name_a, name_b, C),
                         use_container_width=True, config={"displayModeBar": False})
    with rc2:
        st.markdown(f'<div style="color:{C["TEXT_MID"]};font-size:0.85rem;margin-bottom:6px;">Day of week</div>', unsafe_allow_html=True)
        dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        st.plotly_chart(_rhythm_bar_figure(data_a["day_vec"], data_b["day_vec"], dow_labels, name_a, name_b, C),
                         use_container_width=True, config={"displayModeBar": False})

    fav_hour_a = int(np.argmax(data_a["hour_vec"])) if data_a["hour_vec"].sum() else None
    fav_hour_b = int(np.argmax(data_b["hour_vec"])) if data_b["hour_vec"].sum() else None
    fav_day_a = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(np.argmax(data_a["day_vec"]))] if data_a["day_vec"].sum() else "—"
    fav_day_b = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(np.argmax(data_b["day_vec"]))] if data_b["day_vec"].sum() else "—"
    st.markdown(f"""
    <div style="display:flex;gap:24px;margin-top:6px;flex-wrap:wrap;color:{C['TEXT_MID']};font-size:0.85rem;">
        <div>🎧 <b style="color:{C['GREEN']}">{escape(name_a)}</b> peaks at
            <b style="color:{C['TEXT']}">{f'{fav_hour_a:02d}:00' if fav_hour_a is not None else '—'}</b>
            on <b style="color:{C['TEXT']}">{escape(fav_day_a)}</b></div>
        <div>🎧 <b style="color:{ACCENT}">{escape(name_b)}</b> peaks at
            <b style="color:{C['TEXT']}">{f'{fav_hour_b:02d}:00' if fav_hour_b is not None else '—'}</b>
            on <b style="color:{C['TEXT']}">{escape(fav_day_b)}</b></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Section 8: Venn Diagram ──────────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">🎨 Taste Venn Diagram (Artists)</div></div>', unsafe_allow_html=True)
    full_a = set(data_a["artists"]["artist_id"]) if not data_a["artists"].empty else set()
    full_b = set(data_b["artists"]["artist_id"]) if not data_b["artists"].empty else set()
    shared_n = len(full_a & full_b)
    a_only_n = len(full_a - full_b)
    b_only_n = len(full_b - full_a)
    st.plotly_chart(_venn_figure(shared_n, a_only_n, b_only_n, name_a, name_b, C),
                     use_container_width=True, config={"displayModeBar": False})

    # ── Section 9: Steal Their Taste ────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">🕵️ If You Stole Their Taste</div></div>', unsafe_allow_html=True)
    reco_for_a = build_recommendations(b_only_art, art_id_col, art_name_col)
    reco_for_b = build_recommendations(a_only_art, art_id_col, art_name_col)
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        st.markdown(f'<div style="color:{C["TEXT_MID"]};font-size:0.9rem;margin-bottom:8px;">'
                     f'Based on the overlap, <b style="color:{C["TEXT"]}">{escape(name_a)}</b> would probably enjoy:</div>',
                     unsafe_allow_html=True)
        if reco_for_a:
            for r in reco_for_a:
                st.markdown(f'<div style="color:{C["TEXT"]};padding:4px 0;">🎧 {escape(r)}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="fm-empty">Already covers everything {}\'s into!</div>'.format(escape(name_b)), unsafe_allow_html=True)
    with rcol2:
        st.markdown(f'<div style="color:{C["TEXT_MID"]};font-size:0.9rem;margin-bottom:8px;">'
                     f'Based on the overlap, <b style="color:{C["TEXT"]}">{escape(name_b)}</b> would probably enjoy:</div>',
                     unsafe_allow_html=True)
        if reco_for_b:
            for r in reco_for_b:
                st.markdown(f'<div style="color:{C["TEXT"]};padding:4px 0;">🎧 {escape(r)}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="fm-empty">Already covers everything {}\'s into!</div>'.format(escape(name_a)), unsafe_allow_html=True)

    # ── Section 10: Share Card ──────────────────────────────────────────
    st.markdown('<div class="fm-section"><div class="fm-section-title">📸 Share Card</div></div>', unsafe_allow_html=True)
    top_shared_artist = shared_art.iloc[0][art_name_col] if not shared_art.empty else "None yet"
    top_shared_track = shared_trk.iloc[0][trk_name_col] if not shared_trk.empty else "None yet"
    _render_share_card(name_a, name_b, compat, top_shared_artist, top_shared_track, C)