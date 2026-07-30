from matplotlib import style
import streamlit as st
import pandas as pd
import datetime
import warnings
import os
import sys

# ─── HACK ΓΙΑ ΤΟ STREAMLIT CLOUD ───
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from html import escape
import plotly.graph_objects as go
from friends_match import render_friends_match_tab
import streamlit.components.v1 as components

warnings.filterwarnings("ignore")


from config import *
from db import (get_engine, run_query, run_rating_query, get_date_bounds, get_release_year_bounds,
                 get_rating_cache_gen, bump_rating_cache_gen)
from charts import themed, chart_trend, chart_multi_trend, chart_heatmap, chart_bar, chart_year_bar, chart_donut
from ui import (counter_span, inject_counter_script, load_css, inject_custom_css, get_rank_class, 
                get_item_icon, build_filtered_href, render_list_v2, render_kpi_grid, 
                render_detail_header, render_season_cards, render_time_of_day_cards, render_track_spotlight_card)
from share_stats import render_share_stats_button
from ratings import init_ratings_module

st.set_page_config(page_title="Suggestify", page_icon="🎧", layout="wide", initial_sidebar_state="collapsed")

load_css()
inject_counter_script()
inject_custom_css()

def inject_rating_script():
    components.html("""
    <script>
    (function() {
        const parentWin = window.parent;
        const doc = parentWin.document;
        
        if (doc.__ratingDelegated) return;
        doc.__ratingDelegated = true;

        doc.addEventListener('click', function(e) {
            // --- 1. CLICK ΣΤΑ ΑΣΤΕΡΑΚΙΑ ---
            const star = e.target.closest('.star-cell');
            if (star) {
                e.preventDefault();
                e.stopPropagation();

                const container = star.closest('.crate-stars');
                if (!container) return;

                const stars = Array.from(container.querySelectorAll('.star-cell'));
                const idx = stars.indexOf(star);
                const type = container.dataset.type;
                const id = container.dataset.id;
                const uid = container.dataset.uid;
                const current = parseFloat(container.dataset.current || '0');
                const val = (Math.ceil(current) === (idx + 1)) ? 0 : (idx + 1);

                stars.forEach(function(s, i) {
                    const fill = Math.max(0, Math.min(1, val - i)) * 100;
                    s.style.setProperty('--fill', fill + '%');
                });
                container.dataset.current = val;

                function trySubmit(retries) {
                    const input = doc.querySelector('input[aria-label="hidden_rate_input"]');
                    if (!input) {
                        if (retries > 0) setTimeout(function() { trySubmit(retries - 1); }, 60);
                        return;
                    }
                    const setter = Object.getOwnPropertyDescriptor(parentWin.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, type + ':' + id + ':' + val + ':' + uid + ':' + Date.now());
                    input.dispatchEvent(new parentWin.Event('input', { bubbles: true }));
                    input.dispatchEvent(new parentWin.Event('change', { bubbles: true }));
                    input.focus({ preventScroll: true });
                    setTimeout(function() {
                        input.dispatchEvent(new parentWin.KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.dispatchEvent(new parentWin.KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.blur();
                    }, 30);
                }
                trySubmit(5);
                return;
            }

            // --- 2. CLICK ΣΤΑ BUMP ΒΕΛΑΚΙΑ ---
            const bump = e.target.closest('.bump-link');
            if (bump) {
                e.preventDefault();
                e.stopPropagation();
                
                const bumpData = bump.dataset.bump;
                if (!bumpData) return;

                function trySubmitBump(retries) {
                    const input = doc.querySelector('input[aria-label="hidden_bump_input"]');
                    if (!input) {
                        if (retries > 0) setTimeout(function() { trySubmitBump(retries - 1); }, 60);
                        return;
                    }
                    const setter = Object.getOwnPropertyDescriptor(parentWin.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, bumpData + ':' + Date.now());
                    input.dispatchEvent(new parentWin.Event('input', { bubbles: true }));
                    input.dispatchEvent(new parentWin.Event('change', { bubbles: true }));
                    input.focus({ preventScroll: true });
                    setTimeout(function() {
                        input.dispatchEvent(new parentWin.KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.dispatchEvent(new parentWin.KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.blur();
                    }, 30);
                }
                trySubmitBump(5);
            }
            // --- 3. CLICK ΣΤΟ RATING CHIP ---
            const ratingChip = e.target.closest('.rating-chip-toggle');
            if (ratingChip) {
                e.preventDefault();
                e.stopPropagation();
                
                // Βρίσκει και κάνει κλικ στο κουμπί της κεντρικής μπάρας
                const toggleBtn = doc.querySelector('.st-key-quick_rate_toggle button');
                if (toggleBtn) {
                    toggleBtn.click();
                }
                return;
            }
        });
    })();
    </script>
    """, height=0)

inject_rating_script()

# Η μνήμη του server που "πεθαίνει" μόλις κάνεις restart το app (streamlit run app.py)
@st.cache_resource
def get_qr_global_state():
    return {"mode": False}

qr_global = get_qr_global_state()

if "quick_rate_mode" not in st.session_state:
    url_qr = st.query_params.get("qr")
    if url_qr is not None:
        st.session_state.quick_rate_mode = (url_qr == "1")
    else:
        st.session_state.quick_rate_mode = qr_global["mode"]

if st.session_state.quick_rate_mode:
    st.query_params["qr"] = "1"
else:
    st.query_params.pop("qr", None)
    
R = init_ratings_module(get_engine, run_query, run_rating_query, themed, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER,
                         get_rating_cache_gen=get_rating_cache_gen, bump_rating_cache_gen=bump_rating_cache_gen)

st.markdown("""
    <style>
    div[data-testid="stTextInput"]:has(input[aria-label="hidden_rate_input"]),
    div[data-testid="stTextInput"]:has(input[aria-label="hidden_bump_input"]) {
        position: fixed !important;
        top: -1000px !important;
        left: -1000px !important;
        width: 1px !important;
        height: 1px !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        opacity: 0.01 !important;
    }
    </style>
""", unsafe_allow_html=True)

import json
import numpy as np

def get_album_stats_html(album_id, user_id):
    # 1. Βρίσκουμε όλα τα τραγούδια του Album (Γρήγορο query, κάνει cache)
    songs_df = run_query("SELECT id FROM songs WHERE album_id = :aid", {"aid": album_id})
    if songs_df.empty:
        return ""
        
    song_ids = songs_df["id"].tolist()
    
    # 2. Φορτώνουμε τα ratings τους στη μνήμη αν δεν υπάρχουν
    R.preload_ratings(user_id, "song", song_ids)
    
    # 3. Διαβάζουμε ΠΑΝΤΑ τις "ζωντανές" τιμές από το session_state
    ratings = []
    for sid in song_ids:
        val = st.session_state.get(f"rating_val_song_{sid}_{user_id}", 0.0)
        if val > 0:
            ratings.append(val)
            
    n_rated = len(ratings)
    
    if n_rated > 0:
        arr = np.array(ratings)
        mean_val = f"{arr.mean():.2f}"
        median_val = f"{np.median(arr):.2f}"
        std_val_raw = float(np.std(arr, ddof=1)) if n_rated > 1 else 0.0
        std_val = f"± {std_val_raw:.2f}"
        
        sug_min = max(0.0, arr.mean() - std_val_raw)
        sug_max = min(10.0, arr.mean() + std_val_raw)
        suggested_str = f"{sug_min:.1f} – {sug_max:.1f}" if std_val_raw > 0 else f"{arr.mean():.1f}"
    else:
        # Αν δεν έχει βαθμολογήσει τίποτα, δείχνει παύλες
        mean_val = "—"
        median_val = "—"
        std_val = "—"
        suggested_str = "—"

    def _stat_block(icon, label, value, highlight=False):
        is_active_highlight = highlight and n_rated > 0
        cls = "album-stat-block highlight" if is_active_highlight else "album-stat-block"
        color = GREEN if is_active_highlight else (TEXT if n_rated > 0 else TEXT_DIM)
        
        return (
            f'<div class="{cls}">'
            f'<div class="album-stat-icon">{icon}</div>'
            f'<div class="album-stat-text">'
            f'<div class="album-stat-label">{label}</div>'
            f'<div class="album-stat-value" style="color:{color};">{value}</div>'
            f'</div>'
            f'</div>'
        )

    stats_css = f'''<style>
    .album-stats-bar {{
        display: flex; align-items: stretch;
        background: linear-gradient(145deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01));
        border: 1px solid {BORDER}; border-radius: 16px;
        padding: 2px; margin-bottom: 26px; position: relative; overflow: hidden;
        animation: fadeSlideUp 0.45s cubic-bezier(0.16,1,0.3,1) both;
    }}
    .album-stats-bar::before {{
        content: ''; position: absolute; top: 0; left: 8%; right: 8%; height: 2px;
        background: linear-gradient(90deg, transparent, {GREEN}, transparent); opacity: 0.55;
    }}
    .album-stat-block {{
        flex: 1; display: flex; align-items: center; justify-content: center;
        gap: 10px; padding: 15px 10px; position: relative; transition: background 0.2s ease;
    }}
    .album-stat-block:hover {{ background: rgba(255,255,255,0.02); }}
    .album-stat-block + .album-stat-block::before {{
        content: ''; position: absolute; left: 0; top: 22%; bottom: 22%; width: 1px; background: {BORDER};
    }}
    .album-stat-icon {{
        width: 30px; height: 30px; flex-shrink: 0; display: flex; align-items: center; justify-content: center;
        border-radius: 8px; background: rgba(255,255,255,0.05); font-size: 0.85rem;
    }}
    .album-stat-text {{ display: flex; flex-direction: column; gap: 2px; text-align: left; }}
    .album-stat-label {{
        font-size: 0.6rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.08em; color: {TEXT_DIM}; white-space: nowrap;
    }}
    .album-stat-value {{ font-size: 1.15rem; font-weight: 800; letter-spacing: -0.01em; white-space: nowrap; transition: color 0.3s ease; }}
    .album-stat-block.highlight {{
        background: radial-gradient(ellipse at center, rgba(29,185,84,0.10), transparent 70%); border-radius: 13px;
    }}
    .album-stat-block.highlight .album-stat-icon {{ background: rgba(29,185,84,0.18); }}
    .album-stat-block.highlight .album-stat-label {{ color: {GREEN}; opacity: 0.85; }}
    @media (max-width: 768px) {{
        .album-stats-bar {{ flex-wrap: wrap; }}
        .album-stat-block {{ flex: 1 1 45%; padding: 10px 6px; }}
        .album-stat-block + .album-stat-block::before {{ display: none; }}
        .album-stat-value {{ font-size: 0.95rem; }}
    }}
    </style>'''

    stats_body = (
        '<div class="album-stats-bar">'
        + _stat_block("🎯", "Rated Tracks", n_rated)
        + _stat_block("📊", "Mean", mean_val)
        + _stat_block("📍", "Median", median_val)
        + _stat_block("📐", "Std Dev", std_val)
        + _stat_block("⭐", "Suggested", suggested_str, highlight=True)
        + '</div>'
    )
    return stats_css + stats_body

def get_artist_stats_html(artist_id, user_id):
    # 1. Βρίσκουμε όλα τα τραγούδια του Artist
    songs_df = run_query("SELECT song_id FROM song_artists WHERE artist_id = :aid AND is_feature = FALSE", {"aid": artist_id})
    song_ids = songs_df["song_id"].tolist() if not songs_df.empty else []
    
    # 2. Βρίσκουμε όλα τα albums του Artist
    albums_df = run_query("""
        SELECT DISTINCT so.album_id 
        FROM songs so 
        JOIN song_artists sa ON sa.song_id = so.id 
        WHERE sa.artist_id = :aid AND sa.is_feature = FALSE AND so.album_id IS NOT NULL
    """, {"aid": artist_id})
    album_ids = albums_df["album_id"].tolist() if not albums_df.empty else []
    
    # 3. Φορτώνουμε τα ratings τους στη μνήμη
    if song_ids: R.preload_ratings(user_id, "song", song_ids)
    if album_ids: R.preload_ratings(user_id, "album", album_ids)
    
    # 4. Συλλέγουμε ΞΕΧΩΡΙΣΤΑ τις βαθμολογίες για Songs και Albums
    song_ratings = [
        st.session_state.get(f"rating_val_song_{sid}_{user_id}", 0.0) 
        for sid in song_ids if st.session_state.get(f"rating_val_song_{sid}_{user_id}", 0.0) > 0
    ]
    
    album_ratings = [
        st.session_state.get(f"rating_val_album_{aid}_{user_id}", 0.0) 
        for aid in album_ids if st.session_state.get(f"rating_val_album_{aid}_{user_id}", 0.0) > 0
    ]

    # Helper για τη δημιουργία της μπάρας
    def _build_stats_row(ratings_list, label_title, icon_str, is_last=False):
        n_rated = len(ratings_list)
        if n_rated > 0:
            arr = np.array(ratings_list)
            mean_val = f"{arr.mean():.2f}"
            median_val = f"{np.median(arr):.2f}"
            std_val_raw = float(np.std(arr, ddof=1)) if n_rated > 1 else 0.0
            std_val = f"± {std_val_raw:.2f}"
            
            sug_min = max(0.0, arr.mean() - std_val_raw)
            sug_max = min(10.0, arr.mean() + std_val_raw)
            suggested_str = f"{sug_min:.1f} – {sug_max:.1f}" if std_val_raw > 0 else f"{arr.mean():.1f}"
        else:
            mean_val, median_val, std_val, suggested_str = "—", "—", "—", "—"

        def _stat_block(icon, label, value, highlight=False):
            is_active_highlight = highlight and n_rated > 0
            cls = "album-stat-block highlight" if is_active_highlight else "album-stat-block"
            color = GREEN if is_active_highlight else (TEXT if n_rated > 0 else TEXT_DIM)
            return (
                f'<div class="{cls}">'
                f'<div class="album-stat-icon">{icon}</div>'
                f'<div class="album-stat-text">'
                f'<div class="album-stat-label">{label}</div>'
                f'<div class="album-stat-value" style="color:{color};">{value}</div>'
                f'</div>'
                f'</div>'
            )

        margin_bottom = "26px" if is_last else "12px"
        return (
            f'<div class="album-stats-bar" style="margin-bottom: {margin_bottom};">'
            + _stat_block(icon_str, f"Rated {label_title}", n_rated)
            + _stat_block("📊", "Mean", mean_val)
            + _stat_block("📍", "Median", median_val)
            + _stat_block("📐", "Std Dev", std_val)
            + _stat_block("⭐", "Suggested", suggested_str, highlight=True)
            + '</div>'
        )

    # Η CSS είναι η ίδια (αφαιρέσαμε το hardcoded margin-bottom για να το ελέγχουμε δυναμικά)
    stats_css = f'''<style>
    .album-stats-bar {{ display: flex; align-items: stretch; background: linear-gradient(145deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01)); border: 1px solid {BORDER}; border-radius: 16px; padding: 2px; position: relative; overflow: hidden; animation: fadeSlideUp 0.45s cubic-bezier(0.16,1,0.3,1) both; }}
    .album-stats-bar::before {{ content: ''; position: absolute; top: 0; left: 8%; right: 8%; height: 2px; background: linear-gradient(90deg, transparent, {GREEN}, transparent); opacity: 0.55; }}
    .album-stat-block {{ flex: 1; display: flex; align-items: center; justify-content: center; gap: 10px; padding: 15px 10px; position: relative; transition: background 0.2s ease; }}
    .album-stat-block:hover {{ background: rgba(255,255,255,0.02); }}
    .album-stat-block + .album-stat-block::before {{ content: ''; position: absolute; left: 0; top: 22%; bottom: 22%; width: 1px; background: {BORDER}; }}
    .album-stat-icon {{ width: 30px; height: 30px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; border-radius: 8px; background: rgba(255,255,255,0.05); font-size: 0.85rem; }}
    .album-stat-text {{ display: flex; flex-direction: column; gap: 2px; text-align: left; }}
    .album-stat-label {{ font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: {TEXT_DIM}; white-space: nowrap; }}
    .album-stat-value {{ font-size: 1.15rem; font-weight: 800; letter-spacing: -0.01em; white-space: nowrap; transition: color 0.3s ease; }}
    .album-stat-block.highlight {{ background: radial-gradient(ellipse at center, rgba(29,185,84,0.10), transparent 70%); border-radius: 13px; }}
    .album-stat-block.highlight .album-stat-icon {{ background: rgba(29,185,84,0.18); }}
    .album-stat-block.highlight .album-stat-label {{ color: {GREEN}; opacity: 0.85; }}
    @media (max-width: 768px) {{ .album-stats-bar {{ flex-wrap: wrap; }} .album-stat-block {{ flex: 1 1 45%; padding: 10px 6px; }} .album-stat-block + .album-stat-block::before {{ display: none; }} .album-stat-value {{ font-size: 0.95rem; }} }}
    </style>'''

    html_out = stats_css
    html_out += _build_stats_row(song_ratings, "Tracks", "🎵", is_last=False)
    html_out += _build_stats_row(album_ratings, "Albums", "💿", is_last=True)
    
    return html_out

@st.fragment
def hidden_rate_worker():
    def on_rate_change():
        val = st.session_state.get("hidden_rate_state")
        if val:
            parts = val.split(":")
            if len(parts) >= 4:
                r_type, r_id, r_val = parts[0], parts[1], float(parts[2])
                r_uid = int(parts[3])
                ok = False
                
                if r_type == "song":
                    ok = R.set_song_rating(r_uid, r_id, r_val)
                elif r_type == "album":
                    ok = R.set_album_rating(r_uid, r_id, r_val)
                elif r_type == "artist":
                    ok = R.set_artist_rating(r_uid, r_id, r_val)
                    
                if ok:
                    st.session_state[f"rating_val_{r_type}_{r_id}_{r_uid}"] = r_val
                    msg = f"Rated {r_val:g}/10 ✓" if r_val > 0 else "Rating cleared"
                    st.toast(msg, icon="⭐")
                    
                    # Ενεργοποίηση του Live Update
                    params = st.query_params
                    if params.get("view") == "album" and params.get("id"):
                        st.session_state["_live_update_album"] = {
                            "album_id": params.get("id"),
                            "user_id": r_uid
                        }
                    elif params.get("view") == "artist" and params.get("id"):
                        st.session_state["_live_update_artist"] = {
                            "artist_id": params.get("id"),
                            "user_id": r_uid
                        }

    st.text_input("hidden_rate_input", key="hidden_rate_state", label_visibility="collapsed", on_change=on_rate_change)

    # ΜΗΧΑΝΙΣΜΟΣ LIVE UPDATE (Album)
    if "_live_update_album" in st.session_state:
        data = st.session_state["_live_update_album"]
        new_html = get_album_stats_html(data["album_id"], data["user_id"])
        html_json = json.dumps(new_html)
        components.html(f"""
        <script>
        const doc = window.parent.document;
        const wrapper = doc.getElementById('album-stats-wrapper');
        if (wrapper) {{ wrapper.innerHTML = {html_json}; }}
        </script>
        """, height=0)
        del st.session_state["_live_update_album"]
        
    # ΜΗΧΑΝΙΣΜΟΣ LIVE UPDATE (Artist)
    if "_live_update_artist" in st.session_state:
        data = st.session_state["_live_update_artist"]
        new_html = get_artist_stats_html(data["artist_id"], data["user_id"])
        html_json = json.dumps(new_html)
        components.html(f"""
        <script>
        const doc = window.parent.document;
        const wrapper = doc.getElementById('artist-stats-wrapper');
        if (wrapper) {{ wrapper.innerHTML = {html_json}; }}
        </script>
        """, height=0)
        del st.session_state["_live_update_artist"]
        
# 2. BUMP HANDLER (ΧΩΡΙΣ Fragment! Θέλουμε να κάνει Soft-Rerun όλο το UI για να φανεί η νέα σειρά)
def hidden_bump_worker():
    def on_bump_change():
        val = st.session_state.get("hidden_bump_state")
        if val:
            parts = val.split(":")
            if len(parts) >= 4:
                b_type, b_id, b_action, b_target = parts[0], parts[1], parts[2], parts[3]
                try:
                    if R.move_item(selected_user_id, b_type, b_id, b_action, b_target):
                        st.toast("List order updated! 🔃", icon="✅")
                except Exception as e:
                    st.toast(f"⚠️ Couldn't reorder item: {e}", icon="⚠️")

    st.text_input("hidden_bump_input", key="hidden_bump_state", label_visibility="collapsed", on_change=on_bump_change)

# Καλούμε και τους 2 workers
hidden_rate_worker()
hidden_bump_worker()

def render_dimension_detail(extra_where: str, extra_params: dict, type_label: str, title: str, subtitle: str, icon: str, image_url: str = None, redirect_info: dict = None):
    header_df = run_query(f"""
        SELECT COUNT(*) AS streams, ROUND(COALESCE(SUM(ms_played), 0) / 3600000.0, 2) AS hours,
               COUNT(DISTINCT song_id) AS unique_songs
        FROM streams s
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
          AND {extra_where}
    """, {**F, **extra_params})

    streams = int(header_df.iloc[0]["streams"]) if not header_df.empty else 0
    hours = float(header_df.iloc[0]["hours"]) if not header_df.empty else 0.0
    unique_songs = int(header_df.iloc[0]["unique_songs"]) if not header_df.empty else 0

    render_detail_header(
        type_label=type_label, title=title, subtitle=subtitle, icon=icon,
        stats=[
            {"raw": streams, "label": "Streams"},
            {"raw": hours, "decimals": 1, "suffix": "h", "label": "Listened"},
            {"raw": unique_songs, "label": "Unique Songs"},
        ],
        image_url=image_url
    )

    c1, c2, c3 = st.columns(3)
    redirect_filters = redirect_info or {}

    redirect_date_range = None
    if "year" in redirect_filters:
        y = int(redirect_filters["year"])
        if "month" in redirect_filters:
            m = int(redirect_filters["month"])
            month_start = datetime.date(y, m, 1)
            month_end = (pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(1)).date()
            redirect_date_range = (month_start, month_end)
        else:
            redirect_date_range = (datetime.date(y, 1, 1), datetime.date(y, 12, 31))

    with c1:
        st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
        df_tracks = run_query(f"""
            WITH TrackArtists AS (
                SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
                FROM song_artists sa
                JOIN artists a ON a.id = sa.artist_id
                GROUP BY sa.song_id
            )
            SELECT so.id AS song_id, so.title AS song_title, COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
            GROUP BY so.id, so.title, ta.all_artists, so.image_url
            ORDER BY streams DESC LIMIT 10
        """, {**F, **extra_params})
        
        if not df_tracks.empty:
            R.preload_ratings(selected_user_id, "song", df_tracks["song_id"].tolist())
            render_list_v2(df_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song", **qr_kwargs)
            
            if redirect_filters or redirect_date_range:
                if st.button("See Full List →", key=f"seefull_tracks_{type_label}_{title}_{extra_params}", use_container_width=True):
                    curr_user = st.query_params.get("user")
                    st.query_params.clear()
                    st.query_params["tab"] = "tracks"
                    if curr_user: st.query_params["user"] = curr_user
                    
                    if "month" in redirect_filters:
                        st.session_state["filter_month_tracks"] = MONTH_NAMES[redirect_filters["month"]]
                    elif "season" in redirect_filters:
                        s_key = redirect_filters["season"]
                        st.session_state["filter_month_tracks"] = f"{s_key} {SEASON_META[s_key]['icon']}"
                    if "hour" in redirect_filters:
                        st.session_state["filter_hour_tracks"] = f"{redirect_filters['hour']:02d}:00"
                    elif "tod" in redirect_filters:
                        tod_key = redirect_filters["tod"]
                        st.session_state["filter_hour_tracks"] = f"{tod_key} ({TOD_META[tod_key]['range']})"
                        
                    if redirect_date_range:
                        st.session_state["pending_start_date"] = redirect_date_range[0]
                        st.session_state["pending_end_date"] = redirect_date_range[1]
                        st.session_state["pending_date_preset"] = None
                        st.query_params["preset"] = "manual"
                        st.query_params["start"] = redirect_date_range[0].isoformat()
                        st.query_params["end"] = redirect_date_range[1].isoformat()
                    st.rerun()
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)
        df_artists = run_query(f"""
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
            GROUP BY a.id, a.name, a.image_url
            ORDER BY streams DESC LIMIT 10
        """, {**F, **extra_params})
        
        if not df_artists.empty:
            df_artists["sub"] = "Artist"
            R.preload_ratings(selected_user_id, "artist", df_artists["artist_id"].tolist())
            render_list_v2(df_artists, "artist_name", "sub", "streams", "hours_played", "artist_id", "artist", **qr_kwargs)
            
            if redirect_filters or redirect_date_range:
                if st.button("See Full List →", key=f"seefull_artists_{type_label}_{title}_{extra_params}", use_container_width=True):
                    curr_user = st.query_params.get("user")
                    st.query_params.clear()
                    st.query_params["tab"] = "artists"
                    if curr_user: st.query_params["user"] = curr_user
                    
                    if "month" in redirect_filters:
                        st.session_state["filter_month_artists"] = MONTH_NAMES[redirect_filters["month"]]
                    elif "season" in redirect_filters:
                        s_key = redirect_filters["season"]
                        st.session_state["filter_month_artists"] = f"{s_key} {SEASON_META[s_key]['icon']}"  
                    if "hour" in redirect_filters:
                        st.session_state["filter_hour_artists"] = f"{redirect_filters['hour']:02d}:00"
                    elif "tod" in redirect_filters:
                        tod_key = redirect_filters["tod"]
                        st.session_state["filter_hour_artists"] = f"{tod_key} ({TOD_META[tod_key]['range']})"
                        
                    if redirect_date_range:
                        st.session_state["pending_start_date"] = redirect_date_range[0]
                        st.session_state["pending_end_date"] = redirect_date_range[1]
                        st.session_state["pending_date_preset"] = None
                        st.query_params["preset"] = "manual"
                        st.query_params["start"] = redirect_date_range[0].isoformat()
                        st.query_params["end"] = redirect_date_range[1].isoformat()
                    st.rerun()
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>No artists found</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)
        df_albums = run_query(f"""
            SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
              AND so.album_id IS NOT NULL
            GROUP BY al.id, al.title
            ORDER BY streams DESC LIMIT 10
        """, {**F, **extra_params})
        
        if not df_albums.empty:
            df_albums["sub"] = "Album"
            R.preload_ratings(selected_user_id, "album", df_albums["album_id"].tolist())
            render_list_v2(df_albums, "album_title", "sub", "streams", "hours_played", "album_id", "album", **qr_kwargs)
            
            if redirect_filters or redirect_date_range:
                if st.button("See Full List →", key=f"seefull_albums_{type_label}_{title}_{extra_params}", use_container_width=True):
                    curr_user = st.query_params.get("user")
                    st.query_params.clear()
                    st.query_params["tab"] = "albums"
                    if curr_user: st.query_params["user"] = curr_user
                    
                    if "month" in redirect_filters:
                        st.session_state["filter_month_albums"] = MONTH_NAMES[redirect_filters["month"]]
                    elif "season" in redirect_filters:
                        s_key = redirect_filters["season"]
                        st.session_state["filter_month_albums"] = f"{s_key} {SEASON_META[s_key]['icon']}"
                    if "hour" in redirect_filters:
                        st.session_state["filter_hour_albums"] = f"{redirect_filters['hour']:02d}:00"
                    elif "tod" in redirect_filters:
                        tod_key = redirect_filters["tod"]
                        st.session_state["filter_hour_albums"] = f"{tod_key} ({TOD_META[tod_key]['range']})"
                        
                    if redirect_date_range:
                        st.session_state["pending_start_date"] = redirect_date_range[0]
                        st.session_state["pending_end_date"] = redirect_date_range[1]
                        st.session_state["pending_date_preset"] = None
                        st.query_params["preset"] = "manual"
                        st.query_params["start"] = redirect_date_range[0].isoformat()
                        st.query_params["end"] = redirect_date_range[1].isoformat()
                    st.rerun()
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>No albums found</div>', unsafe_allow_html=True)
            
    # Chart code below remains identical
    st.markdown("<br>", unsafe_allow_html=True)
    ch1, ch2, ch3 = st.columns(3)
    
    with ch1:
        st.markdown('<div class="chart-container"><div class="chart-title">📈 Listening Timeline</div>', unsafe_allow_html=True)
        df_t = run_query(f"""
            SELECT DATE_TRUNC('month', played_at) AS period, COUNT(*) AS stream_count,
                   ROUND(SUM(ms_played)/3600000.0, 2) AS hours_played
            FROM streams s
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
            GROUP BY 1 ORDER BY 1
        """, {**F, **extra_params})
        if not df_t.empty:
            st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with ch2:
        st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
        df_h = run_query(f"""
            SELECT EXTRACT(HOUR FROM played_at)::INT as hour, COUNT(*) as stream_count
            FROM streams s
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
            GROUP BY 1 ORDER BY 1
        """, {**F, **extra_params})
        if not df_h.empty:
            st.plotly_chart(
                chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"),
                use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with ch3:
        st.markdown('<div class="chart-container"><div class="chart-title">📅 Active Days</div>', unsafe_allow_html=True)
        df_days = run_query(f"""
            SELECT EXTRACT(ISODOW FROM played_at)::INT AS dow, COUNT(*) AS stream_count
            FROM streams s
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {extra_where}
            GROUP BY 1 ORDER BY 1;
        """, {**F, **extra_params})
        if not df_days.empty:
            dow_map = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
            st.plotly_chart(
                chart_bar(df_days["dow"].map(dow_map).tolist(), df_days["stream_count"].tolist(), "Day"),
                use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)

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
    user = params.get("user")
    qr = params.get("qr")

    st.query_params.clear()
    st.query_params["tab"] = tab
    if pview and pid:
        st.query_params["view"] = pview
        st.query_params["id"] = pid
    if preset: st.query_params["preset"] = preset
    if start: st.query_params["start"] = start
    if end: st.query_params["end"] = end
    if user: st.query_params["user"] = user
    if qr: st.query_params["qr"] = qr

min_date, max_date = get_date_bounds()

def get_parsed_date(date_str, default_date):
    if not date_str: return default_date
    try: return datetime.date.fromisoformat(date_str)
    except: return default_date

params = st.query_params

try:
    users_df = run_query("SELECT id, username FROM users ORDER BY username")
    user_dict = dict(zip(users_df['username'], users_df['id']))
except:
    user_dict = {"Ody": 1}

url_user_id = params.get("user")
usernames = list(user_dict.keys())
if url_user_id:
    selected_username = next((k for k, v in user_dict.items() if str(v) == url_user_id), usernames[0] if usernames else "Ody")
else:
    selected_username = st.session_state.get("username_to_import", usernames[0] if usernames else "Ody")

selected_user_id = user_dict.get(selected_username, 1)
st.query_params["user"] = str(selected_user_id)

qr_kwargs = dict(quick_rate=st.session_state.quick_rate_mode, R=R, 
                 user_id=selected_user_id, rating_scale=10)

# Handle pending redirect dates safely before widgets instantiate
if "pending_start_date" in st.session_state:
    st.session_state.start_date = st.session_state.pop("pending_start_date")
    st.session_state.end_date = st.session_state.pop("pending_end_date")
    if "pending_date_preset" in st.session_state:
        st.session_state.date_preset = st.session_state.pop("pending_date_preset")

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
    # Αν πειράξει τις ημερομηνίες χειροκίνητα, γυρνάει αυτόματα το dropdown στο "Manual"
    st.session_state.date_preset = "manual" 
    st.query_params["preset"] = "manual"
    st.query_params["start"] = st.session_state.start_date.isoformat()
    st.query_params["end"] = st.session_state.end_date.isoformat()

# ΠΡΟΣΤΕΘΗΚΕ ΤΟ "⚙️ Manual" ΣΤΟ ΛΕΞΙΚΟ!
preset_options = {"all": "♾️ All Time", "wrapped": "🎁 Wrapped", "month": "📅 Month", "week": "📅 Week", "manual": "⚙️ Manual"}

view_state = get_current_view()
current_tab = view_state["tab"]
detail_type = view_state["type"]
detail_id = view_state["id"]

with st.container(key="top_bar_wrapper"):
    st.markdown(f"""
            <style>
            /* ═══════════════════════════════════════════
               TOOLBAR CARD (Responsive Fixes)
               ═══════════════════════════════════════════ */
            .st-key-top_bar_wrapper {{
                background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.014));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
                padding: 10px 20px;
                margin: 4px 0 14px;
                box-shadow: 0 10px 28px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
            }}

            /* ─── BASE ELEMENTS (Κοινά) ─── */
            .st-key-top_bar_wrapper .brand-title {{
                font-size: 1.3rem !important;
                font-weight: 800 !important;
                letter-spacing: -0.02em;
                gap: 0.45rem;
                white-space: nowrap;
            }}
            .st-key-top_bar_wrapper .brand-title span {{ font-size: 1.55rem !important; }}

            .st-key-top_bar_wrapper .filter-label {{
                font-size: 0.6rem !important;
                font-weight: 700 !important;
                text-transform: uppercase;
                letter-spacing: 0.07em;
                color: {TEXT_DIM} !important;
                margin: 0 0 3px 2px !important;
            }}

            .st-key-top_bar_wrapper div[data-baseweb="select"] > div,
            .st-key-top_bar_wrapper div[data-testid="stDateInput"] input {{
                height: 38px !important; min-height: 38px !important;
                border-radius: 11px !important;
                background: rgba(255,255,255,0.045) !important;
                border: 1px solid rgba(255,255,255,0.09) !important;
                font-size: 0.82rem !important; font-weight: 600 !important;
                transition: all .2s ease !important;
            }}
            .st-key-top_bar_wrapper div[data-baseweb="select"] > div:hover,
            .st-key-top_bar_wrapper div[data-testid="stDateInput"] input:hover {{
                border-color: rgba(29,185,84,0.4) !important;
                background: rgba(255,255,255,0.065) !important;
            }}
            .st-key-top_bar_wrapper div[data-testid="stDateInput"] > div {{ margin-top: 0 !important; }}

            .st-key-quick_rate_toggle button,
            .st-key-share_row div[data-testid="column"]:last-child button,
            .st-key-share_row div[data-testid="stColumn"]:last-child button {{
                height: 38px !important; border-radius: 9px !important;
                font-weight: 700 !important; font-size: 0.78rem !important;
                padding: 0 15px !important; white-space: nowrap !important;
                background: transparent !important; border: 1px solid transparent !important;
                margin: 0 !important; width: 100% !important; transition: all 0.2s ease !important;
            }}
            .st-key-quick_rate_toggle button[kind="secondary"] {{ color: {TEXT_DIM} !important; }}
            .st-key-quick_rate_toggle button[kind="secondary"]:hover {{ background: rgba(255,255,255,0.06) !important; color: {TEXT} !important; }}
            .st-key-quick_rate_toggle button[kind="primary"] {{ background: rgba(229,57,53,0.16) !important; border-color: rgba(229,57,53,0.45) !important; color: #FF6B6B !important; }}
            .st-key-quick_rate_toggle button[kind="primary"]:hover {{ background: rgba(229,57,53,0.24) !important; color: #fff !important; }}
            .st-key-share_row div[data-testid="column"]:last-child button,
            .st-key-share_row div[data-testid="stColumn"]:last-child button {{ color: {GREEN} !important; }}
            .st-key-share_row div[data-testid="column"]:last-child button:hover,
            .st-key-share_row div[data-testid="stColumn"]:last-child button:hover {{ background: rgba(29,185,84,0.14) !important; color: #fff !important; }}

            /* ─── DESKTOP ONLY ─── */
            @media (min-width: 48.01em) {{
                .st-key-top_bar_wrapper > div > div[data-testid="stHorizontalBlock"],
                .st-key-top_bar_wrapper > div > div[data-testid="stColumns"] {{
                    display: flex !important; align-items: center !important; gap: 24px !important; flex-wrap: nowrap !important;
                }}
                .st-key-top_bar_wrapper > div > div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
                .st-key-top_bar_wrapper > div > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
                .st-key-top_bar_wrapper > div > div[data-testid="stColumns"] > div[data-testid="column"],
                .st-key-top_bar_wrapper > div > div[data-testid="stColumns"] > div[data-testid="stColumn"] {{
                    width: auto !important; flex: 0 0 auto !important; min-width: 0 !important;
                }}
                div[data-testid="column"]:has(.st-key-share_row),
                div[data-testid="stColumn"]:has(.st-key-share_row) {{ margin-left: auto !important; }}

                .st-key-top_filter_row div[data-testid="stHorizontalBlock"],
                .st-key-top_filter_row div[data-testid="stColumns"] {{
                    display: flex !important; align-items: center !important; gap: 14px !important; flex-wrap: nowrap !important;
                }}
                .st-key-top_filter_row div[data-testid="column"],
                .st-key-top_filter_row div[data-testid="stColumn"] {{ width: auto !important; flex: 0 0 auto !important; }}
                
                .st-key-share_row {{
                    display: inline-flex !important; align-items: stretch !important;
                    background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.09);
                    border-radius: 12px; padding: 3px;
                }}
                .st-key-share_row div[data-testid="stHorizontalBlock"],
                .st-key-share_row div[data-testid="stColumns"] {{
                    display: inline-flex !important; width: auto !important; gap: 2px !important; flex-wrap: nowrap !important;
                }}
                .st-key-share_row div[data-testid="column"],
                .st-key-share_row div[data-testid="stColumn"] {{ width: auto !important; flex: 0 0 auto !important; }}
                .st-key-share_row div[data-testid="column"]:first-child,
                .st-key-share_row div[data-testid="stColumn"]:first-child {{ position: relative; padding-right: 4px; }}
                .st-key-share_row div[data-testid="column"]:first-child::after,
                .st-key-share_row div[data-testid="stColumn"]:first-child::after {{
                    content: ''; position: absolute; right: 0; top: 22%; bottom: 22%; width: 1px; background: rgba(255,255,255,0.1);
                }}
            }}

            /* ─── MOBILE ONLY ─── */
            @media (max-width: 48em) {{
                .st-key-top_bar_wrapper {{ padding: 12px !important; }}
                .st-key-top_bar_wrapper > div > div[data-testid="stHorizontalBlock"],
                .st-key-top_bar_wrapper > div > div[data-testid="stColumns"] {{
                    flex-direction: column !important; gap: 12px !important; align-items: stretch !important;
                }}
                
                .st-key-top_filter_row div[data-testid="stHorizontalBlock"],
                .st-key-top_filter_row div[data-testid="stColumns"] {{
                    flex-direction: column !important; gap: 8px !important; align-items: stretch !important;
                }}
                .st-key-top_filter_row div[data-testid="column"],
                .st-key-top_filter_row div[data-testid="stColumn"] {{
                    min-width: 100% !important; width: 100% !important; flex: 1 1 100% !important;
                }}

                /* Διορθώνει το στρίμωγμα του Share Row */
                .st-key-share_row {{
                    display: flex !important; width: 100% !important;
                    background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.09);
                    border-radius: 12px; padding: 4px;
                }}
                .st-key-share_row div[data-testid="stHorizontalBlock"],
                .st-key-share_row div[data-testid="stColumns"] {{
                    display: flex !important; flex-direction: row !important; width: 100% !important; gap: 4px !important;
                }}
                .st-key-share_row div[data-testid="column"],
                .st-key-share_row div[data-testid="stColumn"] {{
                    flex: 1 1 50% !important; width: 50% !important;
                }}
                .st-key-share_row div[data-testid="column"]:first-child::after,
                .st-key-share_row div[data-testid="stColumn"]:first-child::after {{ display: none !important; }}

                /* Ξεπαγιδεύει το Tab Dropdown από το να πέφτει πάνω στα κουμπιά */
                .st-key-tab_nav_mobile {{
                    position: static !important;
                    transform: none !important;
                    width: 100% !important;
                    margin: 0 0 16px 0 !important;
                    display: block !important;
                }}
                .st-key-tab_nav_mobile > div, .st-key-tab_nav_mobile button {{
                    width: 100% !important;
                }}
            }}
            </style>
        """, unsafe_allow_html=True)

    col_brand, col_filters, col_share = st.columns([0.9, 3.2, 1.0])

    with col_brand:
        st.markdown('''
        <div class="navbar">
            <div class="nav-brand brand-title">
                <span>🎧</span> Suggestify
            </div>
        </div>
        ''', unsafe_allow_html=True)

    with col_filters:
        with st.container(key="top_filter_row"):
            if st.session_state.date_preset == "manual":
                f_preset, f_start, f_end = st.columns(3)
                with f_preset:
                    st.markdown('<div class="filter-label">🗓️ Period</div>', unsafe_allow_html=True)
                    st.selectbox("Period", options=list(preset_options.keys()), format_func=lambda x: preset_options[x], label_visibility="collapsed", key="date_preset", on_change=update_dates_from_preset)
                with f_start:
                    st.markdown('<div class="filter-label">From</div>', unsafe_allow_html=True)
                    st.date_input("From", min_value=min_date, max_value=max_date, label_visibility="collapsed", key="start_date", on_change=mark_manual)
                with f_end:
                    st.markdown('<div class="filter-label">To</div>', unsafe_allow_html=True)
                    st.date_input("To", min_value=min_date, max_value=max_date, label_visibility="collapsed", key="end_date", on_change=mark_manual)
            else:
                f_preset = st.columns(1)[0]
                with f_preset:
                    st.markdown('<div class="filter-label">🗓️ Period</div>', unsafe_allow_html=True)
                    st.selectbox("Period", options=list(preset_options.keys()), format_func=lambda x: preset_options[x], label_visibility="collapsed", key="date_preset", on_change=update_dates_from_preset)

    with col_share:
        rating_mode_on = st.session_state.quick_rate_mode
        with st.container(key="share_row"):
            col_a, col_b = st.columns(2)
            with col_a:
                with st.container(key="quick_rate_toggle"):
                    rating_label = "★ Rating On" if rating_mode_on else "☆ Rating Off"
                    if st.button(rating_label, key="quick_rate_btn", type="primary" if rating_mode_on else "secondary"):
                        new_mode = not st.session_state.quick_rate_mode
                        st.session_state.quick_rate_mode = new_mode
                        qr_global["mode"] = new_mode
                        if new_mode:
                            st.query_params["qr"] = "1"
                        else:
                            st.query_params.pop("qr", None)
                        st.rerun()
            with col_b:
                render_share_stats_button(
                    run_query=run_query,
                    user_id=selected_user_id,
                    username=selected_username,
                    min_date=min_date,
                    max_date=max_date,
                    label="📸 Share Stats"
                )
# ====== ΤΕΛΟΣ ΤΗΣ ΠΑΝΩ ΜΠΑΡΑΣ ======
tabs = [
    ("overview", "📊 Overview"), ("tracks", "🎵 Tracks"),
    ("artists", "🎤 Artists"), ("albums", "💿 Albums"),
    ("genres", "🎸 Genres"), ("habits", "🕐 Habits"),
    ("ratings", "⭐ Ratings"),
    ("friends", "🎉 Friends")
]

def navigate_to_tab(tab_id: str):
    curr_preset = st.query_params.get("preset")
    curr_start = st.query_params.get("start")
    curr_end = st.query_params.get("end")
    curr_user = st.query_params.get("user")
    curr_qr = st.query_params.get("qr")

    st.query_params.clear()
    st.query_params["tab"] = tab_id

    if curr_preset: st.query_params["preset"] = curr_preset
    if curr_start: st.query_params["start"] = curr_start
    if curr_end: st.query_params["end"] = curr_end
    if curr_user: st.query_params["user"] = curr_user
    if curr_qr: st.query_params["qr"] = curr_qr

    st.rerun()

tab_labels = dict(tabs)
active_tab_id = current_tab if (current_tab in tab_labels and not detail_type) else "overview"

with st.container(key="tab_nav_row"):
    cols = st.columns(len(tabs))
    for i, (tab_id, tab_label) in enumerate(tabs):
        with cols[i]:
            is_active = (current_tab == tab_id) and not detail_type
            if st.button(tab_label, key=f"nav_{tab_id}", type="primary" if is_active else "secondary", use_container_width=True):
                navigate_to_tab(tab_id)

with st.container(key="tab_nav_mobile"):
    with st.popover(f"{tab_labels[active_tab_id]}   ▾", use_container_width=True):
        for tab_id, tab_label in tabs:
            is_active = (current_tab == tab_id) and not detail_type
            if st.button(tab_label, key=f"nav_mobile_{tab_id}", type="primary" if is_active else "secondary", use_container_width=True):
                navigate_to_tab(tab_id)

F = {
    "start_date": st.session_state.start_date, 
    "end_date": st.session_state.end_date,
    "user_id": selected_user_id
}

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

MONTH_FILTER_OPTIONS = ["All Months"] + [f"{k} {v['icon']}" for k, v in SEASON_META.items()] + list(MONTH_NAMES.values())

SEASON_META = {
    "Winter": {"icon": "❄️", "color": "#4FC3F7", "months": (12, 1, 2),
               "image": "https://images.unsplash.com/photo-1418985991508-e47386d96a71?w=400&q=80&auto=format&fit=crop"},
    "Spring": {"icon": "🌸", "color": "#F48FB1", "months": (3, 4, 5),
               "image": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=400&q=80&auto=format&fit=crop"},
    "Summer": {"icon": "☀️", "color": "#FFD54F", "months": (6, 7, 8),
               "image": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&q=80&auto=format&fit=crop"},
    "Autumn": {"icon": "🍂", "color": "#FF8A65", "months": (9, 10, 11),
               "image": "https://images.unsplash.com/photo-1477414348463-c0eb7f1359b6?w=400&q=80&auto=format&fit=crop"},
}

TOD_META = {
    "Night":     {"icon": "🌙", "range": "9PM–5AM",  "color": "#5C6BC0", "hours": [21, 22, 23, 0, 1, 2, 3, 4],
                  "image": "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?w=400&q=80&auto=format&fit=crop"},
    "Morning":   {"icon": "🌅", "range": "5AM–12PM", "color": "#FFD54F", "hours": list(range(5, 12)),
                  "image": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400&q=80&auto=format&fit=crop"},
    "Afternoon": {"icon": "🌤️", "range": "12PM–5PM",  "color": "#4FC3F7", "hours": list(range(12, 17)),
                  "image": "https://images.unsplash.com/photo-1500964757637-c85e8a162699?w=400&q=80&auto=format&fit=crop"},
    "Evening":   {"icon": "🌆", "range": "5PM–9PM",   "color": "#FF7043", "hours": list(range(17, 21)),
                  "image": "https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?w=400&q=80&auto=format&fit=crop"},
}

# New option list including TOD ranges
HOUR_FILTER_OPTIONS = ["All Hours"] + [f"{k} ({v['range']})" for k, v in TOD_META.items()] + [f"{h:02d}:00" for h in range(24)]

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
        ),
        TrackArtists AS (
            SELECT sa.song_id, 
                   MIN(sa.artist_id) as primary_artist_id,
                   STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
            FROM song_artists sa
            JOIN artists a ON a.id = sa.artist_id
            GROUP BY sa.song_id
        )
        SELECT so.title, COALESCE(ta.all_artists, 'Unknown') as artist, so.image_url,
            COALESCE(r.streams, 0) as streams,
            COALESCE(r.hours, 0) as hours,
            r.global_rank,
            MIN(s.played_at) as first_play,
            so.duration_ms, so.release_date, so.primary_genre, so.is_explicit, so.preview_url,
            so.album_id, al.title as album_title, ta.primary_artist_id
        FROM songs so
        LEFT JOIN TrackArtists ta ON ta.song_id = so.id
        LEFT JOIN albums al ON al.id = so.album_id
        LEFT JOIN ranked r ON r.song_id = so.id
        LEFT JOIN streams s ON s.song_id = so.id 
             AND s.played_at::date BETWEEN :start_date AND :end_date 
             AND s.user_id = :user_id
        WHERE so.id = :id
        GROUP BY so.id, so.title, ta.all_artists, so.image_url, r.streams, r.hours, r.global_rank,
                 so.duration_ms, so.release_date, so.primary_genre, so.is_explicit, so.preview_url,
                 so.album_id, al.title, ta.primary_artist_id
    """, {"id": detail_id, **F})

        if not song_info.empty:
            row = song_info.iloc[0]
            rank_display = f"#{int(row['global_rank'])}" if pd.notnull(row.get('global_rank')) else "—"
            
            display_title = str(row["title"])
            if row.get("is_explicit"):
                display_title += ' <span class="explicit-badge">E</span>'
            
            render_detail_header(
                type_label="Track", title=display_title,
                subtitle=f"by {row['artist']}", icon="🎵",
                stats=[
                    {"value": rank_display, "label": "Song Rank"},
                    {"raw": int(row['streams'] or 0), "label": "Streams"},
                    {"raw": float(row['hours'] or 0), "decimals": 1, "suffix": "h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            if st.session_state.quick_rate_mode:
                R.render_star_rating("song", detail_id, selected_user_id, compact=True)
            else:
                st.markdown(R.rating_chip_html(R.get_song_rating(selected_user_id, detail_id)), unsafe_allow_html=True)
            
            chips_html = '<div class="meta-chip-container">'
            
            if pd.notnull(row.get("primary_artist_id")):
                artist_href = build_filtered_href("artist", str(row["primary_artist_id"]))
                chips_html += (
                    f'<a href="{artist_href}" class="meta-chip-link" target="_self"><div class="meta-chip">'
                    f'<div class="meta-chip-icon">🎤</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Artist</div>'
                    f'<div class="meta-chip-value">{escape(str(row["artist"]).split(",")[0])}</div>'
                    f'</div></div></a>'
                )
            
            if pd.notnull(row.get("album_id")) and pd.notnull(row.get("album_title")):
                album_href = build_filtered_href("album", str(row["album_id"]))
                chips_html += (
                    f'<a href="{album_href}" class="meta-chip-link" target="_self"><div class="meta-chip">'
                    f'<div class="meta-chip-icon">💿</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Album</div>'
                    f'<div class="meta-chip-value">{escape(str(row["album_title"]))}</div>'
                    f'</div></div></a>'
                )

            if pd.notnull(row.get("duration_ms")) and row["duration_ms"] > 0:
                mins = int(row["duration_ms"]) // 60000
                secs = (int(row["duration_ms"]) % 60000) // 1000
                chips_html += (
                    f'<div class="meta-chip"><div class="meta-chip-icon">⏱️</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Length</div>'
                    f'<div class="meta-chip-value">{mins}:{secs:02d}</div></div></div>'
                )
                
            if pd.notnull(row.get("release_date")):
                try:
                    r_date = pd.to_datetime(row["release_date"]).strftime('%d %b %Y')
                    chips_html += (
                        f'<div class="meta-chip"><div class="meta-chip-icon">📅</div><div class="meta-chip-text">'
                        f'<div class="meta-chip-label">Released</div>'
                        f'<div class="meta-chip-value">{r_date}</div></div></div>'
                    )
                except: pass
                
            if pd.notnull(row.get("primary_genre")):
                chips_html += (
                    f'<div class="meta-chip"><div class="meta-chip-icon">🎸</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Genre</div>'
                    f'<div class="meta-chip-value">{escape(str(row["primary_genre"]))}</div></div></div>'
                )
                
            chips_html += '</div>'
            st.markdown(chips_html, unsafe_allow_html=True)
            
            if pd.notnull(row.get("preview_url")):
                st.audio(row["preview_url"], format="audio/mp4")
                st.markdown("<br>", unsafe_allow_html=True)
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
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
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
                        use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
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
                    {"raw": int(row['streams'] or 0), "label": "Streams"},
                    {"raw": float(row['hours'] or 0), "decimals": 1, "suffix": "h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            # --- ΠΡΟΣΘΗΚΗ: RATING STARS & STATS WRAPPER ΓΙΑ ARTISTS ---
            if st.session_state.quick_rate_mode:
                R.render_star_rating("artist", detail_id, selected_user_id, compact=True)
                st.markdown(f'<div id="artist-stats-wrapper">{get_artist_stats_html(detail_id, selected_user_id)}</div>', unsafe_allow_html=True)
            else:
                st.markdown(R.rating_chip_html(R.get_artist_rating(selected_user_id, detail_id)), unsafe_allow_html=True)
            
            # --- FIX: Προσθέτουμε λίγο κενό για να μην κάνουν collide τα elements ---
            st.markdown("<br><br>", unsafe_allow_html=True)
            
            # Αλλάζουμε το layout σε 2 στήλες για τις λίστες
            c_tracks, c_albums = st.columns(2)
            
            with c_tracks:
                c1_hdr, c1_sort = st.columns([2.5, 1])
                with c1_hdr:
                    st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
                with c1_sort:
                    sort_art_tracks = st.selectbox("Sort", ["Streams", "Hours", "Rating"], index=0, label_visibility="collapsed", key=f"sort_art_tr_{detail_id}")

                df_tracks = run_query("""
                    WITH TrackArtists AS (
                        SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
                        FROM song_artists sa
                        JOIN artists a ON a.id = sa.artist_id
                        GROUP BY sa.song_id
                    )
                    SELECT so.id AS song_id, so.title as song_title, COALESCE(ta.all_artists, 'Unknown') as sub, so.image_url,
                           COUNT(s.id) as streams, ROUND(SUM(s.ms_played)/3600000.0, 3) as hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN song_artists sa_filter ON sa_filter.song_id = s.song_id
                    LEFT JOIN TrackArtists ta ON ta.song_id = so.id
                    WHERE sa_filter.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY so.id, so.title, ta.all_artists, so.image_url
                """, {"aid": detail_id, **F})
                
                if not df_tracks.empty:
                    R.preload_ratings(selected_user_id, "song", df_tracks["song_id"].tolist())
                    
                    if sort_art_tracks == "Rating":
                        df_tracks["rating"] = df_tracks["song_id"].apply(
                            lambda x: st.session_state.get(f"rating_val_song_{x}_{selected_user_id}", 0.0)
                        )
                        df_tracks["_mem_weight"] = df_tracks["song_id"].apply(
                            lambda x: st.session_state.get(f"sort_weight_song_{x}_{selected_user_id}", 0.0)
                        )
                        df_tracks = df_tracks.sort_values(by=["rating", "_mem_weight", "streams"], ascending=[False, False, False]).reset_index(drop=True)
                    elif sort_art_tracks == "Hours":
                        df_tracks = df_tracks.sort_values(by=["hours_played", "streams"], ascending=[False, False]).reset_index(drop=True)
                    else:
                        df_tracks = df_tracks.sort_values(by=["streams", "hours_played"], ascending=[False, False]).reset_index(drop=True)

                    df_tracks_top = df_tracks.head(10)
                    render_list_v2(df_tracks_top, "song_title", "sub", "streams", "hours_played", "song_id", "song", **qr_kwargs)
                    
                    if st.button("See Full List →", key=f"btn_full_tracks_{detail_id}", use_container_width=True):
                        curr_user = st.query_params.get("user")
                        st.query_params.clear()
                        if curr_user: st.query_params["user"] = curr_user
                        
                        if sort_art_tracks == "Rating":
                            st.query_params["tab"] = "ratings"
                            st.query_params["view"] = "ratings_full"
                            st.query_params["id"] = "song"
                            st.session_state["search_full_ratings_song"] = artist_name
                            st.session_state["sort_full_ratings_song"] = "Highest Rated"
                        else:
                            st.query_params["tab"] = "tracks"
                            st.session_state["search_tracks"] = artist_name
                            st.session_state["sort_tracks"] = sort_art_tracks
                        st.rerun()

            with c_albums:
                c2_hdr, c2_sort = st.columns([2.5, 1])
                with c2_hdr:
                    st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)
                with c2_sort:
                    sort_art_albums = st.selectbox("Sort", ["Streams", "Hours", "Rating"], index=0, label_visibility="collapsed", key=f"sort_art_al_{detail_id}")

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
                      AND al.id IS NOT NULL
                    GROUP BY al.id, al.title
                """, {"aid": detail_id, **F})
                
                if not df_albums.empty:
                    df_albums["subtitle"] = "Album"
                    R.preload_ratings(selected_user_id, "album", df_albums["album_id"].tolist())

                    if sort_art_albums == "Rating":
                        df_albums["rating"] = df_albums["album_id"].apply(
                            lambda x: st.session_state.get(f"rating_val_album_{x}_{selected_user_id}", 0.0)
                        )
                        df_albums["_mem_weight"] = df_albums["album_id"].apply(
                            lambda x: st.session_state.get(f"sort_weight_album_{x}_{selected_user_id}", 0.0)
                        )
                        df_albums = df_albums.sort_values(by=["rating", "_mem_weight", "streams"], ascending=[False, False, False]).reset_index(drop=True)
                    elif sort_art_albums == "Hours":
                        df_albums = df_albums.sort_values(by=["hours_played", "streams"], ascending=[False, False]).reset_index(drop=True)
                    else:
                        df_albums = df_albums.sort_values(by=["streams", "hours_played"], ascending=[False, False]).reset_index(drop=True)

                    df_albums_top = df_albums.head(10)
                    render_list_v2(df_albums_top, "album_title", "subtitle", "streams", "hours_played", "album_id", "album", **qr_kwargs)
                    
                    if st.button("See Full List →", key=f"btn_full_albums_{detail_id}", use_container_width=True):
                        curr_user = st.query_params.get("user")
                        st.query_params.clear()
                        if curr_user: st.query_params["user"] = curr_user
                        
                        if sort_art_albums == "Rating":
                            st.query_params["tab"] = "ratings"
                            st.query_params["view"] = "ratings_full"
                            st.query_params["id"] = "album"
                            st.session_state["search_full_ratings_album"] = artist_name
                            st.session_state["sort_full_ratings_album"] = "Highest Rated"
                        else:
                            st.query_params["tab"] = "albums"
                            st.session_state["search_albums"] = artist_name
                            st.session_state["sort_albums"] = sort_art_albums
                        st.rerun()

            # Προσθέτουμε λίγο κενό πριν τα διαγράμματα
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Δημιουργούμε 3 στήλες για τα γραφήματα κάτω από τις λίστες
            ch1, ch2, ch3 = st.columns(3)
            
            with ch1:
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
                    st.plotly_chart(chart_trend(df_t), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
                st.markdown('</div>', unsafe_allow_html=True)

            with ch2:
                st.markdown('<div class="chart-container"><div class="chart-title">🕐 Peak Hours</div>', unsafe_allow_html=True)
                df_h = run_query("""
                    SELECT EXTRACT(HOUR FROM s.played_at)::INT AS hour, COUNT(*) AS stream_count
                    FROM streams s
                    JOIN song_artists sa ON sa.song_id = s.song_id
                    WHERE sa.artist_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1;
                """, {"aid": detail_id, **F})
                if not df_h.empty:
                    st.plotly_chart(
                        chart_bar(df_h["hour"].apply(lambda h: f"{h:02d}:00").tolist(), df_h["stream_count"].tolist(), "Hour"),
                        use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

            with ch3:
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
                        use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "album":
        alb_info = run_query("""
        WITH AlbumPrimaryArtists AS (
            SELECT a.id AS artist_id, a.name, COUNT(DISTINCT so.id) as track_cnt
            FROM songs so
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE so.album_id = :id
            GROUP BY a.id, a.name
        ),
        RankedArtists AS (
            SELECT artist_id, name, track_cnt,
                   ROW_NUMBER() OVER (ORDER BY track_cnt DESC) as rn
            FROM AlbumPrimaryArtists
        ),
        TopAlbumArtists AS (
            SELECT STRING_AGG(name, ', ' ORDER BY rn ASC) as artist_names,
                   MAX(CASE WHEN rn = 1 THEN artist_id END) as primary_artist_id
            FROM RankedArtists
            WHERE rn <= 3
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
            (SELECT primary_artist_id FROM TopAlbumArtists) as primary_artist_id,
            r.global_rank,
            al.release_date, al.primary_genre, al.label, al.is_explicit, al.total_tracks
        FROM albums al
        LEFT JOIN songs so ON so.album_id = al.id
        LEFT JOIN streams s ON s.song_id = so.id 
             AND s.played_at::date BETWEEN :start_date AND :end_date
             AND s.user_id = :user_id
        LEFT JOIN album_streams ars ON ars.album_id = al.id
        LEFT JOIN ranked r ON r.album_id = al.id
        WHERE al.id = :id
        GROUP BY al.id, al.title, ars.streams, ars.hours, r.global_rank,
                 al.release_date, al.primary_genre, al.label, al.is_explicit, al.total_tracks
    """, {"id": detail_id, **F})

        if not alb_info.empty:
            row = alb_info.iloc[0]
            artist_name = row["artist_name"] if pd.notnull(row["artist_name"]) else "Unknown Artist"
            rank_display = f"#{int(row['global_rank'])}" if pd.notnull(row.get('global_rank')) else "—"

            display_title = str(row["title"]) if row["title"] else "Unknown Album"
            if row.get("is_explicit"):
                display_title += ' <span class="explicit-badge">E</span>'

            render_detail_header(
                type_label="Album",
                title=display_title,
                subtitle=f"by {artist_name} • {int(row['track_count'] or 0)} tracks played", 
                icon="💿",
                stats=[
                    {"value": rank_display, "label": "Album Rank"},
                    {"raw": int(row['streams'] or 0), "label": "Streams"},
                    {"raw": float(row['hours'] or 0), "decimals": 1, "suffix": "h", "label": "Listened"},
                ],
                image_url=row.get("image_url")
            )
            
            # Replace R.render_star_rating("album", detail_id, selected_user_id) with:
            if st.session_state.quick_rate_mode:
                R.render_star_rating("album", detail_id, selected_user_id, compact=True)
            else:
                st.markdown(R.rating_chip_html(R.get_album_rating(selected_user_id, detail_id)), unsafe_allow_html=True)
            
            chips_html = '<div class="meta-chip-container">'

            if pd.notnull(row.get("primary_artist_id")):
                artist_href = build_filtered_href("artist", str(row["primary_artist_id"]))
                artist_display_name = escape(str(row["artist_name"]).split(",")[0])
                chips_html += (
                    f'<a href="{artist_href}" class="meta-chip-link" target="_self"><div class="meta-chip">'
                    f'<div class="meta-chip-icon">🎤</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Artist</div>'
                    f'<div class="meta-chip-value">{artist_display_name}</div>'
                    f'</div></div></a>'
                )

            if pd.notnull(row.get("release_date")):
                try:
                    r_date = pd.to_datetime(row["release_date"]).strftime('%d %b %Y')
                    chips_html += (
                        f'<div class="meta-chip"><div class="meta-chip-icon">📅</div><div class="meta-chip-text">'
                        f'<div class="meta-chip-label">Released</div>'
                        f'<div class="meta-chip-value">{r_date}</div></div></div>'
                    )
                except: pass

            if pd.notnull(row.get("primary_genre")):
                chips_html += (
                    f'<div class="meta-chip"><div class="meta-chip-icon">🎸</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Genre</div>'
                    f'<div class="meta-chip-value">{escape(str(row["primary_genre"]))}</div></div></div>'
                )

            if pd.notnull(row.get("label")):
                label_text = str(row["label"])
                label_display = label_text[:20] + "…" if len(label_text) > 20 else label_text
                chips_html += (
                    f'<div class="meta-chip"><div class="meta-chip-icon">🏢</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Label</div>'
                    f'<div class="meta-chip-value">{escape(label_display)}</div></div></div>'
                )

            if pd.notnull(row.get("total_tracks")) and row["total_tracks"] > 0:
                chips_html += (
                    f'<div class="meta-chip"><div class="meta-chip-icon">⏱️</div><div class="meta-chip-text">'
                    f'<div class="meta-chip-label">Tracks</div>'
                    f'<div class="meta-chip-value">{int(row["total_tracks"])}</div></div></div>'
                )

            chips_html += '</div>'
            st.markdown(chips_html, unsafe_allow_html=True)
            
           # === ΝΕΟ ΚΟΜΜΑΤΙ: Album Track Statistics ===
            if st.session_state.quick_rate_mode:
                st.markdown(f'<div id="album-stats-wrapper">{get_album_stats_html(detail_id, selected_user_id)}</div>', unsafe_allow_html=True)
            
            c_left, c_right = st.columns([1.2, 1.0])
            
            with c_left:
                c_hdr, c_sort = st.columns([2.5, 1])
                with c_hdr:
                    st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Album Tracks</div>', unsafe_allow_html=True)
                with c_sort:
                    sort_album_tracks = st.selectbox("Sort", ["Streams", "Hours", "Rating"], index=0, label_visibility="collapsed", key=f"sort_al_{detail_id}")

                df_tracks = run_query("""
                    WITH TrackArtists AS (
                        SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
                        FROM song_artists sa
                        JOIN artists a ON a.id = sa.artist_id
                        GROUP BY sa.song_id
                    )
                    SELECT so.id AS song_id, so.title AS song_title,
                           COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
                           COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    LEFT JOIN TrackArtists ta ON ta.song_id = so.id
                    WHERE so.album_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY so.id, so.title, ta.all_artists, so.image_url
                """, {"aid": detail_id, **F})
                
                if not df_tracks.empty:
                    # Πρώτα φορτώνουμε τα ratings στη μνήμη αν δεν υπάρχουν
                    R.preload_ratings(selected_user_id, "song", df_tracks["song_id"].tolist())
                    
                    # Δυναμικό Sorting μέσω Pandas για να έχουμε τα απολύτως live δεδομένα
                    if sort_album_tracks == "Rating":
                        df_tracks["rating"] = df_tracks["song_id"].apply(
                            lambda x: st.session_state.get(f"rating_val_song_{x}_{selected_user_id}", 0.0)
                        )
                        df_tracks["_mem_weight"] = df_tracks["song_id"].apply(
                            lambda x: st.session_state.get(f"sort_weight_song_{x}_{selected_user_id}", 0.0)
                        )
                        df_tracks = df_tracks.sort_values(by=["rating", "_mem_weight", "streams"], ascending=[False, False, False]).reset_index(drop=True)
                    elif sort_album_tracks == "Hours":
                        df_tracks = df_tracks.sort_values(by=["hours_played", "streams"], ascending=[False, False]).reset_index(drop=True)
                    else:
                        df_tracks = df_tracks.sort_values(by=["streams", "hours_played"], ascending=[False, False]).reset_index(drop=True)

                    render_list_v2(df_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song", **qr_kwargs)
                else:
                    st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found in this period</div>', unsafe_allow_html=True)
            with c_right:
                # --- 1. ΝΕΟ: Συνολική Εξέλιξη Ολόκληρου του Album ---
                st.markdown('<div class="chart-container" style="margin-top: 0;"><div class="chart-title">📈 Album Total Evolution</div>', unsafe_allow_html=True)
                df_album_total_trend = run_query("""
                    SELECT DATE_TRUNC('month', s.played_at) AS period, COUNT(*) AS stream_count,
                           ROUND(SUM(s.ms_played)/3600000.0, 2) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    WHERE so.album_id = :aid 
                      AND s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                    GROUP BY 1 ORDER BY 1
                """, {"aid": detail_id, **F})
                
                if not df_album_total_trend.empty:
                    st.plotly_chart(chart_trend(df_album_total_trend), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
                st.markdown('</div>', unsafe_allow_html=True)

                # --- 2. ΥΠΑΡΧΟΝ: Εξέλιξη των Top 5 Tracks ---
                st.markdown('<div class="chart-container"><div class="chart-title">📊 Top 5 Tracks Evolution</div>', unsafe_allow_html=True)
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
                    st.plotly_chart(chart_multi_trend(df_album_trend), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
                st.markdown('</div>', unsafe_allow_html=True)

                # --- 3. ΥΠΑΡΧΟΝ: Peak Hours ---
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
                        use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

                # --- 4. ΥΠΑΡΧΟΝ: Active Days ---
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
                        use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
                    )
                st.markdown('</div>', unsafe_allow_html=True)

    elif detail_type == "genre":
        genre_match_sql = """
            (so.primary_genre ILIKE :genre OR al.primary_genre ILIKE :genre OR EXISTS (
                SELECT 1 FROM album_genres ag2 
                JOIN genres g2 ON g2.id = ag2.genre_id 
                WHERE ag2.album_id = so.album_id AND g2.name ILIKE :genre
            ))
        """
        
        genre_info = run_query(f"""
            SELECT COUNT(s.id) AS streams, ROUND(SUM(s.ms_played)/3600000.0, 2) AS hours,
                   COUNT(DISTINCT s.song_id) AS unique_songs,
                   COUNT(DISTINCT sa.artist_id) AS unique_artists
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND {genre_match_sql}
        """, {"genre": detail_id, **F})

        if not genre_info.empty:
            row = genre_info.iloc[0]
            render_detail_header(
                type_label="Genre",
                title=str(detail_id).title(),
                subtitle="Genre Explorer",
                icon="🎸",
                stats=[
                    {"raw": int(row['streams'] or 0), "label": "Streams"},
                    {"raw": float(row['hours'] or 0), "decimals": 1, "suffix": "h", "label": "Listened"},
                    {"raw": int(row['unique_artists'] or 0), "label": "Artists"},
                    {"raw": int(row['unique_songs'] or 0), "label": "Songs"},
                ]
            )

            c1, c2, c3 = st.columns([1.2, 1, 1.2])

            with c1:
                st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
                df_tracks = run_query(f"""
                    WITH TrackArtists AS (
                        SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
                        FROM song_artists sa
                        JOIN artists a ON a.id = sa.artist_id
                        GROUP BY sa.song_id
                    )
                    SELECT so.id AS song_id, so.title AS song_title,
                           COALESCE(ta.all_artists, 'Unknown') AS main_artist, MAX(so.image_url) AS image_url,
                           COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    LEFT JOIN albums al ON al.id = so.album_id
                    LEFT JOIN TrackArtists ta ON ta.song_id = so.id
                    WHERE s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                      AND {genre_match_sql}
                    GROUP BY so.id, so.title, ta.all_artists
                    ORDER BY streams DESC LIMIT 10
                """, {"genre": detail_id, **F})
                if not df_tracks.empty:
                    R.preload_ratings(selected_user_id, "song", df_tracks["song_id"].tolist())
                    render_list_v2(df_tracks, "song_title", "main_artist", "streams", "hours_played", "song_id", "song", **qr_kwargs)
                else:
                    st.markdown('<div class="empty-state"><div class="icon">📭</div>No tracks found</div>', unsafe_allow_html=True)

            with c2:
                st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)
                df_artists = run_query(f"""
                    SELECT a.id AS artist_id, a.name AS artist_name, MAX(a.image_url) AS image_url,                            COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    LEFT JOIN albums al ON al.id = so.album_id
                    JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                    JOIN artists a ON a.id = sa.artist_id
                    WHERE s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                      AND {genre_match_sql}
                    GROUP BY a.id, a.name
                    ORDER BY streams DESC LIMIT 10
                """, {"genre": detail_id, **F})
                if not df_artists.empty:
                    df_artists["sub"] = "Artist"
                    # --- ΠΡΟΣΘΗΚΗ: Φορτώνουμε τα ratings και περνάμε τα qr_kwargs ---
                    R.preload_ratings(selected_user_id, "artist", df_artists["artist_id"].tolist())
                    render_list_v2(df_artists, "artist_name", "sub", "streams", "hours_played", "artist_id", "artist", **qr_kwargs)
                else:
                    st.markdown('<div class="empty-state"><div class="icon">📭</div>No artists found</div>', unsafe_allow_html=True)

            with c3:
                st.markdown('<div class="section-header" style="margin-top: 0;"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)
                df_albums = run_query(f"""
                    SELECT al.id AS album_id, al.title AS album_title, MAX(so.image_url) AS image_url,
                           COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
                    FROM streams s
                    JOIN songs so ON so.id = s.song_id
                    JOIN albums al ON al.id = so.album_id
                    WHERE s.played_at::date BETWEEN :start_date AND :end_date
                      AND s.user_id = :user_id
                      AND {genre_match_sql}
                    GROUP BY al.id, al.title
                    ORDER BY streams DESC LIMIT 10
                """, {"genre": detail_id, **F})
                if not df_albums.empty:
                    df_albums["sub"] = "Album"
                    R.preload_ratings(selected_user_id, "album", df_albums["album_id"].tolist())
                    render_list_v2(df_albums, "album_title", "sub", "streams", "hours_played", "album_id", "album", **qr_kwargs)
                else:
                    st.markdown('<div class="empty-state"><div class="icon">📭</div>No albums found</div>', unsafe_allow_html=True)

    elif detail_type == "season":
        safe_id = str(detail_id).title()
        if safe_id in SEASON_META:
            meta = SEASON_META[safe_id]
            months = meta["months"]
            month_options = [f"All of {safe_id}"] + [MONTH_NAMES[m] for m in months]
            selected_month = st.selectbox(
                "📅 Narrow down to a specific month", month_options,
                key=f"month_filter_{safe_id}"
            )

            if selected_month == month_options[0]:
                month_list = ",".join(str(m) for m in months)
                cond = f"EXTRACT(MONTH FROM s.played_at) IN ({month_list})"
                extra_params = {}
                redirect_info = {"season": safe_id} # <--- ΠΡΟΣΘΗΚΗ
                subtitle = f"Everything you played during {safe_id.lower()}"
            else:
                month_num = next(m for m in months if MONTH_NAMES[m] == selected_month)
                cond = "EXTRACT(MONTH FROM s.played_at) = :month_val"
                extra_params = {"month_val": month_num}
                redirect_info = {"month": month_num}
                subtitle = f"Everything you played in {selected_month}"

            render_dimension_detail(
                extra_where=cond,
                extra_params=extra_params,
                redirect_info=redirect_info,
                type_label="Season", title=safe_id,
                subtitle=subtitle,
                icon=meta["icon"],
                image_url=meta.get("image")
            )        
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Unknown season</div>', unsafe_allow_html=True)

    elif detail_type == "tod":
        safe_id = str(detail_id).title()
        if safe_id in TOD_META:
            meta = TOD_META[safe_id]
            hours_in_range = meta["hours"]
            hour_options = [f"All {safe_id} ({meta['range']})"] + [f"{h:02d}:00" for h in hours_in_range]
            selected_hour = st.selectbox(
                "🕐 Narrow down to a specific hour", hour_options,
                key=f"hour_filter_{safe_id}"
            )

            if selected_hour == hour_options[0]:
                if safe_id == "Night":
                    cond = "(EXTRACT(HOUR FROM s.played_at) >= 21 OR EXTRACT(HOUR FROM s.played_at) < 5)"
                else:
                    cond = f"EXTRACT(HOUR FROM s.played_at) BETWEEN {hours_in_range[0]} AND {hours_in_range[-1]}"
                extra_params = {}
                redirect_info = {"tod": safe_id}
                subtitle = f"Streams during {meta['range']}"
            else:
                hour_val = int(selected_hour.split(":")[0])
                cond = "EXTRACT(HOUR FROM s.played_at) = :hour_val"
                extra_params = {"hour_val": hour_val}
                redirect_info = {"hour": hour_val}
                subtitle = f"Streams at {selected_hour}"

            render_dimension_detail(
                extra_where=cond,
                extra_params=extra_params,
                redirect_info=redirect_info,
                type_label="Time of Day", title=safe_id,
                subtitle=subtitle,
                icon=meta["icon"],
                image_url=meta.get("image")
            )
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>Unknown time of day</div>', unsafe_allow_html=True)

    elif detail_type == "year":
        try:
            year_val = int(detail_id)
            if 1900 <= year_val <= 2100:
                month_options = ["All Year"] + list(MONTH_NAMES.values())
                selected_month = st.selectbox(
                    "📅 Filter by month", month_options,
                    key=f"year_month_filter_{detail_id}"
                )

                if selected_month == "All Year":
                    cond = "EXTRACT(YEAR FROM s.played_at) = :year"
                    extra_params = {"year": year_val}
                    redirect_info = {"year": year_val}
                    subtitle = "Your year in review"
                else:
                    month_num = next(k for k, v in MONTH_NAMES.items() if v == selected_month)
                    cond = "EXTRACT(YEAR FROM s.played_at) = :year AND EXTRACT(MONTH FROM s.played_at) = :month_val"
                    extra_params = {"year": year_val, "month_val": month_num}
                    redirect_info = {"year": year_val, "month": month_num}
                    subtitle = f"{selected_month} {year_val}"

                render_dimension_detail(
                    extra_where=cond,
                    extra_params=extra_params,
                    redirect_info=redirect_info,
                    type_label="Year", title=str(year_val),
                    subtitle=subtitle, icon="📆"
                )
        except ValueError:
            pass
    elif detail_type == "ratings_full":
            kind_key = detail_id if detail_id in ("song", "album", "artist") else "song"
            R.render_full_ratings_list(selected_user_id, kind_key)
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
            {"icon": "⏱️", "title": "Listening Time", "raw": float(row['total_hours'] or 0), "decimals": 1, "unit": "hrs"},
            {"icon": "🎵", "title": "Total Streams", "raw": int(row['total_streams'] or 0)},
            {"icon": "🎤", "title": "Unique Artists", "raw": int(row['unique_artists'] or 0)},
            {"icon": "🎶", "title": "Unique Songs", "raw": int(row['unique_songs'] or 0)},
        ])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-header"><span class="icon">🎵</span>Top Tracks</div>', unsafe_allow_html=True)
        df_top_tracks = run_query("""
            WITH TrackArtists AS (
                SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
                FROM song_artists sa
                JOIN artists a ON a.id = sa.artist_id
                GROUP BY sa.song_id
            )
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY so.id, so.title, ta.all_artists, so.image_url ORDER BY streams DESC LIMIT 5;
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
        st.plotly_chart(chart_trend(df_trend), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
    st.markdown('</div>', unsafe_allow_html=True)

elif current_tab == "tracks":
    st.markdown('<div class="section-header"><span class="icon">🎵</span>Track Explorer</div>', unsafe_allow_html=True)

    col_search, col_sort, col_limit = st.columns([3, 1, 1])
    search_term = col_search.text_input("🔍 Search tracks...", placeholder="e.g. Starboy, Red Moon...", label_visibility="collapsed", key="search_tracks")
    sort_by = col_sort.selectbox("Sort", ["Streams", "Hours"], index=0, label_visibility="collapsed", key="sort_tracks")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200, 500], index=0, label_visibility="collapsed")

    ry_min, ry_max = get_release_year_bounds()
    release_year_options = ["All Release Years"] + [str(y) for y in range(ry_max, ry_min - 1, -1)]

    with st.container(key="filter_bar_row"):
        col_month, col_hour, col_ryear = st.columns(3)   # ή st.columns(2) στο artists
        with col_month:
            st.markdown('<div class="filter-label">📅 Month</div>', unsafe_allow_html=True)
            filter_month = st.selectbox("Month", MONTH_FILTER_OPTIONS, label_visibility="collapsed", key="filter_month_tracks")
        with col_hour:
            st.markdown('<div class="filter-label">🕐 Hour of Day</div>', unsafe_allow_html=True)
            filter_hour = st.selectbox("Hour", HOUR_FILTER_OPTIONS, label_visibility="collapsed", key="filter_hour_tracks")
        with col_ryear:
            st.markdown('<div class="filter-label">🗓️ Release Year</div>', unsafe_allow_html=True)
            filter_ryear = st.selectbox("Release Year", release_year_options, label_visibility="collapsed", key="filter_release_year_tracks")

    query_params = {**F, "limit": display_limit}
    order_col = "COUNT(s.id)" if sort_by == "Streams" else "SUM(s.ms_played)"

    extra_conds = ""
    if filter_month != "All Months":
        if "Winter" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (12, 1, 2)"
        elif "Spring" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (3, 4, 5)"
        elif "Summer" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (6, 7, 8)"
        elif "Autumn" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (9, 10, 11)"
        else:
            month_num = next(k for k, v in MONTH_NAMES.items() if v == filter_month)
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) = :f_month"
            query_params["f_month"] = month_num
    if filter_hour != "All Hours":
        if "Night" in filter_hour:
            extra_conds += " AND (EXTRACT(HOUR FROM s.played_at) >= 21 OR EXTRACT(HOUR FROM s.played_at) < 5)"
        elif "Morning" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 5 AND 11"
        elif "Afternoon" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 12 AND 16"
        elif "Evening" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 17 AND 20"
        else:
            hour_num = int(filter_hour.split(":")[0])
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) = :f_hour"
            query_params["f_hour"] = hour_num
    if filter_ryear != "All Release Years":
        extra_conds += " AND EXTRACT(YEAR FROM so.release_date) = :f_ryear"
        query_params["f_ryear"] = int(filter_ryear)

    active_filter_chips = []
    if filter_month != "All Months": active_filter_chips.append(f"📅 {filter_month}")
    if filter_hour != "All Hours": active_filter_chips.append(f"🕐 {filter_hour}")
    if filter_ryear != "All Release Years": active_filter_chips.append(f"🗓️ Released {filter_ryear}")
    if active_filter_chips:
        st.markdown(
            f'<div style="color:{TEXT_MID}; font-size:0.85rem; margin: 4px 0 12px;">Filtering by: {" · ".join(active_filter_chips)}</div>',
            unsafe_allow_html=True
        )

    base_tracks_query = """
        WITH TrackArtists AS (
            SELECT sa.song_id, STRING_AGG(a.name, ', ' ORDER BY sa.is_feature ASC) AS all_artists
            FROM song_artists sa
            JOIN artists a ON a.id = sa.artist_id
            GROUP BY sa.song_id
        )
    """

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_songs = run_query(base_tracks_query + f"""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND (
                  so.title ILIKE :search 
                  OR EXISTS (
                      SELECT 1 FROM song_artists sa_search 
                      JOIN artists a_search ON a_search.id = sa_search.artist_id 
                      WHERE sa_search.song_id = so.id AND a_search.name ILIKE :search
                  )
              )
              {extra_conds}
            GROUP BY so.id, so.title, ta.all_artists, so.image_url
            ORDER BY {order_col} DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_songs.empty:
            R.preload_ratings(selected_user_id, "song", df_songs["song_id"].tolist())
            render_list_v2(df_songs, "song_title", "main_artist", "streams", "hours_played",
               "song_id", "song", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🔍</div>No tracks found</div>', unsafe_allow_html=True)

    else:
        df_songs = run_query(base_tracks_query + f"""
            SELECT so.id AS song_id, so.title AS song_title,
                   COALESCE(ta.all_artists, 'Unknown') AS main_artist, so.image_url,
                   COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 3) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY {order_col} DESC, SUM(s.ms_played) DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN TrackArtists ta ON ta.song_id = so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              {extra_conds}
            GROUP BY so.id, so.title, ta.all_artists, so.image_url
            ORDER BY {order_col} DESC LIMIT :limit;
        """, query_params)

        if not df_songs.empty:
           R.preload_ratings(selected_user_id, "song", df_songs["song_id"].tolist())
           render_list_v2(df_songs, "song_title", "main_artist", "streams", "hours_played",
               "song_id", "song", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🔍</div>No tracks found</div>', unsafe_allow_html=True)

elif current_tab == "artists":
    st.markdown('<div class="section-header"><span class="icon">🎤</span>Top Artists</div>', unsafe_allow_html=True)

    col_search, col_sort, col_limit = st.columns([3, 1, 1])
    search_term = col_search.text_input("🔍 Search artists...", placeholder="e.g. Drake, Nicki Minaj...", label_visibility="collapsed", key="search_artists")
    sort_by = col_sort.selectbox("Sort", ["Streams", "Hours"], index=0, label_visibility="collapsed", key="sort_artists")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    # --- ΠΡΟΣΘΗΚΗ ΦΙΛΤΡΩΝ ---
    with st.container(key="filter_bar_row"):
        col_month, col_hour, col_ryear = st.columns(3)   # ή st.columns(2) στο artists
        with col_month:
            st.markdown('<div class="filter-label">📅 Month</div>', unsafe_allow_html=True)
            filter_month = st.selectbox("Month", MONTH_FILTER_OPTIONS, label_visibility="collapsed", key="filter_month_artists")
        with col_hour:
            st.markdown('<div class="filter-label">🕐 Hour of Day</div>', unsafe_allow_html=True)
            filter_hour = st.selectbox("Hour", HOUR_FILTER_OPTIONS, label_visibility="collapsed", key="filter_hour_artists")

    query_params = {**F, "limit": display_limit}
    order_col = "COUNT(s.id)" if sort_by == "Streams" else "SUM(s.ms_played)"

    extra_conds = ""
    if filter_month != "All Months":
        if "Winter" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (12, 1, 2)"
        elif "Spring" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (3, 4, 5)"
        elif "Summer" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (6, 7, 8)"
        elif "Autumn" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (9, 10, 11)"
        else:
            month_num = next(k for k, v in MONTH_NAMES.items() if v == filter_month)
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) = :f_month"
            query_params["f_month"] = month_num
    if filter_hour != "All Hours":
        if "Night" in filter_hour:
            extra_conds += " AND (EXTRACT(HOUR FROM s.played_at) >= 21 OR EXTRACT(HOUR FROM s.played_at) < 5)"
        elif "Morning" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 5 AND 11"
        elif "Afternoon" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 12 AND 16"
        elif "Evening" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 17 AND 20"
        else:
            hour_num = int(filter_hour.split(":")[0])
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) = :f_hour"
            query_params["f_hour"] = hour_num

    active_filter_chips = []
    if filter_month != "All Months": active_filter_chips.append(f"📅 {filter_month}")
    if filter_hour != "All Hours": active_filter_chips.append(f"🕐 {filter_hour}")
    if active_filter_chips:
        st.markdown(
            f'<div style="color:{TEXT_MID}; font-size:0.85rem; margin: 4px 0 12px;">Filtering by: {" · ".join(active_filter_chips)}</div>',
            unsafe_allow_html=True
        )

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_artists = run_query(f"""
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND a.name ILIKE :search
              {extra_conds}
            GROUP BY a.id, a.name, a.image_url
            ORDER BY {order_col} DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_artists.empty:
            df_artists["subtitle"] = "Artist"
            # Φορτώνουμε τα ratings και περνάμε το **qr_kwargs
            R.preload_ratings(selected_user_id, "artist", df_artists["artist_id"].tolist())
            render_list_v2(df_artists, "artist_name", "subtitle", "streams", "hours_played",
               "artist_id", "artist", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🎤</div>No artists found</div>', unsafe_allow_html=True)

    else:
        df_artists = run_query(f"""
        SELECT a.id AS artist_id, a.name AS artist_name, a.image_url,
            COUNT(s.id) AS streams,
            ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
            ROW_NUMBER() OVER (ORDER BY {order_col} DESC) AS global_rank
        FROM streams s
        JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        JOIN artists a ON a.id = sa.artist_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
          {extra_conds}
        GROUP BY a.id, a.name, a.image_url
        ORDER BY {order_col} DESC LIMIT :limit;
    """, query_params)

        if not df_artists.empty:
            df_artists["subtitle"] = "Artist"
            # Φορτώνουμε τα ratings και περνάμε το **qr_kwargs
            R.preload_ratings(selected_user_id, "artist", df_artists["artist_id"].tolist())
            render_list_v2(df_artists, "artist_name", "subtitle", "streams", "hours_played",
               "artist_id", "artist", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)
        else:
            st.markdown('<div class="empty-state"><div class="icon">🎤</div>No artists found</div>', unsafe_allow_html=True)
elif current_tab == "albums":
    st.markdown('<div class="section-header"><span class="icon">💿</span>Top Albums</div>', unsafe_allow_html=True)

    col_search, col_sort, col_limit = st.columns([3, 1, 1])
    search_term = col_search.text_input("🔍 Search albums...", placeholder="e.g. Take Care, UTOPIA...", label_visibility="collapsed", key="search_albums")
    sort_by = col_sort.selectbox("Sort", ["Streams", "Hours"], index=0, label_visibility="collapsed", key="sort_albums")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    # --- ΠΡΟΣΘΗΚΗ ΦΙΛΤΡΩΝ ---
    ry_min, ry_max = get_release_year_bounds()
    release_year_options = ["All Release Years"] + [str(y) for y in range(ry_max, ry_min - 1, -1)]

    with st.container(key="filter_bar_row"):
        col_month, col_hour, col_ryear = st.columns(3)   # ή st.columns(2) στο artists
        with col_month:
            st.markdown('<div class="filter-label">📅 Month</div>', unsafe_allow_html=True)
            filter_month = st.selectbox("Month", MONTH_FILTER_OPTIONS, label_visibility="collapsed", key="filter_month_albums")
        with col_hour:
            st.markdown('<div class="filter-label">🕐 Hour of Day</div>', unsafe_allow_html=True)
            filter_hour = st.selectbox("Hour", HOUR_FILTER_OPTIONS, label_visibility="collapsed", key="filter_hour_albums")
        with col_ryear:
            st.markdown('<div class="filter-label">🗓️ Release Year</div>', unsafe_allow_html=True)
            filter_ryear = st.selectbox("Release Year", release_year_options, label_visibility="collapsed", key="filter_release_year_albums")

    query_params = {**F, "limit": display_limit}
    order_col = "COUNT(s.id)" if sort_by == "Streams" else "SUM(s.ms_played)"

    extra_conds = ""
    if filter_month != "All Months":
        if "Winter" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (12, 1, 2)"
        elif "Spring" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (3, 4, 5)"
        elif "Summer" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (6, 7, 8)"
        elif "Autumn" in filter_month:
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) IN (9, 10, 11)"
        else:
            month_num = next(k for k, v in MONTH_NAMES.items() if v == filter_month)
            extra_conds += " AND EXTRACT(MONTH FROM s.played_at) = :f_month"
            query_params["f_month"] = month_num
            
    if filter_hour != "All Hours":
        if "Night" in filter_hour:
            extra_conds += " AND (EXTRACT(HOUR FROM s.played_at) >= 21 OR EXTRACT(HOUR FROM s.played_at) < 5)"
        elif "Morning" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 5 AND 11"
        elif "Afternoon" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 12 AND 16"
        elif "Evening" in filter_hour:
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) BETWEEN 17 AND 20"
        else:
            hour_num = int(filter_hour.split(":")[0])
            extra_conds += " AND EXTRACT(HOUR FROM s.played_at) = :f_hour"
            query_params["f_hour"] = hour_num
    if filter_ryear != "All Release Years":
        extra_conds += " AND EXTRACT(YEAR FROM al.release_date) = :f_ryear"
        query_params["f_ryear"] = int(filter_ryear)

    active_filter_chips = []
    if filter_month != "All Months": active_filter_chips.append(f"📅 {filter_month}")
    if filter_hour != "All Hours": active_filter_chips.append(f"🕐 {filter_hour}")
    if filter_ryear != "All Release Years": active_filter_chips.append(f"🗓️ Released {filter_ryear}")
    if active_filter_chips:
        st.markdown(
            f'<div style="color:{TEXT_MID}; font-size:0.85rem; margin: 4px 0 12px;">Filtering by: {" · ".join(active_filter_chips)}</div>',
            unsafe_allow_html=True
        )

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
        df_albums = run_query(base_query + f"""
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
              AND (al.title ILIKE :search OR aa.artist_name ILIKE :search)
              {extra_conds}
            GROUP BY al.id, al.title, aa.artist_name
            ORDER BY {order_col} DESC
            LIMIT :limit;
        """, query_params)
        
        if not df_albums.empty:
            R.preload_ratings(selected_user_id, "album", df_albums["album_id"].tolist())
            render_list_v2(df_albums, "album_title", "artist_name", "streams", "hours_played",
               "album_id", "album", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)

        else:
            st.markdown('<div class="empty-state"><div class="icon">💿</div>No albums found</div>', unsafe_allow_html=True)
    else:
        df_albums = run_query(base_query + f"""
            SELECT al.id AS album_id, COALESCE(al.title, 'Unknown Album') AS album_title,
                   COALESCE(aa.artist_name, 'Unknown Artist') AS artist_name,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played,
                   ROW_NUMBER() OVER (ORDER BY {order_col} DESC) AS global_rank
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            LEFT JOIN TrueAlbumArtists aa ON aa.album_id = al.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              {extra_conds}
            GROUP BY al.id, al.title, aa.artist_name
            ORDER BY {order_col} DESC LIMIT :limit;
        """, query_params)

        if not df_albums.empty:
            R.preload_ratings(selected_user_id, "album", df_albums["album_id"].tolist())
            render_list_v2(df_albums, "album_title", "artist_name", "streams", "hours_played",
               "album_id", "album", rank_col="global_rank",
               reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07, **qr_kwargs)
        else:
            st.markdown('<div class="empty-state"><div class="icon">💿</div>No albums found</div>', unsafe_allow_html=True)

elif current_tab == "genres":
    st.markdown('<div class="section-header"><span class="icon">🎸</span>Top Genres</div>', unsafe_allow_html=True)

    col_search, col_limit = st.columns([3, 1])
    search_term = col_search.text_input("🔍 Search genres...", placeholder="e.g. Rap, Pop...", label_visibility="collapsed", key="search_genres")
    display_limit = col_limit.selectbox("Limit", [50, 100, 200], index=0, label_visibility="collapsed")

    query_params = {**F, "limit": display_limit}

    base_genre_query = """
        WITH StreamBase AS (
            SELECT s.id AS stream_id, s.ms_played, sa.artist_id, 
                   so.primary_genre AS song_genre, al.primary_genre AS album_genre, so.album_id
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
        ),
        Unrolled AS (
            SELECT stream_id, ms_played, artist_id, song_genre AS genre_name FROM StreamBase WHERE song_genre IS NOT NULL
            UNION ALL
            SELECT stream_id, ms_played, artist_id, album_genre FROM StreamBase WHERE album_genre IS NOT NULL
            UNION ALL
            SELECT sb.stream_id, sb.ms_played, sb.artist_id, g.name 
            FROM StreamBase sb
            JOIN album_genres ag ON ag.album_id = sb.album_id
            JOIN genres g ON g.id = ag.genre_id
        ),
        UniqueStreamGenres AS (
            SELECT DISTINCT stream_id, ms_played, artist_id, INITCAP(TRIM(genre_name)) AS genre_name
            FROM Unrolled
            WHERE genre_name IS NOT NULL AND LOWER(genre_name) != 'unknown'
        )
        SELECT 
            genre_name AS genre_id, 
            genre_name,
            CAST(COUNT(DISTINCT artist_id) AS TEXT) || ' Artists' AS subtitle,
            COUNT(stream_id) AS streams,
            ROUND(SUM(ms_played) / 3600000.0, 2) AS hours_played
        FROM UniqueStreamGenres
        WHERE 1=1
    """

    if search_term:
        query_params["search"] = f"%{search_term}%"
        df_genres = run_query(base_genre_query + """
            AND genre_name ILIKE :search
            GROUP BY genre_name
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)
    else:
        df_genres = run_query(base_genre_query + """
            GROUP BY genre_name
            ORDER BY streams DESC LIMIT :limit;
        """, query_params)

    if not df_genres.empty:
        render_list_v2(df_genres, "genre_name", "subtitle", "streams", "hours_played",
               "genre_id", "genre", reveal_top_n=10, reveal_delay_base=0.05, reveal_delay_step=0.07)
    else:
        st.markdown('<div class="empty-state"><div class="icon">🎸</div>No genres found</div>', unsafe_allow_html=True)

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
        st.plotly_chart(chart_heatmap(df_heatmap), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
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
                use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
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
                use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
            )
        st.markdown('</div>', unsafe_allow_html=True)

    # ─── 🌍 Seasonal Vibes ───
    st.markdown('<div class="section-header" style="margin-top: 8px;"><span class="icon">🌍</span>Seasonal Vibes</div>', unsafe_allow_html=True)
    df_seasons_raw = run_query("""
        SELECT
            COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (12,1,2)) AS winter_streams,
            ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (12,1,2)), 0) / 3600000.0, 2) AS winter_hours,
            COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (3,4,5)) AS spring_streams,
            ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (3,4,5)), 0) / 3600000.0, 2) AS spring_hours,
            COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (6,7,8)) AS summer_streams,
            ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (6,7,8)), 0) / 3600000.0, 2) AS summer_hours,
            COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (9,10,11)) AS autumn_streams,
            ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(MONTH FROM played_at) IN (9,10,11)), 0) / 3600000.0, 2) AS autumn_hours
        FROM streams
        WHERE played_at::date BETWEEN :start_date AND :end_date
          AND user_id = :user_id;
    """, F)
    if not df_seasons_raw.empty:
        r = df_seasons_raw.iloc[0]
        df_seasons = pd.DataFrame([
            {"season": s, "stream_count": int(r[f"{s.lower()}_streams"] or 0), "hours_played": float(r[f"{s.lower()}_hours"] or 0)}
            for s in ["Winter", "Spring", "Summer", "Autumn"]
        ])
    else:
        df_seasons = pd.DataFrame(columns=["season", "stream_count", "hours_played"])
    render_season_cards(df_seasons)

    # ─── 🌙 Time of Day + 📆 Yearly Breakdown ───
    c3, c4 = st.columns([1, 1.4])

    with c3:
        st.markdown('<div class="section-header"><span class="icon">🌙</span>Time of Day</div>', unsafe_allow_html=True)
        df_tod_raw = run_query("""
            SELECT
                COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM played_at) >= 21 OR EXTRACT(HOUR FROM played_at) < 5) AS night_streams,
                ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(HOUR FROM played_at) >= 21 OR EXTRACT(HOUR FROM played_at) < 5), 0) / 3600000.0, 2) AS night_hours,
                COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 5 AND 11) AS morning_streams,
                ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 5 AND 11), 0) / 3600000.0, 2) AS morning_hours,
                COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 12 AND 16) AS afternoon_streams,
                ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 12 AND 16), 0) / 3600000.0, 2) AS afternoon_hours,
                COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 17 AND 20) AS evening_streams,
                ROUND(COALESCE(SUM(ms_played) FILTER (WHERE EXTRACT(HOUR FROM played_at) BETWEEN 17 AND 20), 0) / 3600000.0, 2) AS evening_hours
            FROM streams
            WHERE played_at::date BETWEEN :start_date AND :end_date
              AND user_id = :user_id;
        """, F)

        tod_order = ["Night", "Morning", "Afternoon", "Evening"]
        if not df_tod_raw.empty:
            r = df_tod_raw.iloc[0]
            df_tod = pd.DataFrame([
                {"time_of_day": t, "stream_count": int(r[f"{t.lower()}_streams"] or 0), "hours_played": float(r[f"{t.lower()}_hours"] or 0)}
                for t in tod_order
            ])
        else:
            df_tod = pd.DataFrame(columns=["time_of_day", "stream_count", "hours_played"])

        if not df_tod.empty and df_tod["stream_count"].sum() > 0:
            df_tod_chart = df_tod[df_tod["stream_count"] > 0]
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.plotly_chart(
                chart_donut(
                    df_tod_chart["time_of_day"].tolist(),
                    df_tod_chart["stream_count"].tolist(),
                    [TOD_META[t]["color"] for t in df_tod_chart["time_of_day"]]
                ),
                use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False}
            )
            st.markdown('</div>', unsafe_allow_html=True)
        render_time_of_day_cards(df_tod)

    with c4:
        st.markdown('<div class="section-header"><span class="icon">📆</span>Yearly Breakdown</div>', unsafe_allow_html=True)
        df_years = run_query("""
            SELECT EXTRACT(YEAR FROM played_at)::INT AS year, COUNT(*) AS stream_count,
                   ROUND(SUM(ms_played) / 3600000.0, 2) AS hours_played
            FROM streams
            WHERE played_at::date BETWEEN :start_date AND :end_date
              AND user_id = :user_id
            GROUP BY 1 ORDER BY 1;
        """, F)
        st.markdown('<div class="chart-container"><div class="chart-title">📈 Streams per Year</div>', unsafe_allow_html=True)
        if not df_years.empty:
            st.plotly_chart(chart_year_bar(df_years), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
            df_years_list = df_years.copy()
            df_years_list["year_str"] = df_years_list["year"].astype(str)
            df_years_list["subtitle"] = "Year"
            df_years_list = df_years_list.sort_values("stream_count", ascending=False).reset_index(drop=True)
            df_years_list["global_rank"] = df_years_list.index + 1
            render_list_v2(df_years_list, "year_str", "subtitle", "stream_count", "hours_played",
                           "year_str", "year", rank_col="global_rank")
        else:
            st.markdown('<div class="empty-state"><div class="icon">📭</div>No data for this period</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ─── ⏱️ Song Length & Release Era ───
    st.markdown('<div class="section-header" style="margin-top: 8px;"><span class="icon">⏱️</span>Song Length &amp; Release Era</div>', unsafe_allow_html=True)

    df_len_kpi = run_query("""
        SELECT
            ROUND(AVG(so.duration_ms) / 60000.0, 2) AS avg_duration_min,
            ROUND(AVG(EXTRACT(YEAR FROM s.played_at) - EXTRACT(YEAR FROM so.release_date))::numeric, 1) AS avg_song_age,
            ROUND(SUM(so.duration_ms) FILTER (WHERE so.duration_ms IS NOT NULL) / 3600000.0, 1) AS total_hours_known
        FROM streams s
        JOIN songs so ON so.id = s.song_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id
          AND so.duration_ms IS NOT NULL;
    """, F)

    df_release_kpi = run_query("""
        SELECT
            COUNT(DISTINCT so.id) FILTER (WHERE so.release_date IS NOT NULL) AS tracks_with_release,
            MIN(so.release_date) AS oldest_release,
            MAX(so.release_date) AS newest_release
        FROM streams s
        JOIN songs so ON so.id = s.song_id
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id;
    """, F)

    if not df_len_kpi.empty and pd.notnull(df_len_kpi.iloc[0]["avg_duration_min"]):
        rlen = df_len_kpi.iloc[0]
        rrel = df_release_kpi.iloc[0] if not df_release_kpi.empty else None
        oldest_year = pd.to_datetime(rrel["oldest_release"]).year if rrel is not None and pd.notnull(rrel.get("oldest_release")) else "—"
        newest_year = pd.to_datetime(rrel["newest_release"]).year if rrel is not None and pd.notnull(rrel.get("newest_release")) else "—"

        render_kpi_grid([
            {"icon": "⏱️", "title": "Avg Track Length", "raw": float(rlen["avg_duration_min"] or 0), "decimals": 1, "unit": " min"},
            {"icon": "🎂", "title": "Avg Song Age When Played", "raw": float(rlen["avg_song_age"] or 0), "decimals": 1, "unit": " yrs"},
            {"icon": "📻", "title": "Oldest Release Played", "value": str(oldest_year)},
            {"icon": "✨", "title": "Newest Release Played", "value": str(newest_year)},
        ])

        col_decade, col_spot = st.columns([1.4, 1])

        with col_decade:
            st.markdown('<div class="chart-container"><div class="chart-title">🗓️ Streams by Release Decade</div>', unsafe_allow_html=True)
            df_decades = run_query("""
                SELECT (FLOOR(EXTRACT(YEAR FROM so.release_date) / 10) * 10)::INT AS decade,
                       COUNT(s.id) AS stream_count, ROUND(SUM(s.ms_played) / 3600000.0, 2) AS hours_played
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                WHERE s.played_at::date BETWEEN :start_date AND :end_date
                  AND s.user_id = :user_id
                  AND so.release_date IS NOT NULL
                GROUP BY 1 ORDER BY 1;
            """, F)
            if not df_decades.empty:
                decade_labels = [f"{int(d)}s" for d in df_decades["decade"]]
                streams = df_decades["stream_count"].tolist()
                max_val = max(streams) if streams else 0
                colors = [GREEN if v == max_val else "rgba(29,185,84,0.35)" for v in streams]
                fig_decade = go.Figure(go.Bar(
                    x=decade_labels, y=streams, marker_color=colors, marker_line=dict(width=0),
                    customdata=df_decades["hours_played"].tolist(),
                    hovertemplate="<b>%{x}</b><br>%{y:,} streams<br>%{customdata:,.1f}h listened<extra></extra>"
                ))
                st.plotly_chart(themed(fig_decade, xaxis_title="", yaxis_title="Streams", bargap=0.3),
                                 use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
            else:
                st.markdown('<div class="empty-state"><div class="icon">📭</div>No release-date data yet</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_spot:
            df_spot = run_query("""
                SELECT so.id AS song_id, so.title AS song_title, COALESCE(a.name, 'Unknown') AS main_artist,
                       so.image_url, so.duration_ms, so.release_date
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :start_date AND :end_date
                  AND s.user_id = :user_id
                GROUP BY so.id, so.title, a.name, so.image_url, so.duration_ms, so.release_date;
            """, F)

            oldest_row = None
            newest_row = None
            longest_row = None
            if not df_spot.empty:
                df_release_rows = df_spot.dropna(subset=["release_date"])
                if not df_release_rows.empty:
                    oldest_row = df_release_rows.loc[df_release_rows["release_date"].idxmin()]
                    newest_row = df_release_rows.loc[df_release_rows["release_date"].idxmax()]
                df_duration_rows = df_spot.dropna(subset=["duration_ms"])
                if not df_duration_rows.empty:
                    longest_row = df_duration_rows.loc[df_duration_rows["duration_ms"].idxmax()]

            fmt_year = lambda v: pd.to_datetime(v).strftime("Released %b %Y")
            fmt_duration = lambda v: f"{int(v)//60000}:{(int(v)%60000)//1000:02d} long"

            row1a, row1b = st.columns(2)
            render_track_spotlight_card(row1a, "Oldest Discovery", "📻", oldest_row, "release_date", fmt_year)
            render_track_spotlight_card(row1b, "Freshest Find", "✨", newest_row, "release_date", fmt_year)
            render_track_spotlight_card(st.container(), "Longest Track Played", "⏳", longest_row, "duration_ms", fmt_duration)
        st.markdown('<div class="empty-state"><div class="icon">📭</div>No track length / release-date data available for this period yet</div>', unsafe_allow_html=True)
elif current_tab == "ratings":
    R.render_ratings_dashboard(selected_user_id, F)
elif current_tab == "friends":
    render_friends_match_tab(
        run_query=run_query,
        user_dict=user_dict,
        min_date=min_date,
        max_date=max_date,
        default_user_id=selected_user_id,
        colors=dict(GREEN=GREEN, TEXT=TEXT, TEXT_MID=TEXT_MID, TEXT_DIM=TEXT_DIM, BG=BG),
    )