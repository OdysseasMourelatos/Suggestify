import io
import os
import datetime
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ══════════════════════════════════════════════════════════════════
# OPTIONAL: point these at bundled font files for pixel-perfect type
# ══════════════════════════════════════════════════════════════════
FONT_REGULAR_PATH = None   # e.g. os.path.join(os.path.dirname(__file__), "assets", "Inter-Regular.ttf")
FONT_BOLD_PATH = None      # e.g. os.path.join(os.path.dirname(__file__), "assets", "Inter-Bold.ttf")

# ══════════════════════════════════════════════════════════════════
# THEMES
# ══════════════════════════════════════════════════════════════════
THEMES = {
    "Spotify Green": {"stops": [(8, 22, 14), (16, 48, 28), (5, 10, 7)],
                       "accent": (29, 185, 84), "accent2": (46, 224, 110)},
    "Purple":        {"stops": [(26, 12, 42), (64, 26, 96), (10, 6, 20)],
                       "accent": (168, 85, 247), "accent2": (216, 180, 254)},
    "Blue":          {"stops": [(6, 18, 42), (16, 62, 122), (4, 8, 20)],
                       "accent": (56, 152, 255), "accent2": (137, 216, 255)},
    "Pink":          {"stops": [(42, 10, 30), (122, 28, 82), (16, 6, 14)],
                       "accent": (244, 63, 148), "accent2": (255, 154, 200)},
    "Orange":        {"stops": [(42, 18, 6), (132, 62, 12), (16, 8, 4)],
                       "accent": (255, 122, 24), "accent2": (255, 182, 92)},
    "Dark Gold":     {"stops": [(24, 20, 8), (74, 58, 14), (9, 8, 4)],
                       "accent": (212, 175, 55), "accent2": (245, 222, 140)},
}

PERIODS = {
    "All Time": "all",
    "Wrapped": "wrapped",
    "Last Month": "month",
    "Last Week": "week",
    "Custom Range": "custom",
}

STAT_TYPES = {
    "Top 5 Artists":  ("artists", 5),
    "Top 10 Artists": ("artists", 10),
    "Top 5 Tracks":   ("tracks", 5),
    "Top 10 Tracks":  ("tracks", 10),
    "Top Albums":     ("albums", 10),
    "Overview":       ("overview", 1),
}

RANK_COLORS = {
    1: (255, 215, 0),
    2: (205, 210, 216),
    3: (205, 127, 50),
}

CARD_W, CARD_H = 1080, 1920
MARGIN = 60


# ══════════════════════════════════════════════════════════════════
# FONT LOADING
# ══════════════════════════════════════════════════════════════════
def _font(size, bold=True):
    if bold and FONT_BOLD_PATH and os.path.exists(FONT_BOLD_PATH):
        return ImageFont.truetype(FONT_BOLD_PATH, size)
    if not bold and FONT_REGULAR_PATH and os.path.exists(FONT_REGULAR_PATH):
        return ImageFont.truetype(FONT_REGULAR_PATH, size)

    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "Arial Bold.ttf" if bold else "Arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1, scalable
    except TypeError:
        return ImageFont.load_default()


def _text_w(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def _truncate(draw, text, font, max_w):
    if _text_w(draw, text, font) <= max_w:
        return text
    while text and _text_w(draw, text + "…", font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


# ══════════════════════════════════════════════════════════════════
# IMAGE HELPERS
# ══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def _download_image(url: str):
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        return img.tobytes(), img.size
    except Exception:
        return None


def _load_cached_image(url):
    cached = _download_image(url)
    if cached is None:
        return None
    data, size = cached
    return Image.frombytes("RGBA", size, data)


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _circle_mask(size):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([0, 0, size[0] - 1, size[1] - 1], fill=255)
    return mask


def _fit_cover(img, size):
    """Resize + center-crop to exactly `size` (like CSS object-fit: cover)."""
    src_w, src_h = img.size
    target_w, target_h = size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(src_w * scale) + 1, int(src_h * scale) + 1
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _placeholder(size, accent, circle=False, icon="\u266A"):
    img = Image.new("RGBA", size, accent + (255,))
    d = ImageDraw.Draw(img)
    f = _font(int(size[0] * 0.42))
    bbox = d.textbbox((0, 0), icon, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size[0] - w) / 2 - bbox[0], (size[1] - h) / 2 - bbox[1]),
           icon, font=f, fill=(255, 255, 255, 225))
    if circle:
        img.putalpha(_circle_mask(size))
    return img


def _get_art(url, size, circle=False, accent=(29, 185, 84)):
    img = None
    if url and isinstance(url, str) and url.startswith("http"):
        img = _load_cached_image(url)
    if img is None:
        return _placeholder(size, accent, circle=circle)
    img = _fit_cover(img, size)
    mask = _circle_mask(size) if circle else _rounded_mask(size, int(size[0] * 0.18))
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


# ══════════════════════════════════════════════════════════════════
# BACKGROUND / GLASS EFFECTS
# ══════════════════════════════════════════════════════════════════
def _make_gradient(size, stops):
    w, h = size
    col = Image.new("RGB", (1, h))
    n = len(stops)
    for y in range(h):
        t = y / max(h - 1, 1)
        seg = t * (n - 1)
        i = min(int(seg), n - 2)
        lt = seg - i
        c0, c1 = stops[i], stops[i + 1]
        r = int(c0[0] + (c1[0] - c0[0]) * lt)
        g = int(c0[1] + (c1[1] - c0[1]) * lt)
        b = int(c0[2] + (c1[2] - c0[2]) * lt)
        col.putpixel((0, y), (r, g, b))
    return col.resize((w, h)).convert("RGBA")


def _add_glow(bg_rgba, center, radius, color, alpha=80):
    glow = Image.new("RGBA", bg_rgba.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([center[0] - radius, center[1] - radius,
               center[0] + radius, center[1] + radius],
              fill=tuple(color) + (alpha,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
    return Image.alpha_composite(bg_rgba, glow)


def _drop_shadow(bg_rgba, box, radius=32, blur=26, offset=(0, 12), alpha=100):
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", bg_rgba.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    d.rounded_rectangle(
        [x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]],
        radius=radius, fill=(0, 0, 0, alpha)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(bg_rgba, shadow)


def _glass_card(bg_rgba, box, radius=32, blur=22, tint=(255, 255, 255, 24),
                 border=(255, 255, 255, 50)):
    x0, y0, x1, y1 = [int(v) for v in box]
    region = bg_rgba.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur))
    mask = _rounded_mask((x1 - x0, y1 - y0), radius)

    frosted = Image.new("RGBA", bg_rgba.size, (0, 0, 0, 0))
    frosted.paste(region, (x0, y0), mask)
    out = Image.alpha_composite(bg_rgba, frosted)

    tint_layer = Image.new("RGBA", bg_rgba.size, (0, 0, 0, 0))
    solid = Image.new("RGBA", (x1 - x0, y1 - y0), tint)
    tint_layer.paste(solid, (x0, y0), mask)
    out = Image.alpha_composite(out, tint_layer)

    d = ImageDraw.Draw(out)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=border, width=2)
    return out


# ══════════════════════════════════════════════════════════════════
# DATA ACCESS  (share-dialog periods are independent of the page's
# own filter bar, so we query fresh with our own date range)
# ══════════════════════════════════════════════════════════════════
def _date_range(period_key, min_date, max_date, custom_start=None, custom_end=None):
    if period_key == "custom":
        start = custom_start or min_date
        end = custom_end or max_date
        if start > end:
            start, end = end, start
        return start, end
    if period_key == "wrapped":
        return datetime.date(max_date.year, 1, 1), max_date
    if period_key == "month":
        return max_date - datetime.timedelta(days=30), max_date
    if period_key == "week":
        return max_date - datetime.timedelta(days=7), max_date
    return min_date, max_date  # "all"


def _period_label_and_range(period_key, min_date, max_date, custom_start=None, custom_end=None):
    start, end = _date_range(period_key, min_date, max_date, custom_start, custom_end)
    if period_key == "all":
        return "ALL TIME", "All time"
    if period_key == "wrapped":
        return f"WRAPPED {max_date.year}", f"Jan – {max_date.strftime('%b %Y')}"
    if period_key == "month":
        return "LAST MONTH", f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    if period_key == "week":
        return "LAST WEEK", f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    # custom
    year_label = f"{start.year}" if start.year == end.year else f"{start.year}–{end.year}"
    return f"{year_label}", f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"


def _fetch_data(run_query, kind, limit, user_id, start_date, end_date):
    params = {"start_date": start_date, "end_date": end_date,
              "user_id": user_id, "limit": limit}

    if kind == "artists":
        sql = """
            SELECT a.name AS name, a.image_url AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s
            JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY a.id, a.name, a.image_url
            ORDER BY streams DESC LIMIT :limit;
        """
    elif kind == "tracks":
        sql = """
            SELECT so.title AS name, COALESCE(ar.name, 'Unknown') AS sub, so.image_url AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            LEFT JOIN artists ar ON ar.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
            GROUP BY so.id, so.title, ar.name, so.image_url
            ORDER BY streams DESC LIMIT :limit;
        """
    else:  # albums
        sql = """
            SELECT COALESCE(al.title, 'Unknown Album') AS name,
                   MAX(so.image_url) AS image_url,
                   COUNT(s.id) AS streams,
                   ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s
            JOIN songs so ON so.id = s.song_id
            LEFT JOIN albums al ON al.id = so.album_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date
              AND s.user_id = :user_id
              AND so.album_id IS NOT NULL
            GROUP BY al.id, al.title
            ORDER BY streams DESC LIMIT :limit;
        """
    return run_query(sql, params)


def _fetch_totals(run_query, user_id, start_date, end_date):
    """Total streams/hours across the WHOLE selected date range — independent
    of whatever Top-N list is being shown, so the footer never undercounts."""
    sql = """
        SELECT COUNT(s.id) AS streams,
               ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
        FROM streams s
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id;
    """
    params = {"start_date": start_date, "end_date": end_date, "user_id": user_id}
    result = run_query(sql, params)
    if result is None or result.empty:
        return 0, 0.0
    row = result.iloc[0]
    return int(row.get("streams") or 0), float(row.get("hours") or 0.0)


def _fetch_overview_data(run_query, user_id, start_date, end_date):
    """Aggregate stats for the 'Overview' card: totals + #1 artist + #1 track."""
    params = {"start_date": start_date, "end_date": end_date, "user_id": user_id}

    totals_sql = """
        SELECT
            COUNT(s.id) AS total_streams,
            ROUND(SUM(s.ms_played) / 3600000.0, 1) AS total_hours,
            COUNT(DISTINCT sa.artist_id) AS unique_artists,
            COUNT(DISTINCT s.song_id) AS unique_tracks
        FROM streams s
        LEFT JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id;
    """
    totals_df = run_query(totals_sql, params)

    overview = {
        "total_streams": 0, "total_hours": 0.0,
        "unique_artists": 0, "unique_tracks": 0,
        "top_artist": None, "top_track": None,
    }

    if totals_df is not None and not totals_df.empty:
        row = totals_df.iloc[0]
        overview["total_streams"] = int(row.get("total_streams") or 0)
        overview["total_hours"] = float(row.get("total_hours") or 0.0)
        overview["unique_artists"] = int(row.get("unique_artists") or 0)
        overview["unique_tracks"] = int(row.get("unique_tracks") or 0)

    top_artist_df = _fetch_data(run_query, "artists", 1, user_id, start_date, end_date)
    if top_artist_df is not None and not top_artist_df.empty:
        overview["top_artist"] = top_artist_df.iloc[0].to_dict()

    top_track_df = _fetch_data(run_query, "tracks", 1, user_id, start_date, end_date)
    if top_track_df is not None and not top_track_df.empty:
        overview["top_track"] = top_track_df.iloc[0].to_dict()

    return overview


def _title_lines(kind, n):
    if kind == "artists":
        return ["MY TOP", f"{n} ARTISTS"]
    if kind == "tracks":
        return ["MY TOP", f"{n} TRACKS"]
    return ["MY TOP", "ALBUMS"]


# ══════════════════════════════════════════════════════════════════
# CARD BUILDER  (1080 × 1920 PNG, Instagram Story sized)
# ══════════════════════════════════════════════════════════════════
def build_share_card(df, kind, username, period_label, theme_name, date_range_label, n,
                      total_streams=0, total_hours=0.0):
    theme = THEMES[theme_name]
    accent = theme["accent"]

    bg = _make_gradient((CARD_W, CARD_H), theme["stops"])
    bg = _add_glow(bg, (CARD_W * 0.12, CARD_H * 0.06), 460, theme["accent2"], 65)
    bg = _add_glow(bg, (CARD_W * 0.92, CARD_H * 0.9), 520, theme["accent"], 55)

    draw = ImageDraw.Draw(bg)

    # ── Logo ──
    logo_font = _font(34)
    draw.text((MARGIN, 74), "\u266A  SUGGESTIFY", font=logo_font, fill=(255, 255, 255, 235))

    # ── Period pill ──
    pill_font = _font(26)
    pill_text = period_label
    pw = _text_w(draw, pill_text, pill_font) + 56
    pill_box = [CARD_W - MARGIN - pw, 62, CARD_W - MARGIN, 62 + 54]
    draw.rounded_rectangle(pill_box, radius=27, fill=accent + (255,))
    draw.text(((pill_box[0] + pill_box[2]) / 2, (pill_box[1] + pill_box[3]) / 2),
               pill_text, font=pill_font, fill=(0, 0, 0, 255), anchor="mm")

    # ── Title ──
    title_font = _font(92)
    y = 190
    for line in _title_lines(kind, n):
        w = _text_w(draw, line, title_font)
        draw.text(((CARD_W - w) / 2, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 104

    # ── Subtitle ──
    sub_font = _font(30)
    sub_text = f"@{username}  ·  {date_range_label}"
    w = _text_w(draw, sub_text, sub_font)
    draw.text(((CARD_W - w) / 2, y + 14), sub_text, font=sub_font, fill=(255, 255, 255, 170))

    list_top = y + 90
    footer_h = 190
    list_bottom = CARD_H - footer_h

    rows = df.to_dict("records")
    n_rows = len(rows)
    gap = 16
    row_h = min(220, (list_bottom - list_top - gap * (n_rows - 1)) / n_rows)
    row_h = max(row_h, 84)

    is_circle = (kind == "artists")
    rank_col_w = 96

    for i, row in enumerate(rows):
        box = [MARGIN, list_top + i * (row_h + gap),
               CARD_W - MARGIN, list_top + i * (row_h + gap) + row_h]

        bg = _drop_shadow(bg, box, radius=28, blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=28, blur=18)
        draw = ImageDraw.Draw(bg)

        rank = i + 1
        rank_color = RANK_COLORS.get(rank, (255, 255, 255))
        rank_font = _font(int(row_h * 0.4))
        draw.text((box[0] + rank_col_w / 2, (box[1] + box[3]) / 2),
                   str(rank), font=rank_font, fill=rank_color + (255,), anchor="mm")

        art_size = int(row_h - 24)
        art_x = box[0] + rank_col_w
        art_y = box[1] + (row_h - art_size) / 2
        art = _get_art(row.get("image_url"), (art_size, art_size), circle=is_circle, accent=accent)
        bg.paste(art, (int(art_x), int(art_y)), art)

        info_x = art_x + art_size + 28
        stats_col_w = 230
        info_max_w = (box[2] - stats_col_w) - info_x - 16

        has_sub = "sub" in df.columns and row.get("sub")
        name = str(row.get("name", ""))

        if has_sub:
            title_f = _font(int(row_h * 0.22))
            sub_f = _font(int(row_h * 0.16), bold=False)
            title_txt = _truncate(draw, name, title_f, info_max_w)
            sub_txt = _truncate(draw, str(row["sub"]), sub_f, info_max_w)
            title_y = box[1] + row_h * 0.28
            draw.text((info_x, title_y), title_txt, font=title_f, fill=(255, 255, 255, 255), anchor="lm")
            draw.text((info_x, box[1] + row_h * 0.66), sub_txt, font=sub_f, fill=(255, 255, 255, 170), anchor="lm")
        else:
            title_f = _font(int(row_h * 0.24))
            title_txt = _truncate(draw, name, title_f, info_max_w)
            draw.text((info_x, (box[1] + box[3]) / 2), title_txt, font=title_f,
                       fill=(255, 255, 255, 255), anchor="lm")

        streams_val = int(row.get("streams") or 0)
        stat_font = _font(int(row_h * 0.24))
        label_font = _font(int(row_h * 0.13), bold=False)
        stats_x = box[2] - 24
        streams_txt = f"{streams_val:,}"
        draw.text((stats_x, box[1] + row_h * 0.38), streams_txt, font=stat_font,
                   fill=accent + (255,), anchor="rm")
        draw.text((stats_x, box[1] + row_h * 0.68), "STREAMS", font=label_font,
                   fill=(255, 255, 255, 140), anchor="rm")

    # ── Footer (totals for the FULL selected period, not just the Top-N shown above) ──
    foot_box = [MARGIN, CARD_H - footer_h + 20, CARD_W - MARGIN, CARD_H - 60]
    bg = _drop_shadow(bg, foot_box, radius=26, blur=16, offset=(0, 6), alpha=70)
    bg = _glass_card(bg, foot_box, radius=26, blur=16, tint=(255, 255, 255, 18))
    draw = ImageDraw.Draw(bg)

    stat_big = _font(40)
    stat_small = _font(20, bold=False)
    third_w = (foot_box[2] - foot_box[0]) / 2
    cx1 = foot_box[0] + third_w / 2
    cx2 = foot_box[0] + third_w + third_w / 2

    draw.text((cx1, foot_box[1] + 24), f"{total_streams:,}", font=stat_big, fill=(255, 255, 255, 255), anchor="mm")
    draw.text((cx1, foot_box[1] + 62), "TOTAL STREAMS", font=stat_small, fill=(255, 255, 255, 150), anchor="mm")
    draw.text((cx2, foot_box[1] + 24), f"{total_hours:,.1f}h", font=stat_big, fill=accent + (255,), anchor="mm")
    draw.text((cx2, foot_box[1] + 62), "TIME LISTENED", font=stat_small, fill=(255, 255, 255, 150), anchor="mm")

    wm_font = _font(20, bold=False)
    wm_text = f"Made with Suggestify \u2022 {datetime.date.today().strftime('%b %d, %Y')}"
    w = _text_w(draw, wm_text, wm_font)
    draw.text(((CARD_W - w) / 2, CARD_H - 40), wm_text, font=wm_font, fill=(255, 255, 255, 120))

    return bg.convert("RGB")


def build_overview_card(overview, username, period_label, theme_name, date_range_label):
    """A summary card: total streams/hours/artists/tracks for the WHOLE period
    plus your #1 artist and #1 track — no ranked list."""
    theme = THEMES[theme_name]
    accent = theme["accent"]

    bg = _make_gradient((CARD_W, CARD_H), theme["stops"])
    bg = _add_glow(bg, (CARD_W * 0.12, CARD_H * 0.06), 460, theme["accent2"], 65)
    bg = _add_glow(bg, (CARD_W * 0.92, CARD_H * 0.9), 520, theme["accent"], 55)

    draw = ImageDraw.Draw(bg)

    # ── Logo ──
    logo_font = _font(34)
    draw.text((MARGIN, 74), "\u266A  SUGGESTIFY", font=logo_font, fill=(255, 255, 255, 235))

    # ── Period pill ──
    pill_font = _font(26)
    pill_text = period_label
    pw = _text_w(draw, pill_text, pill_font) + 56
    pill_box = [CARD_W - MARGIN - pw, 62, CARD_W - MARGIN, 62 + 54]
    draw.rounded_rectangle(pill_box, radius=27, fill=accent + (255,))
    draw.text(((pill_box[0] + pill_box[2]) / 2, (pill_box[1] + pill_box[3]) / 2),
               pill_text, font=pill_font, fill=(0, 0, 0, 255), anchor="mm")

    # ── Title ──
    title_font = _font(88)
    y = 190
    for line in ["MY LISTENING", "OVERVIEW"]:
        w = _text_w(draw, line, title_font)
        draw.text(((CARD_W - w) / 2, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 100

    # ── Subtitle ──
    sub_font = _font(30)
    sub_text = f"@{username}  ·  {date_range_label}"
    w = _text_w(draw, sub_text, sub_font)
    draw.text(((CARD_W - w) / 2, y + 14), sub_text, font=sub_font, fill=(255, 255, 255, 170))

    content_top = y + 100

    # ── 2x2 big stat grid ──
    grid_gap = 24
    grid_h = 260
    col_w = (CARD_W - 2 * MARGIN - grid_gap) / 2

    stats = [
        (f"{overview['total_streams']:,}", "TOTAL STREAMS"),
        (f"{overview['total_hours']:,.1f}h", "TIME LISTENED"),
        (f"{overview['unique_artists']:,}", "UNIQUE ARTISTS"),
        (f"{overview['unique_tracks']:,}", "UNIQUE TRACKS"),
    ]

    for i, (value, label) in enumerate(stats):
        col = i % 2
        row_i = i // 2
        x0 = MARGIN + col * (col_w + grid_gap)
        y0 = content_top + row_i * (grid_h + grid_gap)
        box = [x0, y0, x0 + col_w, y0 + grid_h]

        bg = _drop_shadow(bg, box, radius=32, blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=32, blur=18)
        draw = ImageDraw.Draw(bg)

        val_font = _font(72)
        lab_font = _font(24, bold=False)
        cx = (box[0] + box[2]) / 2
        draw.text((cx, box[1] + grid_h * 0.42), value, font=val_font,
                   fill=accent + (255,), anchor="mm")
        draw.text((cx, box[1] + grid_h * 0.72), label, font=lab_font,
                   fill=(255, 255, 255, 160), anchor="mm")

    highlight_top = content_top + 2 * grid_h + grid_gap + 36
    highlight_h = 200

    def _highlight_row(y0, art_url, is_circle, name, sub, streams, tag):
        nonlocal bg
        box = [MARGIN, y0, CARD_W - MARGIN, y0 + highlight_h]
        bg = _drop_shadow(bg, box, radius=28, blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=28, blur=18)
        d = ImageDraw.Draw(bg)

        tag_font = _font(20)
        d.text((box[0] + 24, box[1] + 16), tag, font=tag_font, fill=accent + (255,))

        art_size = int(highlight_h - 70)
        art_x = box[0] + 24
        art_y = box[1] + 54
        art = _get_art(art_url, (art_size, art_size), circle=is_circle, accent=accent)
        bg.paste(art, (int(art_x), int(art_y)), art)

        info_x = art_x + art_size + 28
        name_font = _font(38)
        sub_font_ = _font(24, bold=False)
        info_max_w = CARD_W - MARGIN - 130 - info_x
        name_txt = _truncate(d, name, name_font, info_max_w)
        d.text((info_x, box[1] + 78), name_txt, font=name_font, fill=(255, 255, 255, 255), anchor="lm")
        if sub:
            sub_txt = _truncate(d, sub, sub_font_, info_max_w)
            d.text((info_x, box[1] + 122), sub_txt, font=sub_font_, fill=(255, 255, 255, 170), anchor="lm")

        stat_font = _font(34)
        lab_font = _font(16, bold=False)
        d.text((box[2] - 24, box[1] + 78), f"{streams:,}", font=stat_font,
               fill=accent + (255,), anchor="rm")
        d.text((box[2] - 24, box[1] + 112), "STREAMS", font=lab_font,
               fill=(255, 255, 255, 140), anchor="rm")

    if overview.get("top_artist"):
        ta = overview["top_artist"]
        _highlight_row(highlight_top, ta.get("image_url"), True, ta.get("name", ""), "",
                       int(ta.get("streams") or 0), "TOP ARTIST")
        highlight_top += highlight_h + 20

    if overview.get("top_track"):
        tt = overview["top_track"]
        _highlight_row(highlight_top, tt.get("image_url"), False, tt.get("name", ""), tt.get("sub", ""),
                       int(tt.get("streams") or 0), "TOP TRACK")

    # ── Footer watermark ──
    draw = ImageDraw.Draw(bg)
    wm_font = _font(20, bold=False)
    wm_text = f"Made with Suggestify \u2022 {datetime.date.today().strftime('%b %d, %Y')}"
    w = _text_w(draw, wm_text, wm_font)
    draw.text(((CARD_W - w) / 2, CARD_H - 50), wm_text, font=wm_font, fill=(255, 255, 255, 120))

    return bg.convert("RGB")


def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════
# LIVE HTML/CSS PREVIEW (cosmetic, shown inside the modal only —
# the downloadable PNG below is the real, CORS-safe export)
# ══════════════════════════════════════════════════════════════════
def _html_preview(df, kind, username, period_label, theme_name, date_range_label, n):
    theme = THEMES[theme_name]
    accent = "rgb({},{},{})".format(*theme["accent"])
    s0, s1, s2 = theme["stops"]
    grad = f"linear-gradient(160deg, rgb{tuple(s1)} 0%, rgb{tuple(s0)} 45%, rgb{tuple(s2)} 100%)"
    is_circle = kind == "artists"
    radius = "50%" if is_circle else "12px"

    rows_html = ""
    for i, row in df.head(n).iterrows():
        rank = i + 1
        rank_color = "rgb({},{},{})".format(*RANK_COLORS.get(rank, (255, 255, 255)))
        img = row.get("image_url")
        art = (f'<img src="{img}" style="width:100%;height:100%;object-fit:cover;border-radius:{radius};">'
               if isinstance(img, str) and img.startswith("http") else "\u266A")
        sub = f'<div class="sh-sub">{row["sub"]}</div>' if "sub" in df.columns and row.get("sub") else ""
        rows_html += f"""
        <div class="sh-row">
            <div class="sh-rank" style="color:{rank_color}">{rank}</div>
            <div class="sh-art" style="border-radius:{radius}">{art}</div>
            <div class="sh-info">
                <div class="sh-name">{row.get('name','')}</div>
                {sub}
            </div>
            <div class="sh-stats">
                <div class="sh-streams" style="color:{accent}">{int(row.get('streams') or 0):,}</div>
                <div class="sh-label">streams</div>
            </div>
        </div>"""

    title = _title_lines(kind, n)
    return f"""
    <!doctype html><html><head><meta charset="utf-8"></head>
    <body>
    <div class="sh-card" style="background:{grad}">
        <div class="sh-glow" style="background:radial-gradient(circle, {accent}55, transparent 70%)"></div>
        <div class="sh-header">
            <div class="sh-logo">\u266A SUGGESTIFY</div>
            <div class="sh-pill" style="background:{accent}">{period_label}</div>
        </div>
        <div class="sh-title">{title[0]}<br>{title[1]}</div>
        <div class="sh-subtitle">@{username} &middot; {date_range_label}</div>
        <div class="sh-list">{rows_html}</div>
        <div class="sh-footer">Made with Suggestify</div>
    </div>
    <style>
        html, body {{ margin: 0; padding: 0; background: transparent; }}
        * {{ box-sizing: border-box; }}
        .sh-card {{
            position: relative; width: 300px; height: 533px; margin: 12px auto;
            border-radius: 24px; overflow: hidden; padding: 22px 18px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            font-family: 'Inter', -apple-system, sans-serif; color: #fff;
        }}
        .sh-glow {{ position:absolute; top:-60px; right:-60px; width:220px; height:220px; filter: blur(10px); }}
        .sh-header {{ display:flex; justify-content:space-between; align-items:center; position:relative; z-index:1; }}
        .sh-logo {{ font-size:11px; font-weight:800; letter-spacing:0.06em; opacity:0.9; }}
        .sh-pill {{ font-size:9px; font-weight:800; color:#000; padding:4px 10px; border-radius:20px; letter-spacing:0.04em; }}
        .sh-title {{ font-size:26px; font-weight:900; line-height:1.05; margin-top:16px; text-align:center; letter-spacing:-0.02em; position:relative; z-index:1; }}
        .sh-subtitle {{ font-size:10px; text-align:center; opacity:0.65; margin-top:6px; position:relative; z-index:1; }}
        .sh-list {{ margin-top:16px; display:flex; flex-direction:column; gap:6px; position:relative; z-index:1; }}
        .sh-row {{
            display:flex; align-items:center; gap:8px; padding:6px 10px;
            background: rgba(255,255,255,0.08); backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.12); border-radius: 14px;
        }}
        .sh-rank {{ font-size:13px; font-weight:800; width:16px; text-align:center; flex-shrink:0; }}
        .sh-art {{ width:30px; height:30px; flex-shrink:0; overflow:hidden; background:rgba(255,255,255,0.15);
                    display:flex; align-items:center; justify-content:center; font-size:12px; }}
        .sh-info {{ flex:1; min-width:0; }}
        .sh-name {{ font-size:11px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .sh-sub {{ font-size:9px; opacity:0.6; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .sh-stats {{ text-align:right; flex-shrink:0; }}
        .sh-streams {{ font-size:12px; font-weight:800; }}
        .sh-label {{ font-size:7px; opacity:0.55; text-transform:uppercase; letter-spacing:0.05em; }}
        .sh-footer {{ position:absolute; bottom:10px; left:0; right:0; text-align:center; font-size:8px; opacity:0.45; }}
    </style>
    </body></html>
    """


# ══════════════════════════════════════════════════════════════════
# STREAMLIT MODAL
# ══════════════════════════════════════════════════════════════════
_dialog_decorator = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)


def _run_share_dialog(run_query, user_id, username, min_date, max_date):
    st.caption("Create a Wrapped-style card of your listening stats and share it anywhere.")

    c1, c2, c3 = st.columns(3)
    with c1:
        stat_choice = st.selectbox("What to show", list(STAT_TYPES.keys()), key="share_stat_choice")
    with c2:
        period_choice = st.selectbox("Time period", list(PERIODS.keys()), key="share_period_choice")
    with c3:
        theme_choice = st.selectbox("Theme", list(THEMES.keys()), key="share_theme_choice")

    kind, n = STAT_TYPES[stat_choice]
    period_key = PERIODS[period_choice]

    # ── Custom range picker (only shown when "Custom Range" is selected) ──
    custom_start, custom_end = None, None
    if period_key == "custom":
        cc1, cc2 = st.columns(2)
        with cc1:
            custom_start = st.date_input("From", value=min_date, min_value=min_date,
                                          max_value=max_date, key="share_custom_start")
        with cc2:
            custom_end = st.date_input("To", value=max_date, min_value=min_date,
                                        max_value=max_date, key="share_custom_end")
        if custom_start > custom_end:
            st.warning("Start date is after end date — swapping them.")
            custom_start, custom_end = custom_end, custom_start

    start_date, end_date = _date_range(period_key, min_date, max_date, custom_start, custom_end)
    period_label, date_range_label = _period_label_and_range(
        period_key, min_date, max_date, custom_start, custom_end
    )

    # Totals for the footer always reflect the FULL selected date range,
    # regardless of whether we're showing a Top 5 / Top 10 / Overview card.
    total_streams, total_hours = _fetch_totals(run_query, user_id, start_date, end_date)

    if kind == "overview":
        overview = _fetch_overview_data(run_query, user_id, start_date, end_date)

        if not overview["total_streams"]:
            st.warning("No listening data for this period yet — try a different range.")
            return

        st.info(
            f"**{overview['total_streams']:,}** streams · **{overview['total_hours']:,.1f}h** listened · "
            f"{overview['unique_artists']:,} artists · {overview['unique_tracks']:,} tracks"
        )

        generate = st.button("✨ Generate high-res PNG", use_container_width=True,
                              type="primary", key="share_generate_btn")

        if generate:
            with st.spinner("Rendering your 1080×1920 overview card…"):
                card = build_overview_card(overview, username, period_label, theme_choice, date_range_label)
                st.session_state["_share_png_bytes"] = image_to_bytes(card)

    else:
        df = _fetch_data(run_query, kind, n, user_id, start_date, end_date)

        if df is None or df.empty:
            st.warning("No listening data for this period yet — try a different range.")
            return

        components.html(
            _html_preview(df, kind, username, period_label, theme_choice, date_range_label, n),
            height=565,
            scrolling=False,
        )

        st.write("")

        generate = st.button("✨ Generate high-res PNG", use_container_width=True,
                              type="primary", key="share_generate_btn")

        if generate:
            with st.spinner("Rendering your 1080×1920 card…"):
                card = build_share_card(
                    df, kind, username, period_label, theme_choice, date_range_label, n,
                    total_streams=total_streams, total_hours=total_hours,
                )
                st.session_state["_share_png_bytes"] = image_to_bytes(card)

    if st.session_state.get("_share_png_bytes"):
        st.download_button(
            "⬇️ Download PNG",
            data=st.session_state["_share_png_bytes"],
            file_name=f"suggestify_{kind}_{period_key}_{datetime.date.today().isoformat()}.png",
            mime="image/png",
            use_container_width=True,
            type="primary",
            key="share_download_btn",
        )
        st.success("Ready! Sized for Instagram Stories (1080×1920).")

    if st.button("Close", use_container_width=True, key="share_close_btn"):
        st.session_state.pop("_share_png_bytes", None)
        st.rerun()


def render_share_stats_button(run_query, user_id, username, min_date, max_date,
                               label="📤 Share Your Stats", accent="#1DB954", accent_dim="#169C46"):
    """
    Renders the trigger as a right-aligned gradient pill button.

    Call this RIGHT AFTER your navbar markdown (before the tab row) so it
    lines up visually in the top-right, e.g.:

        st.markdown('<div class="navbar">...</div>', unsafe_allow_html=True)
        render_share_stats_button(run_query=run_query, user_id=selected_user_id,
                                   username=selected_username, min_date=min_date, max_date=max_date)
        # ...tabs, filter bar, etc.

    NOTE: this intentionally does NOT use position:fixed/absolute. Your
    app's global CSS animates `.main .block-container`, `[data-testid=
    "stVerticalBlock"] > div`, etc. with `transform: translateY(...)`.
    Per the CSS spec, ANY element with a transform other than `none`
    (including an animated-to-identity one) becomes the containing block
    for fixed/absolute descendants — so a `position: fixed` button gets
    pinned to that animated wrapper instead of the real viewport, which
    is exactly the "floats in the middle of the page" bug. Right-aligning
    in normal flow sidesteps that entirely and is far more robust.
    """
    if _dialog_decorator is None:
        st.error("Your Streamlit version doesn't support st.dialog — please upgrade streamlit (>=1.31.0).")
        return

    st.markdown(f"""
    <style>
        .st-key-share_stats_btn_wrap {{
            width: 100% !important;
        }}
        .st-key-share_stats_btn_wrap div[data-testid="stButton"] {{
            display: flex !important;
            justify-content: flex-end !important;
            width: 100% !important;
            margin: -0.25rem 0 0.75rem 0 !important;
        }}
        .st-key-share_stats_btn_wrap div[data-testid="stButton"] button {{
            width: auto !important;
            background: linear-gradient(135deg, {accent} 0%, {accent_dim} 100%) !important;
            color: #000 !important;
            font-weight: 800 !important;
            font-size: 0.85rem !important;
            border: none !important;
            border-radius: 999px !important;
            padding: 0.6rem 1.4rem !important;
            box-shadow: 0 8px 24px {accent}55, 0 2px 10px rgba(0,0,0,0.45) !important;
            transition: all 0.25s cubic-bezier(0.16,1,0.3,1) !important;
            letter-spacing: 0.01em !important;
        }}
        .st-key-share_stats_btn_wrap div[data-testid="stButton"] button:hover {{
            transform: translateY(-2px) scale(1.03) !important;
            box-shadow: 0 12px 34px {accent}77, 0 4px 14px rgba(0,0,0,0.55) !important;
        }}
        @media (max-width: 768px) {{
            .st-key-share_stats_btn_wrap div[data-testid="stButton"] button {{
                padding: 0.5rem 1rem !important; font-size: 0.72rem !important;
            }}
        }}
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="share_stats_btn_wrap"):
        if st.button(label, key="share_stats_trigger"):
            st.session_state.pop("_share_png_bytes", None)
            _open_dialog(run_query, user_id, username, min_date, max_date)


@_dialog_decorator("🎉 Share Your Stats") if _dialog_decorator else (lambda f: f)
def _open_dialog(run_query, user_id, username, min_date, max_date):
    _run_share_dialog(run_query, user_id, username, min_date, max_date)