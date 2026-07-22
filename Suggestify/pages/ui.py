from __future__ import annotations

import streamlit as st
import pandas as pd
import os
import streamlit.components.v1 as components
from html import escape
from config import *
from types import SimpleNamespace
from urllib.parse import quote
import uuid

def counter_span(value: float, decimals: int = 0, prefix: str = "", suffix: str = "") -> str:
    return (
        f'<span class="count-up" data-target="{value}" data-decimals="{decimals}" '
        f'data-prefix="{escape(prefix)}" data-suffix="{escape(suffix)}">{prefix}0{suffix}</span>'
    )

def inject_counter_script():
    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;
        function animate(el) {
            const target = parseFloat(el.dataset.target || "0");
            const decimals = parseInt(el.dataset.decimals || "0");
            const prefix = el.dataset.prefix || "";
            const suffix = el.dataset.suffix || "";
            const duration = 900, start = performance.now();
            function frame(now) {
                const p = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - p, 3);
                el.textContent = prefix + (target * eased).toLocaleString(undefined,
                    {minimumFractionDigits: decimals, maximumFractionDigits: decimals}) + suffix;
                if (p < 1) requestAnimationFrame(frame);
            }
            requestAnimationFrame(frame);
        }
        function scan() { 
            doc.querySelectorAll('.count-up').forEach(el => {
                const currentTarget = el.dataset.target || "0";
                if (el.dataset.animatedTarget !== currentTarget) {
                    el.dataset.animatedTarget = currentTarget;
                    animate(el);
                }
            }); 
        }
        new MutationObserver(scan).observe(doc.body, {
            childList: true, 
            subtree: true, 
            attributes: true, 
            attributeFilter: ['data-target']
        });
        scan();
    })();
    </script>
    """, height=0)

def load_css():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    css_path = os.path.join(os.path.dirname(current_dir), "static", "styles.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        tokens = {
            "VAR_CARD_HOVER": CARD_HOVER, "VAR_GREEN_GLOW": GREEN_GLOW,
            "VAR_BORDER_HL": BORDER_HL, "VAR_GREEN_DIM": GREEN_DIM,
            "VAR_GREEN_XLO": GREEN_XLO, "VAR_TEXT_MID": TEXT_MID,
            "VAR_TEXT_DIM": TEXT_DIM, "VAR_SURFACE": SURFACE,
            "VAR_BORDER": BORDER, "VAR_GREEN": GREEN,
            "VAR_CARD": CARD, "VAR_TEXT": TEXT, "VAR_BG": BG,
        }
        for key, val in tokens.items():
            css = css.replace(key, val)
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

def inject_custom_css():
    st.markdown(f"""
    <style>
    .block-container {{ padding: 1rem 2rem 6rem !important; max-width: 100% !important; }}
    .main .block-container {{ padding-top: 1rem !important; margin-top: -4.5rem !important; }}
    div[data-testid="stVerticalBlock"] {{ gap: 0.2rem !important; }}
    div[data-testid="column"] {{ gap: 0.5rem !important; }}
    header {{ display: none !important; }}

    .brand-title {{ font-size: 2.2rem !important; font-weight: 800 !important; display: flex; align-items: center; gap: 0.5rem; }}
    .brand-title span {{ font-size: 2.8rem !important; }}

    @keyframes fadeSlideUp {{
        from {{ opacity: 0; transform: translateY(14px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes fadeIn {{
        from {{ opacity: 0; }}
        to   {{ opacity: 1; }}
    }}

    .count-up {{ display: inline-block; font-variant-numeric: tabular-nums; }}

    .list-item {{ transition: transform 0.22s ease, background 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease; }}
    .list-item:hover {{ transform: translateX(5px); background: rgba(255,255,255,0.045); border-color: rgba(29,185,84,0.35); box-shadow: 0 6px 22px rgba(0,0,0,0.28); }}
    .item-art {{ transition: transform 0.25s ease; }}
    .list-item:hover .item-art {{ transform: scale(1.07); }}
    .item-arrow {{ transition: transform 0.25s ease, color 0.25s ease; display: inline-block; }}
    .list-item:hover .item-arrow {{ transform: translateX(5px); color: {GREEN}; }}
    .stat-value {{ transition: color 0.2s ease; }}
    
    a.custom-link:has(.list-item-has-rating) {{ margin-bottom: 0 !important; }}
    .list-item-has-rating {{ border-radius: 14px 14px 0 0 !important; border-bottom: none !important; }}

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

    .season-card {{ position: relative; overflow: visible !important; text-align: center; }}
    .season-badge {{
        position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
        background: linear-gradient(135deg, {GREEN}, {GREEN_DIM});
        color: #000; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.03em;
        padding: 3px 10px; border-radius: 999px; white-space: nowrap;
        box-shadow: 0 4px 14px rgba(29,185,84,0.45);
        animation: fadeSlideUp 0.5s ease both;
    }}
    .tod-card {{
        background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px;
        padding: 16px 14px; text-align: center; animation: fadeSlideUp 0.5s ease both;
        transition: transform 0.25s ease, border-color 0.25s ease;
    }}
    .tod-card:hover {{ transform: translateY(-4px); border-color: rgba(29,185,84,0.3); }}
    .tod-icon {{ font-size: 1.6rem; margin-bottom: 4px; }}
    .tod-icon-img {{ width: 44px; height: 44px; border-radius: 10px; object-fit: cover; margin: 0 auto 6px; display: block; }}
    .season-icon-img {{ width: 56px; height: 56px; border-radius: 12px; object-fit: cover; margin: 0 auto; display: block; }}
    .tod-label {{ font-size: 0.78rem; color: {TEXT_MID}; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px; }}
    .tod-value {{ font-size: 1.4rem; font-weight: 700; color: {TEXT}; }}
    .tod-sub {{ font-size: 0.75rem; color: {TEXT_DIM}; margin-top: 2px; }}

    .meta-chip-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 18px; margin-bottom: 28px; }}
    .meta-chip {{
        background: linear-gradient(145deg, rgba(255,255,255,0.045), rgba(255,255,255,0.015));
        border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 12px 14px;
        display: flex; align-items: center; gap: 12px; transition: all 0.25s ease;
    }}
    .meta-chip-icon {{
        width: 34px; height: 34px; flex-shrink: 0; display: flex; align-items: center;
        justify-content: center; border-radius: 9px; background: rgba(29,185,84,0.1); font-size: 1rem;
    }}
    .meta-chip-text {{ display: flex; flex-direction: column; gap: 1px; min-width: 0; }}
    .meta-chip-label {{ font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.05em; color: {TEXT_DIM}; }}
    .meta-chip-value {{ font-size: 0.88rem; font-weight: 600; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    a.meta-chip-link {{ text-decoration: none !important; }}
    a.meta-chip-link:hover .meta-chip {{ border-color: {GREEN}; background: rgba(29,185,84,0.08); transform: translateY(-2px); box-shadow: 0 8px 20px rgba(29,185,84,0.15); }}
    a.meta-chip-link:hover .meta-chip-icon {{ background: rgba(29,185,84,0.25); }}
    a.meta-chip-link:hover .meta-chip-value {{ color: {GREEN}; }}
    .explicit-badge {{ 
        background: rgba(255, 255, 255, 0.1); color: #fff; padding: 2px 6px; 
        border-radius: 4px; font-size: 0.65rem; font-weight: 800; letter-spacing: 1px; margin-left: 8px;
    }}
    /* =========================================================
       PURE HTML LIST ROWS: STARS, BUMP LINKS, HOVER STATES
       ========================================================= */
    .list-item-wrapper {{ margin-bottom: 0.6rem; transition: transform 0.22s ease; }}
    .list-item-wrapper a.custom-link {{ margin-bottom: 0 !important; }}
    .list-item-wrapper:hover {{ transform: translateX(6px); }}
    .list-item-wrapper .list-item {{ transition: none !important; }}
    .list-item-wrapper:hover .list-item {{ background: {CARD_HOVER} !important; border-color: {BORDER_HL} !important; box-shadow: none !important; }}
    .list-item-wrapper:hover .crate-stars {{ background: #262626 !important; border-color: {BORDER_HL} !important; box-shadow: 0 8px 30px rgba(0,0,0,0.3) !important; }}
    .list-item-wrapper:hover .item-art {{ transform: scale(1.07) !important; }}
    .list-item-wrapper:hover .item-arrow {{ transform: translateX(4px) !important; color: {GREEN} !important; }}

    .item-rank-container {{ position: relative; display: flex; align-items: center; justify-content: center; width: 40px; }}

    .bump-container {{
        position: absolute; left: -14px; top: 50%; transform: translateY(-50%);
        opacity: 0; transition: opacity 0.2s ease; z-index: 20;
        display: flex; flex-direction: column; gap: 2px;
    }}
    .list-item-wrapper:hover .bump-container {{ opacity: 1; }}
    .list-item-wrapper:hover .item-rank {{ opacity: 0.05; }}

    .bump-link {{
        display: flex; align-items: center; justify-content: center;
        width: 22px; height: 16px; background: rgba(29,185,84,0.12);
        border: 1px solid {GREEN}; border-radius: 4px;
        color: {GREEN}; font-size: 10px; line-height: 1; text-decoration: none !important;
        transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
    }}
    .bump-link:hover {{ background: {GREEN}; color: #000; transform: scale(1.15); }}

    .crate-stars {{
        display: flex; align-items: center; justify-content: center; gap: 2px;
        background: #151515; backdrop-filter: blur(10px);
        border: 1px solid {BORDER}; border-top: none;
        border-radius: 0 0 14px 14px; padding: 4px 1.5rem 10px;
        margin: -0.35rem 0 0 0; width: 100%; position: relative; z-index: 10;
        transition: background 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
    }}
    .list-item-has-rating {{ border-radius: 14px 14px 0 0 !important; border-bottom: none !important; }}

    .star-cell {{
        display: block; width: 18px; height: 18px; margin: 0 auto;
        position: relative; transition: transform 0.12s ease;
    }}
    .star-cell::before {{
        content: ""; position: absolute; inset: 0;
        background: linear-gradient(90deg, {GREEN} var(--fill, 0%), rgba(255,255,255,0.22) var(--fill, 0%));
        -webkit-mask-image: url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/%3E%3C/svg%3E');
        mask-image: url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"%3E%3Cpath d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/%3E%3C/svg%3E');
        -webkit-mask-size: contain; mask-size: contain; -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
        -webkit-mask-position: center; mask-position: center;
        transition: background 0.12s ease;
    }}
    .star-cell:hover {{ transform: scale(1.22); }}
    .star-cell:hover::before {{ background: rgba(29,185,84,0.8) !important; }}

    @media (max-width: 768px) {{
        .crate-stars {{ padding: 6px 0.8rem 8px; }}
        .star-cell {{ width: 14px; height: 14px; }}
    }}
    </style>
    """, unsafe_allow_html=True)

def get_rank_class(rank: int) -> str:
    if rank == 1: return "gold"
    if rank == 2: return "silver"
    if rank == 3: return "bronze"
    return ""

def get_item_icon(link_type: str) -> str:
    icons = {"song": "🎵", "artist": "🎤", "album": "💿", "genre": "🎸", "year": "📆"}
    return icons.get(link_type, "🎵")

def build_filtered_href(view_type: str, id_val: str) -> str:
    current_tab = st.query_params.get("tab", "habits")
    p_preset = st.query_params.get("preset")
    p_start = st.query_params.get("start")
    p_end = st.query_params.get("end")
    p_user = st.query_params.get("user")
    href = f"?tab={current_tab}&view={view_type}&id={id_val}"
    if p_preset: href += f"&preset={p_preset}"
    if p_start: href += f"&start={p_start}"
    if p_end: href += f"&end={p_end}"
    if p_user: href += f"&user={p_user}"
    return href

def build_base_qs() -> str:
    """Query-string prefix carrying forward all current params except action params (rate_*, bump)."""
    always_exclude = {"rate_type", "rate_id", "rate_val", "bump"}
    params = st.query_params
    tab = params.get("tab", "overview")
    qs = f"?tab={tab}"
    for key, val in params.items():
        if key == "tab" or key in always_exclude:
            continue
        qs += f"&{key}={val}"
    return qs

def render_list_v2(df: pd.DataFrame, title_col: str, sub_col: str, streams_col: str, hours_col: str,
                   id_col: str = None, link_type: str = None, image_col: str = "image_url",
                   rank_col: str = None, reveal_top_n: int = 0,
                   reveal_delay_base: float = 0.5, reveal_delay_step: float = 0.2,
                   quick_rate: bool = False, R=None, user_id: int = None, rating_scale: int = 10,
                   stat1_label: str = "Streams", stat2_label: str = "Time",
                   stat1_fmt=None, stat2_fmt=None, key_prefix: str = ""):
    current_tab = st.query_params.get("tab", "overview")
    _fmt1 = stat1_fmt or (lambda v: f"{int(v):,}")
    _fmt2 = stat2_fmt or (lambda v: f"{float(v):.1f}h")

    has_rating_col = 'rating' in df.columns
    base_qs = build_base_qs()

    html_rows = []

    for i, row in df.iterrows():
        rank = int(row[rank_col]) if (rank_col and rank_col in row.index) else (i + 1)
        rank_class = get_rank_class(rank)
        title = escape(str(row[title_col]))[:60]
        subtitle = escape(str(row[sub_col]))[:50]
        streams = _fmt1(row[streams_col])
        hours = _fmt2(row[hours_col])
        can_navigate = link_type and id_col and id_col in row.index

        item_id = str(row[id_col]) if can_navigate else f"idx_{i}"

        can_up, can_down = False, False
        if can_navigate and has_rating_col:
            my_rating = float(row['rating'])
            if i > 0 and float(df.iloc[i-1]['rating']) == my_rating:
                can_up = True
            if i < len(df) - 1 and float(df.iloc[i+1]['rating']) == my_rating:
                can_down = True

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

        has_rating = quick_rate and link_type in ("song", "album") and R is not None and user_id is not None
        item_class = "list-item-has-rating" if has_rating else ""

        bump_html = ""
        show_arrows = rank <= 50
        if can_navigate and has_rating_col and has_rating and show_arrows:
            top_href = f"{base_qs}&bump={link_type}:{item_id}:top"
            up_href = f"{base_qs}&bump={link_type}:{item_id}:up"
            down_href = f"{base_qs}&bump={link_type}:{item_id}:down"
            bump_buttons = ""
            if can_up:
                bump_buttons += f'<a href="{top_href}" target="_self" class="bump-link" title="Push to Top">⇈</a>'
                bump_buttons += f'<a href="{up_href}" target="_self" class="bump-link" title="Move Up 1">▲</a>'
            if can_down:
                bump_buttons += f'<a href="{down_href}" target="_self" class="bump-link" title="Move Down 1">▼</a>'
            if bump_buttons:
                bump_html = f'<div class="bump-container">{bump_buttons}</div>'

        # Flattened HTML to prevent Streamlit from parsing it as a code block
        card_core = (
            f'<div class="list-item {reveal_class} {item_class}" {reveal_style}>'
            f'<div class="item-rank-container">'
            f'<div class="item-rank {rank_class}">{rank}</div>'
            f'{bump_html}'
            f'</div>'
            f'<div class="item-art">{art_html}</div>'
            f'<div class="item-info">'
            f'<div class="item-title">{title}</div>'
            f'<div class="item-subtitle">{subtitle}</div>'
            f'</div>'
            f'<div class="item-stats">'
            f'<div class="stat">'
            f'<div class="stat-value">{streams}</div>'
            f'<div class="stat-label">{stat1_label}</div>'
            f'</div>'
            f'<div class="stat">'
            f'<div class="stat-value green">{hours}</div>'
            f'<div class="stat-label">{stat2_label}</div>'
            f'</div>'
            f'</div>'
            f'{"<div class=\'item-arrow\'>→</div>" if can_navigate else ""}'
            f'</div>'
        )

        if can_navigate:
            p_view, p_id, p_preset = st.query_params.get("view"), st.query_params.get("id"), st.query_params.get("preset")
            p_start, p_end, p_user = st.query_params.get("start"), st.query_params.get("end"), st.query_params.get("user")

            href = f"?tab={current_tab}&view={link_type}&id={item_id}"
            if p_view and p_id: href += f"&pview={p_view}&pid={p_id}"
            if p_preset: href += f"&preset={p_preset}"
            if p_start: href += f"&start={p_start}"
            if p_end: href += f"&end={p_end}"
            if p_user: href += f"&user={p_user}"

            card_html = f'<a href="{href}" class="custom-link" target="_self">{card_core}</a>'
        else:
            card_html = card_core

        star_html = ""
        if has_rating:
            star_html = R.compact_star_html(link_type, item_id, user_id, rating_scale, key_prefix=key_prefix)

        html_rows.append(f'<div class="list-item-wrapper">{card_html}{star_html}</div>')

    if html_rows:
        st.markdown("\n".join(html_rows), unsafe_allow_html=True)

def render_kpi_grid(kpis: list[dict]):
    cols = st.columns(len(kpis))
    for col, kpi in zip(cols, kpis):
        unit_html = f'<span class="kpi-unit">{kpi.get("unit", "")}</span>' if kpi.get("unit") else ""
        if "raw" in kpi:
            value_html = counter_span(kpi["raw"], kpi.get("decimals", 0), kpi.get("prefix", ""), kpi.get("suffix", ""))
        else:
            value_html = kpi.get("value", "")
        col.markdown(f'''
        <div class="kpi-card">
            <div class="kpi-icon">{kpi["icon"]}</div>
            <div class="kpi-title">{kpi["title"]}</div>
            <div class="kpi-value">{value_html}{unit_html}</div>
        </div>
        ''', unsafe_allow_html=True)

def render_detail_header(type_label: str, title: str, subtitle: str, icon: str, stats: list[dict], image_url: str = None):
    stats_html = ""
    for s in stats:
        if "raw" in s:
            value_html = counter_span(s["raw"], s.get("decimals", 0), s.get("prefix", ""), s.get("suffix", ""))
        else:
            value_html = s.get("value", "")
        stats_html += (
            f'<div class="detail-stat"><div class="detail-stat-value">{value_html}</div>'
            f'<div class="detail-stat-label">{s["label"]}</div></div>'
        )

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

def render_season_cards(df: pd.DataFrame):
    data = {row["season"]: row for _, row in df.iterrows()} if not df.empty else {}
    max_streams = int(df["stream_count"].max()) if not df.empty else 0
    cols = st.columns(4)
    for col, season in zip(cols, ["Winter", "Spring", "Summer", "Autumn"]):
        meta = SEASON_META[season]
        row = data.get(season)
        streams = int(row["stream_count"]) if row is not None else 0
        hours = float(row["hours_played"]) if row is not None else 0.0
        is_top = streams > 0 and streams == max_streams
        badge = '<div class="season-badge">👑 Favorite</div>' if is_top else ""
        glow = f'box-shadow: 0 12px 30px {meta["color"]}33; border-color: {meta["color"]}66;' if is_top else ""
        img = meta.get("image")
        icon_html = (
            f'<img class="season-icon-img" src="{img}" alt="{season}">'
            if img else f'<div class="kpi-icon" style="font-size: 1.9rem;">{meta["icon"]}</div>'
        )
        card_html = (
            f'<div class="kpi-card season-card" style="{glow}">'
            f'{badge}'
            f'{icon_html}'
            f'<div class="kpi-title">{season}</div>'
            f'<div class="kpi-value" style="color:{meta["color"]};">{streams:,}</div>'
            f'<div class="stat-label" style="margin-top:2px;">{hours:.1f}h listened</div>'
            f'</div>'
        )
        href = build_filtered_href("season", season)
        col.markdown(f'<a href="{href}" class="custom-link" target="_self">{card_html}</a>', unsafe_allow_html=True)

def render_time_of_day_cards(df: pd.DataFrame):
    data = {row["time_of_day"]: row for _, row in df.iterrows()} if not df.empty else {}
    for label, meta in TOD_META.items():
        row = data.get(label)
        streams = int(row["stream_count"]) if row is not None else 0
        hours = float(row["hours_played"]) if row is not None else 0.0
        img = meta.get("image")
        icon_html = (
            f'<img class="tod-icon-img" src="{img}" alt="{label}">'
            if img else f'<div class="tod-icon">{meta["icon"]}</div>'
        )
        card_html = (
            f'<div class="tod-card" style="margin-bottom: 10px;">'
            f'{icon_html}'
            f'<div class="tod-label">{label} · {meta["range"]}</div>'
            f'<div class="tod-value">{streams:,}</div>'
            f'<div class="tod-sub">{hours:.1f}h listened</div>'
            f'</div>'
        )
        href = build_filtered_href("tod", label)
        st.markdown(f'<a href="{href}" class="custom-link" target="_self">{card_html}</a>', unsafe_allow_html=True)

def render_track_spotlight_card(col, label: str, icon: str, row, value_field: str, value_fmt, song_id_field="song_id"):
    if row is None:
        with col:
            st.markdown(
                f'<div class="tod-card"><div class="tod-icon">{icon}</div>'
                f'<div class="tod-label">{label}</div>'
                f'<div class="tod-sub">No data</div></div>',
                unsafe_allow_html=True
            )
        return

    title = escape(str(row.get("song_title", "Unknown")))[:40]
    artist = escape(str(row.get("main_artist", "Unknown")))[:40]
    value_display = value_fmt(row[value_field])
    image_url = row.get("image_url")
    art_html = (
        f'<img class="tod-icon-img" src="{image_url}" alt="{title}">'
        if image_url and pd.notnull(image_url) and str(image_url).startswith("http")
        else f'<div class="tod-icon">{icon}</div>'
    )
    card_html = (
        f'<div class="tod-card">'
        f'{art_html}'
        f'<div class="tod-label">{label}</div>'
        f'<div class="tod-value" style="font-size:1.05rem;">{title}</div>'
        f'<div class="tod-sub">{artist}</div>'
        f'<div class="tod-sub" style="color:{GREEN}; font-weight:600; margin-top:4px;">{value_display}</div>'
        f'</div>'
    )
    with col:
        if pd.notnull(row.get(song_id_field)):
            href = build_filtered_href("song", str(row[song_id_field]))
            st.markdown(f'<a href="{href}" class="custom-link" target="_self">{card_html}</a>', unsafe_allow_html=True)
        else:
            st.markdown(card_html, unsafe_allow_html=True)