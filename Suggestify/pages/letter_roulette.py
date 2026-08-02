"""
letter_roulette.py — "Letter Roulette" minigame module for Suggestify.

Drop-in sibling to arena.py: same init_*_module(get_engine, run_query,
run_write_query, GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER) contract,
same hidden-input/JS-timer trick for zero-Python-loop countdowns, same
difflib fuzzy matching for free-text answers.

Two versions:
  - "rally": alternating survival — 60s per turn, one repeat-free song list,
             first player to fail (timeout / no valid song left) loses.
  - "blitz": independent 120s time-attack per player, scored by rarity tier,
             against the same shared, repeat-free song pool.

Design notes
------------
* The full valid song pool for the chosen letter is computed ONCE, in a
  single indexed CTE query (no pandas-side N+1, no full-table scans), and
  cached as JSONB on the match row. Every client loads it once into
  st.session_state and validates guesses 100% in-memory via difflib —
  this is what gives "0-second lag" on Enter.
* The ONLY write on a correct guess is a single
  `INSERT ... ON CONFLICT (match_id, song_id) DO NOTHING` — this is also
  what enforces "a song can't be reused", even across two concurrent
  browser sessions in Friends mode, without any extra round trip.
* Rally turn-taking lives on the match row (turn_user_id, turn_number).
  The non-active player polls cheaply (same JS pattern as the timeout
  ticker) until the turn flips to them.
"""

from __future__ import annotations

import json
import random
import string
import time
import difflib
from html import escape
from types import SimpleNamespace

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

# === TUNABLES ===
RALLY_TURN_SECONDS = 60
BLITZ_SECONDS = 120
LETTER_MIN_POOL = 6           # a letter needs >= this many eligible songs to be selectable
FUZZY_MATCH_THRESHOLD = 0.82  # difflib ratio for free-text answers
TIER_BASE_POINTS = {"core": 50, "regular": 100, "deep_cut": 200}
ALPHABET = list(string.ascii_uppercase)

GAME_META = {
    "rally": {"icon": "🏓", "label": "Rally", "desc": "Alternating survival. Miss once and you're out."},
    "blitz": {"icon": "⚡", "label": "Blitz", "desc": "2-minute time attack. Rare songs score big."},
}

def get_turn_duration() -> int:
    return RALLY_TURN_SECONDS

def get_blitz_duration() -> int:
    return BLITZ_SECONDS

# ─────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS letter_game_matches (
    id                BIGSERIAL PRIMARY KEY,
    mode              VARCHAR(20) NOT NULL CHECK (mode IN ('solo','friends')),
    game_version      VARCHAR(10) NOT NULL CHECK (game_version IN ('rally','blitz')),
    target_letter     CHAR(1) NOT NULL,
    host_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status            VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
    valid_pool        JSONB NOT NULL DEFAULT '[]'::jsonb,
    pool_size         INT NOT NULL DEFAULT 0,
    turn_number       INT NOT NULL DEFAULT 1,
    turn_user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    loser_user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_letter_matches_host   ON letter_game_matches(host_user_id);
CREATE INDEX IF NOT EXISTS idx_letter_matches_friend ON letter_game_matches(friend_user_id);
CREATE INDEX IF NOT EXISTS idx_letter_matches_status ON letter_game_matches(status);

CREATE TABLE IF NOT EXISTS letter_game_sessions (
    id              BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES letter_game_matches(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','failed')),
    score           INT NOT NULL DEFAULT 0,
    songs_found     INT NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    CONSTRAINT uq_letter_game_session UNIQUE (match_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_letter_sessions_user  ON letter_game_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_letter_sessions_match ON letter_game_sessions(match_id);

CREATE TABLE IF NOT EXISTS letter_game_answers (
    id                BIGSERIAL PRIMARY KEY,
    match_id          BIGINT NOT NULL REFERENCES letter_game_matches(id) ON DELETE CASCADE,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    song_id           INTEGER NOT NULL,
    song_name         VARCHAR(255) NOT NULL,
    familiarity_tier  VARCHAR(20) NOT NULL CHECK (familiarity_tier IN ('core','regular','deep_cut')),
    points_earned     INT NOT NULL DEFAULT 0,
    turn_number       INT,
    answered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_letter_game_answer UNIQUE (match_id, song_id)
);
CREATE INDEX IF NOT EXISTS idx_letter_answers_match ON letter_game_answers(match_id);
CREATE INDEX IF NOT EXISTS idx_letter_answers_user  ON letter_game_answers(match_id, user_id);
"""


def init_letter_game_module(get_engine, run_query, run_write_query,
                             GREEN, TEXT, TEXT_MID, TEXT_DIM, BG, CARD, BORDER):

    @st.cache_resource(show_spinner=False)
    def _schema_ready():
        for stmt in _SCHEMA_SQL.strip().split(";\n\n"):
            stmt = stmt.strip()
            if stmt:
                run_write_query(stmt + ";")
        return True

    _schema_ready()

    # ─────────────────────────────────────────────────────────────────
    # Eligibility / pool building — all filtering happens in SQL
    # ─────────────────────────────────────────────────────────────────

    def _uid_filter(user_ids: list[int]) -> tuple[str, dict]:
        """Returns (sql_clause, params) for filtering streams.user_id,
        handling the 1-user (solo) and 2-user (friends) cases explicitly
        rather than relying on array binding support."""
        if len(user_ids) == 1:
            return "= :uid0", {"uid0": int(user_ids[0])}
        return "IN (:uid0, :uid1)", {"uid0": int(user_ids[0]), "uid1": int(user_ids[1])}

    def _letter_counts_by_alpha(user_ids: list[int]) -> dict:
        """One indexed query: distinct-song count per starting letter,
        scoped to the given user(s)' streaming history. Used both for
        eligibility gating and for picking a target letter with enough
        depth to make a real round."""
        clause, params = _uid_filter(user_ids)
        df = run_query(f"""
            WITH scoped_songs AS (
                SELECT DISTINCT s.song_id
                FROM streams s
                WHERE s.user_id {clause}
            )
            SELECT UPPER(LEFT(so.title, 1)) AS letter, COUNT(DISTINCT so.id) AS cnt
            FROM songs so
            JOIN scoped_songs ss ON ss.song_id = so.id
            WHERE so.title ~ '^[A-Za-z]'
            GROUP BY UPPER(LEFT(so.title, 1))
        """, params)
        if df.empty:
            return {}
        return dict(zip(df["letter"], df["cnt"]))

    def _eligible_letters(user_ids: list[int]) -> list[str]:
        counts = _letter_counts_by_alpha(user_ids)
        return [l for l, c in counts.items() if c >= LETTER_MIN_POOL]

    def is_letter_game_eligible(user_id: int) -> bool:
        return len(_eligible_letters([user_id])) > 0

    def eligible_friends_pairs(user_id: int, other_user_ids: list[int]) -> list[int]:
        """Of the candidate friend ids, which ones produce an eligible
        combined pool with user_id? Used to grey out unplayable duel
        partners in the UI."""
        out = []
        for fid in other_user_ids:
            if len(_eligible_letters([user_id, fid])) > 0:
                out.append(fid)
        return out

    def _fetch_letter_pool(user_ids: list[int], letter: str) -> list[dict]:
        """The single high-performance query: songs starting with `letter`
        that the scoped user(s) have actually streamed, tiered by rarity
        via a window function computed server-side (no pandas percentile
        loop, no loading unrelated rows)."""
        clause, params = _uid_filter(user_ids)
        params["pattern"] = f"{letter}%"
        df = run_query(f"""
            WITH scoped_streams AS (
                SELECT song_id, COUNT(*) AS stream_count
                FROM streams
                WHERE user_id {clause}
                GROUP BY song_id
            ),
            lettered AS (
                SELECT so.id AS song_id, so.title AS song_name, ss.stream_count
                FROM songs so
                JOIN scoped_streams ss ON ss.song_id = so.id
                WHERE so.title ILIKE :pattern
            ),
            ranked AS (
                SELECT song_id, song_name, stream_count,
                       PERCENT_RANK() OVER (ORDER BY stream_count DESC) AS pct_rank
                FROM lettered
            )
            SELECT song_id, song_name, stream_count,
                   CASE WHEN pct_rank < 0.20 THEN 'core'
                        WHEN pct_rank < 0.70 THEN 'regular'
                        ELSE 'deep_cut' END AS familiarity_tier
            FROM ranked
            ORDER BY stream_count DESC
        """, params)
        if df.empty:
            return []
        out = []
        for _, row in df.iterrows():
            tier = row["familiarity_tier"]
            out.append({
                "song_id": int(row["song_id"]),
                "song_name": row["song_name"],
                "familiarity_tier": tier,
                "points": TIER_BASE_POINTS[tier],
            })
        return out

    # ─────────────────────────────────────────────────────────────────
    # Match / session lifecycle
    # ─────────────────────────────────────────────────────────────────

    def create_match(host_user_id: int, mode: str, game_version: str,
                      friend_user_id: int | None = None) -> int | None:
        user_ids = [host_user_id] if mode == "solo" else [host_user_id, friend_user_id]
        letters = _eligible_letters(user_ids)
        if not letters:
            return None
        target_letter = random.choice(letters)
        pool = _fetch_letter_pool(user_ids, target_letter)
        if len(pool) < LETTER_MIN_POOL:
            return None

        rows = run_write_query("""
            INSERT INTO letter_game_matches
                (mode, game_version, target_letter, host_user_id, friend_user_id,
                 valid_pool, pool_size, turn_user_id)
            VALUES (:mode, :gv, :letter, :host, :friend, :pool, :psize, :turn_user)
            RETURNING id
        """, dict(mode=mode, gv=game_version, letter=target_letter,
                  host=host_user_id, friend=friend_user_id,
                  pool=json.dumps(pool), psize=len(pool), turn_user=host_user_id))
        match_id = rows[0]["id"]

        for uid in user_ids:
            run_write_query("""
                INSERT INTO letter_game_sessions (match_id, user_id)
                VALUES (:m, :u)
                ON CONFLICT (match_id, user_id) DO NOTHING
            """, {"m": match_id, "u": uid})
        return match_id

    def get_match(match_id: int) -> dict | None:
        rows = run_write_query("SELECT * FROM letter_game_matches WHERE id=:id", {"id": match_id})
        return dict(rows[0]) if rows else None

    def get_session(match_id: int, user_id: int) -> dict | None:
        rows = run_write_query(
            "SELECT * FROM letter_game_sessions WHERE match_id=:m AND user_id=:u",
            {"m": match_id, "u": user_id}
        )
        return dict(rows[0]) if rows else None

    def get_used_song_ids(match_id: int) -> set:
        rows = run_write_query(
            "SELECT song_id FROM letter_game_answers WHERE match_id=:m", {"m": match_id}
        )
        return {r["song_id"] for r in rows} if rows else set()

    def _load_pool_into_state(match: dict):
        """Cache the (large, static) valid pool client-side exactly once
        per match — every subsequent fuzzy-match check is pure Python,
        no DB round trip."""
        key = f"lg_pool_{match['id']}"
        if key not in st.session_state:
            pool = match["valid_pool"]
            if isinstance(pool, str):
                pool = json.loads(pool)
            st.session_state[key] = pool
        return st.session_state[key]

    def _answer_matches(guess: str, correct: str) -> bool:
        g, c = guess.strip().lower(), correct.strip().lower()
        if not g:
            return False
        if g == c:
            return True
        return difflib.SequenceMatcher(None, g, c).ratio() >= FUZZY_MATCH_THRESHOLD

    def _find_local_match(guess: str, pool: list[dict], used_ids: set) -> dict | None:
        """Pure in-memory validation — the whole point of caching the pool."""
        if not guess.strip():
            return None
        for song in pool:
            if song["song_id"] in used_ids:
                continue
            if _answer_matches(guess, song["song_name"]):
                return song
        return None

    def _record_answer(match: dict, user_id: int, song: dict, turn_number: int | None) -> bool:
        """The one DB write on a correct guess. ON CONFLICT DO NOTHING is
        what makes 'a song can't be reused' safe even with two concurrent
        friends-mode sessions racing on the same song."""
        rows = run_write_query("""
            INSERT INTO letter_game_answers
                (match_id, user_id, song_id, song_name, familiarity_tier, points_earned, turn_number)
            VALUES (:m, :u, :sid, :sname, :tier, :pts, :turn)
            ON CONFLICT (match_id, song_id) DO NOTHING
            RETURNING id
        """, dict(m=match["id"], u=user_id, sid=song["song_id"], sname=song["song_name"],
                  tier=song["familiarity_tier"], pts=song["points"], turn=turn_number))
        if not rows:
            return False  # someone else claimed it a beat earlier
        run_write_query("""
            UPDATE letter_game_sessions
            SET score = score + :pts, songs_found = songs_found + 1
            WHERE match_id = :m AND user_id = :u
        """, dict(pts=song["points"], m=match["id"], u=user_id))
        return True

    # ---- Rally-specific ----

    def _advance_rally_turn(match: dict):
        """Flips the active player (friends) or just resets the clock (solo)."""
        next_user = match["host_user_id"]
        if match["mode"] == "friends":
            next_user = match["friend_user_id"] if match["turn_user_id"] == match["host_user_id"] else match["host_user_id"]
        run_write_query("""
            UPDATE letter_game_matches
            SET turn_number = turn_number + 1, turn_user_id = :nu
            WHERE id = :id
        """, {"nu": next_user, "id": match["id"]})

    def _end_rally(match: dict, loser_user_id: int | None):
        """loser_user_id is None for a full pool clear (co-op win)."""
        run_write_query("""
            UPDATE letter_game_matches
            SET status='completed', completed_at=now(), loser_user_id=:loser
            WHERE id=:id
        """, {"loser": loser_user_id, "id": match["id"]})
        for uid in {match["host_user_id"], match["friend_user_id"]}:
            if uid is None:
                continue
            status = "failed" if uid == loser_user_id else "completed"
            run_write_query("""
                UPDATE letter_game_sessions SET status=:s, completed_at=now()
                WHERE match_id=:m AND user_id=:u
            """, {"s": status, "m": match["id"], "u": uid})

    # ---- Blitz-specific ----

    def _end_blitz_session(match_id: int, user_id: int):
        run_write_query("""
            UPDATE letter_game_sessions SET status='completed', completed_at=now()
            WHERE match_id=:m AND user_id=:u
        """, {"m": match_id, "u": user_id})

    # ─────────────────────────────────────────────────────────────────
    # JS: countdown bar + timeout / poll hidden-input pattern
    # (same trick as arena.py's render_round_timer_script)
    # ─────────────────────────────────────────────────────────────────

    def render_countdown_script(tick_key: str, started_at_ms: float, duration_sec: int,
                                 input_aria: str):
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const startedAt = {started_at_ms};
            const durationMs = {duration_sec * 1000};
            const tickKey = {json.dumps(tick_key)};

            if (doc.__lgTickKey === tickKey) return;
            doc.__lgTickKey = tickKey;
            doc.__lgFired = false;
            if (doc.__lgInterval) clearInterval(doc.__lgInterval);

            function fire() {{
                function trySubmit(retries) {{
                    const inp = doc.querySelector('input[aria-label="{input_aria}"]');
                    if (!inp) {{ if (retries > 0) setTimeout(function(){{ trySubmit(retries - 1); }}, 80); return; }}
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                    setter.call(inp, tickKey + ':' + Date.now());
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    inp.focus({{ preventScroll: true }});
                    setTimeout(function() {{
                        inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.blur();
                    }}, 30);
                }}
                trySubmit(5);
            }}

            function tick() {{
                const now = Date.now();
                const frac = Math.min((now - startedAt) / durationMs, 1);
                const bar = doc.getElementById('lg-progress-bar');
                if (bar) bar.style.width = ((1 - frac) * 100) + '%';
                if (frac >= 1 && !doc.__lgFired) {{
                    doc.__lgFired = true;
                    clearInterval(doc.__lgInterval);
                    fire();
                }}
            }}
            doc.__lgInterval = setInterval(tick, 150);
            tick();
        }})();
        </script>
        """, height=0)

    def render_poll_script(poll_key: str, input_aria: str, every_ms: int = 3000):
        """Used only while waiting for the opponent's rally turn — cheaply
        pings the server every few seconds so the UI flips the instant
        turn_user_id changes, without a full websocket layer."""
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const key = {json.dumps("poll_" + poll_key)};
            if (doc.__lgPollKey === key) return;
            doc.__lgPollKey = key;
            if (doc.__lgPollInterval) clearInterval(doc.__lgPollInterval);

            function ping() {{
                function trySubmit(retries) {{
                    const inp = doc.querySelector('input[aria-label="{input_aria}"]');
                    if (!inp) {{ if (retries > 0) setTimeout(function(){{ trySubmit(retries - 1); }}, 80); return; }}
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                    setter.call(inp, key + ':' + Date.now());
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    inp.focus({{ preventScroll: true }});
                    setTimeout(function() {{
                        inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.blur();
                    }}, 30);
                }}
                trySubmit(3);
            }}
            doc.__lgPollInterval = setInterval(ping, {every_ms});
        }})();
        </script>
        """, height=0)

    # ─────────────────────────────────────────────────────────────────
    # Hidden-input workers (timeout / poll resolution)
    # ─────────────────────────────────────────────────────────────────

    def letter_game_hidden_worker():
        def _ctx():
            match_id = st.session_state.get("lg_match_id")
            user_id = st.session_state.get("lg_user_id")
            if not match_id or not user_id:
                return None
            match = get_match(match_id)
            if not match:
                return None
            return match, user_id

        def on_rally_timeout():
            val = st.session_state.get("lg_rally_timeout_state")
            if not val:
                return
            ctx = _ctx()
            if not ctx:
                return
            match, user_id = ctx
            if match["status"] != "active" or match["game_version"] != "rally":
                return
            # Only the active player's timeout actually ends the game —
            # stale timers from a just-completed turn should no-op.
            if match["turn_user_id"] != user_id:
                return
            _end_rally(match, loser_user_id=user_id)
            st.rerun()

        def on_blitz_timeout():
            val = st.session_state.get("lg_blitz_timeout_state")
            if not val:
                return
            ctx = _ctx()
            if not ctx:
                return
            match, user_id = ctx
            session = get_session(match["id"], user_id)
            if session and session["status"] == "in_progress":
                _end_blitz_session(match["id"], user_id)
            st.rerun()

        def on_rally_poll():
            # No-op handler: the mere on_change firing causes Streamlit to
            # rerun the script, which re-reads turn_user_id from the DB.
            pass

        st.text_input("lg_rally_timeout_input", key="lg_rally_timeout_state",
                       label_visibility="collapsed", on_change=on_rally_timeout)
        st.text_input("lg_blitz_timeout_input", key="lg_blitz_timeout_state",
                       label_visibility="collapsed", on_change=on_blitz_timeout)
        st.text_input("lg_rally_poll_input", key="lg_rally_poll_state",
                       label_visibility="collapsed", on_change=on_rally_poll)

    # ─────────────────────────────────────────────────────────────────
    # CSS (trimmed sibling of arena's modal look)
    # ─────────────────────────────────────────────────────────────────

    _MODAL_CSS = f"""
    <style>
    /* 1. Σκοτώνουμε τα transforms του Streamlit που χαλάνε το Modal */
    body:has(.st-key-lg_modal_overlay) .stApp > div,
    body:has(.st-key-lg_modal_overlay) section.main > div.block-container,
    body:has(.st-key-lg_modal_overlay) [data-testid="stVerticalBlock"] > div,
    body:has(.st-key-lg_modal_overlay) div.element-container {{
        transform: none !important;
        animation: none !important;
        filter: none !important;
        perspective: none !important;
        will-change: auto !important;
    }}

    /* 2. Στήνουμε το Overlay (Σκοτεινό φόντο πίσω) */
    div.element-container:has(.st-key-lg_modal_overlay) {{
        position: fixed !important; inset: 0 !important;
        width: 100vw !important; height: 100vh !important; z-index: 999999 !important;
    }}
    div.st-key-lg_modal_overlay {{
        position: fixed !important; inset: 0 !important;
        width: 100vw !important; height: 100vh !important;
        background: rgba(0,0,0,0.85) !important; backdrop-filter: blur(8px) !important;
        display: flex !important; flex-direction: column !important; align-items: center !important; justify-content: center !important;
        z-index: 999999 !important;
    }}

    /* 3. Στήνουμε την κεντρική Κάρτα (Το Modal Content) */
    div.st-key-lg_modal_content {{
        position: relative !important;
        background: radial-gradient(circle at 18% -12%, {GREEN}26 0%, transparent 42%),
                    linear-gradient(165deg, {CARD} 0%, #0b0b0d 130%) !important;
        border: 1px solid {BORDER} !important; border-radius: 22px !important;
        padding: 2.6rem 2.5rem 2.5rem !important; max-width: 520px !important; width: 90% !important;
        max-height: 85vh !important; overflow-y: auto !important; overflow-x: hidden !important;
        box-shadow: 0 30px 70px -12px rgba(0,0,0,1.0), inset 0 1px 0 rgba(255,255,255,0.04) !important;
        margin: auto !important;
    }}

    /* 4. Κουμπί κλεισίματος (Πάνω Δεξιά) */
    div.st-key-lg_close_btn {{
        position: absolute !important; top: 1.15rem !important; right: 1.15rem !important; z-index: 30 !important; width: auto !important;
    }}
    div.st-key-lg_close_btn button {{
        width: 34px !important; height: 34px !important; min-width: 34px !important; padding: 0 !important;
        border-radius: 50% !important; background: rgba(255,255,255,0.06) !important;
        border: 1px solid {BORDER} !important; color: {TEXT_MID} !important;
    }}
    div.st-key-lg_close_btn button:hover {{ background: rgba(255,255,255,0.14) !important; color: {TEXT} !important; }}

    /* 5. Εσωτερικά Στοιχεία UI του Παιχνιδιού */
    .lg-kicker-wrap {{ text-align: center; margin-bottom: 0.9rem; }}
    .lg-kicker {{ display: inline-block; font-size: 0.66rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; color: {GREEN}; background: rgba(29,185,84,0.10); border: 1px solid rgba(29,185,84,0.32); padding: 5px 14px; border-radius: 999px; }}
    .lg-title {{ font-size: 1.8rem; font-weight: 800; color: {TEXT}; text-align: center; margin-bottom: 0.25rem; }}
    .lg-subtitle {{ font-size: 0.95rem; color: {TEXT_MID}; text-align: center; margin-bottom: 1.6rem; }}
    .lg-letter-badge {{ width: 84px; height: 84px; margin: 0 auto 1.4rem; border-radius: 20px; background: linear-gradient(135deg, {GREEN} 0%, #12793a 100%); display: flex; align-items: center; justify-content: center; font-size: 2.6rem; font-weight: 900; color: #05130a; box-shadow: 0 10px 30px rgba(29,185,84,0.35); }}
    .lg-progress-track {{ width: 100%; height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; margin-bottom: 1.2rem; }}
    .lg-progress-bar {{ height: 100%; width: 100%; background: {GREEN}; transition: width 0.15s linear; }}
    .lg-found-list {{ display: flex; flex-wrap: wrap; gap: 0.4rem; justify-content: center; margin: 0.8rem 0 1.2rem; }}
    .lg-found-chip {{ background: rgba(29,185,84,0.12); border: 1px solid rgba(29,185,84,0.35); color: {GREEN}; border-radius: 999px; padding: 0.3rem 0.75rem; font-size: 0.78rem; font-weight: 700; }}
    .lg-waiting {{ text-align: center; color: {TEXT_MID}; font-size: 0.95rem; padding: 1.2rem 0; }}
    
    div.st-key-lg_modal_content div[data-testid="stTextInput"] input {{ text-align: center !important; font-size: 1.1rem !important; font-weight: 600 !important; padding: 1rem !important; }}
    
    body:has(.st-key-lg_modal_overlay) {{ overflow: hidden !important; }}
    </style>
    """

    def _close_letter_game():
        st.query_params.pop("letter_game", None)
        st.query_params.pop("lg_view", None)
        for k in list(st.session_state.keys()):
            if k.startswith("lg_") or k.startswith("_lg_"):
                del st.session_state[k]
        st.rerun()

    def render_modal(selected_user_id: int, user_dict: dict):
        if st.query_params.get("letter_game") != "1":
            return
        st.markdown(_MODAL_CSS, unsafe_allow_html=True)
        view = st.query_params.get("lg_view", "mode")

        with st.container(key="lg_modal_overlay"):
            with st.container(key="lg_modal_content"):
                if st.button("✕", key="lg_close_btn"):
                    _close_letter_game()

                if view == "mode":
                    _render_mode_select(selected_user_id)
                elif view == "version":
                    _render_version_select(selected_user_id)
                elif view == "setup":
                    _render_setup(selected_user_id, user_dict)
                elif view == "play":
                    _render_gameplay(selected_user_id)
                elif view == "recap":
                    _render_recap(selected_user_id)

    def _header(kicker: str, title: str, subtitle: str | None = None):
        sub_html = f'<div class="lg-subtitle">{subtitle}</div>' if subtitle else ""
        st.markdown(
            f'<div class="lg-kicker-wrap"><span class="lg-kicker">{kicker}</span></div>'
            f'<div class="lg-title">{title}</div>{sub_html}',
            unsafe_allow_html=True
        )

    def _render_mode_select(user_id: int):
        _header("🎧 Suggestify", "🔤 Letter Roulette",
                 "Name songs starting with the roulette letter — from your own library.")
        if not is_letter_game_eligible(user_id):
            st.info(f"Keep listening! You need at least {LETTER_MIN_POOL} streamed songs "
                    f"sharing a starting letter to unlock this game.")
            return
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎮 Single player", key="lg_mode_solo", use_container_width=True):
                st.session_state["lg_mode"] = "solo"
                st.query_params["lg_view"] = "version"
                st.rerun()
        with c2:
            if st.button("🤝 Play with friends", key="lg_mode_friends", use_container_width=True):
                st.session_state["lg_mode"] = "friends"
                st.query_params["lg_view"] = "version"
                st.rerun()

    def _render_version_select(user_id: int):
        _header("🔤 Letter Roulette", "Choose a version")
        for gv, meta in GAME_META.items():
            cols = st.columns([4, 1])
            cols[0].markdown(
                f"**{meta['icon']} {meta['label']}**  \n"
                f"<span style='color:{TEXT_MID};font-size:0.85rem;'>{meta['desc']}</span>",
                unsafe_allow_html=True
            )
            if cols[1].button("Play", key=f"lg_version_{gv}"):
                st.session_state["lg_game_version"] = gv
                st.query_params["lg_view"] = "setup"
                st.rerun()

    def _render_setup(user_id: int, user_dict: dict):
        mode = st.session_state.get("lg_mode", "solo")
        gv = st.session_state.get("lg_game_version", "rally")
        meta = GAME_META[gv]
        _header(f'{meta["icon"]} {meta["label"]}', "Ready up")

        friend_user_id = None
        if mode == "friends":
            candidates = [u for u in user_dict.keys() if user_dict[u] != user_id]
            candidate_ids = [user_dict[u] for u in candidates]
            playable_ids = set(eligible_friends_pairs(user_id, candidate_ids))
            playable = [u for u in candidates if user_dict[u] in playable_ids]
            if not playable:
                st.info("No friend shares enough overlapping-letter listening history yet.")
                return
            friend_username = st.selectbox("Duel who?", playable, key="lg_friend_select")
            friend_user_id = user_dict[friend_username]

        if gv == "rally":
            st.markdown(
                f'<div class="lg-subtitle">{RALLY_TURN_SECONDS}s per turn. Miss the clock, '
                f'or run out of valid songs, and you lose.</div>', unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="lg-subtitle">{BLITZ_SECONDS}s on the clock. '
                f'Rarer songs in your history score more.</div>', unsafe_allow_html=True
            )

        if st.button("Spin the Letter", key="lg_start_btn", type="primary", use_container_width=True):
            match_id = create_match(user_id, mode, gv, friend_user_id)
            if match_id is None:
                st.error("Couldn't find a letter with enough eligible songs — try again after streaming more.")
                return
            st.session_state["lg_match_id"] = match_id
            st.session_state["lg_user_id"] = user_id
            st.query_params["lg_view"] = "play"
            st.rerun()

    # ---- Gameplay: Rally ----

    def _render_rally_gameplay(user_id: int, match: dict):
        if match["status"] == "completed":
            st.query_params["lg_view"] = "recap"
            st.rerun()
            return

        pool = _load_pool_into_state(match)
        used_ids = get_used_song_ids(match["id"])
        is_my_turn = match["turn_user_id"] == user_id
        opponent_id = match["friend_user_id"] if match["mode"] == "friends" else None

        st.markdown(
            f'<div class="lg-kicker-wrap"><span class="lg-kicker">🏓 Rally</span></div>'
            f'<div class="lg-title">Turn {match["turn_number"]}</div>',
            unsafe_allow_html=True
        )
        st.markdown(f'<div class="lg-letter-badge">{escape(match["target_letter"])}</div>', unsafe_allow_html=True)

        found_chips = "".join(
            f'<span class="lg-found-chip">{escape(a)}</span>'
            for a in [s["song_name"] for s in pool if s["song_id"] in used_ids]
        )
        if found_chips:
            st.markdown(f'<div class="lg-found-list">{found_chips}</div>', unsafe_allow_html=True)

        if len(used_ids) >= len(pool):
            _end_rally(match, loser_user_id=None)
            st.rerun()
            return

        if not is_my_turn:
            other_label = "your friend" if opponent_id else "the timer"
            st.markdown(f'<div class="lg-waiting">⏳ Waiting on {other_label}\'s turn…</div>', unsafe_allow_html=True)
            render_poll_script(f"{match['id']}_{match['turn_number']}", "lg_rally_poll_input")
            return

        start_key = f"lg_turn_start_{match['id']}_{match['turn_number']}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown('<div class="lg-progress-track"><div class="lg-progress-bar" id="lg-progress-bar"></div></div>',
                    unsafe_allow_html=True)
        turn_key = f"{match['id']}_{match['turn_number']}"
        render_countdown_script(turn_key, started_at * 1000, RALLY_TURN_SECONDS, "lg_rally_timeout_input")

        guess_key = f"lg_rally_guess_{turn_key}"

        def _on_submit():
            guess = st.session_state.get(guess_key, "")
            song = _find_local_match(guess, pool, used_ids)
            if not song:
                st.toast("Not a valid, unused song for this letter.", icon="❌")
                return
            ok = _record_answer(match, user_id, song, match["turn_number"])
            if not ok:
                st.toast("That one was just claimed — try another!", icon="⚠️")
                return
            st.toast(f"✅ {song['song_name']} (+{song['points']} pts)", icon="🎯")
            _advance_rally_turn(match)

        st.text_input("Your song", key=guess_key, label_visibility="collapsed",
                      placeholder=f"A song starting with '{match['target_letter']}'…",
                      on_change=_on_submit)

        if st.button("🏳️ I've got nothing", key=f"lg_rally_giveup_{turn_key}", use_container_width=True):
            _end_rally(match, loser_user_id=user_id)
            st.rerun()

    # ---- Gameplay: Blitz ----

    def _render_blitz_gameplay(user_id: int, match: dict):
        pool = _load_pool_into_state(match)
        session = get_session(match["id"], user_id)
        if session is None:
            st.query_params["lg_view"] = "mode"
            st.rerun()
            return

        if session["status"] != "in_progress":
            st.query_params["lg_view"] = "recap"
            st.rerun()
            return

        used_ids = get_used_song_ids(match["id"])

        st.markdown(
            f'<div class="lg-kicker-wrap"><span class="lg-kicker">⚡ Blitz</span></div>'
            f'<div class="lg-title">Score: {session["score"]}</div>'
            f'<div class="lg-subtitle">Found {session["songs_found"]} songs</div>',
            unsafe_allow_html=True
        )
        st.markdown(f'<div class="lg-letter-badge">{escape(match["target_letter"])}</div>', unsafe_allow_html=True)

        mine = run_write_query(
            "SELECT song_name FROM letter_game_answers WHERE match_id=:m AND user_id=:u ORDER BY answered_at",
            {"m": match["id"], "u": user_id}
        )
        found_chips = "".join(f'<span class="lg-found-chip">{escape(r["song_name"])}</span>' for r in mine)
        if found_chips:
            st.markdown(f'<div class="lg-found-list">{found_chips}</div>', unsafe_allow_html=True)

        start_key = f"lg_blitz_start_{match['id']}_{user_id}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown('<div class="lg-progress-track"><div class="lg-progress-bar" id="lg-progress-bar"></div></div>',
                    unsafe_allow_html=True)
        blitz_key = f"{match['id']}_{user_id}"
        render_countdown_script(blitz_key, started_at * 1000, BLITZ_SECONDS, "lg_blitz_timeout_input")

        if len(used_ids) >= len(pool):
            _end_blitz_session(match["id"], user_id)
            st.rerun()
            return

        nonce_key = f"lg_blitz_nonce_{blitz_key}"
        nonce = st.session_state.get(nonce_key, 0)
        guess_key = f"lg_blitz_guess_{blitz_key}_{nonce}"

        def _on_submit():
            guess = st.session_state.get(guess_key, "")
            song = _find_local_match(guess, pool, used_ids)
            if song:
                if _record_answer(match, user_id, song, None):
                    st.toast(f"✅ {song['song_name']} (+{song['points']} pts)", icon="🎯")
                else:
                    st.toast("That one was just claimed — keep going!", icon="⚠️")
            st.session_state[nonce_key] = nonce + 1

        st.text_input("Your song", key=guess_key, label_visibility="collapsed",
                      placeholder=f"Type songs starting with '{match['target_letter']}'…",
                      on_change=_on_submit)

    def _render_gameplay(user_id: int):
        match_id = st.session_state.get("lg_match_id")
        if not match_id:
            st.query_params["lg_view"] = "mode"
            st.rerun()
            return
        match = get_match(match_id)
        if not match:
            st.query_params["lg_view"] = "mode"
            st.rerun()
            return

        if match["game_version"] == "rally":
            _render_rally_gameplay(user_id, match)
        else:
            _render_blitz_gameplay(user_id, match)

    def _render_recap(user_id: int):
        match_id = st.session_state.get("lg_match_id")
        if not match_id:
            st.query_params["lg_view"] = "mode"
            st.rerun()
            return
        match = get_match(match_id)
        my_session = get_session(match_id, user_id)

        meta = GAME_META[match["game_version"]]
        _header(f'{meta["icon"]} {meta["label"]}', "🏁 Recap")

        if match["game_version"] == "rally":
            if match["loser_user_id"] is None:
                st.success("✨ Full clear — you cleared the entire pool together!")
            elif match["loser_user_id"] == user_id:
                st.error("💥 You missed a beat. Rally over.")
            else:
                st.success("🏆 Your opponent missed a beat — you win!")
            c1, c2 = st.columns(2)
            c1.metric("Your score", my_session["score"] if my_session else 0)
            c1.metric("Songs found", my_session["songs_found"] if my_session else 0)
            if match["mode"] == "friends":
                opp_session = get_session(match_id, match["friend_user_id"] if match["host_user_id"] == user_id else match["host_user_id"])
                if opp_session:
                    c2.metric("Opponent score", opp_session["score"])
                    c2.metric("Opponent found", opp_session["songs_found"])
        else:
            c1, c2 = st.columns(2)
            c1.metric("Your score", my_session["score"] if my_session else 0)
            c1.metric("Songs found", my_session["songs_found"] if my_session else 0)
            if match["mode"] == "friends":
                other_uid = match["friend_user_id"] if match["host_user_id"] == user_id else match["host_user_id"]
                opp_session = get_session(match_id, other_uid)
                if opp_session and opp_session["status"] == "completed":
                    c2.metric("Opponent score", opp_session["score"])
                    c2.metric("Opponent found", opp_session["songs_found"])
                    if opp_session["score"] > (my_session["score"] if my_session else 0):
                        st.info("Your friend edged you out this round!")
                    elif my_session and my_session["score"] > opp_session["score"]:
                        st.success("You beat your friend's score!")
                else:
                    st.info("⏳ Waiting on your friend to finish their Blitz run.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Play Again", key="lg_play_again_btn", type="primary", use_container_width=True):
            st.query_params["lg_view"] = "mode"
            for k in ("lg_match_id", "lg_user_id", "lg_mode", "lg_game_version"):
                st.session_state.pop(k, None)
            st.rerun()

    return SimpleNamespace(
        letter_game_hidden_worker=letter_game_hidden_worker,
        render_modal=render_modal,
        is_letter_game_eligible=is_letter_game_eligible,
        create_match=create_match,
    )