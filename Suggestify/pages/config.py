# config.py

BG        = "#050505"
SURFACE   = "rgba(18, 18, 18, 0.85)"
CARD      = "rgba(28, 28, 28, 0.75)"
CARD_HOVER= "rgba(45, 45, 45, 0.85)"
BORDER    = "rgba(255, 255, 255, 0.08)"
BORDER_HL = "rgba(255, 255, 255, 0.15)"
GREEN     = "#1DB954"
GREEN_DIM = "#169C46"
GREEN_GLOW= "rgba(29, 185, 84, 0.35)"
GREEN_XLO = "rgba(29, 185, 84, 0.08)"
TEXT      = "#FFFFFF"
TEXT_MID  = "#B3B3B3"
TEXT_DIM  = "#727272"

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}

MONTH_FILTER_OPTIONS = ["All Months"] + list(MONTH_NAMES.values())
HOUR_FILTER_OPTIONS = ["All Hours"] + [f"{h:02d}:00" for h in range(24)]

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