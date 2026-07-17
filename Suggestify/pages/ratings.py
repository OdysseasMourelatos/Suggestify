"""
ratings.py — Song/Album rating system for Suggestify.

Plug-and-play: bind it once to your existing engine/query/theme helpers,
then use it anywhere in app.py.

    from ratings import init_ratings_module
    R = init_ratings_module(get_engine, run_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG)

    # On a song/album detail page:
    R.render_star_rating("song", detail_id, selected_user_id)

    # As its own tab:
    R.render_ratings_dashboard(selected_user_id, F)

Design notes
------------
- Tables are defined in ratings_schema.sql, FK'd to songs/albums, and are
  never touched by your Java metadata enrichers — only the app writes here.
- Writes use INSERT ... ON CONFLICT ... DO UPDATE (UPSERT), so re-running
  enrichment or re-importing a Spotify export never wipes a rating.
- render_star_rating is wrapped in @st.fragment. A star click reruns only
  that fragment's element tree, not the whole page — this is what gives
  the "instant, non-blocking" feel; the DB write itself is a single-row
  UPSERT keyed on a unique (user_id, item_id) index, so it's sub-millisecond
  on Postgres. Errors are caught and surfaced via st.toast instead of
  raising, so a flaky connection never crashes the page.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from html import escape
from types import SimpleNamespace

STAR_FULL = "★"
STAR_EMPTY = "☆"


def init_ratings_module(get_engine, run_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG):
    """Factory binding this module to the host app's engine, cached query
    runner (`run_query`, an @st.cache_data-wrapped fn), and Plotly theme
    helper (`themed`), so behavior/caching/styling stay consistent with
    the rest of the app. Returns a namespace of ready-to-call functions."""

    # ══════════════════════════════════════════════════════════
    # SQL
    # ══════════════════════════════════════════════════════════
    _UPSERT_SONG = """
        INSERT INTO song_ratings (user_id, song_id, rating, updated_at)
        VALUES (:user_id, :song_id, :rating, now())
        ON CONFLICT (user_id, song_id)
        DO UPDATE SET rating = EXCLUDED.rating, updated_at = now();
    """
    _UPSERT_ALBUM = """
        INSERT INTO album_ratings (user_id, album_id, rating, updated_at)
        VALUES (:user_id, :album_id, :rating, now())
        ON CONFLICT (user_id, album_id)
        DO UPDATE SET rating = EXCLUDED.rating, updated_at = now();
    """
    _DELETE_SONG = "DELETE FROM song_ratings WHERE user_id = :user_id AND song_id = :song_id;"
    _DELETE_ALBUM = "DELETE FROM album_ratings WHERE user_id = :user_id AND album_id = :album_id;"
    _GET_SONG = "SELECT rating FROM song_ratings WHERE user_id = :user_id AND song_id = :song_id;"
    _GET_ALBUM = "SELECT rating FROM album_ratings WHERE user_id = :user_id AND album_id = :album_id;"

    # ══════════════════════════════════════════════════════════
    # WRITE PATH — direct engine, bypasses the cached run_query
    # ══════════════════════════════════════════════════════════
    def _execute(sql: str, params: dict) -> bool:
        try:
            with get_engine().begin() as conn:
                conn.execute(text(sql), params)
            return True
        except Exception as e:
            st.toast(f"⚠️ Couldn't save rating ({e.__class__.__name__})", icon="⚠️")
            return False

    def set_song_rating(user_id: int, song_id, rating: int) -> bool:
        ok = _execute(_DELETE_SONG, {"user_id": user_id, "song_id": song_id}) if rating == 0 \
            else _execute(_UPSERT_SONG, {"user_id": user_id, "song_id": song_id, "rating": rating})
        if ok:
            run_query.clear()  # dashboard/aggregate reads should see the new value
        return ok

    def set_album_rating(user_id: int, album_id, rating: int) -> bool:
        ok = _execute(_DELETE_ALBUM, {"user_id": user_id, "album_id": album_id}) if rating == 0 \
            else _execute(_UPSERT_ALBUM, {"user_id": user_id, "album_id": album_id, "rating": rating})
        if ok:
            run_query.clear()
        return ok

    def get_song_rating(user_id: int, song_id) -> int:
        df = run_query(_GET_SONG, {"user_id": user_id, "song_id": song_id})
        return int(df.iloc[0]["rating"]) if not df.empty else 0

    def get_album_rating(user_id: int, album_id) -> int:
        df = run_query(_GET_ALBUM, {"user_id": user_id, "album_id": album_id})
        return int(df.iloc[0]["rating"]) if not df.empty else 0

    # ══════════════════════════════════════════════════════════
    # STAR WIDGET (fragment-scoped, non-blocking)
    # ══════════════════════════════════════════════════════════
    @st.fragment
    def render_star_rating(item_type: str, item_id, user_id: int, size: str = "1.35rem"):
        """5 clickable stars. Runs in its own fragment so a click reruns
        only this widget, not the whole page."""
        assert item_type in ("song", "album"), "item_type must be 'song' or 'album'"

        safe_id = str(item_id).replace(" ", "_")
        container_key = f"star_{item_type}_{safe_id}"
        state_key = f"rating_val_{item_type}_{safe_id}_{user_id}"

        if state_key not in st.session_state:
            getter = get_song_rating if item_type == "song" else get_album_rating
            st.session_state[state_key] = getter(user_id, item_id)

        current = st.session_state[state_key]

        def _on_click(n: int):
            new_val = 0 if current == n else n  # clicking the current top star clears it
            setter = set_song_rating if item_type == "song" else set_album_rating
            if setter(user_id, item_id, new_val):
                st.session_state[state_key] = new_val

        with st.container(key=container_key):
            st.markdown(f"""
            <style>
            .st-key-{container_key} div[data-testid="stHorizontalBlock"] {{ gap: 2px !important; }}
            .st-key-{container_key} button {{
                font-size: {size} !important; line-height: 1 !important;
                padding: 0 !important; min-height: unset !important; height: auto !important;
                width: auto !important; border: none !important; background: transparent !important;
                color: {GREEN} !important; box-shadow: none !important;
            }}
            .st-key-{container_key} button:hover {{ transform: scale(1.15); color: {GREEN} !important; }}
            </style>
            """, unsafe_allow_html=True)

            cols = st.columns(5, gap="small")
            for i, col in enumerate(cols, start=1):
                label = STAR_FULL if i <= current else STAR_EMPTY
                col.button(label, key=f"{container_key}_{i}", on_click=_on_click, args=(i,))

    def rating_chip_html(rating: int, count: int | None = None) -> str:
        """Small read-only star chip, styled to match the app's meta-chip
        cards — drop this into a detail page's chip row."""
        stars = STAR_FULL * rating + STAR_EMPTY * (5 - rating)
        sub = f'<div class="meta-chip-label">Your Rating</div>' if rating else '<div class="meta-chip-label">Rating</div>'
        val = f'<div class="meta-chip-value" style="color:{GREEN};">{stars}</div>' if rating else \
              f'<div class="meta-chip-value" style="color:{TEXT_DIM};">Not rated</div>'
        return (f'<div class="meta-chip"><div class="meta-chip-icon">⭐</div>'
                f'<div class="meta-chip-text">{sub}{val}</div></div>')

    # ══════════════════════════════════════════════════════════
    # DASHBOARD QUERIES
    # ══════════════════════════════════════════════════════════
    def _distribution(user_id: int, kind: str) -> pd.DataFrame:
        table = "song_ratings" if kind == "song" else "album_ratings"
        df = run_query(f"""
            SELECT rating, COUNT(*) AS n
            FROM {table}
            WHERE user_id = :user_id
            GROUP BY rating ORDER BY rating;
        """, {"user_id": user_id})
        full = pd.DataFrame({"rating": [1, 2, 3, 4, 5]})
        return full.merge(df, on="rating", how="left").fillna(0)

    def _hall_of_fame_songs(user_id: int, limit: int = 20) -> pd.DataFrame:
        return run_query("""
            SELECT DISTINCT ON (so.id)
                   so.id AS song_id, so.title AS song_title, a.name AS main_artist,
                   so.image_url, sr.rating, sr.updated_at
            FROM song_ratings sr
            JOIN songs so ON so.id = sr.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE sr.user_id = :user_id
            ORDER BY so.id, sa.is_feature ASC NULLS LAST
        """, {"user_id": user_id}).sort_values(
            ["rating", "updated_at"], ascending=[False, False]
        ).head(limit).reset_index(drop=True)

    def _hall_of_fame_albums(user_id: int, limit: int = 20) -> pd.DataFrame:
        return run_query("""
            SELECT DISTINCT ON (al.id)
                   al.id AS album_id, al.title AS album_title,
                   (SELECT MAX(so2.image_url) FROM songs so2 WHERE so2.album_id = al.id) AS image_url,
                   ar.rating, ar.updated_at
            FROM album_ratings ar
            JOIN albums al ON al.id = ar.album_id
            WHERE ar.user_id = :user_id
            ORDER BY al.id
        """, {"user_id": user_id}).sort_values(
            ["rating", "updated_at"], ascending=[False, False]
        ).head(limit).reset_index(drop=True)

    def _cross_analysis_songs(user_id: int, F: dict) -> pd.DataFrame:
        return run_query("""
            WITH stream_counts AS (
                SELECT song_id, COUNT(*) AS streams
                FROM streams
                WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
                GROUP BY song_id
            )
            SELECT DISTINCT ON (so.id)
                   so.id AS song_id, so.title AS song_title, a.name AS main_artist,
                   sr.rating, COALESCE(sc.streams, 0) AS streams
            FROM song_ratings sr
            JOIN songs so ON so.id = sr.song_id
            LEFT JOIN stream_counts sc ON sc.song_id = so.id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE sr.user_id = :user_id
            ORDER BY so.id, sa.is_feature ASC NULLS LAST
        """, {**F, "user_id": user_id})

    # ══════════════════════════════════════════════════════════
    # DASHBOARD CHARTS
    # ══════════════════════════════════════════════════════════
    def _chart_distribution(df: pd.DataFrame) -> go.Figure:
        max_val = df["n"].max() if not df.empty else 0
        colors = [GREEN if v == max_val and v > 0 else "rgba(29,185,84,0.35)" for v in df["n"]]
        fig = go.Figure(go.Bar(
            x=[STAR_FULL * int(r) for r in df["rating"]], y=df["n"],
            marker_color=colors, marker_line=dict(width=0),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} ratings<extra></extra>",
        ))
        return themed(fig, xaxis_title="", yaxis_title="Ratings", bargap=0.35,
                      margin=dict(t=20, b=40, l=50, r=20))

    def _chart_cross_analysis(df: pd.DataFrame) -> go.Figure:
        if df.empty:
            return themed(go.Figure())
        median_streams = df["streams"].median()
        hidden_gems = df[(df["rating"] >= 4) & (df["streams"] <= median_streams)]
        guilty_pleasures = df[(df["rating"] <= 2) & (df["streams"] > median_streams)]
        rest_idx = df.index.difference(hidden_gems.index).difference(guilty_pleasures.index)
        rest = df.loc[rest_idx]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=rest["streams"], y=rest["rating"], mode="markers", name="Other",
            marker=dict(size=9, color="rgba(255,255,255,0.25)", line=dict(width=0)),
            text=rest["song_title"] + " — " + rest["main_artist"].fillna("Unknown"),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=hidden_gems["streams"], y=hidden_gems["rating"], mode="markers", name="Hidden Gems",
            marker=dict(size=12, color=GREEN, line=dict(width=1, color=BG)),
            text=hidden_gems["song_title"] + " — " + hidden_gems["main_artist"].fillna("Unknown"),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=guilty_pleasures["streams"], y=guilty_pleasures["rating"], mode="markers", name="Guilty Pleasures",
            marker=dict(size=12, color="#FF7043", line=dict(width=1, color=BG)),
            text=guilty_pleasures["song_title"] + " — " + guilty_pleasures["main_artist"].fillna("Unknown"),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_vline(x=median_streams, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        fig.add_hline(y=3, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        return themed(fig, xaxis_title="Streams", yaxis_title="Your Rating",
                      yaxis=dict(range=[0.5, 5.5], dtick=1, gridcolor="rgba(255,255,255,0.05)",
                                 linecolor="rgba(255,255,255,0.08)", zeroline=False, fixedrange=True),
                      legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
                      margin=dict(t=40, b=40, l=50, r=20))

    # ══════════════════════════════════════════════════════════
    # DASHBOARD RENDER
    # ══════════════════════════════════════════════════════════
    def _render_hof_row(row: pd.Series, subtitle: str, id_col: str, link_type: str):
        stars = STAR_FULL * int(row["rating"]) + STAR_EMPTY * (5 - int(row["rating"]))
        title = escape(str(row.get("song_title") or row.get("album_title")))[:50]
        image_url = row.get("image_url")
        radius = "50%" if link_type == "artist" else "8px"
        art_html = (f'<img src="{image_url}" style="width:100%;height:100%;object-fit:cover;'
                    f'border-radius:{radius};">') if image_url and pd.notnull(image_url) and str(image_url).startswith("http") else "🎵"
        st.markdown(f'''
        <div class="list-item">
            <div class="item-art">{art_html}</div>
            <div class="item-info">
                <div class="item-title">{title}</div>
                <div class="item-subtitle">{escape(subtitle)}</div>
            </div>
            <div class="item-stats">
                <div class="stat"><div class="stat-value green" style="letter-spacing:1px;">{stars}</div></div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    def render_ratings_dashboard(user_id: int, F: dict):
        """Full 'Ratings' tab: distribution, Hall of Fame, cross-analysis."""
        kind = st.radio("Scope", ["Songs", "Albums"], horizontal=True, label_visibility="collapsed", key="ratings_scope")
        kind_key = "song" if kind == "Songs" else "album"

        # ── Distribution ──
        st.markdown('<div class="section-header"><span class="icon">⭐</span>Rating Distribution</div>', unsafe_allow_html=True)
        dist_df = _distribution(user_id, kind_key)
        total_rated = int(dist_df["n"].sum())
        if total_rated == 0:
            st.markdown(f'<div class="empty-state"><div class="icon">⭐</div>No {kind.lower()} rated yet</div>', unsafe_allow_html=True)
            return

        avg_rating = float((dist_df["rating"] * dist_df["n"]).sum() / total_rated)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(_chart_distribution(dist_df), use_container_width=True,
                             config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'''
            <div class="kpi-card" style="text-align:center; padding: 2rem;">
                <div class="kpi-title">Average Rating</div>
                <div class="kpi-value" style="font-size:2.6rem;">{avg_rating:.2f} {STAR_FULL}</div>
                <div class="stat-label" style="margin-top:6px;">{total_rated} {kind.lower()} rated</div>
            </div>
            ''', unsafe_allow_html=True)

        # ── Hall of Fame ──
        st.markdown('<div class="section-header" style="margin-top:12px;"><span class="icon">🏆</span>Hall of Fame</div>', unsafe_allow_html=True)
        hof_df = _hall_of_fame_songs(user_id) if kind_key == "song" else _hall_of_fame_albums(user_id)
        if hof_df.empty:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing rated yet</div>', unsafe_allow_html=True)
        else:
            for _, row in hof_df.iterrows():
                if kind_key == "song":
                    _render_hof_row(row, row.get("main_artist") or "Unknown", "song_id", "song")
                else:
                    _render_hof_row(row, "Album", "album_id", "album")

        # ── Cross-analysis (songs only — streams are song-level) ──
        st.markdown('<div class="section-header" style="margin-top:12px;"><span class="icon">🔎</span>Hidden Gems vs Guilty Pleasures</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="color:{TEXT_MID}; font-size:0.85rem; margin-bottom:8px;">'
                     f'Rating vs. streams in the selected date range. <b>Green</b> = high rating, low streams '
                     f'(hidden gems). <b>Orange</b> = high streams, low rating (guilty pleasures).</div>',
                     unsafe_allow_html=True)
        cross_df = _cross_analysis_songs(user_id, F)
        if cross_df.empty:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Rate some songs to see this chart</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(_chart_cross_analysis(cross_df), use_container_width=True,
                             config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
            st.markdown('</div>', unsafe_allow_html=True)

    return SimpleNamespace(
        set_song_rating=set_song_rating,
        set_album_rating=set_album_rating,
        get_song_rating=get_song_rating,
        get_album_rating=get_album_rating,
        render_star_rating=render_star_rating,
        rating_chip_html=rating_chip_html,
        render_ratings_dashboard=render_ratings_dashboard,
    )