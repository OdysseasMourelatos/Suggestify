from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import text
from html import escape
from types import SimpleNamespace
from urllib.parse import quote
import uuid
import math

from ui import render_kpi_grid, get_rank_class, render_list_v2, build_filtered_href, build_base_qs

# -- Rating scale --
RATING_MAX: float = 10.0          # 10-star scale
RATING_STEP_SONG: float = 0.5     # songs: half-star precision (e.g. 9.5)
RATING_STEP_ALBUM: float = 0.1    # albums: fine decimal precision (e.g. 9.9)
RATING_STEP: float = RATING_STEP_SONG  # kept for distribution-chart bucketing

STAR = "★"

MIN_N_FOR_SKEW = 3
MIN_N_FOR_TREND_WINDOW = 3

def init_ratings_module(get_engine, run_query, run_rating_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER, build_href_fn=None):
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
        if ok: run_rating_query.clear()
        return ok

    def set_album_rating(user_id: int, album_id, rating: float) -> bool:
        ok = _execute(_DELETE_ALBUM, {"user_id": user_id, "album_id": album_id}) if rating <= 0 \
            else _execute(_UPSERT_ALBUM, {"user_id": user_id, "album_id": album_id, "rating": rating})
        if ok: run_rating_query.clear()
        return ok

    # === Ο ΑΠΟΛΥΤΟΣ ΑΛΓΟΡΙΘΜΟΣ ΤΑΞΙΝΟΜΗΣΗΣ (FOOLPROOF ΔΙΑΧΕΙΡΙΣΗ ΧΡΟΝΟΥ) ===
    def move_item(user_id: int, item_type: str, item_id: str, action: str) -> bool:
        import datetime
        df = _all_rated_songs(user_id) if item_type == "song" else _all_rated_albums(user_id)
        if df.empty: return False

        id_col = f"{item_type}_id"
        table = "song_ratings" if item_type == "song" else "album_ratings"

        current_idx_list = df.index[df[id_col].astype(str) == str(item_id)].tolist()
        if not current_idx_list: return False
        
        my_rating = float(df.iloc[current_idx_list[0]]['rating'])
        
        # Απομονώνουμε ΜΟΝΟ τα items που έχουν την ίδια βαθμολογία (το ίδιο Tier)
        df_tier = df[df['rating'] == my_rating].reset_index(drop=True)
        if len(df_tier) <= 1: return True
        
        tier_idx = df_tier.index[df_tier[id_col].astype(str) == str(item_id)].tolist()[0]
        
        with get_engine().begin() as conn:
            if action == "top":
                if tier_idx == 0: return True
                # Το βάζει στην κορυφή
                sql = f"UPDATE {table} SET updated_at = now() WHERE user_id = :uid AND {id_col} = :me_id"
                conn.execute(text(sql), {"uid": user_id, "me_id": item_id})
                
            elif action in ["up", "down"]:
                if action == "up":
                    if tier_idx == 0: return True
                    target_id = str(df_tier.iloc[tier_idx - 1][id_col])
                else:
                    if tier_idx == len(df_tier) - 1: return True
                    target_id = str(df_tier.iloc[tier_idx + 1][id_col])
                    
                # Παίρνουμε τα native datetime objects κατευθείαν από τη βάση (μηδενικό timezone bug)
                sql_get = f"SELECT {id_col}, updated_at FROM {table} WHERE user_id = :uid AND {id_col} IN (:id1, :id2)"
                res = conn.execute(text(sql_get), {"uid": user_id, "id1": item_id, "id2": target_id}).fetchall()
                
                if len(res) == 2:
                    ts_map = {str(r[0]): r[1] for r in res}
                    ts_me = ts_map[str(item_id)]
                    ts_target = ts_map[str(target_id)]
                    
                    if action == "up":
                        # Το επιλεγμένο μας item παίρνει τον χρόνο του Target + 1 millisecond
                        new_me = ts_target + datetime.timedelta(milliseconds=1)
                        # To Target παίρνει τον παλιό χρόνο του Me - 1 millisecond
                        new_target = ts_me - datetime.timedelta(milliseconds=1)
                    else:
                        # Το επιλεγμένο μας item παίρνει τον χρόνο του Target - 1 millisecond
                        new_me = ts_target - datetime.timedelta(milliseconds=1)
                        # To Target παίρνει τον παλιό χρόνο του Me + 1 millisecond
                        new_target = ts_me + datetime.timedelta(milliseconds=1)

                    sql_upd = f"UPDATE {table} SET updated_at = :ts WHERE user_id = :uid AND {id_col} = :sid"
                    conn.execute(text(sql_upd), {"uid": user_id, "sid": item_id, "ts": new_me})
                    conn.execute(text(sql_upd), {"uid": user_id, "sid": target_id, "ts": new_target})

        run_rating_query.clear()
        return True

    def get_song_rating(user_id: int, song_id) -> float:
        df = run_rating_query(_GET_SONG, {"user_id": user_id, "song_id": song_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def get_album_rating(user_id: int, album_id) -> float:
        df = run_rating_query(_GET_ALBUM, {"user_id": user_id, "album_id": album_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def _getter(item_type): return get_song_rating if item_type == "song" else get_album_rating
    def _setter(item_type): return set_song_rating if item_type == "song" else set_album_rating
    def _step(item_type) -> float: return RATING_STEP_SONG if item_type == "song" else RATING_STEP_ALBUM

    def _current(item_type: str, item_id, user_id: int) -> float:
        state_key = f"rating_val_{item_type}_{item_id}_{user_id}"
        if state_key not in st.session_state:
            st.session_state[state_key] = _getter(item_type)(user_id, item_id)
        return st.session_state[state_key]

    _GET_SONG_BULK = "SELECT song_id AS item_id, rating FROM song_ratings WHERE user_id = :user_id AND song_id = ANY(:ids);"
    _GET_ALBUM_BULK = "SELECT album_id AS item_id, rating FROM album_ratings WHERE user_id = :user_id AND album_id = ANY(:ids);"

    def preload_ratings(user_id: int, item_type: str, item_ids: list) -> None:
        assert item_type in ("song", "album")
        ids = [i for i in dict.fromkeys(item_ids) if i is not None]
        missing = [i for i in ids if f"rating_val_{item_type}_{i}_{user_id}" not in st.session_state]
        if not missing:
            return
        sql = _GET_SONG_BULK if item_type == "song" else _GET_ALBUM_BULK
        df = run_rating_query(sql, {"user_id": user_id, "ids": missing})
        found = dict(zip(df["item_id"], df["rating"])) if not df.empty else {}
        for i in missing:
            st.session_state[f"rating_val_{item_type}_{i}_{user_id}"] = float(found.get(i, 0.0))
            
    # ==============================================================
    # STATIC STAR BAR (For Chips, Hall of Fame rows, and the live preview)
    # ==============================================================
    _STAR_PATH = "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"

    _STAR_SVG_DATAURI = (
        "data:image/svg+xml," + quote(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path d="{_STAR_PATH}"/></svg>'
        )
    )

    def _seed_ratings_from_df(item_type: str, df: pd.DataFrame, id_col: str, user_id: int) -> None:
        if df.empty or "rating" not in df.columns:
            return
        for _, r in df[[id_col, "rating"]].drop_duplicates(subset=[id_col]).iterrows():
            key = f"rating_val_{item_type}_{r[id_col]}_{user_id}"
            if key not in st.session_state:
                st.session_state[key] = float(r["rating"])
            
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
    # PURE HTML QUICK-RATE
    # ==============================================================
    def compact_star_html(item_type: str, item_id, user_id: int, scale: int = 10, key_prefix: str = "") -> str:
        assert item_type in ("song", "album")
        current = float(_current(item_type, item_id, user_id))
        base_qs = build_base_qs()

        cells = []
        for i in range(1, 11):
            fill_pct = max(0.0, min(1.0, current - (i - 1))) * 100
            
            # Clear rating if user clicks the star that represents their current ceiling.
            target_val = 0 if math.ceil(current) == i else i
            href = f"{base_qs}&rate_type={item_type}&rate_id={item_id}&rate_val={target_val}"
            
            cells.append(
                f'<a href="{href}" target="_self" class="star-cell" '
                f'style="--fill:{fill_pct:.0f}%" title="{i}/10"></a>'
            )
        return f'<div class="crate-stars">{"".join(cells)}</div>'
    
    _qr_R = SimpleNamespace(
        compact_star_html=compact_star_html,
        move_item=move_item
    )

    # ==============================================================
    # FULL DETAIL-PAGE WIDGET (FRAGMENT)
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
    # FANCY SEGMENTED TOGGLE
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
        if kind == "song":
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (sr.song_id) sr.rating
                    FROM song_ratings sr
                    JOIN songs s ON s.id = sr.song_id
                    WHERE sr.user_id = :user_id
                    ORDER BY sr.song_id
                )
                SELECT ROUND(rating * 2) / 2.0 AS rating, COUNT(*) AS n 
                FROM unique_ratings
                GROUP BY 1 ORDER BY 1;
            """
        else:
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (ar.album_id) ar.rating
                    FROM album_ratings ar
                    JOIN albums a ON a.id = ar.album_id
                    WHERE ar.user_id = :user_id
                    ORDER BY ar.album_id
                )
                SELECT ROUND(rating * 2) / 2.0 AS rating, COUNT(*) AS n 
                FROM unique_ratings
                GROUP BY 1 ORDER BY 1;
            """
        df = run_rating_query(sql, {"user_id": user_id})
        buckets = [round(i * RATING_STEP, 1) for i in range(1, int(RATING_MAX / RATING_STEP) + 1)]
        full = pd.DataFrame({"rating": buckets})
        return full.merge(df, on="rating", how="left").fillna(0)
    
    def _rating_stats(user_id: int, kind: str) -> dict:
        if kind == "song":
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (sr.song_id) sr.rating, sr.updated_at
                    FROM song_ratings sr
                    JOIN songs s ON s.id = sr.song_id
                    WHERE sr.user_id = :user_id
                    ORDER BY sr.song_id
                )
                SELECT rating, updated_at FROM unique_ratings;
            """
        else:
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (ar.album_id) ar.rating, ar.updated_at
                    FROM album_ratings ar
                    JOIN albums a ON a.id = ar.album_id
                    WHERE ar.user_id = :user_id
                    ORDER BY ar.album_id
                )
                SELECT rating, updated_at FROM unique_ratings;
            """
        df = run_rating_query(sql, {"user_id": user_id})

        empty = {
            "total": 0, "avg": 0.0, "median": 0.0, "std": 0.0, "skew": 0.0,
            "perfect": 0, "this_month": 0, "mean_median_div": 0.0,
            "trend_delta": None, "recent_avg": None, "prior_avg": None,
            "consistency": 0.0,
        }

        ratings = pd.to_numeric(df["rating"], errors="coerce").dropna()
        total = int(len(ratings))
        if total == 0:
            return empty

        updated = pd.to_datetime(df["updated_at"], errors="coerce", utc=True)

        avg = float(ratings.mean())
        median = float(ratings.median())
        std = float(ratings.std(ddof=1)) if total > 1 else 0.0
        skew = float(ratings.skew()) if total > MIN_N_FOR_SKEW else 0.0
        perfect = int((ratings >= RATING_MAX).sum())

        now = pd.Timestamp.now(tz="UTC")
        this_month = int(((updated.dt.year == now.year) & (updated.dt.month == now.month)).sum())

        recent_mask = updated >= (now - pd.Timedelta(days=30))
        prior_mask = (updated < (now - pd.Timedelta(days=30))) & (updated >= (now - pd.Timedelta(days=60)))
        recent_n, prior_n = int(recent_mask.sum()), int(prior_mask.sum())
        recent_avg = float(ratings[recent_mask].mean()) if recent_n >= MIN_N_FOR_TREND_WINDOW else None
        prior_avg = float(ratings[prior_mask].mean()) if prior_n >= MIN_N_FOR_TREND_WINDOW else None
        trend_delta = (recent_avg - prior_avg) if (recent_avg is not None and prior_avg is not None) else None

        max_plausible_std = RATING_MAX / 2
        consistency = max(0.0, min(100.0, (1 - (std / max_plausible_std)) * 100)) if max_plausible_std else 0.0

        return {
            "total": total, "avg": avg, "median": median, "std": std, "skew": skew,
            "perfect": perfect, "this_month": this_month,
            "mean_median_div": avg - median,
            "trend_delta": trend_delta, "recent_avg": recent_avg, "prior_avg": prior_avg,
            "consistency": consistency,
        }

    def _rating_trend_over_time(user_id: int, kind: str) -> pd.DataFrame:
        if kind == "song":
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (sr.song_id) sr.rating, sr.updated_at
                    FROM song_ratings sr
                    JOIN songs s ON s.id = sr.song_id
                    WHERE sr.user_id = :user_id
                    ORDER BY sr.song_id
                )
                SELECT DATE_TRUNC('month', updated_at) AS period,
                       AVG(rating) AS avg_rating, COUNT(*) AS n
                FROM unique_ratings
                GROUP BY 1 ORDER BY 1;
            """
        else:
            sql = """
                WITH unique_ratings AS (
                    SELECT DISTINCT ON (ar.album_id) ar.rating, ar.updated_at
                    FROM album_ratings ar
                    JOIN albums a ON a.id = ar.album_id
                    WHERE ar.user_id = :user_id
                    ORDER BY ar.album_id
                )
                SELECT DATE_TRUNC('month', updated_at) AS period,
                       AVG(rating) AS avg_rating, COUNT(*) AS n
                FROM unique_ratings
                GROUP BY 1 ORDER BY 1;
            """
        return run_rating_query(sql, {"user_id": user_id})

    def _hall_of_fame_songs(user_id: int, limit: int = 10) -> pd.DataFrame:
        return run_rating_query("""
            SELECT * FROM (
                SELECT DISTINCT ON (so.id)
                    so.id AS song_id, so.title AS song_title,
                    COALESCE(a.name, 'Unknown') AS main_artist,
                    so.image_url, sr.rating, sr.updated_at
                FROM song_ratings sr
                JOIN songs so ON so.id = sr.song_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE sr.user_id = :user_id
                ORDER BY so.id, sa.is_feature ASC NULLS LAST
            ) sub
            ORDER BY rating DESC, updated_at DESC
            LIMIT :limit;
        """, {"user_id": user_id, "limit": limit}).reset_index(drop=True)

    def _hall_of_fame_albums(user_id: int, limit: int = 10) -> pd.DataFrame:
        return run_rating_query("""
            SELECT * FROM (
                SELECT DISTINCT ON (al.id)
                    al.id AS album_id, al.title AS album_title,
                    (SELECT MAX(so2.image_url) FROM songs so2 WHERE so2.album_id = al.id) AS image_url,
                    ar.rating, ar.updated_at
                FROM album_ratings ar
                JOIN albums al ON al.id = ar.album_id
                WHERE ar.user_id = :user_id
                ORDER BY al.id
            ) sub
            ORDER BY rating DESC, updated_at DESC
            LIMIT :limit;
        """, {"user_id": user_id, "limit": limit}).reset_index(drop=True)

    def _all_rated_songs(user_id: int, search: str = None) -> pd.DataFrame:
        """Every rated song, unpaginated — backs the 'See Full Ranking' page."""
        sql = """
            SELECT DISTINCT ON (so.id)
                   so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist,
                   so.image_url, sr.rating, sr.updated_at
            FROM song_ratings sr
            JOIN songs so ON so.id = sr.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE sr.user_id = :user_id
        """
        params = {"user_id": user_id}
        if search:
            sql += " AND (so.title ILIKE :search OR a.name ILIKE :search)"
            params["search"] = f"%{search}%"
        sql += " ORDER BY so.id, sa.is_feature ASC NULLS LAST"
        df = run_rating_query(sql, params)
        if df.empty:
            return df
        return df.sort_values(["rating", "updated_at"], ascending=[False, False]).reset_index(drop=True)

    def _all_rated_albums(user_id: int, search: str = None) -> pd.DataFrame:
        """Every rated album, unpaginated — backs the 'See Full Ranking' page."""
        sql = """
            SELECT DISTINCT ON (al.id)
                   al.id AS album_id, al.title AS album_title,
                   (SELECT MAX(so2.image_url) FROM songs so2 WHERE so2.album_id = al.id) AS image_url,
                   ar.rating, ar.updated_at
            FROM album_ratings ar
            JOIN albums al ON al.id = ar.album_id
            WHERE ar.user_id = :user_id
        """
        params = {"user_id": user_id}
        if search:
            sql += " AND al.title ILIKE :search"
            params["search"] = f"%{search}%"
        sql += " ORDER BY al.id"
        df = run_rating_query(sql, params)
        if df.empty:
            return df
        return df.sort_values(["rating", "updated_at"], ascending=[False, False]).reset_index(drop=True)

    def _cross_analysis_songs(user_id: int, F: dict) -> pd.DataFrame:
        return run_rating_query("""
            WITH stream_counts AS (
                SELECT song_id, COUNT(*) AS streams
                FROM streams
                WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
                GROUP BY song_id
            )
            SELECT DISTINCT ON (so.id)
                   so.id AS song_id, so.title AS song_title,
                   COALESCE(a.name, 'Unknown') AS main_artist, so.image_url,
                   sr.rating, COALESCE(sc.streams, 0) AS streams
            FROM song_ratings sr
            JOIN songs so ON so.id = sr.song_id
            LEFT JOIN stream_counts sc ON sc.song_id = so.id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists a ON a.id = sa.artist_id
            WHERE sr.user_id = :user_id
            ORDER BY so.id, sa.is_feature ASC NULLS LAST
        """, {**F, "user_id": user_id})

    def _engagement_metrics(df: pd.DataFrame) -> dict:
        if df.empty or len(df) < 3:
            return {"corr": None, "efficiency_top": pd.DataFrame()}

        d = df.copy()
        corr = float(d["rating"].corr(d["streams"])) if d["streams"].std() > 0 else None
        d["efficiency"] = d["rating"] / np.log1p(d["streams"])
        efficiency_top = d[d["streams"] > 0].sort_values("efficiency", ascending=False).head(5)
        return {"corr": corr, "efficiency_top": efficiency_top}

    # ==============================================================
    # CHARTS
    # ==============================================================
    def _chart_distribution(df: pd.DataFrame, mean_val: float = None, median_val: float = None) -> go.Figure:
        max_val = df["n"].max() if not df.empty else 0
        colors = [GREEN if v == max_val and v > 0 else "rgba(29,185,84,0.35)" for v in df["n"]]
        fig = go.Figure(go.Bar(
            x=df["rating"], y=df["n"], width=RATING_STEP * 0.85,
            marker_color=colors, marker_line=dict(width=0),
            hovertemplate="<b>%{x:g} ★</b><br>%{y:,.0f} ratings<extra></extra>",
        ))
        if mean_val:
            fig.add_vline(x=mean_val, line_dash="dash", line_color="#FFD54F",
                          annotation_text=f"Mean {mean_val:.2f}", annotation_position="top right",
                          annotation_font_color="#FFD54F", annotation_font_size=11)
        if median_val and abs(median_val - (mean_val or 0)) > 1e-6:
            fig.add_vline(x=median_val, line_dash="dot", line_color="#4FC3F7",
                          annotation_text=f"Median {median_val:.2f}", annotation_position="bottom right",
                          annotation_font_color="#4FC3F7", annotation_font_size=11)
        return themed(fig, xaxis_title="Rating", yaxis_title="Count", bargap=0.15,
                      xaxis=dict(tickmode="linear", tick0=0, dtick=0.5, range=[0, RATING_MAX + 0.25],
                        gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)",
                        zeroline=False, fixedrange=True),
                      margin=dict(t=50, b=40, l=50, r=20))

    def _chart_rating_trend(df: pd.DataFrame) -> go.Figure:
        if df.empty or len(df) < 2:
            return themed(go.Figure())
        d = df.copy()
        d["period"] = pd.to_datetime(d["period"])
        x_numeric = np.arange(len(d))

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=d["period"], y=d["avg_rating"], mode="lines+markers", name="Monthly Avg",
            line=dict(color=GREEN, width=3, shape="spline"),
            marker=dict(size=7, color=GREEN, line=dict(width=2, color=BG)),
            fill="tozeroy", fillcolor="rgba(29,185,84,0.08)",
            customdata=d["n"],
            hovertemplate="<b>%{x|%b %Y}</b><br>Avg %{y:.2f}★ · %{customdata} rated<extra></extra>",
        ))

        if len(d) >= 3:
            slope, intercept = np.polyfit(x_numeric, d["avg_rating"], 1)
            trend_y = intercept + slope * x_numeric
            if slope > 0.015:
                trend_label = "Trend: Inflating 📈"
            elif slope < -0.015:
                trend_label = "Trend: Deflating 📉"
            else:
                trend_label = "Trend: Stable ➡️"
            fig.add_trace(go.Scatter(
                x=d["period"], y=trend_y, mode="lines", name=trend_label,
                line=dict(color="rgba(255,255,255,0.45)", width=2, dash="dot"),
                hoverinfo="skip",
            ))

        return themed(fig, yaxis_title="Avg Rating", xaxis_title="",
                      yaxis=dict(range=[0, RATING_MAX + 0.5], gridcolor="rgba(255,255,255,0.05)",
                                 linecolor="rgba(255,255,255,0.08)", zeroline=False, fixedrange=True),
                      hovermode="x unified",
                      legend=dict(orientation="h", y=1.16, x=0.5, xanchor="center"),
                      margin=dict(t=44, b=40, l=50, r=20))

    def _chart_cross_analysis(df: pd.DataFrame, corr: float = None) -> go.Figure:
        if df.empty:
            return themed(go.Figure())
        median_streams = df["streams"].median()
        gem_cut = RATING_MAX * 0.8
        low_cut = RATING_MAX * 0.4
        hidden_gems = df[(df["rating"] >= gem_cut) & (df["streams"] <= median_streams)]
        guilty_pleasures = df[(df["rating"] <= low_cut) & (df["streams"] > median_streams)]
        rest_idx = df.index.difference(hidden_gems.index).difference(guilty_pleasures.index)
        rest = df.loc[rest_idx]

        def _labels(d):
            return d["song_title"] + " — " + d["main_artist"].fillna("Unknown")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=rest["streams"], y=rest["rating"], mode="markers", name="Other",
            marker=dict(size=9, color="rgba(255,255,255,0.25)", line=dict(width=0)),
            text=_labels(rest),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=hidden_gems["streams"], y=hidden_gems["rating"], mode="markers", name="Hidden Gems",
            marker=dict(size=12, color=GREEN, line=dict(width=1, color=BG)),
            text=_labels(hidden_gems),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=guilty_pleasures["streams"], y=guilty_pleasures["rating"], mode="markers", name="Guilty Pleasures",
            marker=dict(size=12, color="#FF7043", line=dict(width=1, color=BG)),
            text=_labels(guilty_pleasures),
            hovertemplate="<b>%{text}</b><br>%{x:,} streams · %{y}★<extra></extra>",
        ))
        fig.add_vline(x=median_streams, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        fig.add_hline(y=RATING_MAX / 2, line_dash="dot", line_color="rgba(255,255,255,0.2)")

        if corr is not None:
            fig.add_annotation(
                xref="paper", yref="paper", x=0.0, y=1.16, showarrow=False, align="left",
                text=f"Taste ↔ plays correlation: r = {corr:+.2f}",
                font=dict(color=TEXT_MID, size=11),
            )

        return themed(fig, xaxis_title="Streams", yaxis_title="Your Rating",
                      yaxis=dict(range=[0, RATING_MAX + 0.5], dtick=max(1, RATING_MAX // 5),
                                 gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)",
                                 zeroline=False, fixedrange=True),
                      legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
                      margin=dict(t=54, b=40, l=50, r=20))

    # ==============================================================
    # SMALL FORMATTING HELPERS
    # ==============================================================
    def _skew_label(skew: float) -> str:
        if skew > 0.5:
            return "Harsh Critic"
        if skew < -0.5:
            return "Generous Rater"
        return "Balanced Rater"

    def _trend_kpi(trend_delta) -> dict:
        if trend_delta is None:
            return {"value": "Not enough data"}
        if trend_delta > 0.05:
            return {"value": f"📈 +{trend_delta:.2f}"}
        if trend_delta < -0.05:
            return {"value": f"📉 {trend_delta:.2f}"}
        return {"value": f"➡️ {trend_delta:+.2f}"}

    def _fmt_rating(v) -> str:
        return f"{float(v):g}/{RATING_MAX:g}"

    def _fmt_rated_date(v) -> str:
        return pd.to_datetime(v).strftime("%b %d, %Y") if pd.notnull(v) else "—"

    # ==============================================================
    # FULL RANKED LIST PAGE ("See Full Ranking" destination)
    # ==============================================================
    def render_full_ratings_list(user_id: int, kind_key: str):
        assert kind_key in ("song", "album")
        label = "Songs" if kind_key == "song" else "Albums"

        st.markdown(
            f'<div class="section-header" style="margin-top:0;"><span class="icon">🏆</span>All Rated {label}</div>',
            unsafe_allow_html=True
        )

        col_search, col_sort, col_limit = st.columns([3, 1, 1])
        search_term = col_search.text_input(
            f"🔍 Search rated {label.lower()}...",
            placeholder=f"e.g. search a {'song or artist' if kind_key == 'song' else 'album'}...",
            label_visibility="collapsed", key=f"search_full_ratings_{kind_key}",
        )
        sort_by = col_sort.selectbox(
            "Sort", ["Highest Rated", "Recently Rated"], index=0,
            label_visibility="collapsed", key=f"sort_full_ratings_{kind_key}",
        )
        
        display_limit = col_limit.selectbox(
            "Limit", [50, 100, 200, 500], index=0,
            label_visibility="collapsed", key=f"limit_full_ratings_{kind_key}",
        )

        df = (_all_rated_songs(user_id, search_term) if kind_key == "song"
              else _all_rated_albums(user_id, search_term))

        if df.empty:
            st.markdown(
                f'<div class="empty-state"><div class="icon">📭</div>No rated {label.lower()} found</div>',
                unsafe_allow_html=True
            )
            return

        if sort_by == "Recently Rated":
            df = df.sort_values("updated_at", ascending=False).reset_index(drop=True)

        if display_limit != "All":
            df = df.head(int(display_limit))

        df = df.reset_index(drop=True)
        df["global_rank"] = df.index + 1

        qr = dict(
            quick_rate=st.session_state.get("quick_rate_mode", False),
            R=_qr_R, user_id=user_id, rating_scale=int(RATING_MAX),
        )
        
        _seed_ratings_from_df(kind_key, df, f"{kind_key}_id", user_id)
        if kind_key == "song":
            render_list_v2(
                df, "song_title", "main_artist", "rating", "updated_at",
                id_col="song_id", link_type="song", rank_col="global_rank",
                reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.05,
                stat1_label="Rating", stat1_fmt=_fmt_rating,
                stat2_label="Rated On", stat2_fmt=_fmt_rated_date,
                **qr,
            )
        else:
            df["subtitle"] = "Album"
            render_list_v2(
                df, "album_title", "subtitle", "rating", "updated_at",
                id_col="album_id", link_type="album", rank_col="global_rank",
                reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.05,
                stat1_label="Rating", stat1_fmt=_fmt_rating,
                stat2_label="Rated On", stat2_fmt=_fmt_rated_date,
                **qr,
            )

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

        # --- Headline KPIs ---
        st.markdown('<div class="section-header" style="margin-top:14px;"><span class="icon">⭐</span>Rating Overview</div>', unsafe_allow_html=True)
        render_kpi_grid([
            {"icon": "⭐", "title": "Average Rating", "raw": stats["avg"], "decimals": 2, "suffix": f" / {RATING_MAX:g}"},
            {"icon": "🎯", "title": f"{kind} Rated", "raw": stats["total"], "decimals": 0},
            {"icon": "🏆", "title": f"Perfect {RATING_MAX:g}s", "raw": stats["perfect"], "decimals": 0},
            {"icon": "🆕", "title": "Rated This Month", "raw": stats["this_month"], "decimals": 0},
        ])

        # --- Statistical deep-dive ---
        st.markdown('<div class="section-header" style="margin-top:20px;"><span class="icon">📐</span>Statistical Profile</div>', unsafe_allow_html=True)
        render_kpi_grid([
            {"icon": "📏", "title": "Median Rating", "raw": stats["median"], "decimals": 2},
            {"icon": "📊", "title": "Std. Deviation", "raw": stats["std"], "decimals": 2},
            {"icon": "🎭", "title": _skew_label(stats["skew"]), "raw": stats["skew"], "decimals": 2},
            {"icon": "🌊", "title": "30-Day Trend (vs. prior 30d)", **_trend_kpi(stats["trend_delta"])},
        ])
        st.markdown(
            f'<div style="color:{TEXT_MID}; font-size:0.8rem; margin: -6px 0 6px;">'
            f'Consistency score: <b style="color:{GREEN};">{stats["consistency"]:.0f}/100</b>'
            f'&nbsp;·&nbsp;Mean − median gap: <b>{stats["mean_median_div"]:+.2f}</b>'
            f'&nbsp;<span style="opacity:0.7;">(positive = a few low outliers pull the average down '
            f'from a mostly-high median, and vice versa)</span></div>',
            unsafe_allow_html=True
        )

        # --- Distribution chart ---
        st.markdown('<div class="section-header" style="margin-top:20px;"><span class="icon">📊</span>Rating Distribution</div>', unsafe_allow_html=True)
        dist_df = _distribution(user_id, kind_key)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(_chart_distribution(dist_df, stats["avg"], stats["median"]), use_container_width=True,
                         config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
                         key=f"chart_dist_{kind_key}")
        st.markdown('</div>', unsafe_allow_html=True)

        # --- Rating trend over time (inflation / deflation) ---
        trend_df = _rating_trend_over_time(user_id, kind_key)
        if not trend_df.empty and len(trend_df) >= 2:
            st.markdown('<div class="section-header" style="margin-top:16px;"><span class="icon">🌊</span>Rating Trend Over Time</div>', unsafe_allow_html=True)
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(_chart_rating_trend(trend_df), use_container_width=True,
                         config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
                         key=f"chart_trend_{kind_key}")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- Hall of Fame, ranked ---
        @st.fragment
        def _render_hof_fragment():
            st.markdown('<div class="section-header" style="margin-top:16px;"><span class="icon">🏆</span>Hall of Fame</div>', unsafe_allow_html=True)
            hof_df = _hall_of_fame_songs(user_id) if kind_key == "song" else _hall_of_fame_albums(user_id)
            if hof_df.empty:
                st.markdown('<div class="empty-state"><div class="icon">📭</div>Nothing rated yet</div>', unsafe_allow_html=True)
            else:
                hof_df = hof_df.copy()
                hof_df["global_rank"] = hof_df.index + 1
                qr = dict(
                    quick_rate=st.session_state.get("quick_rate_mode", False),
                    R=_qr_R, user_id=user_id, rating_scale=int(RATING_MAX),
                )
                _seed_ratings_from_df(kind_key, hof_df, f"{kind_key}_id", user_id)
                if kind_key == "song":
                    render_list_v2(
                        hof_df, "song_title", "main_artist", "rating", "updated_at",
                        id_col="song_id", link_type="song", rank_col="global_rank",
                        stat1_label="Rating", stat1_fmt=_fmt_rating,
                        stat2_label="Rated On", stat2_fmt=_fmt_rated_date, **qr,
                    )
                else:
                    hof_df["subtitle"] = "Album"
                    render_list_v2(
                        hof_df, "album_title", "subtitle", "rating", "updated_at",
                        id_col="album_id", link_type="album", rank_col="global_rank",
                        stat1_label="Rating", stat1_fmt=_fmt_rating,
                        stat2_label="Rated On", stat2_fmt=_fmt_rated_date, **qr,
                    )
            full_href = build_filtered_href("ratings_full", kind_key)
            st.markdown(
                f'<a href="{full_href}" target="_self" style="text-decoration:none;">'
                f'<div class="back-btn" style="display:inline-flex; margin-top: 6px;">'
                f'See Full Ranking ({stats["total"]:,}) →</div></a>', unsafe_allow_html=True
            )
        
        _render_hof_fragment()

        # --- Hidden Gems vs Guilty Pleasures + engagement metrics (songs only) ---
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
                metrics = _engagement_metrics(cross_df)
                st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                st.plotly_chart(_chart_cross_analysis(cross_df, metrics["corr"]), use_container_width=True,
                                 config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
                                 key=f"chart_cross_{kind_key}")                
                st.markdown('</div>', unsafe_allow_html=True)

                eff_top = metrics["efficiency_top"]
                if not eff_top.empty:
                    st.markdown(
                        '<div class="section-header" style="margin-top:14px; font-size:0.95rem;">'
                        '<span class="icon">💎</span>Highest Value-Density Tracks</div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f'<div style="color:{TEXT_MID}; font-size:0.8rem; margin-bottom:6px;">'
                        f'Rating earned per unit of exposure — the tracks giving you the most love '
                        f'for the least airplay.</div>',
                        unsafe_allow_html=True
                    )
                    eff_df = eff_top.reset_index(drop=True)
                    eff_df["global_rank"] = eff_df.index + 1
                    _seed_ratings_from_df("song", eff_df, "song_id", user_id)
                    render_list_v2(
                        eff_df, "song_title", "main_artist", "rating", "efficiency",
                        id_col="song_id", link_type="song", rank_col="global_rank",
                        stat1_label="Rating", stat1_fmt=_fmt_rating,
                        stat2_label="Value Density", stat2_fmt=lambda v: f"{float(v):.2f}",
                        quick_rate=st.session_state.get("quick_rate_mode", False),
                        R=_qr_R, user_id=user_id, rating_scale=int(RATING_MAX),
                        key_prefix="eff_"
                    )

    return SimpleNamespace(
        set_song_rating=set_song_rating,
        set_album_rating=set_album_rating,
        get_song_rating=get_song_rating,
        get_album_rating=get_album_rating,
        move_item=move_item,
        render_star_rating=render_star_rating,
        compact_star_html=compact_star_html,
        rating_chip_html=rating_chip_html,
        star_bar_html=star_bar_html,
        render_ratings_dashboard=render_ratings_dashboard,
        render_full_ratings_list=render_full_ratings_list,
        preload_ratings=preload_ratings,
    )