import io
import os
import math
import random
import colorsys
import zipfile
import datetime
import requests
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import qrcode
except ImportError:
    qrcode = None

# ══════════════════════════════════════════════════════════════════
# OPTIONAL: point these at bundled font files for pixel-perfect type
# ══════════════════════════════════════════════════════════════════
FONT_REGULAR_PATH = None   # e.g. os.path.join(os.path.dirname(__file__), "assets", "Inter-Regular.ttf")
FONT_BOLD_PATH = None      # e.g. os.path.join(os.path.dirname(__file__), "assets", "Inter-Bold.ttf")

# Link embedded in the QR code / referenced by the watermark.
APP_URL = "https://suggestify.app"

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

DYNAMIC_THEME_LABEL = "🎨 Auto (Top Artist Colors)"

PERIODS = {
    "All Time": "all",
    "Wrapped": "wrapped",
    "Last Month": "month",
    "Last Week": "week",
    "Custom Range": "custom",
}

STAT_TYPES = {
    "Top 5 Artists":             ("artists", 5),
    "Top 10 Artists":            ("artists", 10),
    "Top 5 Tracks":              ("tracks", 5),
    "Top 10 Tracks":             ("tracks", 10),
    "Top Albums":                ("albums", 10),
    "Top Genres":                ("genres", 7),
    "Top Seasons":               ("seasons", 4),
    "Top Times of Day":          ("tod", 4),
    "Specific Album Top Tracks": ("specific_album", 5),
    "Specific Artist Insights":  ("specific_artist", 6),
    "Overview":                  ("overview", 1),
    "Listening Personality":     ("personality", 1),
}

CUSTOM_IMAGES = {
    "Winter": "https://images.unsplash.com/photo-1418985991508-e47386d96a71?w=400&q=80&auto=format&fit=crop",
    "Spring": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?w=400&q=80&auto=format&fit=crop",
    "Summer": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&q=80&auto=format&fit=crop",
    "Autumn": "https://images.unsplash.com/photo-1477414348463-c0eb7f1359b6?w=400&q=80&auto=format&fit=crop",
    "Night": "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?w=400&q=80&auto=format&fit=crop",
    "Morning": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400&q=80&auto=format&fit=crop",
    "Afternoon": "https://images.unsplash.com/photo-1500964757637-c85e8a162699?w=400&q=80&auto=format&fit=crop",
    "Evening": "https://images.unsplash.com/photo-1495616811223-4d98c6e9c869?w=400&q=80&auto=format&fit=crop",
}

RANK_COLORS = {
    1: (255, 215, 0),
    2: (205, 210, 216),
    3: (205, 127, 50),
}

FORMATS = {
    "Story (1080×1920)":  (1080, 1920),
    "Square (1080×1080)": (1080, 1080),
}
CARD_W, CARD_H = FORMATS["Story (1080×1920)"]
MARGIN = 60

PERSONALITIES = {
    "night_owl":       {"label": "Night Owl",        "emoji": "🦉", "desc": "Your best playlists come alive after dark."},
    "superfan":        {"label": "Superfan",          "emoji": "💜", "desc": "One artist, unwavering loyalty."},
    "marathoner":      {"label": "Marathon Listener", "emoji": "⏱️", "desc": "Hours upon hours — the music never stops."},
    "weekend_warrior": {"label": "Weekend Warrior",   "emoji": "🎉", "desc": "Your speakers really come alive on weekends."},
    "repeater":        {"label": "Repeat Offender",   "emoji": "🔁", "desc": "When you find a favorite, you ride with it."},
    "explorer":        {"label": "Explorer",          "emoji": "🧭", "desc": "Always chasing the next new sound."},
    "collector":       {"label": "Collector",         "emoji": "📀", "desc": "A vast, ever-growing library of tracks."},
    "newcomer":        {"label": "Fresh Start",       "emoji": "🌱", "desc": "Just getting started — the story is unfolding."},
    "default":         {"label": "Music Lover",       "emoji": "🎧", "desc": "A well-rounded, ever-curious listener."},
}

# ══════════════════════════════════════════════════════════════════
# FONT LOADING
# ══════════════════════════════════════════════════════════════════
def _font(size, bold=True):
    size = max(int(size), 8)
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
        return ImageFont.load_default(size)
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

def _wrap_text(draw, text, font, max_w, max_lines=3):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if _text_w(draw, trial, font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == max_lines - 1:
            break
    if cur:
        lines.append(cur)
    if len(lines) < len(text.split()) and len(lines) >= max_lines:
        lines[-1] = _truncate(draw, lines[-1] + "…", font, max_w)
    return lines[:max_lines]

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
    if not url: return None
    cached = _download_image(url)
    if cached is None: return None
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

def _get_art(url, size, circle=False, accent=(29, 185, 84), icon="\u266A"):
    img = None
    if url and isinstance(url, str) and url.startswith("http"):
        img = _load_cached_image(url)
    if img is None:
        return _placeholder(size, accent, circle=circle, icon=icon)
    img = _fit_cover(img, size)
    mask = _circle_mask(size) if circle else _rounded_mask(size, int(size[0] * 0.18))
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out

def _initials(name):
    parts = [p for p in (name or "").strip().split() if p]
    if not parts: return "?"
    if len(parts) == 1: return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

def _avatar_image(username, accent, size=96, avatar_url=None):
    if avatar_url:
        img = _load_cached_image(avatar_url)
        if img is not None:
            img = _fit_cover(img, (size, size))
            img = img.convert("RGBA")
            img.putalpha(_circle_mask((size, size)))
            return img
    img = Image.new("RGBA", (size, size), tuple(accent) + (255,))
    d = ImageDraw.Draw(img)
    f = _font(size * 0.4)
    text = _initials(username)
    bbox = d.textbbox((0, 0), text, font=f)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, font=f, fill=(255, 255, 255, 240))
    img.putalpha(_circle_mask((size, size)))
    return img

def _qr_image(url=APP_URL, size=140, pad_ratio=0.16):
    if qrcode is None: return None
    try:
        qr = qrcode.QRCode(border=1, box_size=10)
        qr.add_data(url)
        qr.make(fit=True)
        code_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        code_img = code_img.resize((size, size), Image.LANCZOS)
        pad = int(size * pad_ratio)
        card = Image.new("RGBA", (size + pad * 2, size + pad * 2), (255, 255, 255, 255))
        card.putalpha(_rounded_mask(card.size, int(pad * 1.1)))
        card.paste(code_img, (pad, pad), code_img)
        return card
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════
# DOMINANT-COLOR EXTRACTION
# ══════════════════════════════════════════════════════════════════
def _extract_dominant_colors(img, n=5):
    small = img.convert("RGB").resize((64, 64))
    paletted = small.quantize(colors=max(n, 5), method=Image.MEDIANCUT)
    palette = paletted.getpalette()
    counts = sorted(paletted.getcolors(), reverse=True, key=lambda c: c[0])
    colors = []
    for count, idx in counts[:n]:
        colors.append(tuple(palette[idx * 3: idx * 3 + 3]))
    return colors

def _adjust(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)

def _dynamic_theme_from_colors(colors):
    def sat_val(c):
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        return s * v
    ordered = sorted(colors, key=sat_val, reverse=True)
    base = ordered[0]
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in base))
    s = max(s, 0.55)
    v = max(v, 0.75)
    accent = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
    accent2 = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, max(s - 0.3, 0.15), min(v + 0.15, 1)))
    stops = [_adjust(accent, 0.34), _adjust(accent, 0.55), _adjust(accent, 0.10)]
    return {"stops": stops, "accent": accent, "accent2": accent2}

def _get_dynamic_theme(image_url, fallback_theme):
    img = _load_cached_image(image_url) if image_url else None
    if img is None: return fallback_theme
    try:
        colors = _extract_dominant_colors(img, n=5)
        if not colors: return fallback_theme
        return _dynamic_theme_from_colors(colors)
    except Exception:
        return fallback_theme

def _resolve_theme(theme_choice, run_query, user_id, start_date, end_date, overview=None):
    if theme_choice != DYNAMIC_THEME_LABEL:
        return THEMES[theme_choice]
    top_artist_img = None
    if overview and overview.get("top_artist"):
        top_artist_img = overview["top_artist"].get("image_url")
    if not top_artist_img:
        ta_df = _fetch_data(run_query, "artists", 1, user_id, start_date, end_date)
        if ta_df is not None and not ta_df.empty:
            top_artist_img = ta_df.iloc[0].get("image_url")
    return _get_dynamic_theme(top_artist_img, THEMES["Spotify Green"])

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

def _add_particles(bg_rgba, accent, seed=0, density=1.0):
    w, h = bg_rgba.size
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dot_count = int(46 * density * (w * h) / (1080 * 1920))
    for _ in range(max(dot_count, 12)):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        r = rnd.uniform(2, 6) * (w / 1080)
        color = accent if rnd.random() < 0.35 else (255, 255, 255)
        alpha = rnd.randint(20, 85)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(color) + (alpha,))
    for _ in range(max(int(6 * density), 3)):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        r = rnd.uniform(26, 80) * (w / 1080)
        alpha = rnd.randint(10, 24)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(accent) + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(1))
    return Image.alpha_composite(bg_rgba, layer)

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
# DATA ACCESS 
# ══════════════════════════════════════════════════════════════════
def _date_range(period_key, min_date, max_date, custom_start=None, custom_end=None):
    if period_key == "custom":
        start = custom_start or min_date
        end = custom_end or max_date
        if start > end: start, end = end, start
        return start, end
    if period_key == "wrapped": return datetime.date(max_date.year, 1, 1), max_date
    if period_key == "month": return max_date - datetime.timedelta(days=30), max_date
    if period_key == "week": return max_date - datetime.timedelta(days=7), max_date
    return min_date, max_date

def _period_label_and_range(period_key, min_date, max_date, custom_start=None, custom_end=None):
    start, end = _date_range(period_key, min_date, max_date, custom_start, custom_end)
    if period_key == "all": return "ALL TIME", "All time"
    if period_key == "wrapped": return f"WRAPPED {max_date.year}", f"Jan – {max_date.strftime('%b %Y')}"
    if period_key == "month": return "LAST MONTH", f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    if period_key == "week": return "LAST WEEK", f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    year_label = f"{start.year}" if start.year == end.year else f"{start.year}–{end.year}"
    return f"{year_label}", f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"

def _title_lines(kind, n, item_name=None):
    if kind == "artists": return ["MY TOP", f"{n} ARTISTS"]
    if kind == "tracks": return ["MY TOP", f"{n} TRACKS"]
    if kind == "genres": return ["MY TOP", f"{n} GENRES"]
    if kind == "seasons": return ["MY TOP", "SEASONS"]
    if kind == "tod": return ["FAVORITE", "TIMES OF DAY"]
    if kind == "specific_album":
        safe = (item_name or "ALBUM").upper()
        if len(safe) > 16: safe = safe[:15] + "…"
        return ["TOP TRACKS FROM", safe]
    if kind == "specific_artist":
        safe = (item_name or "ARTIST").upper()
        if len(safe) > 16: safe = safe[:15] + "…"
        return [safe, "TOP INSIGHTS"]
    return ["MY TOP", "ALBUMS"]

def _fetch_data(run_query, kind, limit, user_id, start_date, end_date, item_id=None):
    params = {"start_date": start_date, "end_date": end_date, "user_id": user_id, "limit": limit}
    if item_id is not None:
        params["item_id"] = item_id

    if kind == "artists":
        sql = """
            SELECT a.name AS name, a.image_url AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE JOIN artists a ON a.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id
            GROUP BY a.id, a.name, a.image_url ORDER BY streams DESC LIMIT :limit;
        """
        return run_query(sql, params)
    elif kind == "tracks":
        sql = """
            SELECT so.title AS name, COALESCE(ar.name, 'Unknown') AS sub, so.image_url AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE LEFT JOIN artists ar ON ar.id = sa.artist_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id
            GROUP BY so.id, so.title, ar.name, so.image_url ORDER BY streams DESC LIMIT :limit;
        """
        return run_query(sql, params)
    elif kind == "albums":
        sql = """
            SELECT COALESCE(al.title, 'Unknown Album') AS name, MAX(so.image_url) AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN albums al ON al.id = so.album_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND so.album_id IS NOT NULL
            GROUP BY al.id, al.title ORDER BY streams DESC LIMIT :limit;
        """
        return run_query(sql, params)
    elif kind == "genres":
        sql = """
            WITH StreamBase AS (
                SELECT s.id AS stream_id, s.ms_played, sa.artist_id, so.primary_genre AS song_genre, al.primary_genre AS album_genre, so.album_id
                FROM streams s JOIN songs so ON so.id = s.song_id LEFT JOIN albums al ON al.id = so.album_id JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id
            ),
            Unrolled AS (
                SELECT stream_id, ms_played, artist_id, song_genre AS genre_name FROM StreamBase WHERE song_genre IS NOT NULL
                UNION ALL SELECT stream_id, ms_played, artist_id, album_genre FROM StreamBase WHERE album_genre IS NOT NULL
                UNION ALL SELECT sb.stream_id, sb.ms_played, sb.artist_id, g.name FROM StreamBase sb JOIN album_genres ag ON ag.album_id = sb.album_id JOIN genres g ON g.id = ag.genre_id
            ),
            UniqueStreamGenres AS (
                SELECT DISTINCT stream_id, ms_played, artist_id, INITCAP(TRIM(genre_name)) AS genre_name FROM Unrolled WHERE genre_name IS NOT NULL AND LOWER(genre_name) != 'unknown'
            )
            SELECT genre_name AS name, CAST(COUNT(DISTINCT artist_id) AS TEXT) || ' Artists' AS sub, NULL AS image_url, COUNT(stream_id) AS streams, ROUND(SUM(ms_played) / 3600000.0, 1) AS hours
            FROM UniqueStreamGenres GROUP BY genre_name ORDER BY streams DESC LIMIT :limit;
        """
        return run_query(sql, params)
    elif kind == "seasons":
        sql = """
            SELECT CASE WHEN EXTRACT(MONTH FROM played_at) IN (12,1,2) THEN 'Winter' WHEN EXTRACT(MONTH FROM played_at) IN (3,4,5) THEN 'Spring' WHEN EXTRACT(MONTH FROM played_at) IN (6,7,8) THEN 'Summer' ELSE 'Autumn' END AS name,
                   'Seasonal Listening' AS sub, NULL AS image_url, COUNT(*) AS streams, ROUND(SUM(ms_played) / 3600000.0, 1) AS hours
            FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id GROUP BY name ORDER BY streams DESC LIMIT :limit;
        """
        df = run_query(sql, params)
        if df is not None and not df.empty: df['image_url'] = df['name'].map(CUSTOM_IMAGES)
        return df
    elif kind == "tod":
        sql = """
            SELECT CASE WHEN EXTRACT(HOUR FROM played_at) >= 21 OR EXTRACT(HOUR FROM played_at) < 5 THEN 'Night' WHEN EXTRACT(HOUR FROM played_at) BETWEEN 5 AND 11 THEN 'Morning' WHEN EXTRACT(HOUR FROM played_at) BETWEEN 12 AND 16 THEN 'Afternoon' ELSE 'Evening' END AS name,
                   'Time of Day' AS sub, NULL AS image_url, COUNT(*) AS streams, ROUND(SUM(ms_played) / 3600000.0, 1) AS hours
            FROM streams WHERE played_at::date BETWEEN :start_date AND :end_date AND user_id = :user_id GROUP BY name ORDER BY streams DESC LIMIT :limit;
        """
        df = run_query(sql, params)
        if df is not None and not df.empty: df['image_url'] = df['name'].map(CUSTOM_IMAGES)
        return df
    elif kind == "specific_album":
        sql = """
            SELECT so.title AS name, 'Track' AS sub, so.image_url AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played) / 3600000.0, 1) AS hours
            FROM streams s JOIN songs so ON so.id = s.song_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND so.album_id = :item_id
            GROUP BY so.id, so.title, so.image_url ORDER BY streams DESC LIMIT :limit;
        """
        return run_query(sql, params)
    elif kind == "specific_artist":
        sql_tracks = """
            SELECT so.title AS name, 'Track' AS sub, so.image_url AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played)/3600000.0,1) AS hours
            FROM streams s JOIN songs so ON so.id=s.song_id JOIN song_artists sa ON sa.song_id=so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND sa.artist_id = :item_id AND sa.is_feature=FALSE
            GROUP BY so.id, so.title, so.image_url ORDER BY streams DESC LIMIT 3
        """
        sql_albums = """
            SELECT al.title AS name, 'Album' AS sub, MAX(so.image_url) AS image_url, COUNT(s.id) AS streams, ROUND(SUM(s.ms_played)/3600000.0,1) AS hours
            FROM streams s JOIN songs so ON so.id=s.song_id JOIN albums al ON al.id=so.album_id JOIN song_artists sa ON sa.song_id=so.id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND sa.artist_id = :item_id AND sa.is_feature=FALSE
            GROUP BY al.id, al.title ORDER BY streams DESC LIMIT 3
        """
        df_t = run_query(sql_tracks, params)
        df_a = run_query(sql_albums, params)
        dfs = []
        if df_t is not None and not df_t.empty: dfs.append(df_t)
        if df_a is not None and not df_a.empty: dfs.append(df_a)
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()
    return pd.DataFrame()


def _fetch_totals(run_query, user_id, start_date, end_date):
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

def _fetch_personality_signals(run_query, user_id, start_date, end_date):
    sql = """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE EXTRACT(HOUR FROM s.played_at) >= 21 OR EXTRACT(HOUR FROM s.played_at) < 5) AS night_count,
          COUNT(*) FILTER (WHERE EXTRACT(ISODOW FROM s.played_at) IN (6,7)) AS weekend_count,
          COUNT(DISTINCT s.song_id) AS unique_tracks,
          COUNT(DISTINCT sa.artist_id) AS unique_artists
        FROM streams s
        LEFT JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
        WHERE s.played_at::date BETWEEN :start_date AND :end_date
          AND s.user_id = :user_id;
    """
    params = {"start_date": start_date, "end_date": end_date, "user_id": user_id}
    df = run_query(sql, params)
    if df is None or df.empty:
        return {"total": 0, "night_count": 0, "weekend_count": 0, "unique_tracks": 0, "unique_artists": 0}
    row = df.iloc[0]
    return {
        "total": int(row.get("total") or 0),
        "night_count": int(row.get("night_count") or 0),
        "weekend_count": int(row.get("weekend_count") or 0),
        "unique_tracks": int(row.get("unique_tracks") or 0),
        "unique_artists": int(row.get("unique_artists") or 0),
    }

def _compute_personality(signals, overview):
    total = signals["total"]
    if total < 20: return PERSONALITIES["newcomer"]
    night_pct = signals["night_count"] / total
    weekend_pct = signals["weekend_count"] / total
    unique_tracks = signals["unique_tracks"] or 1
    unique_artists = signals["unique_artists"] or 1
    repeat_rate = total / unique_tracks
    diversity = unique_artists / total
    top_artist_streams = int(overview["top_artist"].get("streams") or 0) if overview.get("top_artist") else 0
    concentration = (top_artist_streams / total) if total else 0

    if night_pct >= 0.42: return PERSONALITIES["night_owl"]
    if concentration >= 0.22: return PERSONALITIES["superfan"]
    if overview.get("total_hours", 0) >= 250: return PERSONALITIES["marathoner"]
    if weekend_pct >= 0.45: return PERSONALITIES["weekend_warrior"]
    if repeat_rate >= 7: return PERSONALITIES["repeater"]
    if diversity >= 0.12 or unique_artists >= 120: return PERSONALITIES["explorer"]
    if unique_tracks >= total * 0.55: return PERSONALITIES["collector"]
    return PERSONALITIES["default"]


# ══════════════════════════════════════════════════════════════════
# SHARED CARD SHELL 
# ══════════════════════════════════════════════════════════════════
def _card_background(card_w, card_h, theme, seed):
    bg = _make_gradient((card_w, card_h), theme["stops"])
    bg = _add_glow(bg, (card_w * 0.12, card_h * 0.06), int(card_h * 0.24), theme["accent2"], 65)
    bg = _add_glow(bg, (card_w * 0.92, card_h * 0.9), int(card_h * 0.27), theme["accent"], 55)
    bg = _add_particles(bg, theme["accent"], seed=seed, density=card_h / 1920)
    return bg

def _card_header(bg, card_w, card_h, scale, accent, username, avatar_url, period_label,
                 title_lines, subtitle_text, title_font_size=92):
    draw = ImageDraw.Draw(bg)

    avatar_size = int(64 * scale)
    avatar_img = _avatar_image(username, accent, size=avatar_size, avatar_url=avatar_url)
    avatar_y = int(56 * scale)
    bg.paste(avatar_img, (MARGIN, avatar_y), avatar_img)
    draw = ImageDraw.Draw(bg)
    ring_box = [MARGIN - 2, avatar_y - 2, MARGIN + avatar_size + 2, avatar_y + avatar_size + 2]
    draw.ellipse(ring_box, outline=(255, 255, 255, 90), width=2)

    logo_font = _font(24 * scale)
    logo_x = MARGIN + avatar_size + int(18 * scale)
    draw.text((logo_x, avatar_y + avatar_size / 2 - 8 * scale), "\u266A SUGGESTIFY",
               font=logo_font, fill=(255, 255, 255, 235))
    uname_font = _font(18 * scale, bold=False)
    draw.text((logo_x, avatar_y + avatar_size / 2 + 14 * scale), f"@{username}",
               font=uname_font, fill=(255, 255, 255, 150))

    pill_font = _font(26 * scale)
    pw = _text_w(draw, period_label, pill_font) + int(56 * scale)
    ph = int(54 * scale)
    pill_top = int(62 * scale)
    pill_box = [card_w - MARGIN - pw, pill_top, card_w - MARGIN, pill_top + ph]
    draw.rounded_rectangle(pill_box, radius=ph // 2, fill=tuple(accent) + (255,))
    draw.text(((pill_box[0] + pill_box[2]) / 2, (pill_box[1] + pill_box[3]) / 2),
               period_label, font=pill_font, fill=(0, 0, 0, 255), anchor="mm")

    title_font = _font(title_font_size * scale)
    y = int(190 * scale)
    line_h = int(title_font_size * scale * 1.13)
    for line in title_lines:
        w = _text_w(draw, line, title_font)
        draw.text(((card_w - w) / 2, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += line_h

    sub_font = _font(30 * scale)
    w = _text_w(draw, subtitle_text, sub_font)
    draw.text(((card_w - w) / 2, y + 14 * scale), subtitle_text, font=sub_font, fill=(255, 255, 255, 170))

    return bg, y + int(90 * scale)

def _card_footer(bg, card_w, card_h, scale, accent, footer_stats):
    extras_h = int(140 * scale)
    footer_h = int(150 * scale)
    footer_top = card_h - extras_h - footer_h - int(20 * scale)
    foot_box = [MARGIN, footer_top, card_w - MARGIN, footer_top + footer_h]

    bg = _drop_shadow(bg, foot_box, radius=int(26 * scale), blur=int(16 * scale), offset=(0, int(6 * scale)), alpha=70)
    bg = _glass_card(bg, foot_box, radius=int(26 * scale), blur=16, tint=(255, 255, 255, 18))
    draw = ImageDraw.Draw(bg)

    num_stats = len(footer_stats)
    col_w = (foot_box[2] - foot_box[0]) / num_stats
    
    stat_big = _font(36 * scale if num_stats > 2 else 40 * scale)
    stat_small = _font(18 * scale if num_stats > 2 else 20 * scale, bold=False)
    
    cy1 = foot_box[1] + footer_h * 0.38
    cy2 = foot_box[1] + footer_h * 0.72

    for i, (val, lab) in enumerate(footer_stats):
        cx = foot_box[0] + i * col_w + col_w / 2
        
        # Color logic: alternate white and accent
        if num_stats == 3:
            val_color = tuple(accent) + (255,) if i == 1 else (255, 255, 255, 255)
        else:
            val_color = (255, 255, 255, 255) if i == 0 else tuple(accent) + (255,)
            
        draw.text((cx, cy1), str(val), font=stat_big, fill=val_color, anchor="mm")
        draw.text((cx, cy2), str(lab), font=stat_small, fill=(255, 255, 255, 150), anchor="mm")

    extras_top = card_h - extras_h
    qr_size = int(96 * scale)
    qr_img = _qr_image(size=qr_size)

    wm_font = _font(20 * scale)
    date_font = _font(16 * scale, bold=False)
    wm_text = "Generated by Suggestify"
    date_text = datetime.date.today().strftime("%b %d, %Y")

    draw.text((MARGIN, extras_top + extras_h * 0.38), wm_text, font=wm_font,
               fill=(255, 255, 255, 200), anchor="lm")
    draw.text((MARGIN, extras_top + extras_h * 0.68), date_text, font=date_font,
               fill=(255, 255, 255, 130), anchor="lm")

    if qr_img:
        qr_x = card_w - MARGIN - qr_img.width
        qr_y = int(extras_top + (extras_h - qr_img.height) / 2)
        bg.paste(qr_img, (qr_x, qr_y), qr_img)
        draw = ImageDraw.Draw(bg)
        scan_font = _font(14 * scale, bold=False)
        draw.text((qr_x + qr_img.width / 2, qr_y - 6 * scale), "SCAN ME", font=scan_font,
                   fill=(255, 255, 255, 130), anchor="mb")
    return bg

def _finalize(bg):
    return bg.convert("RGB")

# ══════════════════════════════════════════════════════════════════
# CARD BUILDER 1 — Top-N ranked list 
# ══════════════════════════════════════════════════════════════════
def build_share_card(df, kind, username, period_label, theme, date_range_label, n,
                      footer_stats, avatar_url=None, item_name=None,
                      card_w=CARD_W, card_h=CARD_H):
    accent = theme["accent"]
    scale = card_h / 1920.0
    seed = abs(hash((username, kind, period_label, n))) % (2 ** 32)

    bg = _card_background(card_w, card_h, theme, seed)
    subtitle_text = f"@{username}  ·  {date_range_label}"
    bg, list_top = _card_header(bg, card_w, card_h, scale, accent, username, avatar_url,
                                 period_label, _title_lines(kind, n, item_name), subtitle_text)

    extras_h = int(140 * scale)
    footer_h = int(150 * scale)
    list_bottom = card_h - extras_h - footer_h - int(40 * scale)

    rows = df.to_dict("records")
    n_rows = max(len(rows), 1)
    gap = int(16 * scale)
    
    available_h = list_bottom - list_top
    header_h = 0
    if kind == "specific_artist":
        header_h = int(35 * scale)
        available_h -= (2 * header_h) + int(15 * scale)

    row_h = min(220 * scale, (available_h - gap * (n_rows - 1)) / n_rows)
    row_h = max(row_h, int(60 * scale))

    is_circle = (kind == "artists" or kind == "specific_artist")
    rank_col_w = int(96 * scale)

    icon = "🎵"
    if kind == "genres": icon = "🎸"
    elif kind == "seasons": icon = "🌍"
    elif kind == "tod": icon = "🕐"

    track_count = 0
    album_count = 0
    current_y = list_top

    for i, row in enumerate(rows):
        if kind == "specific_artist":
            if row.get("sub") == "Track":
                if track_count == 0:
                    draw = ImageDraw.Draw(bg)
                    header_f = _font(20 * scale, bold=True)
                    txt = "TOP TRACKS"
                    w = _text_w(draw, txt, header_f)
                    draw.text((card_w/2 - w/2, current_y + 4 * scale), txt, font=header_f, fill=tuple(accent)+(255,))
                    current_y += header_h
                track_count += 1
                rank = track_count
            elif row.get("sub") == "Album":
                if album_count == 0:
                    current_y += int(15 * scale) 
                    draw = ImageDraw.Draw(bg)
                    header_f = _font(20 * scale, bold=True)
                    txt = "TOP ALBUMS"
                    w = _text_w(draw, txt, header_f)
                    draw.text((card_w/2 - w/2, current_y + 4 * scale), txt, font=header_f, fill=tuple(accent)+(255,))
                    current_y += header_h
                album_count += 1
                rank = album_count
            else:
                rank = i + 1
        else:
            rank = i + 1

        box = [MARGIN, current_y, card_w - MARGIN, current_y + row_h]

        bg = _drop_shadow(bg, box, radius=int(28 * scale), blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=int(28 * scale), blur=18)
        draw = ImageDraw.Draw(bg)

        rank_color = RANK_COLORS.get(rank, (255, 255, 255))
        rank_font = _font(row_h * 0.4)
        draw.text((box[0] + rank_col_w / 2, (box[1] + box[3]) / 2),
                   str(rank), font=rank_font, fill=rank_color + (255,), anchor="mm")

        art_size = int(row_h - 24 * scale)
        art_x = box[0] + rank_col_w
        art_y = box[1] + (row_h - art_size) / 2
        
        row_icon = icon
        if kind == "specific_artist":
            row_icon = "🎵" if row.get("sub") == "Track" else "💿"
            
        art = _get_art(row.get("image_url"), (art_size, art_size), circle=is_circle, accent=accent, icon=row_icon)
        bg.paste(art, (int(art_x), int(art_y)), art)

        info_x = art_x + art_size + 28 * scale
        stats_col_w = 230 * scale
        info_max_w = (box[2] - stats_col_w) - info_x - 16 * scale

        has_sub = "sub" in df.columns and row.get("sub")
        name = str(row.get("name", ""))

        if has_sub:
            title_f = _font(row_h * 0.22)
            sub_f = _font(row_h * 0.16, bold=False)
            title_txt = _truncate(draw, name, title_f, info_max_w)
            sub_txt = _truncate(draw, str(row["sub"]), sub_f, info_max_w)
            title_y = box[1] + row_h * 0.28
            draw.text((info_x, title_y), title_txt, font=title_f, fill=(255, 255, 255, 255), anchor="lm")
            draw.text((info_x, box[1] + row_h * 0.66), sub_txt, font=sub_f, fill=(255, 255, 255, 170), anchor="lm")
        else:
            title_f = _font(row_h * 0.24)
            title_txt = _truncate(draw, name, title_f, info_max_w)
            draw.text((info_x, (box[1] + box[3]) / 2), title_txt, font=title_f,
                       fill=(255, 255, 255, 255), anchor="lm")

        streams_val = int(row.get("streams") or 0)
        stat_font = _font(row_h * 0.24)
        label_font = _font(row_h * 0.13, bold=False)
        stats_x = box[2] - 24 * scale
        draw.text((stats_x, box[1] + row_h * 0.38), f"{streams_val:,}", font=stat_font,
                   fill=tuple(accent) + (255,), anchor="rm")
        draw.text((stats_x, box[1] + row_h * 0.68), "STREAMS", font=label_font,
                   fill=(255, 255, 255, 140), anchor="rm")

        current_y += row_h + gap

    bg = _card_footer(bg, card_w, card_h, scale, accent, footer_stats)
    return _finalize(bg)

# ══════════════════════════════════════════════════════════════════
# CARD BUILDER 2 — Overview
# ══════════════════════════════════════════════════════════════════
def build_overview_card(overview, username, period_label, theme, date_range_label, footer_stats,
                         avatar_url=None, card_w=CARD_W, card_h=CARD_H):
    accent = theme["accent"]
    scale = card_h / 1920.0
    seed = abs(hash((username, "overview", period_label))) % (2 ** 32)

    bg = _card_background(card_w, card_h, theme, seed)
    subtitle_text = f"@{username}  ·  {date_range_label}"
    bg, content_top = _card_header(bg, card_w, card_h, scale, accent, username, avatar_url,
                                    period_label, ["MY LISTENING", "OVERVIEW"], subtitle_text,
                                    title_font_size=88)

    grid_gap = int(24 * scale)
    grid_h = int(230 * scale)
    col_w = (card_w - 2 * MARGIN - grid_gap) / 2

    stats = [
        (f"{overview['total_streams']:,}", "TOTAL STREAMS"),
        (f"{overview['total_hours']:,.1f}h", "TIME LISTENED"),
        (f"{overview['unique_artists']:,}", "UNIQUE ARTISTS"),
        (f"{overview['unique_tracks']:,}", "UNIQUE TRACKS"),
    ]

    for i, (value, label) in enumerate(stats):
        col, row_i = i % 2, i // 2
        x0 = MARGIN + col * (col_w + grid_gap)
        y0 = content_top + row_i * (grid_h + grid_gap)
        box = [x0, y0, x0 + col_w, y0 + grid_h]

        bg = _drop_shadow(bg, box, radius=int(32 * scale), blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=int(32 * scale), blur=18)
        draw = ImageDraw.Draw(bg)

        val_font = _font(64 * scale)
        lab_font = _font(22 * scale, bold=False)
        cx = (box[0] + box[2]) / 2
        draw.text((cx, box[1] + grid_h * 0.42), value, font=val_font, fill=tuple(accent) + (255,), anchor="mm")
        draw.text((cx, box[1] + grid_h * 0.72), label, font=lab_font, fill=(255, 255, 255, 160), anchor="mm")

    highlight_top = content_top + 2 * grid_h + grid_gap + int(30 * scale)
    highlight_h = int(180 * scale)

    def _highlight_row(y0, art_url, is_circle, name, sub, streams, tag):
        nonlocal bg
        box = [MARGIN, y0, card_w - MARGIN, y0 + highlight_h]
        bg = _drop_shadow(bg, box, radius=int(28 * scale), blur=18, offset=(0, 8), alpha=85)
        bg = _glass_card(bg, box, radius=int(28 * scale), blur=18)
        d = ImageDraw.Draw(bg)

        tag_font = _font(18 * scale)
        d.text((box[0] + 24 * scale, box[1] + 14 * scale), tag, font=tag_font, fill=tuple(accent) + (255,))

        art_size = int(highlight_h - 62 * scale)
        art_x = box[0] + 24 * scale
        art_y = box[1] + 48 * scale
        art = _get_art(art_url, (art_size, art_size), circle=is_circle, accent=accent)
        bg.paste(art, (int(art_x), int(art_y)), art)

        info_x = art_x + art_size + 26 * scale
        name_font = _font(34 * scale)
        sub_font_ = _font(22 * scale, bold=False)
        info_max_w = card_w - MARGIN - 120 * scale - info_x
        name_txt = _truncate(d, name, name_font, info_max_w)
        d.text((info_x, box[1] + 70 * scale), name_txt, font=name_font, fill=(255, 255, 255, 255), anchor="lm")
        if sub:
            sub_txt = _truncate(d, sub, sub_font_, info_max_w)
            d.text((info_x, box[1] + 110 * scale), sub_txt, font=sub_font_, fill=(255, 255, 255, 170), anchor="lm")

        stat_font = _font(30 * scale)
        lab_font = _font(15 * scale, bold=False)
        d.text((box[2] - 24 * scale, box[1] + 70 * scale), f"{streams:,}", font=stat_font,
               fill=tuple(accent) + (255,), anchor="rm")
        d.text((box[2] - 24 * scale, box[1] + 100 * scale), "STREAMS", font=lab_font,
               fill=(255, 255, 255, 140), anchor="rm")

    if overview.get("top_artist"):
        ta = overview["top_artist"]
        _highlight_row(highlight_top, ta.get("image_url"), True, ta.get("name", ""), "",
                       int(ta.get("streams") or 0), "TOP ARTIST")
        highlight_top += highlight_h + int(18 * scale)

    if overview.get("top_track"):
        tt = overview["top_track"]
        _highlight_row(highlight_top, tt.get("image_url"), False, tt.get("name", ""), tt.get("sub", ""),
                       int(tt.get("streams") or 0), "TOP TRACK")

    bg = _card_footer(bg, card_w, card_h, scale, accent, footer_stats)
    return _finalize(bg)

# ══════════════════════════════════════════════════════════════════
# CARD BUILDER 3 — Listening Personality
# ══════════════════════════════════════════════════════════════════
def build_personality_card(personality, overview, username, period_label, theme, date_range_label,
                            footer_stats, avatar_url=None, card_w=CARD_W, card_h=CARD_H):
    accent = theme["accent"]
    scale = card_h / 1920.0
    seed = abs(hash((username, "personality", period_label))) % (2 ** 32)

    bg = _card_background(card_w, card_h, theme, seed)
    subtitle_text = f"@{username}  ·  {date_range_label}"
    bg, content_top = _card_header(bg, card_w, card_h, scale, accent, username, avatar_url,
                                    period_label, ["YOUR LISTENING", "PERSONALITY"], subtitle_text,
                                    title_font_size=76)
    draw = ImageDraw.Draw(bg)

    hero_h = int(560 * scale)
    hero_box = [MARGIN, content_top, card_w - MARGIN, content_top + hero_h]
    bg = _drop_shadow(bg, hero_box, radius=int(40 * scale), blur=20, offset=(0, 10), alpha=90)
    bg = _glass_card(bg, hero_box, radius=int(40 * scale), blur=20, tint=(255, 255, 255, 22))
    draw = ImageDraw.Draw(bg)

    emoji_font = _font(150 * scale)
    cx = (hero_box[0] + hero_box[2]) / 2
    emoji_y = hero_box[1] + hero_h * 0.28
    draw.text((cx, emoji_y), personality["emoji"], font=emoji_font, anchor="mm")

    label_font = _font(64 * scale)
    label_y = hero_box[1] + hero_h * 0.56
    w = _text_w(draw, personality["label"], label_font)
    draw.text(((card_w - w) / 2, label_y - 40 * scale), personality["label"], font=label_font,
               fill=tuple(accent) + (255,))

    desc_font = _font(28 * scale, bold=False)
    desc_lines = _wrap_text(draw, personality["desc"], desc_font, hero_box[2] - hero_box[0] - 120 * scale, max_lines=2)
    dy = hero_box[1] + hero_h * 0.72
    for line in desc_lines:
        w = _text_w(draw, line, desc_font)
        draw.text(((card_w - w) / 2, dy), line, font=desc_font, fill=(255, 255, 255, 190))
        dy += 40 * scale

    stats_top = hero_box[3] + int(30 * scale)
    stats_h = int(190 * scale)
    stats_gap = int(20 * scale)
    stats = [
        (f"{overview['total_streams']:,}", "STREAMS"),
        (f"{overview['total_hours']:,.1f}h", "HOURS"),
        (f"{overview['unique_artists']:,}", "ARTISTS"),
    ]
    col_w = (card_w - 2 * MARGIN - 2 * stats_gap) / 3
    for i, (value, label) in enumerate(stats):
        x0 = MARGIN + i * (col_w + stats_gap)
        box = [x0, stats_top, x0 + col_w, stats_top + stats_h]
        bg = _drop_shadow(bg, box, radius=int(26 * scale), blur=16, offset=(0, 6), alpha=80)
        bg = _glass_card(bg, box, radius=int(26 * scale), blur=16)
        d = ImageDraw.Draw(bg)
        val_font = _font(42 * scale)
        lab_font = _font(17 * scale, bold=False)
        cxi = (box[0] + box[2]) / 2
        d.text((cxi, box[1] + stats_h * 0.42), value, font=val_font, fill=(255, 255, 255, 255), anchor="mm")
        d.text((cxi, box[1] + stats_h * 0.72), label, font=lab_font, fill=(255, 255, 255, 150), anchor="mm")

    bg = _card_footer(bg, card_w, card_h, scale, accent, footer_stats)
    return _finalize(bg)

def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def _zip_bytes(named_pngs: dict):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in named_pngs.items():
            zf.writestr(name, data)
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════
# LIVE HTML/CSS PREVIEW
# ══════════════════════════════════════════════════════════════════
def _particles_html(seed, accent_css, count=22):
    rnd = random.Random(seed)
    spans = []
    for _ in range(count):
        left = rnd.uniform(2, 98)
        size = rnd.uniform(3, 8)
        delay = rnd.uniform(0, 6)
        duration = rnd.uniform(6, 14)
        color = accent_css if rnd.random() < 0.4 else "rgba(255,255,255,0.8)"
        spans.append(
            f'<span class="sh-particle" style="left:{left:.1f}%; width:{size:.1f}px; height:{size:.1f}px; '
            f'background:{color}; animation-delay:-{delay:.1f}s; animation-duration:{duration:.1f}s;"></span>'
        )
    return "".join(spans)

def _html_preview(df, kind, username, period_label, theme, date_range_label, n, avatar_url=None, item_name=None):
    accent = "rgb({},{},{})".format(*theme["accent"])
    s0, s1, s2 = theme["stops"]
    grad = f"linear-gradient(160deg, rgb{tuple(s1)} 0%, rgb{tuple(s0)} 45%, rgb{tuple(s2)} 100%)"
    is_circle = kind == "artists" or kind == "specific_artist"
    radius = "50%" if is_circle else "12px"
    seed = abs(hash((username, kind, period_label))) % (2 ** 32)

    avatar_html = (
        f'<img src="{avatar_url}" class="sh-avatar-img">' if avatar_url
        else f'<div class="sh-avatar-fallback" style="background:{accent}">{_initials(username)}</div>'
    )

    icon = "🎵"
    if kind == "genres": icon = "🎸"
    elif kind == "seasons": icon = "🌍"
    elif kind == "tod": icon = "🕐"

    rows_html = ""
    track_count = 0
    album_count = 0

    for i, row in df.head(n).iterrows():
        if kind == "specific_artist":
            if row.get("sub") == "Track":
                if track_count == 0:
                    rows_html += f'<div style="text-align:center; font-size:10px; font-weight:800; color:{accent}; margin: 8px 0 4px; letter-spacing:0.1em;">TOP TRACKS</div>'
                track_count += 1
                rank = track_count
            elif row.get("sub") == "Album":
                if album_count == 0:
                    rows_html += f'<div style="text-align:center; font-size:10px; font-weight:800; color:{accent}; margin: 12px 0 4px; letter-spacing:0.1em;">TOP ALBUMS</div>'
                album_count += 1
                rank = album_count
            else:
                rank = i + 1
        else:
            rank = i + 1

        rank_color = "rgb({},{},{})".format(*RANK_COLORS.get(rank, (255, 255, 255)))
        
        row_icon = icon
        if kind == "specific_artist":
            row_icon = "🎵" if row.get("sub") == "Track" else "💿"

        img = row.get("image_url")
        art = (f'<img src="{img}" style="width:100%;height:100%;object-fit:cover;border-radius:{radius};">'
               if isinstance(img, str) and img.startswith("http") else row_icon)
        
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

    title = _title_lines(kind, n, item_name)
    particles = _particles_html(seed, accent)
    return f"""
    <!doctype html><html><head><meta charset="utf-8"></head>
    <body>
    <div class="sh-card" style="background:{grad}">
        <div class="sh-particles">{particles}</div>
        <div class="sh-glow" style="background:radial-gradient(circle, {accent}55, transparent 70%)"></div>
        <div class="sh-header">
            <div class="sh-id">
                {avatar_html}
                <div class="sh-logo">\u266A SUGGESTIFY</div>
            </div>
            <div class="sh-pill" style="background:{accent}">{period_label}</div>
        </div>
        <div class="sh-title">{title[0]}<br>{title[1]}</div>
        <div class="sh-subtitle">@{username} &middot; {date_range_label}</div>
        <div class="sh-list">{rows_html}</div>
        <div class="sh-footer">Generated by Suggestify</div>
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
        .sh-particles {{ position:absolute; inset:0; overflow:hidden; pointer-events:none; }}
        .sh-particle {{
            position:absolute; bottom:-10px; border-radius:50%; opacity:0.9;
            animation-name: sh-float; animation-timing-function: linear; animation-iteration-count: infinite;
        }}
        @keyframes sh-float {{
            0%   {{ transform: translateY(0) translateX(0); opacity: 0; }}
            10%  {{ opacity: 0.9; }}
            90%  {{ opacity: 0.5; }}
            100% {{ transform: translateY(-560px) translateX(14px); opacity: 0; }}
        }}
        .sh-header {{ display:flex; justify-content:space-between; align-items:center; position:relative; z-index:1; }}
        .sh-id {{ display:flex; align-items:center; gap:8px; }}
        .sh-avatar-img, .sh-avatar-fallback {{
            width:26px; height:26px; border-radius:50%; object-fit:cover;
            border:1px solid rgba(255,255,255,0.5);
        }}
        .sh-avatar-fallback {{
            display:flex; align-items:center; justify-content:center;
            font-size:9px; font-weight:800; color:#000;
        }}
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
        .sh-footer {{ position:absolute; bottom:10px; left:0; right:0; text-align:center; font-size:8px; opacity:0.45; z-index:1; }}
    </style>
    </body></html>
    """

# ══════════════════════════════════════════════════════════════════
# STREAMLIT MODAL
# ══════════════════════════════════════════════════════════════════
_dialog_decorator = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)

def _generate_both_formats(builder_fn, **kwargs):
    out = {}
    for fmt_label, (w, h) in FORMATS.items():
        img = builder_fn(card_w=w, card_h=h, **kwargs)
        out[fmt_label] = image_to_bytes(img)
    return out

def _run_share_dialog(run_query, user_id, username, min_date, max_date, avatar_url=None):
    st.caption("Create a Wrapped-style card of your listening stats and share it anywhere.")

    theme_options = list(THEMES.keys()) + [DYNAMIC_THEME_LABEL]

    c1, c2, c3 = st.columns(3)
    with c1:
        stat_choice = st.selectbox("What to show", list(STAT_TYPES.keys()), key="share_stat_choice")
    with c2:
        period_choice = st.selectbox("Time period", list(PERIODS.keys()), key="share_period_choice")
    with c3:
        theme_choice = st.selectbox("Theme", theme_options, key="share_theme_choice")

    kind, n = STAT_TYPES[stat_choice]
    period_key = PERIODS[period_choice]

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

    # ---> NEW: TEXT INPUT SEARCH FOR SPECIFIC ALBUM / ARTIST <---
    item_id = None
    item_name = None

    if kind == "specific_album":
        search_term = st.text_input("🔍 Search for an Album (leave empty for your Top 50):", key="search_album_input")
        if search_term:
            albums_df = run_query("""
                SELECT al.id, al.title, MAX(a.name) as artist
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                JOIN albums al ON al.id = so.album_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :sd AND :ed AND s.user_id = :uid
                  AND al.title ILIKE :search
                GROUP BY al.id, al.title
                ORDER BY COUNT(s.id) DESC LIMIT 20
            """, {"sd": start_date, "ed": end_date, "uid": user_id, "search": f"%{search_term}%"})
            
            if albums_df is None or albums_df.empty:
                st.warning("No albums found matching your search in this period.")
                return
            
            opts = {row["id"]: f"{row['title']} (by {row['artist']})" for _, row in albums_df.iterrows()}
            item_id = st.selectbox("Select Album:", options=list(opts.keys()), format_func=lambda x: opts[x])
            item_name = albums_df.loc[albums_df["id"] == item_id, "title"].iloc[0]
        else:
            albums_df = run_query("""
                SELECT al.id, al.title, MAX(a.name) as artist
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                JOIN albums al ON al.id = so.album_id
                LEFT JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                LEFT JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :sd AND :ed AND s.user_id = :uid
                GROUP BY al.id, al.title
                ORDER BY COUNT(s.id) DESC LIMIT 50
            """, {"sd": start_date, "ed": end_date, "uid": user_id})
            
            if albums_df is None or albums_df.empty:
                st.warning("No albums found in this period.")
                return
                
            opts = {row["id"]: f"{row['title']} (by {row['artist']})" for _, row in albums_df.iterrows()}
            item_id = st.selectbox("Select Album:", options=list(opts.keys()), format_func=lambda x: opts[x])
            item_name = albums_df.loc[albums_df["id"] == item_id, "title"].iloc[0]

    elif kind == "specific_artist":
        search_term = st.text_input("🔍 Search for an Artist (leave empty for your Top 50):", key="search_artist_input")
        if search_term:
            artists_df = run_query("""
                SELECT a.id, a.name
                FROM streams s
                JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :sd AND :ed AND s.user_id = :uid
                  AND a.name ILIKE :search
                GROUP BY a.id, a.name
                ORDER BY COUNT(s.id) DESC LIMIT 20
            """, {"sd": start_date, "ed": end_date, "uid": user_id, "search": f"%{search_term}%"})
            
            if artists_df is None or artists_df.empty:
                st.warning("No artists found matching your search in this period.")
                return
                
            opts = {row["id"]: row["name"] for _, row in artists_df.iterrows()}
            item_id = st.selectbox("Select Artist:", options=list(opts.keys()), format_func=lambda x: opts[x])
            item_name = opts[item_id]
        else:
            artists_df = run_query("""
                SELECT a.id, a.name
                FROM streams s
                JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE s.played_at::date BETWEEN :sd AND :ed AND s.user_id = :uid
                GROUP BY a.id, a.name
                ORDER BY COUNT(s.id) DESC LIMIT 50
            """, {"sd": start_date, "ed": end_date, "uid": user_id})
            
            if artists_df is None or artists_df.empty:
                st.warning("No artists found in this period.")
                return
                
            opts = {row["id"]: row["name"] for _, row in artists_df.iterrows()}
            item_id = st.selectbox("Select Artist:", options=list(opts.keys()), format_func=lambda x: opts[x])
            item_name = opts[item_id]

    total_streams, total_hours = _fetch_totals(run_query, user_id, start_date, end_date)
    
    # ── ΔΥΝΑΜΙΚΟ FOOTER ΓΙΑ ΣΥΓΚΕΚΡΙΜΕΝΟ ARTIST / ALBUM ──
    footer_stats = [(f"{total_streams:,}", "TOTAL STREAMS"), (f"{total_hours:,.1f}h", "TIME LISTENED")]
    
    if kind == "specific_album":
        item_overview = run_query("""
            SELECT COUNT(s.id) AS streams, ROUND(COALESCE(SUM(s.ms_played),0)/3600000.0, 1) AS hours, COUNT(DISTINCT s.song_id) AS songs
            FROM streams s JOIN songs so ON so.id = s.song_id
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND so.album_id = :item_id
        """, {"start_date": start_date, "end_date": end_date, "user_id": user_id, "item_id": item_id}).iloc[0]
        footer_stats = [
            (f"{int(item_overview['streams']):,}", "STREAMS"),
            (f"{float(item_overview['hours']):,.1f}h", "HOURS"),
            (f"{int(item_overview['songs']):,}", "SONGS")
        ]
    elif kind == "specific_artist":
        item_overview = run_query("""
            SELECT COUNT(s.id) AS streams, ROUND(COALESCE(SUM(s.ms_played),0)/3600000.0, 1) AS hours, COUNT(DISTINCT s.song_id) AS songs
            FROM streams s JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
            WHERE s.played_at::date BETWEEN :start_date AND :end_date AND s.user_id = :user_id AND sa.artist_id = :item_id
        """, {"start_date": start_date, "end_date": end_date, "user_id": user_id, "item_id": item_id}).iloc[0]
        footer_stats = [
            (f"{int(item_overview['streams']):,}", "STREAMS"),
            (f"{float(item_overview['hours']):,.1f}h", "HOURS"),
            (f"{int(item_overview['songs']):,}", "SONGS")
        ]

    generate = False

    if kind == "overview":
        overview = _fetch_overview_data(run_query, user_id, start_date, end_date)
        if not overview["total_streams"]:
            st.warning("No listening data for this period yet — try a different range.")
            return

        st.info(
            f"**{overview['total_streams']:,}** streams · **{overview['total_hours']:,.1f}h** listened · "
            f"{overview['unique_artists']:,} artists · {overview['unique_tracks']:,} tracks"
        )
        generate = st.button("✨ Generate high-res PNGs", use_container_width=True,
                              type="primary", key="share_generate_btn")
        if generate:
            with st.spinner("Rendering your overview cards (Story + Square)…"):
                theme = _resolve_theme(theme_choice, run_query, user_id, start_date, end_date, overview)
                pngs = _generate_both_formats(
                    build_overview_card, overview=overview, username=username,
                    period_label=period_label, theme=theme, date_range_label=date_range_label,
                    footer_stats=footer_stats, avatar_url=avatar_url,
                )
                st.session_state["_share_png_bytes"] = pngs
                st.session_state["_share_file_stub"] = f"suggestify_overview_{period_key}"

    elif kind == "personality":
        overview = _fetch_overview_data(run_query, user_id, start_date, end_date)
        signals = _fetch_personality_signals(run_query, user_id, start_date, end_date)
        if not overview["total_streams"]:
            st.warning("No listening data for this period yet — try a different range.")
            return

        personality = _compute_personality(signals, overview)
        st.info(f"{personality['emoji']} **{personality['label']}** — {personality['desc']}")

        generate = st.button("✨ Generate high-res PNGs", use_container_width=True,
                              type="primary", key="share_generate_btn")
        if generate:
            with st.spinner("Rendering your personality cards (Story + Square)…"):
                theme = _resolve_theme(theme_choice, run_query, user_id, start_date, end_date, overview)
                pngs = _generate_both_formats(
                    build_personality_card, personality=personality, overview=overview,
                    username=username, period_label=period_label, theme=theme,
                    date_range_label=date_range_label, footer_stats=footer_stats, avatar_url=avatar_url,
                )
                st.session_state["_share_png_bytes"] = pngs
                st.session_state["_share_file_stub"] = f"suggestify_personality_{period_key}"

    else:
        df = _fetch_data(run_query, kind, n, user_id, start_date, end_date, item_id=item_id)
        if df is None or df.empty:
            st.warning("No listening data for this period yet — try a different range.")
            return

        theme = _resolve_theme(theme_choice, run_query, user_id, start_date, end_date)

        components.html(
            _html_preview(df, kind, username, period_label, theme, date_range_label, n, avatar_url=avatar_url, item_name=item_name),
            height=565,
            scrolling=False,
        )

        st.write("")
        generate = st.button("✨ Generate high-res PNGs", use_container_width=True,
                              type="primary", key="share_generate_btn")

        if generate:
            with st.spinner("Rendering your cards (Story + Square)…"):
                pngs = _generate_both_formats(
                    build_share_card, df=df, kind=kind, username=username, period_label=period_label,
                    theme=theme, date_range_label=date_range_label, n=n,
                    footer_stats=footer_stats, avatar_url=avatar_url, item_name=item_name
                )
                st.session_state["_share_png_bytes"] = pngs
                st.session_state["_share_file_stub"] = f"suggestify_{kind}_{period_key}"

    pngs = st.session_state.get("_share_png_bytes")
    if pngs:
        stub = st.session_state.get("_share_file_stub", "suggestify")
        today = datetime.date.today().isoformat()

        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.download_button(
                "⬇️ Download Story (9:16)",
                data=pngs["Story (1080×1920)"],
                file_name=f"{stub}_story_{today}.png",
                mime="image/png", use_container_width=True, type="primary",
                key="share_download_story_btn",
            )
        with dcol2:
            st.download_button(
                "⬇️ Download Square (1:1)",
                data=pngs["Square (1080×1080)"],
                file_name=f"{stub}_square_{today}.png",
                mime="image/png", use_container_width=True, type="primary",
                key="share_download_square_btn",
            )

        zip_data = _zip_bytes({
            f"{stub}_story_{today}.png": pngs["Story (1080×1920)"],
            f"{stub}_square_{today}.png": pngs["Square (1080×1080)"],
        })
        st.download_button(
            "📦 Download Both (.zip)",
            data=zip_data,
            file_name=f"{stub}_{today}.zip",
            mime="application/zip", use_container_width=True,
            key="share_download_zip_btn",
        )
        st.success("Ready! One story-sized and one square-sized card, both 1080px wide.")

    if st.button("Close", use_container_width=True, key="share_close_btn"):
        st.session_state.pop("_share_png_bytes", None)
        st.session_state.pop("_share_file_stub", None)
        st.rerun()

def render_share_stats_button(run_query, user_id, username, min_date, max_date,
                               label="📤 Share Your Stats", accent="#1DB954", accent_dim="#169C46",
                               avatar_url=None):
    if _dialog_decorator is None:
        st.error("Your Streamlit version doesn't support st.dialog — please upgrade streamlit (>=1.31.0).")
        return

    import uuid
    marker_id = f"share_marker_{uuid.uuid4().hex[:8]}"

    # Χρησιμοποιούμε CSS Adjacent Sibling (+ div) για να στοχεύσουμε το κουμπί
    # ΧΩΡΙΣ να το τυλίξουμε σε st.container(), λύνοντας το bug του διπλού rendering!
    st.markdown(f"""
    <div id="{marker_id}" style="display:none;"></div>
    <style>
        #{marker_id} + div[data-testid="stButton"] {{
            display: flex !important; justify-content: flex-end !important;
            width: 100% !important; margin: -0.25rem 0 0.75rem 0 !important;
        }}
        #{marker_id} + div[data-testid="stButton"] button {{
            width: auto !important; background: linear-gradient(135deg, {accent} 0%, {accent_dim} 100%) !important;
            color: #000 !important; font-weight: 800 !important; font-size: 0.85rem !important;
            border: none !important; border-radius: 999px !important; padding: 0.6rem 1.4rem !important;
            box-shadow: 0 8px 24px {accent}55, 0 2px 10px rgba(0,0,0,0.45) !important;
            transition: all 0.25s cubic-bezier(0.16,1,0.3,1) !important; letter-spacing: 0.01em !important;
        }}
        #{marker_id} + div[data-testid="stButton"] button:hover {{
            transform: translateY(-2px) scale(1.03) !important;
            box-shadow: 0 12px 34px {accent}77, 0 4px 14px rgba(0,0,0,0.55) !important;
        }}
        @media (max-width: 768px) {{
            #{marker_id} + div[data-testid="stButton"] button {{
                padding: 0.5rem 1rem !important; font-size: 0.72rem !important;
            }}
        }}
    </style>
    """, unsafe_allow_html=True)

    if st.button(label, key="share_stats_trigger"):
        st.session_state.pop("_share_png_bytes", None)
        st.session_state.pop("_share_file_stub", None)
        _open_dialog(run_query, user_id, username, min_date, max_date, avatar_url)
        
@_dialog_decorator("🎉 Share Your Stats") if _dialog_decorator else (lambda f: f)
def _open_dialog(run_query, user_id, username, min_date, max_date, avatar_url=None):
    _run_share_dialog(run_query, user_id, username, min_date, max_date, avatar_url=avatar_url)