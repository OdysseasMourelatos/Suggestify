import streamlit as st
import subprocess
import time
import os
import tempfile
import threading
import sys
import urllib.parse
import requests
import base64

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

# CSS Ειδικά για το Uploader, τα Tabs και το Πράσινο Κουμπί
st.markdown("""
<style>
/* Διώχνουμε το κενό στην κορυφή */
.block-container {
    max-width: 660px !important;
    padding-top: 1rem !important; 
}
header { display: none !important; }

/* --- CUSTOM TABS STYLING --- */
.stTabs [data-baseweb="tab-list"] {
    gap: 1rem;
    background-color: transparent;
    justify-content: center;
}
.stTabs [data-baseweb="tab"] {
    height: 3.2rem;
    white-space: break-spaces;
    background-color: rgba(255,255,255,0.04);
    border-radius: 12px;
    color: #B3B3B3;
    gap: 0.5rem;
    padding: 0 1.5rem;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.08);
}
.stTabs [aria-selected="true"] {
    background-color: rgba(29, 185, 84, 0.1) !important;
    color: #1DB954 !important;
    border-color: #1DB954 !important;
}
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* ==================================================================
   FILE UPLOADER - MAGIC CSS
   ================================================================== */
div[data-testid="stFileUploader"] > label { display: none !important; }

div[data-testid="stFileUploader"] section {
    position: relative !important;
    background: rgba(22, 22, 22, 0.9) !important;
    border: 1.5px dashed rgba(255,255,255,0.14) !important;
    border-radius: 22px !important;
    min-height: 230px !important;
    padding: 0 !important;
    margin-bottom: 0 !important;
    transition: all 0.3s ease !important;
}

div[data-testid="stFileUploader"] section:hover {
    border-color: #1DB954 !important;
    background: rgba(29,185,84,0.04) !important;
}

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

div[data-testid="stFileUploader"] section::before {
    content: "📦"; 
    position: absolute; top: 35%; left: 50%;
    transform: translate(-50%, -50%); 
    pointer-events: none;
    width: 64px; height: 64px; display: flex; align-items: center; justify-content: center;
    background: rgba(29,185,84,0.1); border: 1px solid rgba(29,185,84,0.2);
    border-radius: 18px; font-size: 1.8rem;
}

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

div[data-testid="stUploadedFile"] > div:first-child {
    display: none !important; 
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

/* ─── ΠΡΑΣΙΝΟ ΚΟΥΜΠΙ ─── */
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

@keyframes breathe {
    0%, 100% { transform: scale(1); }
    50%      { transform: scale(1.18); }
}

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
    java_env = os.environ.copy()
    if "DATABASE_URL" in st.secrets:
        java_env["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    if "SPOTIFY_CLIENT_ID" in st.secrets:
        java_env["SPOTIFY_CLIENT_ID"] = st.secrets["SPOTIFY_CLIENT_ID"]
    if "SPOTIFY_CLIENT_SECRET" in st.secrets:
        java_env["SPOTIFY_CLIENT_SECRET"] = st.secrets["SPOTIFY_CLIENT_SECRET"]

    return subprocess.run(
        ["java", "-jar", JAVA_JAR_PATH, zip_path, username],
        capture_output=False, text=True, timeout=1200, env=java_env
    )

# ══════════════════════════════════════════════════════════════════
# IDLE — landing page
# ══════════════════════════════════════════════════════════════════
if st.session_state.upload_state == "idle":
    auth_code = st.query_params.get("code")
    
    if auth_code:
        # Μόλις γυρίσαμε από το Spotify! Ανταλλάσσουμε το code με Token
        client_id = st.secrets.get("SPOTIFY_CLIENT_ID", "")
        client_secret = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
        redirect_uri = st.secrets.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501")
        
        token_url = "https://accounts.spotify.com/api/token"
        auth_str = f"{client_id}:{client_secret}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri
        }
        
        with st.spinner("🎵 Authenticating with Spotify..."):
            response = requests.post(token_url, headers=headers, data=data)
            
            if response.status_code == 200:
                token_info = response.json()
                access_token = token_info["access_token"]
                refresh_token = token_info.get("refresh_token")
                
                # Χτυπάμε το /me endpoint για να δούμε ποιος μπήκε!
                me_response = requests.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"})
                
                if me_response.status_code == 200:
                    user_data = me_response.json()
                    spotify_username = user_data.get("display_name") or user_data.get("id")
                    
                    # Αποθηκεύουμε τα στοιχεία στο Session State!
                    st.session_state["spotify_access_token"] = access_token
                    st.session_state["spotify_refresh_token"] = refresh_token
                    st.session_state["username_to_import"] = spotify_username
                    st.session_state["is_spotify_logged_in"] = True
                    
                    # Καθαρίζουμε το URL για να μην ξανατρέξει ο κώδικας
                    st.query_params.clear()
                    
                    # Πανηγυρικό UI και μετάβαση στο Dashboard!
                    st.success(f"🎉 Welcome back, {spotify_username}! Let's explore your music.")
                    time.sleep(1.5)
                    st.switch_page("pages/app.py")
                else:
                    st.error("⚠️ Failed to fetch user profile from Spotify.")
            else:
                st.error("⚠️ Failed to exchange authorization code.")
                st.write(response.json())
                
        st.stop()
        
    st.markdown("""
    <div style="text-align: center; margin-top: -1rem; margin-bottom: 2rem;">
        <div style="font-size: 3.2rem; margin-bottom: 0.5rem; animation: breathe 3s ease-in-out infinite;">🎧</div>
        <div style="font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.18em; color: #1DB954; margin-bottom: 0.5rem;">Suggestify · Your private music stats</div>
        <div style="font-size: 3rem; font-weight: 900; letter-spacing: -0.045em; line-height: 1.0; margin-bottom: 1rem; color: #FFFFFF;">Your music,<br><em style="font-style: normal; color: #1DB954;">fully yours.</em></div>
        <p style="font-size: 1rem; color: #B3B3B3; line-height: 1.6; max-width: 440px; margin: 0 auto;">Connect your account for live stats, or drop your Spotify export for a full historical breakdown.</p>
    </div>
    """, unsafe_allow_html=True)

    tab_live, tab_zip = st.tabs(["🟢 Connect Spotify (Live Sync)", "📦 Upload Full History (ZIP)"])

    import urllib.parse

    with tab_live:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center;">
            <h3 style="color: #fff; font-size: 1.3rem; margin-bottom: 0.5rem;">Instant Access</h3>
            <p style="color: #727272; font-size: 0.9rem; margin-bottom: 2rem;">Log in securely via Spotify to instantly pull your top tracks, artists, and live currently-playing status.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            # --- ΔΗΜΙΟΥΡΓΙΑ ΤΟΥ SPOTIFY OAUTH URL ---
            client_id = st.secrets.get("SPOTIFY_CLIENT_ID", "")
            redirect_uri = st.secrets.get("SPOTIFY_REDIRECT_URI", "")
            
            # Εδώ ζητάμε άδεια για να διαβάζουμε το ιστορικό, τα top tracks και το τι ακούει τώρα!
            scope = "user-read-recently-played user-top-read user-read-currently-playing user-read-private"
            
            auth_params = {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": scope,
                "show_dialog": "true" # Αναγκάζει το Spotify να δείξει την οθόνη έγκρισης
            }
            
            spotify_auth_url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(auth_params)}"
            
            st.markdown(f"""
            <a href="{spotify_auth_url}" target="_top" style="display: block; text-align: center; background: #1DB954; color: #000; font-weight: 800; font-size: 1rem; text-decoration: none; border-radius: 999px; padding: 0.8rem 2rem; transition: all 0.2s ease; box-shadow: 0 4px 24px rgba(29,185,84,0.25);">
                Connect with Spotify
            </a>
            """, unsafe_allow_html=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

    with tab_zip:
        st.markdown("<br>", unsafe_allow_html=True)
        username_input = st.text_input("👤 Enter Username:")
        
        uploaded = st.file_uploader("Upload ZIP", type=["zip"], label_visibility="collapsed")
        
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

            col1, col2, col3 = st.columns([1, 1.2, 1])
            with col2:
                submitted = st.button("🚀  Import my Spotify data", type="primary", use_container_width=True)
            
            if submitted:
                if not username_input.strip():
                    st.warning("⚠️ Please enter a Username!")
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
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Connect or upload<br><strong style="color: #FFFFFF; font-weight: 600;">your history</strong></div>
        </div>
        <div class="step-card" style="flex: 1; background: rgba(255,255,255,0.025); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 1rem 0.85rem; text-align: center;">
            <div style="font-size: 0.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.14em; color: #1DB954; margin-bottom: 0.45rem;">Step 2</div>
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Wait ~60 s while we<br><strong style="color: #FFFFFF; font-weight: 600;">crunch the numbers</strong></div>
        </div>
        <div class="step-card" style="flex: 1; background: rgba(255,255,255,0.025); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 1rem 0.85rem; text-align: center;">
            <div style="font-size: 0.6rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.14em; color: #1DB954; margin-bottom: 0.45rem;">Step 3</div>
            <div style="font-size: 0.79rem; color: #B3B3B3; line-height: 1.45;">Explore your private<br><strong style="color: #FFFFFF; font-weight: 600;">music dashboard</strong></div>
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

        java_env = os.environ.copy()
        if "DATABASE_URL" in st.secrets:
            java_env["DATABASE_URL"] = st.secrets["DATABASE_URL"]
        if "SPOTIFY_CLIENT_ID" in st.secrets:
            java_env["SPOTIFY_CLIENT_ID"] = st.secrets["SPOTIFY_CLIENT_ID"]
        if "SPOTIFY_CLIENT_SECRET" in st.secrets:
            java_env["SPOTIFY_CLIENT_SECRET"] = st.secrets["SPOTIFY_CLIENT_SECRET"]

        try:
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.ImageUpdater", user_to_process], creationflags=flags, env=java_env)
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.ArtistImageUpdater", user_to_process], creationflags=flags, env=java_env)
            
            # 2. Last.fm Album Genres (Πλέον θα το αλλάξουμε σε Spotify!)
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.GenreEnricher", user_to_process], creationflags=flags, env=java_env)
            
            # 3. Spotify Track Metadata & Audio Features Hunter
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.TrackMetadataEnricher", user_to_process], creationflags=flags, env=java_env)
            
            # 4. Album Metadata
            subprocess.Popen(["java", "-cp", JAVA_JAR_PATH, "com.Suggestify.AlbumMetadataEnricher", user_to_process], creationflags=flags, env=java_env)
            
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