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

def init_ratings_module(get_engine, run_query, run_rating_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER,
                         build_href_fn=None, get_rating_cache_gen=None, bump_rating_cache_gen=None):
    CARD = CARD or "rgba(255,255,255,0.04)"
    BORDER = BORDER or "rgba(255,255,255,0.08)"

    _raw_run_rating_query = run_rating_query

    def run_rating_query(sql: str, params: dict | None = None):
        params = params or {}
        uid = params.get("user_id")
        gen = get_rating_cache_gen(uid) if (get_rating_cache_gen and uid is not None) else 0
        return _raw_run_rating_query(sql, params, cache_gen=gen)

    def _invalidate_rating_cache(user_id: int) -> None:
        if bump_rating_cache_gen:
            bump_rating_cache_gen(user_id)
            
# ==============================================================
    # SQL
    # ==============================================================
    _UPSERT_SONG = """
        INSERT INTO song_ratings (user_id, song_id, rating, sort_weight, updated_at)
        VALUES (:user_id, :song_id, :rating, EXTRACT(EPOCH FROM now()), now())
        ON CONFLICT (user_id, song_id)
        DO UPDATE SET 
            sort_weight = CASE WHEN song_ratings.rating != EXCLUDED.rating THEN EXTRACT(EPOCH FROM now()) ELSE song_ratings.sort_weight END,
            rating = EXCLUDED.rating, 
            updated_at = now();
    """
    _UPSERT_ALBUM = """
        INSERT INTO album_ratings (user_id, album_id, rating, sort_weight, updated_at)
        VALUES (:user_id, :album_id, :rating, EXTRACT(EPOCH FROM now()), now())
        ON CONFLICT (user_id, album_id)
        DO UPDATE SET 
            sort_weight = CASE WHEN album_ratings.rating != EXCLUDED.rating THEN EXTRACT(EPOCH FROM now()) ELSE album_ratings.sort_weight END,
            rating = EXCLUDED.rating, 
            updated_at = now();
    """
    _UPSERT_ARTIST = """
        INSERT INTO artist_ratings (user_id, artist_id, rating, sort_weight, updated_at)
        VALUES (:user_id, :artist_id, :rating, EXTRACT(EPOCH FROM now()), now())
        ON CONFLICT (user_id, artist_id)
        DO UPDATE SET 
            sort_weight = CASE WHEN artist_ratings.rating != EXCLUDED.rating THEN EXTRACT(EPOCH FROM now()) ELSE artist_ratings.sort_weight END,
            rating = EXCLUDED.rating, 
            updated_at = now();
    """

    _DELETE_SONG = "DELETE FROM song_ratings WHERE user_id = :user_id AND song_id = :song_id;"
    _DELETE_ALBUM = "DELETE FROM album_ratings WHERE user_id = :user_id AND album_id = :album_id;"
    _DELETE_ARTIST = "DELETE FROM artist_ratings WHERE user_id = :user_id AND artist_id = :artist_id;"

    _GET_SONG = "SELECT rating FROM song_ratings WHERE user_id = :user_id AND song_id = :song_id;"
    _GET_ALBUM = "SELECT rating FROM album_ratings WHERE user_id = :user_id AND album_id = :album_id;"
    _GET_ARTIST = "SELECT rating FROM artist_ratings WHERE user_id = :user_id AND artist_id = :artist_id;"

    _GET_SONG_REVIEW = "SELECT review FROM song_ratings WHERE user_id = :user_id AND song_id = :song_id;"
    _GET_ALBUM_REVIEW = "SELECT review FROM album_ratings WHERE user_id = :user_id AND album_id = :album_id;"
    _GET_ARTIST_REVIEW = "SELECT review FROM artist_ratings WHERE user_id = :user_id AND artist_id = :artist_id;"
    
    _SET_SONG_REVIEW = "UPDATE song_ratings SET review = :review, updated_at = now() WHERE user_id = :user_id AND song_id = :song_id;"
    _SET_ALBUM_REVIEW = "UPDATE album_ratings SET review = :review, updated_at = now() WHERE user_id = :user_id AND album_id = :album_id;"
    _SET_ARTIST_REVIEW = "UPDATE artist_ratings SET review = :review, updated_at = now() WHERE user_id = :user_id AND artist_id = :artist_id;"

    _GET_SONG_BULK = "SELECT song_id AS item_id, rating, sort_weight FROM song_ratings WHERE user_id = :user_id AND song_id = ANY(:ids);"
    _GET_ALBUM_BULK = "SELECT album_id AS item_id, rating, sort_weight FROM album_ratings WHERE user_id = :user_id AND album_id = ANY(:ids);"
    _GET_ARTIST_BULK = "SELECT artist_id AS item_id, rating, sort_weight FROM artist_ratings WHERE user_id = :user_id AND artist_id = ANY(:ids);"

    def get_song_review(user_id: int, song_id) -> str:
        df = run_rating_query(_GET_SONG_REVIEW, {"user_id": user_id, "song_id": song_id})
        return str(df.iloc[0]["review"]) if not df.empty and pd.notnull(df.iloc[0]["review"]) else ""

    def get_album_review(user_id: int, album_id) -> str:
        df = run_rating_query(_GET_ALBUM_REVIEW, {"user_id": user_id, "album_id": album_id})
        return str(df.iloc[0]["review"]) if not df.empty and pd.notnull(df.iloc[0]["review"]) else ""

    def get_artist_review(user_id: int, artist_id) -> str:
        df = run_rating_query(_GET_ARTIST_REVIEW, {"user_id": user_id, "artist_id": artist_id})
        return str(df.iloc[0]["review"]) if not df.empty and pd.notnull(df.iloc[0]["review"]) else ""

    def set_song_review(user_id: int, song_id, review: str) -> bool:
        ok = _execute(_SET_SONG_REVIEW, {"user_id": user_id, "song_id": song_id, "review": review})
        if ok: _invalidate_rating_cache(user_id)
        return ok

    def set_album_review(user_id: int, album_id, review: str) -> bool:
        ok = _execute(_SET_ALBUM_REVIEW, {"user_id": user_id, "album_id": album_id, "review": review})
        if ok: _invalidate_rating_cache(user_id)
        return ok

    def set_artist_review(user_id: int, artist_id, review: str) -> bool:
        ok = _execute(_SET_ARTIST_REVIEW, {"user_id": user_id, "artist_id": artist_id, "review": review})
        if ok: _invalidate_rating_cache(user_id)
        return ok

    # ==============================================================
    # WRITE PATH & HELPERS
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
        if ok: _invalidate_rating_cache(user_id)
        return ok

    def set_album_rating(user_id: int, album_id, rating: float) -> bool:
        ok = _execute(_DELETE_ALBUM, {"user_id": user_id, "album_id": album_id}) if rating <= 0 \
            else _execute(_UPSERT_ALBUM, {"user_id": user_id, "album_id": album_id, "rating": rating})
        if ok: _invalidate_rating_cache(user_id)
        return ok

    def set_artist_rating(user_id: int, artist_id, rating: float) -> bool:
        ok = _execute(_DELETE_ARTIST, {"user_id": user_id, "artist_id": artist_id}) if rating <= 0 \
            else _execute(_UPSERT_ARTIST, {"user_id": user_id, "artist_id": artist_id, "rating": rating})
        if ok: _invalidate_rating_cache(user_id)
        return ok

    # === Ο ΑΠΟΛΥΤΟΣ ΑΛΓΟΡΙΘΜΟΣ ΤΑΞΙΝΟΜΗΣΗΣ (PURE SQL = ΑΣΤΡΑΠΙΑΙΟΣ) ===
    def move_item(user_id: int, item_type: str, item_id: str, action: str, target_id: str = None) -> bool:
        id_col = f"{item_type}_id"
        table = "song_ratings" if item_type == "song" else ("album_ratings" if item_type == "album" else "artist_ratings")
        
        with get_engine().begin() as conn:
            if action == "swap" and target_id:
                # O(1) Ανταλλαγή βάρους!
                sql_get = f"SELECT {id_col}, sort_weight FROM {table} WHERE user_id = :uid AND {id_col} IN (:id1, :id2)"
                rows = conn.execute(text(sql_get), {"uid": user_id, "id1": item_id, "id2": target_id}).fetchall()
                if len(rows) == 2:
                    w1 = rows[0][1] if str(rows[0][0]) == item_id else rows[1][1]
                    w2 = rows[1][1] if str(rows[0][0]) == item_id else rows[0][1]

                    if w1 == w2:
                        w2 = w1 - 1.0

                    sql_upd = f"UPDATE {table} SET sort_weight = :w, updated_at = now() WHERE user_id = :uid AND {id_col} = :id"
                    conn.execute(text(sql_upd), {"w": w2, "uid": user_id, "id": item_id})
                    conn.execute(text(sql_upd), {"w": w1, "uid": user_id, "id": target_id})
                    
                    # --- Η ΛΥΣΗ ΓΙΑ ΤΟ REFRESH: Ενημερώνουμε ΤΑΥΤΟΧΡΟΝΑ τη μνήμη του Streamlit! ---
                    st.session_state[f"sort_weight_{item_type}_{item_id}_{user_id}"] = float(w2)
                    st.session_state[f"sort_weight_{item_type}_{target_id}_{user_id}"] = float(w1)
                    
            elif action == "top" and target_id:
                # Απλά παίρνει το βάρος της κορυφής και προσθέτει +1
                sql_target = f"SELECT sort_weight FROM {table} WHERE user_id = :uid AND {id_col} = :tid"
                t_row = conn.execute(text(sql_target), {"uid": user_id, "tid": target_id}).fetchone()
                if t_row:
                    new_w = float(t_row[0]) + 1.0
                    sql_upd = f"UPDATE {table} SET sort_weight = :w, updated_at = now() WHERE user_id = :uid AND {id_col} = :id"
                    conn.execute(text(sql_upd), {"w": new_w, "uid": user_id, "id": item_id})
                    
                    # --- Η ΛΥΣΗ ΓΙΑ ΤΟ REFRESH: Ενημερώνουμε ΤΑΥΤΟΧΡΟΝΑ τη μνήμη του Streamlit! ---
                    st.session_state[f"sort_weight_{item_type}_{item_id}_{user_id}"] = float(new_w)

        _invalidate_rating_cache(user_id)
        return True

    def get_song_rating(user_id: int, song_id) -> float:
        df = run_rating_query(_GET_SONG, {"user_id": user_id, "song_id": song_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def get_album_rating(user_id: int, album_id) -> float:
        df = run_rating_query(_GET_ALBUM, {"user_id": user_id, "album_id": album_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def get_artist_rating(user_id: int, artist_id) -> float:
        df = run_rating_query(_GET_ARTIST, {"user_id": user_id, "artist_id": artist_id})
        return float(df.iloc[0]["rating"]) if not df.empty else 0.0

    def _getter(item_type): 
        if item_type == "song": return get_song_rating
        elif item_type == "album": return get_album_rating
        else: return get_artist_rating

    def _setter(item_type): 
        if item_type == "song": return set_song_rating
        elif item_type == "album": return set_album_rating
        else: return set_artist_rating

    def _step(item_type) -> float: 
        return RATING_STEP_SONG if item_type == "song" else RATING_STEP_ALBUM

    def _current(item_type: str, item_id, user_id: int) -> float:
        state_key = f"rating_val_{item_type}_{item_id}_{user_id}"
        if state_key not in st.session_state:
            st.session_state[state_key] = _getter(item_type)(user_id, item_id)
        return st.session_state[state_key]

    def preload_ratings(user_id: int, item_type: str, item_ids: list) -> None:
        assert item_type in ("song", "album", "artist")
        ids = [i for i in dict.fromkeys(item_ids) if i is not None]
        missing = [i for i in ids if f"rating_val_{item_type}_{i}_{user_id}" not in st.session_state]
        if not missing: return
        
        if item_type == "song": sql = _GET_SONG_BULK
        elif item_type == "album": sql = _GET_ALBUM_BULK
        else: sql = _GET_ARTIST_BULK
            
        df = run_rating_query(sql, {"user_id": user_id, "ids": missing})
        
        found_rating = dict(zip(df["item_id"], df["rating"])) if not df.empty else {}
        found_weight = dict(zip(df["item_id"], df["sort_weight"])) if not df.empty else {}
        for i in missing:
            st.session_state[f"rating_val_{item_type}_{i}_{user_id}"] = float(found_rating.get(i, 0.0))
            st.session_state[f"sort_weight_{item_type}_{i}_{user_id}"] = float(found_weight.get(i, 0.0))
            
    # ==============================================================
    # STATIC STAR BAR
    # ==============================================================
    _STAR_PATH = "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"

    def _seed_ratings_from_df(item_type: str, df: pd.DataFrame, id_col: str, user_id: int) -> None:
        if df.empty or "rating" not in df.columns:
            return
            
        unique_df = df.drop_duplicates(subset=[id_col])
        
        # Το zip() διαβάζει απευθείας τα columns χωρίς type casting (τα int μένουν int).
        for i_id, r_val in zip(unique_df[id_col], unique_df["rating"]):
            # Για απόλυτη ασφάλεια, αν έρθει ποτέ 123.0, το καθαρίζουμε.
            clean_id = str(i_id).split('.')[0]
            key = f"rating_val_{item_type}_{clean_id}_{user_id}"
            
            if key not in st.session_state:
                st.session_state[key] = float(r_val)
            
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
            f'<div class="meta-chip rating-chip-toggle" title="Click to open Rating Mode" style="cursor: pointer !important;"><div class="meta-chip-icon">⭐</div>'
            f'<div class="meta-chip-text"><div class="meta-chip-label">Your Rating</div>'
            f'<div class="meta-chip-value" style="{color_style}">{escape(label)}</div>'
            f'<div style="margin-top:5px; width:88px;">{star_bar_html(rating, size="0.6rem", glow=False)}</div>'
            f'</div></div>'
        )

    def compact_star_html(item_type: str, item_id, user_id: int, scale: int = 10, key_prefix: str = "") -> str:
        assert item_type in ("song", "album", "artist") # <--- ΠΡΟΣΤΕΘΗΚΕ Ο ARTIST
        current = float(_current(item_type, item_id, user_id))

        cells = []
        for i in range(1, 11):
            fill_pct = max(0.0, min(1.0, current - (i - 1))) * 100
            cells.append(
                f'<div class="star-cell" style="--fill:{fill_pct:.0f}%" title="{i}/10"></div>'
            )
        return (
            f'<div class="crate-stars" data-type="{item_type}" data-id="{item_id}" '
            f'data-uid="{user_id}" data-current="{current}">{"".join(cells)}</div>'
        )
    
    _qr_R = SimpleNamespace(
        compact_star_html=compact_star_html,
        move_item=move_item
    )
    # ==============================================================
    # FULL DETAIL-PAGE WIDGET (FRAGMENT)
    # ==============================================================
    @st.fragment
    def render_star_rating(item_type: str, item_id, user_id: int, compact: bool = False):
        assert item_type in ("song", "album", "artist")
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
                
                /* Center the button pair as a compact block, matching the slider's width */
                .st-key-btnrow_{widget_key} {{
                    max-width: 460px !important;
                    margin: 10px auto 0 !important;
                }}
                .st-key-btnrow_{widget_key} div[data-testid="stHorizontalBlock"] {{
                    gap: 10px !important;
                }}
                /* ─── Action row (Clear Rating / Add Review) ─── */
                .st-key-{wrap_key} div[data-testid="stHorizontalBlock"] button[kind="secondary"] {{
                    background: rgba(255,255,255,0.03) !important;
                    border: 1px solid rgba(255,255,255,0.12) !important;
                    color: {TEXT_MID} !important;
                    font-size: 0.75rem !important;
                    font-weight: 700 !important;
                    letter-spacing: 0.01em !important;
                    padding: 0.55rem 0 !important;
                    margin-top: 10px !important;
                    border-radius: 10px !important;
                    transition: all 0.2s cubic-bezier(0.16,1,0.3,1) !important;
                    box-shadow: none !important;
                }}
                .st-key-{wrap_key} div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {{
                    transform: translateY(-1px) !important;
                }}

                /* Clear Rating — neutral at rest, true red on hover */
                .st-key-btnrow_{widget_key} .st-key-clear_{widget_key} button[kind="secondary"] {{
                    color: {TEXT_MID} !important;
                    border-color: rgba(255,255,255,0.12) !important;
                    background: rgba(255,255,255,0.03) !important;
                }}
                .st-key-btnrow_{widget_key} .st-key-clear_{widget_key} button[kind="secondary"]:hover {{
                    color: #FF5252 !important;
                    border-color: rgba(244,67,54,0.5) !important;
                    background: rgba(244,67,54,0.10) !important;
                    box-shadow: 0 4px 14px rgba(244,67,54,0.2) !important;
                    transform: translateY(-1px) !important;
                }}

                /* Add Review — green accent to mark it as the "positive" action */
                .st-key-btnrow_{widget_key} div[data-testid="stPopover"] > div > button[kind="secondary"] {{
                    color: {GREEN} !important;
                    border-color: rgba(29,185,84,0.28) !important;
                    background: rgba(29,185,84,0.05) !important;
                }}
                .st-key-btnrow_{widget_key} div[data-testid="stPopover"] > div > button[kind="secondary"]:hover {{
                    color: #fff !important;
                    border-color: {GREEN} !important;
                    background: rgba(29,185,84,0.18) !important;
                    box-shadow: 0 4px 16px rgba(29,185,84,0.28) !important;
                    transform: translateY(-1px) !important;
                }}

                /* ─── Review popover content ─── */
                div[data-testid="stPopoverBody"] {{
                    background: linear-gradient(165deg, #181818, #101010) !important;
                    border: 1px solid rgba(255,255,255,0.1) !important;
                    border-radius: 18px !important;
                    padding: 1.1rem !important;
                    min-width: 320px !important;
                    box-shadow: 0 24px 60px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.04) !important;
                }}
                .review-popover-header {{
                    display: flex; align-items: center; gap: 8px;
                    font-size: 0.7rem; font-weight: 800; text-transform: uppercase;
                    letter-spacing: 0.08em; color: {TEXT_DIM};
                    margin-bottom: 10px;
                }}
                .review-popover-header .dot {{
                    width: 6px; height: 6px; border-radius: 50%;
                    background: {GREEN}; box-shadow: 0 0 8px {GREEN};
                }}
                .st-key-txt_{widget_key} label {{ display: none !important; }}
                .st-key-txt_{widget_key} textarea {{
                    background: rgba(255,255,255,0.035) !important;
                    border: 1px solid rgba(255,255,255,0.1) !important;
                    border-radius: 12px !important;
                    color: {TEXT} !important;
                    font-size: 0.88rem !important;
                    line-height: 1.5 !important;
                    padding: 0.8rem !important;
                    transition: all 0.2s ease !important;
                }}
                .st-key-txt_{widget_key} textarea::placeholder {{ color: {TEXT_DIM} !important; }}
                .st-key-txt_{widget_key} textarea:focus {{
                    border-color: {GREEN} !important;
                    box-shadow: 0 0 0 3px rgba(29,185,84,0.12) !important;
                }}
                .st-key-save_rev_{widget_key} button {{
                    border-radius: 10px !important;
                    font-weight: 700 !important;
                    font-size: 0.85rem !important;
                    background: {GREEN} !important;
                    color: #000 !important;
                    border: none !important;
                    margin-top: 10px !important;
                    box-shadow: 0 4px 14px rgba(29,185,84,0.3) !important;
                    transition: all 0.2s ease !important;
                }}
                .st-key-save_rev_{widget_key} button:hover {{
                    transform: translateY(-1px) !important;
                    box-shadow: 0 6px 20px rgba(29,185,84,0.42) !important;
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

            # === ΕΔΩ ΜΠΑΙΝΕΙ Η ΔΙΟΡΘΩΣΗ ΚΑΙ ΤΟ ΠΛΑΙΣΙΟ ΤΟΥ REVIEW ===
            if current > 0:
                with st.container(key=f"btnrow_{widget_key}"):
                    btn_col1, btn_col2 = st.columns(2)

                    with btn_col1:
                        if st.button("✕ Clear Rating", key=f"clear_{widget_key}", use_container_width=True):
                            if _setter(item_type)(user_id, item_id, 0.0):
                                st.session_state[f"rating_val_{item_type}_{item_id}_{user_id}"] = 0.0
                                if widget_key in st.session_state:
                                    del st.session_state[widget_key]
                                st.rerun(scope="fragment")

                    with btn_col2:
                        with st.popover("📝 Add Review", use_container_width=True):
                            st.markdown(
                                '<div class="review-popover-header"><span class="dot"></span>Your Review</div>',
                                unsafe_allow_html=True
                            )
                            rev_getter = get_song_review if item_type == "song" else get_album_review
                            rev_setter = set_song_review if item_type == "song" else set_album_review

                            curr_rev = rev_getter(user_id, item_id)
                            new_rev = st.text_area(
                                "Write your thoughts...", value=curr_rev, height=120,
                                key=f"txt_{widget_key}", placeholder="What stood out to you?",
                                label_visibility="collapsed",
                            )

                            if st.button("💾 Save Review", key=f"save_rev_{widget_key}", use_container_width=True):
                                if rev_setter(user_id, item_id, new_rev):
                                    st.toast("Review saved successfully!", icon="✅")
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
    # DASHBOARD QUERIES (HYPER-OPTIMIZED WITH CTEs)
    # ==============================================================
    def _distribution(user_id: int, kind: str) -> pd.DataFrame:
        table = "song_ratings" if kind == "song" else "album_ratings"
        sql = f"""
            SELECT ROUND(rating * 2) / 2.0 AS rating, COUNT(*) AS n 
            FROM {table}
            WHERE user_id = :user_id
            GROUP BY 1 ORDER BY 1;
        """
        df = run_rating_query(sql, {"user_id": user_id})
        buckets = [round(i * RATING_STEP, 1) for i in range(1, int(RATING_MAX / RATING_STEP) + 1)]
        full = pd.DataFrame({"rating": buckets})
        return full.merge(df, on="rating", how="left").fillna(0)
    
    def _rating_stats(user_id: int, kind: str) -> dict:
        table = "song_ratings" if kind == "song" else "album_ratings"
        sql = f"SELECT rating, updated_at FROM {table} WHERE user_id = :user_id;"
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
        table = "song_ratings" if kind == "song" else "album_ratings"
        sql = f"""
            SELECT DATE_TRUNC('month', updated_at) AS period,
                   AVG(rating) AS avg_rating, COUNT(*) AS n
            FROM {table}
            WHERE user_id = :user_id
            GROUP BY 1 ORDER BY 1;
        """
        return run_rating_query(sql, {"user_id": user_id})

    # ---> FULL LIST QUERIES WITH SQL LIMIT & SORTING (ZERO OVERHEAD) <---
    def _all_rated_songs(user_id: int, search: str = None, limit: int = None, sort_by: str = "Highest Rated") -> pd.DataFrame:
        params = {"user_id": user_id}
        order_sql = "ORDER BY updated_at DESC" if sort_by == "Recently Rated" else "ORDER BY rating DESC, sort_weight DESC, updated_at DESC"
        limit_sql = "LIMIT :limit" if limit else ""
        if limit: params["limit"] = limit
        
        sql = f"""
            WITH base_ratings AS (
                SELECT song_id, rating, sort_weight, updated_at
                FROM song_ratings
                WHERE user_id = :user_id
        """
        if search:
            sql += """ 
                AND (
                    song_id IN (SELECT id FROM songs WHERE title ILIKE :search)
                    OR song_id IN (
                        SELECT sa.song_id 
                        FROM song_artists sa 
                        JOIN artists a ON a.id = sa.artist_id 
                        WHERE a.name ILIKE :search
                    )
                ) 
            """
            params["search"] = f"%{search}%"
            
        sql += f"""
                {order_sql} {limit_sql}
            ),
            TrackArtists AS (
                SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS main_artist
                FROM song_artists sa
                JOIN artists a ON a.id = sa.artist_id
                WHERE sa.song_id IN (SELECT song_id FROM base_ratings)
                GROUP BY sa.song_id
            )
            SELECT br.song_id, so.title AS song_title,
                   COALESCE(ta.main_artist, 'Unknown') AS main_artist,
                   so.image_url, br.rating, br.sort_weight, br.updated_at
            FROM base_ratings br
            JOIN songs so ON so.id = br.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = br.song_id
            {order_sql};
        """
        return run_rating_query(sql, params).reset_index(drop=True)

    def _all_rated_albums(user_id: int, search: str = None, limit: int = None, sort_by: str = "Highest Rated") -> pd.DataFrame:
        params = {"user_id": user_id}
        order_sql = "ORDER BY updated_at DESC" if sort_by == "Recently Rated" else "ORDER BY rating DESC, sort_weight DESC, updated_at DESC"
        limit_sql = "LIMIT :limit" if limit else ""
        if limit: params["limit"] = limit
        
        sql = f"""
            WITH base_ratings AS (
                SELECT album_id, rating, sort_weight, updated_at
                FROM album_ratings
                WHERE user_id = :user_id
        """
        if search:
            sql += """ 
                AND (
                    album_id IN (SELECT id FROM albums WHERE title ILIKE :search)
                    OR album_id IN (
                        SELECT so.album_id 
                        FROM songs so
                        JOIN song_artists sa ON sa.song_id = so.id
                        JOIN artists a ON a.id = sa.artist_id
                        WHERE a.name ILIKE :search AND so.album_id IS NOT NULL
                    )
                ) 
            """
            params["search"] = f"%{search}%"
            
        sql += f"""
                {order_sql} {limit_sql}
            ),
            TrueAlbumArtists AS (
                SELECT album_id, STRING_AGG(name, ', ') as artist_name
                FROM (
                    SELECT so.album_id, a.name,
                           RANK() OVER(PARTITION BY so.album_id ORDER BY COUNT(DISTINCT so.id) DESC) as rnk
                    FROM songs so
                    JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                    JOIN artists a ON a.id = sa.artist_id
                    WHERE so.album_id IN (SELECT album_id FROM base_ratings)
                    GROUP BY so.album_id, a.name
                ) ranked
                WHERE rnk = 1
                GROUP BY album_id
            )
            SELECT br.album_id, al.title AS album_title,
                   COALESCE(taa.artist_name, 'Unknown Artist') AS artist_name,
                   (SELECT MAX(so2.image_url) FROM songs so2 WHERE so2.album_id = br.album_id) AS image_url,
                   br.rating, br.sort_weight, br.updated_at
            FROM base_ratings br
            JOIN albums al ON al.id = br.album_id
            LEFT JOIN TrueAlbumArtists taa ON taa.album_id = br.album_id
            {order_sql};
        """
        return run_rating_query(sql, params).reset_index(drop=True)

    def _cross_analysis_songs(user_id: int, F: dict) -> pd.DataFrame:
        return run_rating_query("""
            WITH stream_counts AS (
                SELECT song_id, COUNT(*) AS streams
                FROM streams
                WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id
                GROUP BY song_id
            ),
            TrackArtists AS (
                SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS main_artist
                FROM song_artists sa
                JOIN artists a ON a.id = sa.artist_id
                WHERE sa.song_id IN (SELECT song_id FROM song_ratings WHERE user_id = :user_id)
                GROUP BY sa.song_id
            )
            SELECT sr.song_id, so.title AS song_title,
                   COALESCE(ta.main_artist, 'Unknown') AS main_artist,
                   so.image_url, sr.rating, COALESCE(sc.streams, 0) AS streams
            FROM song_ratings sr
            JOIN songs so ON so.id = sr.song_id
            LEFT JOIN stream_counts sc ON sc.song_id = sr.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = sr.song_id
            WHERE sr.user_id = :user_id;
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

        search_key = f"search_full_ratings_{kind_key}"
        sort_key = f"sort_full_ratings_{kind_key}"
        limit_key = f"limit_full_ratings_{kind_key}"
        qp_q, qp_sort, qp_limit = f"rf_q_{kind_key}", f"rf_sort_{kind_key}", f"rf_limit_{kind_key}"

        if search_key not in st.session_state:
            st.session_state[search_key] = st.query_params.get(qp_q, "")
        if sort_key not in st.session_state:
            v = st.query_params.get(qp_sort, "Highest Rated")
            st.session_state[sort_key] = v if v in ("Highest Rated", "Recently Rated") else "Highest Rated"
        if limit_key not in st.session_state:
            try:
                v = int(st.query_params.get(qp_limit, 50))
                st.session_state[limit_key] = v if v in (50, 100, 200, 500) else 50
            except (TypeError, ValueError):
                st.session_state[limit_key] = 50

        def _sync_full_ratings_params():
            st.query_params[qp_q] = st.session_state[search_key]
            st.query_params[qp_sort] = st.session_state[sort_key]
            st.query_params[qp_limit] = str(st.session_state[limit_key])

        col_search, col_sort, col_limit = st.columns([3, 1, 1])
        search_term = col_search.text_input(
            f"🔍 Search rated {label.lower()}...",
            placeholder=f"e.g. search a {'song or artist' if kind_key == 'song' else 'album'}...",
            label_visibility="collapsed", key=search_key,
            on_change=_sync_full_ratings_params,
        )
        sort_by = col_sort.selectbox(
            "Sort", ["Highest Rated", "Recently Rated"],
            label_visibility="collapsed", key=sort_key,
            on_change=_sync_full_ratings_params,
        )
        display_limit = col_limit.selectbox(
            "Limit", [50, 100, 200, 500],
            label_visibility="collapsed", key=limit_key,
            on_change=_sync_full_ratings_params,
        )
        
        limit_val = int(display_limit) if display_limit != "All" else None

        df = (_all_rated_songs(user_id, search_term, limit=limit_val, sort_by=sort_by) if kind_key == "song"
              else _all_rated_albums(user_id, search_term, limit=limit_val, sort_by=sort_by))

        if df.empty:
            st.markdown(
                f'<div class="empty-state"><div class="icon">📭</div>No rated {label.lower()} found</div>',
                unsafe_allow_html=True
            )
            return

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
                reveal_top_n=limit_val or 50, reveal_delay_base=0.05, reveal_delay_step=0.04, # Εδω μπηκε το Animation Limit
                stat1_label="Rating", stat1_fmt=_fmt_rating,
                stat2_label="Rated On", stat2_fmt=_fmt_rated_date,
                **qr,
            )
        else:
            render_list_v2(
                df, "album_title", "artist_name", "rating", "updated_at",
                id_col="album_id", link_type="album", rank_col="global_rank",
                reveal_top_n=limit_val or 50, reveal_delay_base=0.05, reveal_delay_step=0.04, # Εδω μπηκε το Animation Limit
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
            
            with st.spinner("Loading your top rated..."):
                hof_df = _all_rated_songs(user_id, limit=10) if kind_key == "song" else _all_rated_albums(user_id, limit=10)
            
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
                        reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.05,
                        stat1_label="Rating", stat1_fmt=_fmt_rating,
                        stat2_label="Rated On", stat2_fmt=_fmt_rated_date, **qr,
                    )
                else:
                    render_list_v2(
                        hof_df, "album_title", "artist_name", "rating", "updated_at",
                        id_col="album_id", link_type="album", rank_col="global_rank",
                        reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.05,
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
                        reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.05,
                        stat1_label="Rating", stat1_fmt=_fmt_rating,
                        stat2_label="Value Density", stat2_fmt=lambda v: f"{float(v):.2f}",
                        quick_rate=st.session_state.get("quick_rate_mode", False),
                        R=_qr_R, user_id=user_id, rating_scale=int(RATING_MAX),
                        key_prefix="eff_"
                    )

    return SimpleNamespace(
        set_song_rating=set_song_rating,
        set_album_rating=set_album_rating,
        set_artist_rating=set_artist_rating, # ΠΡΟΣΘΗΚΗ
        get_song_rating=get_song_rating,
        get_album_rating=get_album_rating,
        get_artist_rating=get_artist_rating, # ΠΡΟΣΘΗΚΗ
        move_item=move_item,
        render_star_rating=render_star_rating,
        compact_star_html=compact_star_html,
        rating_chip_html=rating_chip_html,
        star_bar_html=star_bar_html,
        render_ratings_dashboard=render_ratings_dashboard,
        render_full_ratings_list=render_full_ratings_list,
        preload_ratings=preload_ratings,
    )