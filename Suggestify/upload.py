import streamlit as st
import subprocess
import time
import os
import tempfile
import threading
import sys

try:
    os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except KeyError:
    os.environ["DATABASE_URL"] = "postgresql://postgres.pxpplxyszvrzubdqykmw:dKPJjO2jZtkmwjYh@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
# ══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Suggestify — Import Your Data",
    page_icon="🎧",
    layout="centered",
    initial_sidebar_state="collapsed",
)

current_dir = os.path.dirname(os.path.abspath(__file__))
JAVA_JAR_PATH = os.path.join(current_dir, "SuggestifyProject.jar")

# ══════════════════════════════════════════════════════════════════
# LOAD EXTERNAL CSS & LOCAL OVERRIDES
# ══════════════════════════════════════════════════════════════════
def load_css():
    try:
        with open("styles.css", "r", encoding="utf-8") as f:
            css = f.read()
        
        css = css.replace("VAR_BG", "#050505").replace("VAR_CARD", "rgba(28, 28, 28, 0.75)")
        css = css.replace("VAR_BORDER", "rgba(255, 255, 255, 0.08)").replace("VAR_BORDER_HL", "rgba(255, 255, 255, 0.18)")
        css = css.replace("VAR_GREEN", "#1DB954").replace("VAR_GREEN_DIM", "#169C46")
        css = css.replace("VAR_GREEN_GLOW", "rgba(29, 185, 84, 0.35)").replace("VAR_GREEN_XLO", "rgba(29, 185, 84, 0.08)")
        css = css.replace("VAR_TEXT", "#FFFFFF").replace("VAR_TEXT_MID", "#B3B3B3").replace("VAR_TEXT_DIM", "#727272")

        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css()

# CSS Ειδικά για το Uploader και το Πράσινο Κουμπί
st.markdown("""
<style>
/* Διώχνουμε το κενό στην κορυφή */
.block-container {
    max-width: 660px !important;
    padding-top: 1rem !important; 
}
header { display: none !important; }

/* ==================================================================
   FILE UPLOADER - MAGIC CSS (ΧΩΡΙΣ JAVASCRIPT)
   ================================================================== */
/* Διώχνουμε την ετικέτα */
div[data-testid="stFileUploader"] > label { display: none !important; }

/* Βασικό στυλ του Dropzone */
div[data-testid="stFileUploader"] section {
    position: relative !important;
    background: rgba(22, 22, 22, 0.9) !important;
    border: 1.5px dashed rgba(255,255,255,0.14) !important;
    border-radius: 22px !important;
    min-height: 230px !important; /* Μεγαλώσαμε το ύψος! */
    padding: 0 !important;
    margin-bottom: 0 !important;
    transition: all 0.3s ease !important;
}

div[data-testid="stFileUploader"] section:hover {
    border-color: #1DB954 !important;
    background: rgba(29,185,84,0.04) !important;
}

/* Κρύβουμε ΤΕΛΕΙΩΣ τα προεπιλεγμένα κείμενα του Streamlit για να μην χαλάνε τη στοίχιση */
div[data-testid="stFileUploader"] section [data-testid="stMarkdownContainer"],
div[data-testid="stFileUploader"] section button,
div[data-testid="stFileUploader"] section small,
div[data-testid="stFileUploader"] section svg,
div[data-testid="stFileUploaderDropzoneInstructions"],
span[data-testid="stFileUploaderDropzoneInstructions"],
div[data-testid="stFileUploader"] section > div > span { 
    opacity: 0 !important; 
    display: none !important;
}

/* 1. ΣΤΑΔΙΟ ΑΝΑΜΟΝΗΣ: Το εικονίδιο 📦 */
div[data-testid="stFileUploader"] section::before {
    content: "📦"; 
    position: absolute; top: 35%; left: 50%;
    transform: translate(-50%, -50%); 
    pointer-events: none;
    width: 64px; height: 64px; display: flex; align-items: center; justify-content: center;
    background: rgba(29,185,84,0.1); border: 1px solid rgba(29,185,84,0.2);
    border-radius: 18px; font-size: 1.8rem;
}

/* 2. ΣΤΑΔΙΟ UPLOADING (Ανιχνεύει αυτόματα τη μπάρα προόδου) */
div[data-testid="stFileUploader"]:has([data-testid="stProgressBar"]) section {
    border-color: #1DB954 !important;
    background: rgba(29,185,84,0.08) !important;
}

div[data-testid="stFileUploader"]:has([data-testid="stProgressBar"]) section::before {
    content: "⏳" !important;
    animation: breathe 1s ease-in-out infinite !important;
}

div[data-testid="stFileUploader"]:has([data-testid="stProgressBar"]) section::after {
    content: "Uploading ZIP... παρακαλώ περιμένετε";
    position: absolute; top: 75%; left: 50%;
    transform: translate(-50%, 0);
    color: #1DB954; font-weight: 700; font-size: 0.95rem;
    pointer-events: none;
}

/* 3. ΜΟΛΙΣ ΑΝΕΒΕΙ: Κρύβουμε το χαλασμένο native box, ΚΡΑΤΑΜΕ ΜΟΝΟ ΤΗ ΜΠΑΡΑ ΠΡΟΟΔΟΥ */
div[data-testid="stUploadedFile"] > div:first-child {
    display: none !important; /* Αυτό κρύβει το εικονίδιο και το όνομα αρχείου που κάνανε overlap! */
}
div[data-testid="stFileUploader"] [data-testid="stProgressBar"] {
    opacity: 1 !important;
    display: block !important;
    position: absolute;
    bottom: 25px;
    left: 10%;
    width: 80%;
}
div[data-testid="stFileUploader"] [data-testid="stProgressBar"] > div > div {
    background-color: #1DB954 !important;
}

/* ─── ΠΡΑΣΙΝΟ ΚΟΥΜΠΙ (Εφαρμόζεται στο primary type) ─── */
div[data-testid="stButton"] button[kind="primary"] {
    background: #1DB954 !important; 
    color: #000 !important; 
    font-weight: 800 !important;
    font-size: 0.97rem !important;
    border: none !important; 
    border-radius: 12px !important; 
    padding: 0.75rem 2rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 24px rgba(29,185,84,0.25) !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
    background: #1ed760 !important; 
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 32px rgba(29,185,84,0.4) !important;
}

/* ─── Hero headphone emoji "breathing" animation ─── */
@keyframes breathe {
    0%, 100% { transform: scale(1); }
    50%      { transform: scale(1.18); }
}

/* ─── Step cards: interactive hover ─── */
.step-card {
    transition: transform 0.25s ease, border-color 0.25s ease, background 0.25s ease, box-shadow 0.25s ease;
    cursor: default;
}
.step-card:hover {
    transform: translateY(-6px) scale(1.035);
    border-color: rgba(29,185,84,0.45) !important;
    background: rgba(29,185,84,0.06) !important;
    box-shadow: 0 10px 28px rgba(29,185,84,0.18);
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# STATE & HELPERS
# ══════════════════════════════════════════════════════════════════
for key, default in [
    ("upload_state", "idle"), ("progress_pct", 0), ("log_lines", []),
    ("saved_zip_path", None), ("username_to_import", ""), ("error_msg", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

LOG_STEPS = [
    (2,  "📂  Opening ZIP archive…"), (7,  "🎵  Parsing Streaming_History_Audio files…"),
    (15, "🔍  Extracting artists, albums & songs…"), (24, "🗄️  Initialising database schema…"),
    (35, "⬆️  Importing stream records…"), (48, "🔗  Building relationships & indexes…"),
    (58, "📊  Running post-import aggregations…"), (65, "✅  Finalising — almost there…"),
]

def save_uploaded_file(uploaded_file) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name

def run_java_parser(zip_path: str, username: str):
    return subprocess.run(
        ["java", "-jar", JAVA_JAR_PATH, zip_path, username],
        capture_output=False, text=True, timeout=1200
    )

# ══════════════════════════════════════════════════════════════════
# IDLE — landing page
# ══════════════════════════════════════════════════════════════════
if st.session_state.upload_state == "idle":

    st.markdown("""
    <div style="text-align: center; margin-top: -1rem; margin-bottom: 2rem;">
        <div style="font-size: 3.2rem; margin-bottom: 0.5rem; animation: breathe 3s ease-in-out infinite;">🎧</div>
        <div style="font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.18em; color: #1DB954; margin-bottom: 0.5rem;">Suggestify · Your private music stats</div>
        <div style="font-size: 3rem; font-weight: 900; letter-spacing: -0.045em; line-height: 1.0; margin-bottom: 1rem; color: #FFFFFF;">Your music,<br><em style="font-style: normal; color: #1DB954;">fully yours.</em></div>
        <p style="font-size: 1rem; color: #B3B3B3; line-height: 1.6; max-width: 440px; margin: 0 auto;">Drop your Spotify data export and get a beautiful, private breakdown of everything you've ever listened to.</p>
    </div>
    """, unsafe_allow_html=True)

    username_input = st.text_input("👤 Enter Username:")
    
    uploaded = st.file_uploader("Upload ZIP", type=["zip"], label_visibility="collapsed")
    
    # ΕΔΩ: Ενσωματώσαμε το "200MB per file" για τέλεια στοίχιση!
    st.markdown("""
    <div style="position:relative; margin-top:-115px; pointer-events:none; text-align:center;">
        <div style="font-weight:700; font-size:1.1rem; color:#fff; margin-bottom:0.4rem;">Drag & drop your Spotify export ZIP</div>
        <div style="font-size:0.75rem; color:#727272; margin-bottom:0.4rem;">200MB per file • ZIP</div>
        <div style="font-size:0.75rem; color:#1DB954;">my_spotify_data.zip · stays on your machine, never uploaded anywhere</div>
    </div>
    """, unsafe_allow_html=True)

    if uploaded:
        size_mb = uploaded.size / 1_000_000
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 0.75rem; background: rgba(29,185,84,0.07); border: 1px solid rgba(29,185,84,0.22); border-radius: 12px; padding: 0.7rem 1rem; margin-top: 1rem; margin-bottom: 1rem; animation: revealUp 0.4s ease-out;">
            <span style="font-size:1.3rem;">✅</span>
            <div>
                <div style="font-weight: 700; color: #FFFFFF; font-size: 0.9rem;">{uploaded.name}</div>
                <div style="font-size: 0.78rem; color: #727272;">{size_mb:.1f} MB  ·  Ready to import</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ─── ΑΠΟΛΥΤΟ ΚΕΝΤΡΑΡΙΣΜΑ ΚΟΥΜΠΙΟΥ ───
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            submitted = st.button("🚀  Import my Spotify data", type="primary", use_container_width=True)
        
        if submitted:
            if not username_input.strip():
                st.warning("⚠️ Please enter a Username (Step 1)!")
                st.components.v1.html("<script>parent.document.querySelector('input[data-testid=\"stTextInput\"]').focus();</script>", height=0)
            else:
                st.session_state.saved_zip_path = save_uploaded_file(uploaded)
                st.session_state.username_to_import = username_input.strip()
                st.session_state.upload_state = "processing"
                st.session_state.progress_pct = 0
                st.session_state.log_lines = []
                st.rerun()

    st.markdown("""
    <div style="display: flex; gap: 0.75rem; margin-top: 1.5rem;">
        <div class="step-card" style="flex: 1; background: rgba(255,255,255,0.025); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 1rem 0.85rem; text-align: center;">
            <div style="font-size: 0.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.14em; color: #1DB954; margin-bottom: 0.45rem;">Step 1</div>
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Download your data from<br><strong style="color: #FFFFFF; font-weight: 600;">spotify.com/account</strong></div>
        </div>
        <div class="step-card" style="flex: 1; background: rgba(255,255,255,0.025); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 1rem 0.85rem; text-align: center;">
            <div style="font-size: 0.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.14em; color: #1DB954; margin-bottom: 0.45rem;">Step 2</div>
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Drop the ZIP here<br>& hit <strong style="color: #FFFFFF; font-weight: 600;">Import</strong></div>
        </div>
        <div class="step-card" style="flex: 1; background: rgba(255,255,255,0.025); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 1rem 0.85rem; text-align: center;">
            <div style="font-size: 0.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.14em; color: #1DB954; margin-bottom: 0.45rem;">Step 3</div>
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Wait ~60 s while we<br>crunch the numbers</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# PROCESSING
# ══════════════════════════════════════════════════════════════════
elif st.session_state.upload_state == "processing":
    card_ph = st.empty()
    log_ph  = st.empty()

    def render_proc(pct, lines):
        card_ph.markdown(f"""
        <div style="background: rgba(22,22,22,0.95); border: 1px solid #1DB954; border-radius: 22px; padding: 2.5rem 2rem; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; margin-bottom: 0.35rem;">Parsing listening history for {st.session_state.username_to_import}…</div>
            <div style="font-size: 0.85rem; color: #B3B3B3; margin-bottom: 1.6rem;">This takes about a minute. Grab a coffee ☕</div>
            <div style="background: rgba(255,255,255,0.07); border-radius: 999px; height: 5px; overflow: hidden; margin-bottom: 0.5rem;">
                <div style="height: 100%; border-radius: 999px; background: #1DB954; width:{pct}%; transition: width 0.5s ease;"></div>
            </div>
            <div style="font-size: 0.72rem; color: #727272; text-align: right;">{pct}%</div>
        </div>
        """, unsafe_allow_html=True)
        if lines:
            log_ph.markdown(
                f'<div style="background: rgba(0,0,0,0.45); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 0.7rem 1rem; text-align: left; font-family: monospace; font-size: 0.72rem; color: #1DB954; max-height: 110px; overflow-y: auto; line-height: 1.75;">{"<br>".join(lines[-6:])}</div>',
                unsafe_allow_html=True
            )

    # Χρησιμοποιούμε απλό dictionary (όχι session_state) για να μην κρασάρει το thread του Streamlit
    result_holder = {"result": None, "done": False}

    if "import_running" not in st.session_state:
        st.session_state.import_running = True
        
        zip_path_to_process = st.session_state.saved_zip_path
        user_to_process = st.session_state.username_to_import

        def java_thread(target_path, target_user):
            try:
                res = run_java_parser(target_path, target_user)
                result_holder["result"] = res
            except Exception as e:
                result_holder["result"] = type("R", (), {"returncode": 1, "stderr": str(e), "stdout": ""})()
            result_holder["done"] = True

        threading.Thread(target=java_thread, args=(zip_path_to_process, user_to_process), daemon=True).start()

    elapsed, interval = 0.0, 0.5
    while not result_holder["done"]:
        elapsed += interval
        for secs, msg in LOG_STEPS:
            if elapsed >= secs and msg not in st.session_state.log_lines:
                st.session_state.log_lines.append(msg)
        st.session_state.progress_pct = min(97, int(elapsed / 70 * 100))
        render_proc(st.session_state.progress_pct, st.session_state.log_lines)
        time.sleep(interval)

    result = result_holder["result"]

    if result.returncode == 0:
        current_pct = st.session_state.progress_pct
        while current_pct < 80:
            current_pct += 2
            render_proc(min(current_pct, 80), st.session_state.log_lines)
            time.sleep(0.02)
            
        st.session_state.log_lines.append("🎉  Database import complete!")
        render_proc(80, st.session_state.log_lines)
        
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW

        try:
            # 1. Spotify Cover Art (Images)
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.ImageUpdater"], creationflags=flags)
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.ArtistImageUpdater"], creationflags=flags)
            
            # 2. Last.fm Album Genres
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.GenreEnricher"], creationflags=flags)
            
            # 3. iTunes Track Metadata & Feature Hunter
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.TrackMetadataEnricher"], creationflags=flags)
            
        except Exception as e:
            print(f"Background tasks failed: {e}")
            
        st.session_state.log_lines.append("✨ Fetching artwork, genres & metadata in the background...")
        for i in range(1, 101):
            pct = 80 + int(20 * (i / 100))
            render_proc(pct, st.session_state.log_lines)
            time.sleep(0.1)

        try:
            os.unlink(st.session_state.saved_zip_path)
        except Exception:
            pass
        
        if "import_running" in st.session_state:
            del st.session_state["import_running"]
            
        st.cache_data.clear()
            
        st.session_state.upload_state = "done"
        st.rerun()
    else:
        if "import_running" in st.session_state:
            del st.session_state["import_running"]
            
        st.session_state.upload_state = "error"
        st.session_state.error_msg = result.stderr or "Unknown error."
        st.rerun()
# ══════════════════════════════════════════════════════════════════
# DONE & ERROR
# ══════════════════════════════════════════════════════════════════
elif st.session_state.upload_state == "done":
    username = st.session_state.get("username_to_import", "")

    st.markdown(f"""
    <div style="text-align: center; padding: 3.5rem 2rem; background: rgba(22,22,22,0.95);
                border: 1px solid #1DB954; border-radius: 24px; margin: 2rem 0;
                position: relative; overflow: hidden;">
        <div style="position: absolute; top: -80px; left: 50%; transform: translateX(-50%);
                    width: 400px; height: 400px;
                    background: radial-gradient(ellipse, rgba(29,185,84,0.12) 0%, transparent 70%);
                    pointer-events: none;"></div>
        <div style="font-size: 3.5rem; margin-bottom: 1rem; animation: breathe 3s ease-in-out infinite;">🎉</div>
        <div style="font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
                    letter-spacing: 0.18em; color: #1DB954; margin-bottom: 0.5rem;">Import Complete</div>
        <div style="font-size: 2.2rem; font-weight: 900; color: #FFFFFF;
                    letter-spacing: -0.04em; margin-bottom: 0.75rem;">
            {"Welcome, " + username + "! 🎧" if username else "Your data is ready! 🎧"}
        </div>
        <p style="color: #B3B3B3; font-size: 0.95rem; line-height: 1.6;
                  max-width: 380px; margin: 0 auto 0.5rem;">
            Your Spotify history has been imported and is ready to explore.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        if st.button("🎧  Open Dashboard →", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.switch_page("pages/app.py")   # ← adjust to your actual page filename
        
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        
        if st.button("↩  Import another file", use_container_width=True):
            st.session_state.upload_state = "idle"
            st.rerun()

elif st.session_state.upload_state == "error":
    st.error(f"Import failed: {st.session_state.get('error_msg', '')[:600]}")
    if st.button("↩  Try again"):
        st.session_state.upload_state = "idle"
        st.rerun()