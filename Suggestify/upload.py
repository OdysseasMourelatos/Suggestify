import streamlit as st
import subprocess
import time
import os
import tempfile

# ══════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Suggestify — Import Your Data",
    page_icon="🎧",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════
# DESIGN TOKENS  (mirrors app.py)
# ══════════════════════════════════════════════════════════════════
BG        = "#050505"
CARD      = "rgba(28, 28, 28, 0.75)"
BORDER    = "rgba(255, 255, 255, 0.08)"
BORDER_HL = "rgba(255, 255, 255, 0.18)"
GREEN     = "#1DB954"
GREEN_DIM = "#169C46"
GREEN_GLOW= "rgba(29, 185, 84, 0.35)"
GREEN_XLO = "rgba(29, 185, 84, 0.08)"
TEXT      = "#FFFFFF"
TEXT_MID  = "#B3B3B3"
TEXT_DIM  = "#727272"

# ══════════════════════════════════════════════════════════════════
# PATH TO YOUR JAVA JAR  ← edit this once
# ══════════════════════════════════════════════════════════════════
JAVA_JAR_PATH = r"C:\Users\spmou\Documents\ODY\Suggestify\Suggestify.jar"
# If you run from Maven/IntelliJ instead, swap the line above for:
# JAVA_CMD = ["mvn", "-f", r"C:\path\to\pom.xml", "exec:java", "-Dexec.mainClass=com.Suggestify.SpotifyParser"]

# ══════════════════════════════════════════════════════════════════
# STYLES
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: {BG} !important;
    color: {TEXT} !important;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{
    padding: 4rem 2rem 4rem !important;
    max-width: 680px !important;
}}

/* ── Animations ── */
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(24px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes pulseGlow {{
    0%, 100% {{ box-shadow: 0 0 30px {GREEN_GLOW}; }}
    50%       {{ box-shadow: 0 0 60px {GREEN_GLOW}, 0 0 100px rgba(29,185,84,0.12); }}
}}
@keyframes spin {{
    to {{ transform: rotate(360deg); }}
}}
@keyframes progressFill {{
    from {{ width: 0%; }}
    to   {{ width: 100%; }}
}}
@keyframes blink {{
    0%, 100% {{ opacity: 1; }}
    50%       {{ opacity: 0.3; }}
}}
@keyframes waveBar {{
    0%, 100% {{ transform: scaleY(0.4); }}
    50%       {{ transform: scaleY(1.0); }}
}}

/* ── Hero ── */
.hero {{
    text-align: center;
    margin-bottom: 2.5rem;
    animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}}
.hero-icon {{
    font-size: 3.5rem;
    margin-bottom: 1rem;
    display: block;
    filter: drop-shadow(0 0 20px {GREEN_GLOW});
}}
.hero-title {{
    font-size: 2.4rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    line-height: 1.1;
    margin-bottom: 0.6rem;
    background: linear-gradient(135deg, {TEXT} 0%, {TEXT_MID} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.hero-title span {{
    background: linear-gradient(135deg, {GREEN} 0%, #1ed760 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.hero-subtitle {{
    font-size: 1rem;
    color: {TEXT_MID};
    line-height: 1.6;
    max-width: 440px;
    margin: 0 auto;
}}

/* ── Drop Zone ── */
.drop-card {{
    background: {CARD};
    border: 2px dashed {BORDER_HL};
    border-radius: 20px;
    padding: 2.5rem 2rem;
    text-align: center;
    transition: border-color 0.25s ease, background 0.25s ease;
    animation: fadeUp 0.6s 0.1s cubic-bezier(0.16, 1, 0.3, 1) both;
    position: relative;
    overflow: hidden;
}}
.drop-card::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 0%, {GREEN_XLO} 0%, transparent 70%);
    pointer-events: none;
}}
.drop-icon {{
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
    opacity: 0.7;
}}
.drop-label {{
    font-size: 1.05rem;
    font-weight: 600;
    color: {TEXT};
    margin-bottom: 0.3rem;
}}
.drop-hint {{
    font-size: 0.82rem;
    color: {TEXT_DIM};
}}

/* ── Steps ── */
.steps {{
    display: flex;
    gap: 1rem;
    margin-top: 2rem;
    animation: fadeUp 0.6s 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
}}
.step {{
    flex: 1;
    background: rgba(255,255,255,0.03);
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 1rem;
    text-align: center;
}}
.step-num {{
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: {GREEN};
    margin-bottom: 0.3rem;
}}
.step-text {{
    font-size: 0.82rem;
    color: {TEXT_MID};
    line-height: 1.4;
}}

/* ── Processing state ── */
.processing-card {{
    background: {CARD};
    border: 1px solid {GREEN};
    border-radius: 20px;
    padding: 2.5rem 2rem;
    text-align: center;
    animation: pulseGlow 2.5s infinite, fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}}
.wave-bars {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    height: 40px;
    margin-bottom: 1.5rem;
}}
.wave-bar {{
    width: 5px;
    border-radius: 3px;
    background: {GREEN};
    animation: waveBar 0.9s ease-in-out infinite;
}}
.wave-bar:nth-child(2) {{ animation-delay: 0.1s; height: 28px; }}
.wave-bar:nth-child(3) {{ animation-delay: 0.2s; height: 36px; }}
.wave-bar:nth-child(4) {{ animation-delay: 0.3s; height: 22px; }}
.wave-bar:nth-child(5) {{ animation-delay: 0.4s; height: 32px; }}
.wave-bar:nth-child(1) {{ height: 20px; }}
.wave-bar:nth-child(6) {{ animation-delay: 0.5s; height: 18px; }}
.wave-bar:nth-child(7) {{ animation-delay: 0.15s; height: 30px; }}

.proc-title {{
    font-size: 1.3rem;
    font-weight: 800;
    color: {TEXT};
    margin-bottom: 0.4rem;
    letter-spacing: -0.02em;
}}
.proc-subtitle {{
    font-size: 0.88rem;
    color: {TEXT_MID};
    margin-bottom: 1.5rem;
}}

/* Progress bar */
.progress-track {{
    background: rgba(255,255,255,0.07);
    border-radius: 999px;
    height: 6px;
    overflow: hidden;
    margin-bottom: 0.6rem;
}}
.progress-fill {{
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, {GREEN_DIM}, {GREEN}, #1ed760);
    transition: width 0.4s ease;
}}
.progress-label {{
    font-size: 0.75rem;
    color: {TEXT_DIM};
    display: flex;
    justify-content: space-between;
}}

/* Log lines */
.log-box {{
    background: rgba(0,0,0,0.4);
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin-top: 1.25rem;
    text-align: left;
    font-family: 'Courier New', monospace;
    font-size: 0.75rem;
    color: {GREEN};
    max-height: 120px;
    overflow-y: auto;
    line-height: 1.7;
}}

/* ── Done state ── */
.done-card {{
    background: {CARD};
    border: 1px solid {GREEN};
    border-radius: 20px;
    padding: 2.5rem 2rem;
    text-align: center;
    animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}}
.done-icon {{
    font-size: 3rem;
    margin-bottom: 0.75rem;
}}
.done-title {{
    font-size: 1.5rem;
    font-weight: 800;
    color: {TEXT};
    margin-bottom: 0.4rem;
    letter-spacing: -0.02em;
}}
.done-sub {{
    font-size: 0.9rem;
    color: {TEXT_MID};
    margin-bottom: 1.5rem;
}}

/* ── Streamlit overrides ── */
div[data-testid="stFileUploader"] {{
    margin-top: 0.5rem;
}}
div[data-testid="stFileUploader"] > label {{ display: none !important; }}
div[data-testid="stFileUploader"] section {{
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}}
div[data-testid="stFileUploader"] section > div {{
    background: rgba(29, 185, 84, 0.06) !important;
    border: 2px dashed {BORDER_HL} !important;
    border-radius: 14px !important;
    transition: all 0.25s ease !important;
}}
div[data-testid="stFileUploader"] section > div:hover {{
    border-color: {GREEN} !important;
    background: rgba(29, 185, 84, 0.1) !important;
}}
div[data-testid="stFileUploader"] button {{
    background: {GREEN} !important;
    color: #000 !important;
    border: none !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
}}

/* ── Launch button ── */
div[data-testid="stButton"] button[kind="primary"] {{
    background: {GREEN} !important;
    color: #000 !important;
    font-weight: 800 !important;
    font-size: 1rem !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.75rem 2rem !important;
    width: 100% !important;
    letter-spacing: -0.01em !important;
    transition: all 0.2s ease !important;
}}
div[data-testid="stButton"] button[kind="primary"]:hover {{
    background: #1ed760 !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 30px {GREEN_GLOW} !important;
}}
div[data-testid="stButton"] button[kind="secondary"] {{
    background: rgba(255,255,255,0.06) !important;
    color: {TEXT} !important;
    border: 1px solid {BORDER_HL} !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    width: 100% !important;
    transition: all 0.2s ease !important;
}}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════
if "upload_state" not in st.session_state:
    st.session_state.upload_state = "idle"   # idle | processing | done | error
if "progress_pct" not in st.session_state:
    st.session_state.progress_pct = 0
if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
if "saved_zip_path" not in st.session_state:
    st.session_state.saved_zip_path = None


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════
LOG_SEQUENCE = [
    (5,  "📂  Reading ZIP archive…"),
    (15, "🎵  Parsing Streaming_History_Audio files…"),
    (30, "🔍  Extracting entities (artists, albums, songs)…"),
    (48, "🗄️  Initialising database schema…"),
    (62, "⬆️  Importing stream records…"),
    (78, "🔗  Building relationships & indexes…"),
    (90, "✅  Finalising import…"),
    (99, "🎉  Almost done…"),
]

def save_uploaded_file(uploaded_file) -> str:
    """Save the Streamlit UploadedFile to a temp path and return it."""
    suffix = ".zip"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.getbuffer())
    tmp.close()
    return tmp.name

def run_java_parser(zip_path: str, username: str):
    cmd = ["java", "-jar", JAVA_JAR_PATH, zip_path, username] 
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )
    return result


# ══════════════════════════════════════════════════════════════════
# RENDER  — IDLE STATE
# ══════════════════════════════════════════════════════════════════
if st.session_state.upload_state == "idle":

    st.markdown("""
    <div class="hero">
        <span class="hero-icon">🎧</span>
        <div class="hero-title">Your music,<br><span>fully yours.</span></div>
        <p class="hero-subtitle">
            Drop your Spotify data export and get a private, beautiful breakdown
            of everything you've ever listened to.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="drop-card">
        <div class="drop-icon">📦</div>
        <div class="drop-label">Drag & drop your Spotify export ZIP</div>
        <div class="drop-hint">my_spotify_data.zip · stays on your machine, never uploaded anywhere</div>
    </div>
    """, unsafe_allow_html=True)

    username = st.text_input("👤 Username", placeholder="e.g. Ody", key="username_input") # <--- ΝΕΟ

    uploaded = st.file_uploader(
        "Upload ZIP",
        type=["zip"],
        label_visibility="collapsed",
        key="zip_uploader"
    )

    if uploaded and username:
        st.markdown(f"""
        <div style="
            background: rgba(29,185,84,0.08);
            border: 1px solid rgba(29,185,84,0.3);
            border-radius: 12px;
            padding: 0.75rem 1rem;
            margin-top: 1rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.88rem;
            color: #B3B3B3;
        ">
            <span style="font-size:1.2rem;">✅</span>
            <div>
                <strong style="color:#fff;">{uploaded.name}</strong>
                &nbsp;·&nbsp; {uploaded.size / 1_000_000:.1f} MB ready to import
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀  Import my Spotify data", type="primary"):
            zip_path = save_uploaded_file(uploaded)
            st.session_state.saved_zip_path = zip_path
            st.session_state.current_user = username
            st.session_state.upload_state = "processing"
            st.session_state.progress_pct = 0
            st.session_state.log_lines = []
            st.rerun()

    st.markdown("""
    <div class="steps">
        <div class="step">
            <div class="step-num">Step 1</div>
            <div class="step-text">Download your data from<br><strong style="color:#fff;">spotify.com/account</strong></div>
        </div>
        <div class="step">
            <div class="step-num">Step 2</div>
            <div class="step-text">Drop the ZIP file<br>here &amp; hit Import</div>
        </div>
        <div class="step">
            <div class="step-num">Step 3</div>
            <div class="step-text">Wait ~60 seconds while<br>we crunch the numbers</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# RENDER  — PROCESSING STATE
# ══════════════════════════════════════════════════════════════════
elif st.session_state.upload_state == "processing":

    proc_placeholder = st.empty()
    progress_bar_ph  = st.empty()
    log_placeholder  = st.empty()

    def render_processing(pct: int, log_lines: list):
        proc_placeholder.markdown(f"""
        <div class="processing-card">
            <div class="wave-bars">
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
                <div class="wave-bar"></div>
            </div>
            <div class="proc-title">Parsing your listening history…</div>
            <div class="proc-subtitle">This takes about a minute. Grab a coffee ☕</div>
            <div class="progress-track">
                <div class="progress-fill" style="width: {pct}%;"></div>
            </div>
            <div class="progress-label">
                <span>Importing</span>
                <span>{pct}%</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if log_lines:
            log_html = "<br>".join(log_lines[-6:])
            log_placeholder.markdown(
                f'<div class="log-box">{log_html}</div>',
                unsafe_allow_html=True
            )

    # ── Kick off Java in a subprocess, animate while waiting ──
    import threading

    result_holder = {"result": None, "done": False}

    def java_thread():
        try:
            result_holder["result"] = run_java_parser(st.session_state.saved_zip_path, st.session_state.current_user)
        except Exception as e:
            result_holder["result"] = type("R", (), {"returncode": 1, "stderr": str(e), "stdout": ""})()
        result_holder["done"] = True

    t = threading.Thread(target=java_thread, daemon=True)
    t.start()

    log_idx = 0
    elapsed  = 0
    interval = 0.5   # seconds between UI refreshes

    while not result_holder["done"]:
        elapsed += interval

        # Advance the scripted log messages on a timeline
        for threshold_s, msg in [
            (2,  LOG_SEQUENCE[0]),
            (6,  LOG_SEQUENCE[1]),
            (14, LOG_SEQUENCE[2]),
            (22, LOG_SEQUENCE[3]),
            (32, LOG_SEQUENCE[4]),
            (44, LOG_SEQUENCE[5]),
            (54, LOG_SEQUENCE[6]),
            (62, LOG_SEQUENCE[7]),
        ]:
            if elapsed >= threshold_s and msg[1] not in st.session_state.log_lines:
                st.session_state.log_lines.append(msg[1])

        # Smooth progress — cap at 97 until Java finishes
        target_pct = min(97, int(elapsed / 70 * 100))
        st.session_state.progress_pct = target_pct

        render_processing(st.session_state.progress_pct, st.session_state.log_lines)
        time.sleep(interval)

    # ── Java finished ──
    result = result_holder["result"]

    if result.returncode == 0:
        render_processing(100, st.session_state.log_lines + ["✅  Done!"])
        time.sleep(0.8)
        # Clean up temp file
        try:
            os.unlink(st.session_state.saved_zip_path)
        except Exception:
            pass
        st.session_state.upload_state = "done"
        st.rerun()
    else:
        st.session_state.upload_state = "error"
        st.session_state.error_msg = result.stderr or "Unknown error from Java parser."
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# RENDER  — DONE STATE
# ══════════════════════════════════════════════════════════════════
elif st.session_state.upload_state == "done":

    st.markdown("""
    <div class="done-card">
        <div class="done-icon">🎉</div>
        <div class="done-title">Your data is ready!</div>
        <div class="done-sub">All your streams have been imported.<br>Head to your dashboard to explore.</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🎧  Open my dashboard →", type="primary"):
        # Redirect to your main app
        # If using multi-page: st.switch_page("app.py")
        # If same-domain single app, use JS redirect:
        st.markdown('<meta http-equiv="refresh" content="0; url=/?tab=overview">',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↩  Import another file", type="secondary"):
        st.session_state.upload_state = "idle"
        st.session_state.saved_zip_path = None
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# RENDER  — ERROR STATE
# ══════════════════════════════════════════════════════════════════
elif st.session_state.upload_state == "error":

    st.markdown(f"""
    <div style="
        background: rgba(220,38,38,0.08);
        border: 1px solid rgba(220,38,38,0.35);
        border-radius: 20px;
        padding: 2.5rem 2rem;
        text-align: center;
    ">
        <div style="font-size:2.5rem; margin-bottom:0.75rem;">⚠️</div>
        <div style="font-size:1.3rem; font-weight:800; color:#fff; margin-bottom:0.5rem;">
            Import failed
        </div>
        <div style="font-size:0.88rem; color:{TEXT_MID}; margin-bottom:1.5rem;">
            The Java parser returned an error. Check that the JAR path is correct
            and your database is running.
        </div>
        <div style="
            background: rgba(0,0,0,0.4);
            border-radius: 10px;
            padding: 0.75rem 1rem;
            font-family: monospace;
            font-size: 0.72rem;
            color: #f87171;
            text-align: left;
            max-height: 140px;
            overflow-y: auto;
            margin-bottom: 1.25rem;
        ">{st.session_state.get('error_msg', '')[:600]}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↩  Try again", type="secondary"):
        st.session_state.upload_state = "idle"
        st.session_state.saved_zip_path = None
        st.rerun()