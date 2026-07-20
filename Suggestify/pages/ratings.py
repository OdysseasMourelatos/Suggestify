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
from urllib.parse import quote
import uuid

from ui import render_kpi_grid, get_rank_class

# -- Rating scale --
RATING_MAX: float = 10.0          # 10-star scale
RATING_STEP_SONG: float = 0.5     # songs: half-star precision (e.g. 9.5)
RATING_STEP_ALBUM: float = 0.1    # albums: fine decimal precision (e.g. 9.9)
RATING_STEP: float = RATING_STEP_SONG  # kept for distribution-chart bucketing

STAR = "★"

# Replace your current definition of init_ratings_module (lines 14-15) with this:
def init_ratings_module(get_engine, run_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER, build_href_fn=None):
    CARD = CARD or "rgba(255,255,255,0.04)"
    BORDER = BORDER or "rgba(255,255,255,0.08)"
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
    def _step(item_type) -> float: return RATING_STEP_SONG if item_type == "song" else RATING_STEP_ALBUM

    def _current(item_type: str, item_id, user_id: int) -> float:
        state_key = f"rating_val_{item_type}_{item_id}_{user_id}"
        if state_key not in st.session_state:
            st.session_state[state_key] = _getter(item_type)(user_id, item_id)
        return st.session_state[state_key]

    # ==============================================================
    # STATIC STAR BAR (For Chips, Hall of Fame rows, and the live preview)
    #
    # Renders real inline SVG star shapes (the same star path used
    # elsewhere in the app) instead of the Unicode "★" glyph. Text-glyph
    # stars depend on the active font actually containing that glyph and
    # on `background-clip: text` being honored — when either fails, the
    # browser falls back to a solid block, which is what produced the
    # green rectangles instead of stars. An SVG <path> has no such
    # dependency: it's drawn the same way everywhere. Each star gets its
    # own <linearGradient> with a hard color stop at that star's exact
    # fill percentage, so partial/decimal ratings render a precisely
    # proportioned partial fill.
    # ==============================================================
    _STAR_PATH = "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"

    # Same star shape, packaged as a URL-encoded SVG data-URI so it can be
    # used as a CSS mask on real <button> elements (the compact quick-rate
    # stars below). Buttons need a *clickable* star, not just a painted
    # one, so we can't reuse the gradient-<svg> trick from star_bar_html
    # (that one is inert, decorative markup). Masking a plain background
    # color onto this shape gives a crisp star that is 100% font-independent
    # (fixing the "broken glyph" look) while still letting a real <button>
    # sit underneath for the click handling.
    _STAR_SVG_DATAURI = (
        "data:image/svg+xml," + quote(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path d="{_STAR_PATH}"/></svg>'
        )
    )

    def _px(size: str) -> float:
        try:
            return float(str(size).replace("rem", "").replace("px", "").strip()) * (16 if "rem" in str(size) else 1)
        except Exception:
            return 24.0

    def star_bar_html(rating: float, max_stars: int = None, size: str = "1.6rem", glow: bool = True) -> str:
        n = max_stars or int(RATING_MAX)
        rating = max(0.0, min(RATING_MAX, rating or 0.0))
        per_star = RATING_MAX / n
        px = _px(size)
        uid = uuid.uuid4().hex[:8]
        glow_style = f"filter: drop-shadow(0 0 5px {GREEN}aa);" if glow and rating > 0 else ""

        svgs = ""
        for i in range(n):
            fill_pct = max(0.0, min(1.0, (rating - i * per_star) / per_star)) * 100
            gid = f"sg_{uid}_{i}"
            svgs += (
                f'<svg width="{px:.0f}" height="{px:.0f}" viewBox="0 0 24 24" '
                f'style="display:inline-block; vertical-align:middle; margin:0 1px;">'
                f'<defs><linearGradient id="{gid}">'
                f'<stop offset="{fill_pct:.1f}%" stop-color="{GREEN}"/>'
                f'<stop offset="{fill_pct:.1f}%" stop-color="rgba(255,255,255,0.14)"/>'
                f'</linearGradient></defs>'
                f'<path d="{_STAR_PATH}" fill="url(#{gid})"/>'
                f'</svg>'
            )

        return f'<div style="display:inline-flex; align-items:center; {glow_style}">{svgs}</div>'

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
    #
    # FIX (fill not reflecting the saved rating): the old version filled
    # stars with a single blanket rule — `:nth-child(-n+{current})` on the
    # column divs. nth-child counts a div's position among ALL of its
    # siblings, which only lines up with "the first N stars" if nothing
    # else shares that parent in exactly the order we assume. That
    # assumption is invisible and can silently stop holding, and when it
    # does, the only star that ever looks lit is the one under the mouse
    # (via the separate `:hover` rule) — which is exactly the symptom
    # reported. Fixing it properly means not depending on sibling
    # position at all: each star now sits in its OWN uniquely-keyed
    # container, and we target that key directly. That's a 1:1,
    # unambiguous mapping from "star i" to "the CSS rule for star i" —
    # it can't drift out of sync with what Streamlit actually renders.
    # ==============================================================
    @st.fragment
    def render_compact_star_rating(item_type: str, item_id, user_id: int, scale: int = 10):
        assert item_type in ("song", "album")
        current = int(round(_current(item_type, item_id, user_id)))
        wrap_key = f"crate_{item_type}_{item_id}_{user_id}"
        state_key = f"rating_val_{item_type}_{item_id}_{user_id}"

        def _make_cb(star_n):
            def _cb():
                new_val = 0.0 if star_n == current else float(star_n)
                previous = st.session_state.get(state_key, current)
                st.session_state[state_key] = new_val
                if _setter(item_type)(user_id, item_id, new_val):
                    st.toast(f"Rated {new_val:g}/10 ✓" if new_val > 0 else "Rating cleared", icon="⭐")
                else:
                    st.session_state[state_key] = previous
            return _cb

        with st.container(key=wrap_key):
            # One explicit, deterministic rule per star — filled if its
            # index is <= the saved rating, unfilled otherwise.
            cell_fill_rules = "\n".join(
                f'.st-key-{wrap_key}_cell_{i} button::before {{ '
                f'background-color: {GREEN if i <= current else "rgba(255,255,255,0.22)"} !important; }}'
                for i in range(1, 11)
            )

            st.markdown(f"""
            <style>
            /* Ανυψώνουμε το container για να φάμε το κενό του Streamlit */
            div.element-container:has(> .st-key-{wrap_key}) {{
                margin-top: -0.2rem !important;
            }}

            .st-key-{wrap_key} {{
                display: flex !important;
                align-items: center !important;
                background: #151515 !important;
                backdrop-filter: blur(10px) !important;
                -webkit-backdrop-filter: blur(10px) !important;
                border: 1px solid {BORDER} !important;
                border-top: none !important; 
                border-radius: 0 0 14px 14px !important; 
                padding: 4px 1.5rem 10px !important;
                margin: 0 !important;
                width: 100% !important;
                /* ΜΟΝΟ χρώματα στο transition, ΟΧΙ transform! */
                transition: background 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease !important;
            }}
            .st-key-{wrap_key} div[data-testid="stHorizontalBlock"] {{
                display: flex !important;
                gap: 2px !important;
                flex-wrap: nowrap !important;
                width: auto !important;
            }}
            .st-key-{wrap_key} div[data-testid="column"] {{
                width: 22px !important;
                min-width: 22px !important;
                max-width: 22px !important;
                flex: 0 0 22px !important;
                padding: 0 !important;
            }}
            .st-key-{wrap_key} div[data-testid="stButton"] {{ width: 100% !important; }}
            .st-key-{wrap_key} button {{
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                outline: none !important;
                padding: 0 !important;
                margin: 0 auto !important;
                min-height: 0 !important;
                height: 18px !important;
                width: 18px !important;
                display: block !important;
                position: relative !important;
                color: transparent !important;
                font-size: 0 !important;
                line-height: 0 !important;
                transition: transform 0.12s ease !important;
            }}
            .st-key-{wrap_key} button p {{ display: none !important; }}
            .st-key-{wrap_key} button::before {{
                content: "";
                position: absolute;
                inset: 0;
                background-color: rgba(255,255,255,0.22);
                -webkit-mask-image: url("{_STAR_SVG_DATAURI}");
                mask-image: url("{_STAR_SVG_DATAURI}");
                -webkit-mask-size: contain;
                mask-size: contain;
                -webkit-mask-repeat: no-repeat;
                mask-repeat: no-repeat;
                -webkit-mask-position: center;
                mask-position: center;
                transition: background-color 0.12s ease;
            }}
            .st-key-{wrap_key} button:hover {{ transform: scale(1.22) !important; }}
            .st-key-{wrap_key} button:hover::before {{ background-color: {GREEN}cc !important; }}
            {cell_fill_rules}

            @media (max-width: 768px) {{
                .st-key-{wrap_key} {{
                    padding: 6px 0.8rem 8px !important;
                }}
                .st-key-{wrap_key} div[data-testid="column"] {{
                    width: 16px !important;
                    min-width: 16px !important;
                    max-width: 16px !important;
                    flex: 0 0 16px !important;
                }}
                .st-key-{wrap_key} button {{
                    height: 14px !important;
                    width: 14px !important;
                }}
            }}
            </style>
            """, unsafe_allow_html=True)

            cols = st.columns(10)
            for i, col in enumerate(cols, start=1):
                with col:
                    with st.container(key=f"{wrap_key}_cell_{i}"):
                        st.button("★", key=f"{wrap_key}_star_{i}", on_click=_make_cb(i), help=f"{i}/10")

    # ==============================================================
    # FULL DETAIL-PAGE WIDGET
    # ==============================================================
    @st.fragment
    def render_star_rating(item_type: str, item_id, user_id: int, compact: bool = False):
        assert item_type in ("song", "album")
        current = _current(item_type, item_id, user_id)
        step = _step(item_type)
        widget_key = f"slider_{item_type}_{item_id}_{user_id}"
        wrap_key = f"ratewrap_{item_type}_{item_id}_{user_id}"

        def _on_change():
            raw = st.session_state[widget_key]
            new_val = round(round(raw / step) * step, 1)
            new_val = max(0.0, min(RATING_MAX, new_val))
            if _setter(item_type)(user_id, item_id, new_val):
                st.session_state[f"rating_val_{item_type}_{item_id}_{user_id}"] = new_val

        pad = "12px 20px 8px" if compact else "24px 30px 16px"
        star_size = "1.5rem" if compact else "2.3rem"
        margin = "6px 0 4px" if compact else "10px 0 6px"

        with st.container(key=wrap_key):
            st.markdown(f"""
            <style>
            .st-key-{wrap_key} {{
                background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.012));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: {pad};
                margin: 10px 0 6px;
            }}
            .st-key-{wrap_key} div[data-testid="stSlider"] {{
                max-width: 460px !important;
                margin: 4px auto 0 !important;
            }}
            .st-key-{wrap_key} div[data-testid="stSlider"] label {{ display:none; }}
            .st-key-{wrap_key} div[data-testid="stTickBar"] {{ display: none !important; }}
            .st-key-{wrap_key} button {{
                background: transparent !important;
                border: 1px solid rgba(255,255,255,0.15) !important;
                color: {TEXT_MID} !important;
                font-size: 0.75rem !important;
                padding: 0.2rem 0 !important;
                margin: {"10px" if compact else "18px"} auto 0 !important;
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
                    f'color:{TEXT_MID}; font-weight:700; margin-bottom:{"4px" if compact else "8px"};">Drag to Rate '
                    f'<span style="opacity:0.6; text-transform:none; letter-spacing:0;">'
                    f'(steps of {step:g})</span></div>',
                    unsafe_allow_html=True,
                )
            with head_r:
                value_label = f"{current:g}" if current > 0 else "Not rated"
                st.markdown(
                    f'<div style="text-align:right; font-size:{"1.15rem" if compact else "1.5rem"}; font-weight:800; '
                    f'color:{GREEN if current > 0 else TEXT_DIM};">{value_label}'
                    f'<span style="font-size:0.9rem; color:{TEXT_DIM}; font-weight:600;"> / {RATING_MAX:g}</span></div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div style="margin: {margin}; text-align:center;">'
                f'{star_bar_html(current, size=star_size, glow=True)}</div>',
                unsafe_allow_html=True,
            )

            st.slider(
                "Your rating", min_value=0.0, max_value=RATING_MAX, step=step, value=current,
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
    # DASHBOARD QUERIES
    # ==============================================================
    def _distribution(user_id: int, kind: str) -> pd.DataFrame:
        table = "song_ratings" if kind == "song" else "album_ratings"
        # Bucket to the nearest 0.5 for the chart regardless of the input
        # precision (albums can be rated to 0.1, but we still want a
        # readable ~20-bar distribution rather than 100 tiny bars).
        df = run_query(f"""
            SELECT ROUND(rating * 2) / 2.0 AS rating, COUNT(*) AS n FROM {table}
            WHERE user_id = :user_id GROUP BY 1 ORDER BY 1;
        """, {"user_id": user_id})
        buckets = [round(i * RATING_STEP, 1) for i in range(1, int(RATING_MAX / RATING_STEP) + 1)]
        full = pd.DataFrame({"rating": buckets})
        return full.merge(df, on="rating", how="left").fillna(0)

    def _rating_stats(user_id: int, kind: str) -> dict:
        """Headline KPIs for the dashboard: total rated, mean rating,
        perfect (max-score) count, and how many were rated this month."""
        table = "song_ratings" if kind == "song" else "album_ratings"
        df = run_query(f"""
            SELECT
                COUNT(*) AS total,
                AVG(rating) AS avg_rating,
                SUM(CASE WHEN rating >= :max_r THEN 1 ELSE 0 END) AS perfect,
                SUM(CASE WHEN date_trunc('month', updated_at) = date_trunc('month', now())
                         THEN 1 ELSE 0 END) AS this_month
            FROM {table}
            WHERE user_id = :user_id;
        """, {"user_id": user_id, "max_r": RATING_MAX})
        if df.empty or int(df.iloc[0]["total"] or 0) == 0:
            return {"total": 0, "avg": 0.0, "perfect": 0, "this_month": 0}
        row = df.iloc[0]
        return {
            "total": int(row["total"]),
            "avg": float(row["avg_rating"] or 0.0),
            "perfect": int(row["perfect"] or 0),
            "this_month": int(row["this_month"] or 0),
        }

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

    # ==============================================================
    # CHARTS
    # ==============================================================
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

    # ==============================================================
    # HALL OF FAME ROW (ranked, matching render_list_v2's rank badges)
    # ==============================================================
    def _render_hof_row(row: pd.Series, item_type: str, user_id: int, subtitle: str, rank: int = None):
        item_id = row["song_id"] if item_type == "song" else row["album_id"]
        title = escape(str(row.get("song_title") or row.get("album_title")))[:50]
        image_url = row.get("image_url")
        radius = "50%" if item_type == "artist" else "8px"
        art_html = (f'<img src="{image_url}" style="width:100%;height:100%;object-fit:cover;border-radius:{radius};">'
                    if image_url and pd.notnull(image_url) and str(image_url).startswith("http") else "🎵")

        rank_class = get_rank_class(rank) if rank else ""
        rank_html = f'<div class="item-rank {rank_class}">{rank}</div>' if rank else ""

        row_key = f"hof_row_{item_type}_{item_id}"
        with st.container(key=row_key):
            st.markdown(f"""
            <style>
            .st-key-{row_key} {{ padding: 6px 10px; border-radius: 10px; transition: background 0.2s ease; }}
            .st-key-{row_key}:hover {{ background: rgba(255,255,255,0.03); }}
            </style>
            """, unsafe_allow_html=True)
            c_rank, c_art, c_info, c_stars = st.columns([0.4, 0.5, 3.1, 2.0], vertical_alignment="center")
            with c_rank:
                st.markdown(rank_html, unsafe_allow_html=True)
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

    # ==============================================================
    # DASHBOARD RENDER
    # ==============================================================
    def render_ratings_dashboard(user_id: int, F: dict):
        kind = _segmented_toggle("ratings_scope", ["Songs", "Albums"])
        kind_key = "song" if kind == "Songs" else "album"

        stats = _rating_stats(user_id, kind_key)
        if stats["total"] == 0:
            st.markdown(f'<div class="empty-state"><div class="icon">⭐</div>No {kind.lower()} rated yet</div>', unsafe_allow_html=True)
            return

        # --- Headline KPIs, using the app's shared counter-animated grid ---
        st.markdown('<div class="section-header" style="margin-top:14px;"><span class="icon">⭐</span>Rating Overview</div>', unsafe_allow_html=True)
        render_kpi_grid([
            {"icon": "⭐", "title": "Average Rating", "raw": stats["avg"], "decimals": 1, "suffix": f" / {RATING_MAX:g}"},
            {"icon": "🎯", "title": f"{kind} Rated", "raw": stats["total"], "decimals": 0},
            {"icon": "🏆", "title": f"Perfect {RATING_MAX:g}s", "raw": stats["perfect"], "decimals": 0},
            {"icon": "🆕", "title": "Rated This Month", "raw": stats["this_month"], "decimals": 0},
        ])

        # --- Distribution chart ---
        st.markdown('<div class="section-header" style="margin-top:20px;"><span class="icon">📊</span>Rating Distribution</div>', unsafe_allow_html=True)
        dist_df = _distribution(user_id, kind_key)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(_chart_distribution(dist_df), use_container_width=True,
                         config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        st.markdown('</div>', unsafe_allow_html=True)

        # --- Hall of Fame, now ranked ---
        st.markdown('<div class="section-header" style="margin-top:16px;"><span class="icon">🏆</span>Hall of Fame</div>', unsafe_allow_html=True)
        hof_df = _hall_of_fame_songs(user_id) if kind_key == "song" else _hall_of_fame_albums(user_id)
        if hof_df.empty:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing rated yet</div>', unsafe_allow_html=True)
        else:
            for i, row in hof_df.iterrows():
                subtitle = (row.get("main_artist") or "Unknown") if kind_key == "song" else "Album"
                _render_hof_row(row, kind_key, user_id, subtitle, rank=i + 1)

        # --- Hidden Gems vs Guilty Pleasures (songs only) ---
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