"""
ratings.py — Song/Album rating system for Suggestify (v3).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from html import escape
from types import SimpleNamespace

# -- Rating scale --
RATING_MAX: float = 10.0    # 10-star scale
RATING_STEP: float = 0.5    # 0.5 steps (e.g., 9.5) — used on the full detail-page slider only

STAR = "★"

def init_ratings_module(get_engine, run_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG,
                         build_href_fn=None):

    # ==============================================================
    # SQL
    # ==============================================================
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

    # ==============================================================
    # WRITE PATH
    # ==============================================================
    def _execute(sql: str, params: dict) -> bool:
        try:
            with get_engine().begin() as conn:
                conn.execute(text(sql), params)
            return True
        except Exception as e:
            st.toast(f"⚠️ Couldn't save rating ({e.__class__.__name__})", icon="⚠️")
            return False

    def set_song_rating(user_id: int, song_id, rating: float) -> bool:
        ok = _execute(_DELETE_SONG, {"user_id": user_id, "song_id": song_id}) if rating <= 0 \
            else _execute(_UPSERT_SONG, {"user_id": user_id, "song_id": song_id, "rating": rating})
        if ok: run_query.clear()
        return ok

    def set_album_rating(user_id: int, album_id, rating: float) -> bool:
        ok = _execute(_DELETE_ALBUM, {"user_id": user_id, "album_id": album_id}) if rating <= 0 \
            else _execute(_UPSERT_ALBUM, {"user_id": user_id, "album_id": album_id, "rating": rating})
        if ok: run_query.clear()
        return ok

    def get_song_rating(user_id: int, song_id) -> float:
        df = run_query(_GET_SONG, {"user_id": user_id, "song_id": song_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def get_album_rating(user_id: int, album_id) -> float:
        df = run_query(_GET_ALBUM, {"user_id": user_id, "album_id": album_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def _getter(item_type): return get_song_rating if item_type == "song" else get_album_rating
    def _setter(item_type): return set_song_rating if item_type == "song" else set_album_rating

    def _current(item_type: str, item_id, user_id: int) -> float:
        state_key = f"rating_val_{item_type}_{item_id}_{user_id}"
        if state_key not in st.session_state:
            st.session_state[state_key] = _getter(item_type)(user_id, item_id)
        return st.session_state[state_key]

    STAR_SVG = 'data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22M12%2017.27L18.18%2021l-1.64-7.03L22%209.24l-7.19-.61L12%202%209.19%208.63%202%209.24l5.46%204.73L5.82%2021z%22%2F%3E%3C%2Fsvg%3E'

    # ==============================================================
    # STATIC STAR BAR (For Chips & Hall of Fame rows)
    # ==============================================================
    def star_bar_html(rating: float, max_stars: int = None, size: str = "1.6rem", glow: bool = True) -> str:
        n = max_stars or int(RATING_MAX)
        pct = max(0.0, min(100.0, (rating / RATING_MAX) * 100)) if RATING_MAX else 0
        stars = STAR * n
        glow_css = f"text-shadow: 0 0 8px {GREEN}aa, 0 0 18px {GREEN}55;" if glow and rating > 0 else ""
        return f'''
        <div style="position:relative; display:inline-block; font-size:{size}; letter-spacing:3px; line-height:1;">
            <div style="color:rgba(255,255,255,0.12);">{stars}</div>
            <div style="position:absolute; top:0; left:0; overflow:hidden; width:{pct:.2f}%;
                        white-space:nowrap; color:{GREEN}; {glow_css}">{stars}</div>
        </div>'''

    def rating_chip_html(rating: float) -> str:
        label = f"{rating:g} / {RATING_MAX:g}" if rating else "Not rated"
        color_style = f'color:{GREEN};' if rating else f'color:{TEXT_DIM};'
        return (
            f'<div class="meta-chip"><div class="meta-chip-icon">⭐</div>'
            f'<div class="meta-chip-text"><div class="meta-chip-label">Your Rating</div>'
            f'<div class="meta-chip-value" style="{color_style}">{escape(label)}</div>'
            f'<div style="margin-top:5px; width:88px;">{star_bar_html(rating, size="0.6rem", glow=False)}</div>'
            f'</div></div>'
        )

    # ==============================================================
    # COMPACT QUICK-RATE (10 clickable star buttons — fully responsive)
    # ==============================================================
    @st.fragment
    def render_compact_star_rating(item_type: str, item_id, user_id: int, scale: int = 10):
        """
        Renders 10 clickable star buttons fused to the bottom of a list card.
        Clicking star N sets the rating to N; clicking the currently-set star
        again clears the rating. Fill color is recomputed from session state
        on every click (fragment rerun), so it never needs a page refresh.
        """
        assert item_type in ("song", "album")
        current = int(round(_current(item_type, item_id, user_id)))  # whole stars for quick-rate
        wrap_key = f"crate_{item_type}_{item_id}_{user_id}"

        def _make_cb(star_n):
            def _cb():
                new_val = 0.0 if star_n == current else float(star_n)
                if _setter(item_type)(user_id, item_id, new_val):
                    st.session_state[f"rating_val_{item_type}_{item_id}_{user_id}"] = new_val
            return _cb

        with st.container(key=wrap_key):
            fill_rule = ""
            if current > 0:
                fill_rule = f"""
                .st-key-{wrap_key} div[data-testid="column"]:nth-child(-n+{current}) button {{
                    color: {GREEN} !important;
                    text-shadow: 0 0 6px {GREEN}88;
                }}
                """
            st.markdown(f"""
            <style>
            .st-key-{wrap_key} {{
                background: rgba(255,255,255,0.025) !important;
                border: 1px solid rgba(255,255,255,0.07) !important;
                border-top: none !important;
                border-radius: 0 0 14px 14px !important;
                margin-top: -0.62rem !important;
                margin-bottom: 0.6rem !important;
                padding: 3px 16px 6px 118px !important;
            }}
            .st-key-{wrap_key} div[data-testid="stHorizontalBlock"] {{
                gap: 0px !important;
            }}
            .st-key-{wrap_key} div[data-testid="column"] {{
                width: auto !important;
                min-width: 0 !important;
                flex: 0 0 auto !important;
                padding: 0 !important;
            }}
            .st-key-{wrap_key} div[data-testid="stButton"] {{
                width: auto !important;
            }}
            .st-key-{wrap_key} button {{
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                padding: 0 3px !important;
                margin: 0 !important;
                min-height: 0 !important;
                height: 22px !important;
                width: 22px !important;
                font-size: 1rem !important;
                line-height: 1 !important;
                color: rgba(255,255,255,0.16) !important;
                transition: transform 0.12s ease, color 0.12s ease !important;
            }}
            .st-key-{wrap_key} button:hover {{
                transform: scale(1.3) !important;
                color: {GREEN}bb !important;
            }}
            {fill_rule}
            </style>
            """, unsafe_allow_html=True)

            cols = st.columns(10)
            for i, col in enumerate(cols, start=1):
                with col:
                    st.button("★", key=f"{wrap_key}_star_{i}", on_click=_make_cb(i),
                              help=f"{i}/10")

    # ==============================================================
    # FULL DETAIL-PAGE WIDGET (CSS Mask Slider, unchanged — half-star precision)
    # ==============================================================
    @st.fragment
    def render_star_rating(item_type: str, item_id, user_id: int):
        assert item_type in ("song", "album")
        current = _current(item_type, item_id, user_id)
        widget_key = f"slider_{item_type}_{item_id}_{user_id}"
        wrap_key = f"ratewrap_{item_type}_{item_id}_{user_id}"

        def _on_change():
            new_val = st.session_state[widget_key]
            if _setter(item_type)(user_id, item_id, new_val):
                st.session_state[f"rating_val_{item_type}_{item_id}_{user_id}"] = new_val

        with st.container(key=wrap_key):
            st.markdown(f"""
            <style>
            .st-key-{wrap_key} {{
                background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.012));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: 24px 30px 14px;
                margin: 10px 0 6px;
            }}
            .st-key-{wrap_key} div[data-testid="stSlider"] {{
                max-width: 440px !important;
                margin: 0 auto !important; 
                padding-top: 5px !important;
            }}
            .st-key-{wrap_key} div[data-testid="stSlider"] label {{ display:none; }}
            .st-key-{wrap_key} div[data-testid="stTickBar"] {{ display:none; }}

            .st-key-{wrap_key} div[data-baseweb="slider"] > div:first-child {{
                height: 44px !important;
                border-radius: 0 !important;
                background: rgba(255,255,255,0.12) !important;
                -webkit-mask-image: url('{STAR_SVG}') !important;
                -webkit-mask-size: {100/RATING_MAX}% 100% !important;
                -webkit-mask-repeat: repeat-x !important;
                mask-image: url('{STAR_SVG}') !important;
                mask-size: {100/RATING_MAX}% 100% !important;
                mask-repeat: repeat-x !important;
            }}
            .st-key-{wrap_key} div[data-baseweb="slider"] > div:first-child > div {{
                height: 44px !important;
                border-radius: 0 !important;
                background: linear-gradient(90deg, {GREEN}cc, {GREEN}) !important;
                -webkit-mask-image: url('{STAR_SVG}') !important;
                -webkit-mask-size: {100/RATING_MAX}% 100% !important;
                -webkit-mask-repeat: repeat-x !important;
                mask-image: url('{STAR_SVG}') !important;
                mask-size: {100/RATING_MAX}% 100% !important;
                mask-repeat: repeat-x !important;
                filter: drop-shadow(0 0 8px {GREEN}88);
            }}
            .st-key-{wrap_key} div[role="slider"] {{
                opacity: 0 !important; 
                width: 44px !important;
                height: 44px !important;
                cursor: pointer !important;
            }}
            .st-key-{wrap_key} button {{
                background: transparent !important;
                border: 1px solid rgba(255,255,255,0.15) !important;
                color: {TEXT_MID} !important;
                font-size: 0.75rem !important;
                padding: 0.2rem 0 !important;
                margin: 25px auto 0 !important;
                max-width: 120px !important;
                display: block !important;
                transition: all 0.2s ease !important;
                border-radius: 999px !important;
            }}
            .st-key-{wrap_key} button:hover {{
                color: #FF7043 !important;
                border-color: #FF704355 !important;
                background: rgba(255,112,67,0.05) !important;
            }}
            </style>
            """, unsafe_allow_html=True)

            head_l, head_r = st.columns([3, 2])
            with head_l:
                st.markdown(
                    f'<div style="font-size:0.75rem; letter-spacing:0.08em; text-transform:uppercase; '
                    f'color:{TEXT_MID}; font-weight:700; margin-bottom:10px;">Drag to Rate</div>',
                    unsafe_allow_html=True,
                )
            with head_r:
                value_label = f"{current:g}" if current > 0 else "Not rated"
                st.markdown(
                    f'<div style="text-align:right; font-size:1.5rem; font-weight:800; '
                    f'color:{GREEN if current > 0 else TEXT_DIM};">{value_label}'
                    f'<span style="font-size:0.9rem; color:{TEXT_DIM}; font-weight:600;"> / {RATING_MAX:g}</span></div>',
                    unsafe_allow_html=True,
                )

            st.slider(
                "Your rating", min_value=0.0, max_value=RATING_MAX, step=RATING_STEP, value=current,
                key=widget_key, on_change=_on_change, label_visibility="collapsed",
            )

            if current > 0:
                if st.button("Clear Rating", key=f"clear_{widget_key}"):
                    if _setter(item_type)(user_id, item_id, 0.0):
                        st.session_state[f"rating_val_{item_type}_{item_id}_{user_id}"] = 0.0
                        st.session_state[widget_key] = 0.0
                        st.rerun(scope="fragment")

    # ==============================================================
    # FANCY SEGMENTED TOGGLE  (For Dashboard)
    # ==============================================================
    def _segmented_toggle(key: str, options: list, default: str = None) -> str:
        state_key = f"seg_{key}"
        if state_key not in st.session_state:
            st.session_state[state_key] = default or options[0]

        with st.container(key=f"segwrap_{key}"):
            st.markdown(f"""
            <style>
            .st-key-segwrap_{key} div[data-testid="stHorizontalBlock"] {{
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 999px; padding: 4px; gap: 4px !important;
                display: inline-flex !important; flex-wrap: nowrap !important;
                width: fit-content !important;
            }}
            .st-key-segwrap_{key} div[data-testid="column"] {{
                width: auto !important; min-width: 0 !important; flex: 0 0 auto !important;
            }}
            .st-key-segwrap_{key} div[data-testid="stButton"] {{ width: auto !important; }}
            .st-key-segwrap_{key} button {{
                border-radius: 999px !important; border: none !important;
                padding: 0.35rem 1.4rem !important; font-weight: 700 !important;
                white-space: nowrap !important; width: auto !important;
                transition: all 0.2s ease !important;
            }}
            .st-key-segwrap_{key} button[kind="secondary"] {{
                background: transparent !important; color: {TEXT_MID} !important; box-shadow: none !important;
            }}
            .st-key-segwrap_{key} button[kind="secondary"]:hover {{ color: {TEXT} !important; }}
            .st-key-segwrap_{key} button[kind="primary"] {{
                background: {GREEN} !important; color: #000 !important;
                box-shadow: 0 4px 16px rgba(29,185,84,0.35) !important;
            }}
            </style>
            """, unsafe_allow_html=True)

            cols = st.columns(len(options))
            for col, opt in zip(cols, options):
                is_active = st.session_state[state_key] == opt
                with col:
                    if st.button(opt, key=f"{state_key}_{opt}", type="primary" if is_active else "secondary"):
                        st.session_state[state_key] = opt
                        st.rerun()
        return st.session_state[state_key]


    # ==============================================================
    # DASHBOARD QUERIES & RENDER
    # ==============================================================
    def _distribution(user_id: int, kind: str) -> pd.DataFrame:
        table = "song_ratings" if kind == "song" else "album_ratings"
        df = run_query(f"""
            SELECT rating, COUNT(*) AS n FROM {table}
            WHERE user_id = :user_id GROUP BY rating ORDER BY rating;
        """, {"user_id": user_id})
        buckets = [round(i * RATING_STEP, 1) for i in range(1, int(RATING_MAX / RATING_STEP) + 1)]
        full = pd.DataFrame({"rating": buckets})
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

    def _chart_distribution(df: pd.DataFrame) -> go.Figure:
        max_val = df["n"].max() if not df.empty else 0
        colors = [GREEN if v == max_val and v > 0 else "rgba(29,185,84,0.35)" for v in df["n"]]
        fig = go.Figure(go.Bar(
            x=[f"{r:g}" for r in df["rating"]], y=df["n"],
            marker_color=colors, marker_line=dict(width=0),
            hovertemplate="<b>%{x} ★</b><br>%{y:,.0f} ratings<extra></extra>",
        ))
        return themed(fig, xaxis_title="Rating", yaxis_title="Count", bargap=0.35,
                      margin=dict(t=20, b=40, l=50, r=20))

    def _chart_cross_analysis(df: pd.DataFrame) -> go.Figure:
        if df.empty:
            return themed(go.Figure())
        median_streams = df["streams"].median()
        gem_cut = RATING_MAX * 0.8
        low_cut = RATING_MAX * 0.4
        hidden_gems = df[(df["rating"] >= gem_cut) & (df["streams"] <= median_streams)]
        guilty_pleasures = df[(df["rating"] <= low_cut) & (df["streams"] > median_streams)]
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
        fig.add_hline(y=RATING_MAX / 2, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        return themed(fig, xaxis_title="Streams", yaxis_title="Your Rating",
                      yaxis=dict(range=[0, RATING_MAX + 0.5], dtick=max(1, RATING_MAX // 5),
                                 gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)",
                                 zeroline=False, fixedrange=True),
                      legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
                      margin=dict(t=40, b=40, l=50, r=20))

    def _render_hof_row(row: pd.Series, item_type: str, user_id: int, subtitle: str):
        item_id = row["song_id"] if item_type == "song" else row["album_id"]
        title = escape(str(row.get("song_title") or row.get("album_title")))[:50]
        image_url = row.get("image_url")
        radius = "50%" if item_type == "artist" else "8px"
        art_html = (f'<img src="{image_url}" style="width:100%;height:100%;object-fit:cover;border-radius:{radius};">'
                    if image_url and pd.notnull(image_url) and str(image_url).startswith("http") else "🎵")

        row_key = f"hof_row_{item_type}_{item_id}"
        with st.container(key=row_key):
            st.markdown(f"""
            <style>
            .st-key-{row_key} {{ padding: 6px 10px; border-radius: 10px; transition: background 0.2s ease; }}
            .st-key-{row_key}:hover {{ background: rgba(255,255,255,0.03); }}
            </style>
            """, unsafe_allow_html=True)
            c_art, c_info, c_stars = st.columns([0.5, 3.5, 2.0], vertical_alignment="center")
            with c_art:
                st.markdown(f'<div style="width:40px;height:40px;border-radius:{radius};overflow:hidden;'
                            f'display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.05);">{art_html}</div>',
                            unsafe_allow_html=True)
            with c_info:
                st.markdown(f'<div style="font-weight:600;">{title}</div>'
                            f'<div style="color:{TEXT_MID}; font-size:0.8rem;">{escape(subtitle)}</div>',
                            unsafe_allow_html=True)
            with c_stars:
                st.markdown(f'<div style="text-align:right;">{star_bar_html(float(row["rating"]), size="1.2rem", glow=False)}</div>', unsafe_allow_html=True)

    def render_ratings_dashboard(user_id: int, F: dict):
        kind = _segmented_toggle("ratings_scope", ["Songs", "Albums"])
        kind_key = "song" if kind == "Songs" else "album"

        st.markdown('<div class="section-header" style="margin-top:14px;"><span class="icon">⭐</span>Rating Distribution</div>', unsafe_allow_html=True)
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
                <div class="kpi-value" style="font-size:2.4rem;">{avg_rating:.1f} / {RATING_MAX:g}</div>
                {star_bar_html(avg_rating, size="1.3rem", glow=False)}
                <div class="stat-label" style="margin-top:6px;">{total_rated} {kind.lower()} rated</div>
            </div>
            ''', unsafe_allow_html=True)

        st.markdown('<div class="section-header" style="margin-top:16px;"><span class="icon">🏆</span>Hall of Fame</div>', unsafe_allow_html=True)
        hof_df = _hall_of_fame_songs(user_id) if kind_key == "song" else _hall_of_fame_albums(user_id)
        if hof_df.empty:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing rated yet</div>', unsafe_allow_html=True)
        else:
            for _, row in hof_df.iterrows():
                subtitle = (row.get("main_artist") or "Unknown") if kind_key == "song" else "Album"
                _render_hof_row(row, kind_key, user_id, subtitle)

        if kind_key == "song":
            st.markdown('<div class="section-header" style="margin-top:16px;"><span class="icon">🔎</span>Hidden Gems vs Guilty Pleasures</div>', unsafe_allow_html=True)
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
        render_compact_star_rating=render_compact_star_rating,
        rating_chip_html=rating_chip_html,
        star_bar_html=star_bar_html,
        render_ratings_dashboard=render_ratings_dashboard,
    )