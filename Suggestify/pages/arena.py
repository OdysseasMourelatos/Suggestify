"""
arena.py — "Arena" minigame hub for Suggestify.
"""

from __future__ import annotations

import json
import random
import time
import difflib
import datetime
from html import escape
from types import SimpleNamespace

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

# === ΧΡΟΝΟΣ ΑΝΑ ΓΥΡΟ ΣΤΑ 25 ΔΕΥΤΕΡΟΛΕΠΤΑ ===
REVEAL_SECONDS = 25
ELIGIBILITY_FLOOR = 15          # min eligible items per game_type before Arena unlocks for a user
HINT_BUDGET = {5: 1, 10: 2, 20: 4}
TIER_TARGET_FRAC = {"core": 0.35, "regular": 0.35, "deep_cut": 0.30}
TIER_BASE_POINTS = {"core": 50, "regular": 100, "deep_cut": 200}
FUZZY_MATCH_THRESHOLD = 0.82    # difflib ratio for free-text answers
EASY_SCORE_MULTIPLIER = 0.8     # slight point discount for the always-multiple-choice mode

GAME_META = {
    "cover":  {"icon": "🖼️", "label": "Guess the Cover",  "desc": "Album art, progressively revealed."},
    "artist": {"icon": "🎤", "label": "Guess the Artist", "desc": "Artist photos, progressively revealed."},
}

# ─────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS arena_pools (
    id              BIGSERIAL PRIMARY KEY,
    mode            VARCHAR(20) NOT NULL CHECK (mode IN ('solo','friends')),
    game_type       VARCHAR(20) NOT NULL CHECK (game_type IN ('cover','artist')),
    round_count     INT NOT NULL CHECK (round_count IN (5,10,20)),
    difficulty      VARCHAR(10) NOT NULL DEFAULT 'hard' CHECK (difficulty IN ('easy','hard')),
    hint_budget     INT NOT NULL,
    host_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_user_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_arena_pools_host   ON arena_pools(host_user_id);
CREATE INDEX IF NOT EXISTS idx_arena_pools_friend ON arena_pools(friend_user_id);

ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS difficulty VARCHAR(10) NOT NULL DEFAULT 'hard';

CREATE TABLE IF NOT EXISTS arena_pool_rounds (
    id                BIGSERIAL PRIMARY KEY,
    pool_id           BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    round_number      INT NOT NULL,
    item_type         VARCHAR(20) NOT NULL CHECK (item_type IN ('album','artist')),
    item_id           INTEGER NOT NULL,
    item_name         VARCHAR(255) NOT NULL,
    image_url         VARCHAR(500),
    owner_user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    familiarity_tier  VARCHAR(20) NOT NULL CHECK (familiarity_tier IN ('core','regular','deep_cut')),
    base_points       INT NOT NULL,
    distractor_names  TEXT[] NOT NULL DEFAULT '{}',
    CONSTRAINT uq_arena_pool_round UNIQUE (pool_id, round_number)
);
CREATE INDEX IF NOT EXISTS idx_arena_pool_rounds_pool ON arena_pool_rounds(pool_id);

CREATE TABLE IF NOT EXISTS arena_sessions (
    id                     BIGSERIAL PRIMARY KEY,
    pool_id                BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    user_id                INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status                 VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','abandoned')),
    current_round          INT NOT NULL DEFAULT 1,
    hints_used             INT NOT NULL DEFAULT 0,
    total_score            INT NOT NULL DEFAULT 0,
    correct_count          INT NOT NULL DEFAULT 0,
    best_round_score       INT NOT NULL DEFAULT 0,
    perfect_bonus_applied  BOOLEAN NOT NULL DEFAULT FALSE,
    started_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at           TIMESTAMPTZ,
    CONSTRAINT uq_arena_session UNIQUE (pool_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_user ON arena_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_arena_sessions_pool ON arena_sessions(pool_id);

CREATE TABLE IF NOT EXISTS arena_round_answers (
    id                    BIGSERIAL PRIMARY KEY,
    session_id            BIGINT NOT NULL REFERENCES arena_sessions(id) ON DELETE CASCADE,
    round_number          INT NOT NULL,
    used_hint             BOOLEAN NOT NULL DEFAULT FALSE,
    is_correct            BOOLEAN NOT NULL DEFAULT FALSE,
    time_taken_ms         INT,
    speed_multiplier      NUMERIC(3,2),
    ownership_multiplier  NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    points_earned         INT NOT NULL DEFAULT 0,
    answered_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_arena_round_answer UNIQUE (session_id, round_number)
);
CREATE INDEX IF NOT EXISTS idx_arena_round_answers_session ON arena_round_answers(session_id);
"""

def init_arena_module(get_engine, run_query, run_write_query,
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
    # Pool building
    # ─────────────────────────────────────────────────────────────────

    def _eligible_pool(user_id: int, game_type: str) -> pd.DataFrame:
        if game_type == "cover":
            df = run_query("""
                SELECT al.id AS item_id, al.title AS item_name, MAX(so.image_url) AS image_url,
                       COUNT(s.id) AS stream_count
                FROM streams s
                JOIN songs so ON so.id = s.song_id
                JOIN albums al ON al.id = so.album_id
                WHERE s.user_id = :uid AND so.image_url IS NOT NULL
                GROUP BY al.id, al.title
                HAVING COUNT(s.id) >= 10
                ORDER BY stream_count DESC
            """, {"uid": user_id})
        else:
            df = run_query("""
                SELECT a.id AS item_id, a.name AS item_name, a.image_url AS image_url,
                       COUNT(s.id) AS stream_count
                FROM streams s
                JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE s.user_id = :uid AND a.image_url IS NOT NULL
                GROUP BY a.id, a.name, a.image_url
                HAVING COUNT(s.id) >= 10
                ORDER BY stream_count DESC
            """, {"uid": user_id})

        if df.empty:
            df["tier"] = []
            return df

        n = len(df)
        tiers = []
        for i in range(n):
            pct = i / n
            if pct < 0.20:
                tiers.append("core")
            elif pct < 0.70:
                tiers.append("regular")
            else:
                tiers.append("deep_cut")
        df = df.reset_index(drop=True)
        df["tier"] = tiers
        return df

    def is_arena_eligible(user_id: int) -> dict:
        out = {}
        for gt in ("cover", "artist"):
            pool = _eligible_pool(user_id, gt)
            out[gt] = len(pool) >= ELIGIBILITY_FLOOR
        return out

    def _stratified_sample(pool: pd.DataFrame, n: int) -> list[dict]:
        if pool.empty: return []
        by_tier = {t: pool[pool["tier"] == t] for t in ("core", "regular", "deep_cut")}
        targets = {t: round(n * frac) for t, frac in TIER_TARGET_FRAC.items()}
        diff = n - sum(targets.values())
        targets["regular"] += diff

        chosen_ids = set()
        chosen = []
        for t, want in targets.items():
            avail = by_tier[t][~by_tier[t]["item_id"].isin(chosen_ids)]
            take = min(want, len(avail))
            picked = avail.sample(n=take, random_state=None) if take > 0 else avail.iloc[0:0]
            for _, row in picked.iterrows():
                chosen.append(row.to_dict())
                chosen_ids.add(row["item_id"])

        if len(chosen) < n:
            remaining = pool[~pool["item_id"].isin(chosen_ids)]
            take = min(n - len(chosen), len(remaining))
            if take > 0:
                picked = remaining.sample(n=take, random_state=None)
                for _, row in picked.iterrows():
                    chosen.append(row.to_dict())
                    chosen_ids.add(row["item_id"])

        random.shuffle(chosen)
        return chosen[:n]

    def _pick_distractors(pool: pd.DataFrame, correct_id, correct_tier: str, k: int = 3) -> list[str]:
        same_tier = pool[(pool["tier"] == correct_tier) & (pool["item_id"] != correct_id)]
        pick_from = same_tier if len(same_tier) >= k else pool[pool["item_id"] != correct_id]
        if pick_from.empty: return []
        take = min(k, len(pick_from))
        return pick_from.sample(n=take, random_state=None)["item_name"].tolist()

    def create_pool(host_user_id: int, game_type: str, round_count: int,
                     mode: str, friend_user_id: int | None = None,
                     difficulty: str = "hard") -> int:
        if difficulty not in ("easy", "hard"):
            difficulty = "hard"
        hint_budget = HINT_BUDGET[round_count]
        host_pool = _eligible_pool(host_user_id, game_type)

        if mode == "friends" and friend_user_id:
            friend_pool = _eligible_pool(friend_user_id, game_type)
            n_host = round_count // 2
            n_friend = round_count - n_host
            host_items = _stratified_sample(host_pool, n_host)
            friend_items = _stratified_sample(friend_pool, n_friend)
            for it in host_items:
                it["owner_user_id"] = host_user_id
                it["_pool"] = host_pool
            for it in friend_items:
                it["owner_user_id"] = friend_user_id
                it["_pool"] = friend_pool
            chosen = host_items + friend_items
            random.shuffle(chosen)
        else:
            chosen = _stratified_sample(host_pool, round_count)
            for it in chosen:
                it["owner_user_id"] = host_user_id
                it["_pool"] = host_pool

        rows = run_write_query("""
            INSERT INTO arena_pools (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id)
            VALUES (:mode, :game_type, :round_count, :difficulty, :hint_budget, :host_user_id, :friend_user_id)
            RETURNING id
        """, dict(mode=mode, game_type=game_type, round_count=round_count, difficulty=difficulty,
                  hint_budget=hint_budget, host_user_id=host_user_id, friend_user_id=friend_user_id))
        pool_id = rows[0]["id"]

        item_type = "album" if game_type == "cover" else "artist"
        for i, item in enumerate(chosen, start=1):
            distractors = _pick_distractors(item["_pool"], item["item_id"], item["tier"])
            run_write_query("""
                INSERT INTO arena_pool_rounds
                    (pool_id, round_number, item_type, item_id, item_name, image_url,
                     owner_user_id, familiarity_tier, base_points, distractor_names)
                VALUES (:pool_id, :round_number, :item_type, :item_id, :item_name, :image_url,
                        :owner_user_id, :tier, :base_points, :distractors)
            """, dict(pool_id=pool_id, round_number=i, item_type=item_type,
                      item_id=int(item["item_id"]), item_name=item["item_name"], image_url=item["image_url"],
                      owner_user_id=item["owner_user_id"], tier=item["tier"],
                      base_points=TIER_BASE_POINTS[item["tier"]], distractors=distractors))
        return pool_id

    # ─────────────────────────────────────────────────────────────────
    # Sessions / rounds
    # ─────────────────────────────────────────────────────────────────

    def get_pool(pool_id: int) -> dict | None:
        rows = run_write_query("SELECT * FROM arena_pools WHERE id = :id", {"id": pool_id})
        return dict(rows[0]) if rows else None

    def get_or_create_session(pool_id: int, user_id: int) -> dict:
        rows = run_write_query("SELECT * FROM arena_sessions WHERE pool_id=:p AND user_id=:u", {"p": pool_id, "u": user_id})
        if rows: return dict(rows[0])
        rows = run_write_query("""
            INSERT INTO arena_sessions (pool_id, user_id) VALUES (:p, :u) RETURNING id
        """, {"p": pool_id, "u": user_id})
        new_id = rows[0]["id"]
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": new_id})
        return dict(rows[0])

    def get_round(pool_id: int, round_number: int) -> dict | None:
        rows = run_write_query("""
            SELECT * FROM arena_pool_rounds WHERE pool_id=:p AND round_number=:rn
        """, {"p": pool_id, "rn": round_number})
        return dict(rows[0]) if rows else None

    def _score_answer(pool: dict, round_row: dict, session_user_id: int,
                       is_correct: bool, used_hint: bool, time_taken_ms: int):
        if not is_correct: return 0.0, 1.0, 0
        frac = min(max(time_taken_ms / (REVEAL_SECONDS * 1000), 0.0), 1.0)
        if frac <= 0.25: speed_mult = 2.0
        elif frac <= 0.50: speed_mult = 1.5
        elif frac <= 0.75: speed_mult = 1.0
        else: speed_mult = 0.5
        if used_hint: speed_mult = min(speed_mult, 1.0)
        owner_mult = 1.3 if (pool["mode"] == "friends" and round_row["owner_user_id"] != session_user_id) else 1.0
        difficulty_mult = EASY_SCORE_MULTIPLIER if pool.get("difficulty") == "easy" else 1.0
        points = round(round_row["base_points"] * speed_mult * owner_mult * difficulty_mult)
        return speed_mult, owner_mult, points

    def submit_round_answer(session: dict, pool: dict, round_row: dict,
                             is_correct: bool, used_hint: bool, time_taken_ms: int) -> int:
        speed_mult, owner_mult, points = _score_answer(
            pool, round_row, session["user_id"], is_correct, used_hint, time_taken_ms
        )
        
        existing = run_write_query("SELECT id FROM arena_round_answers WHERE session_id=:sid AND round_number=:rn", 
                                   {"sid": session["id"], "rn": round_row["round_number"]})
        if existing:
            return 0
            
        run_write_query("""
            INSERT INTO arena_round_answers
              (session_id, round_number, used_hint, is_correct, time_taken_ms,
               speed_multiplier, ownership_multiplier, points_earned)
            VALUES (:sid, :rn, :hint, :correct, :tms, :sm, :om, :pts)
            ON CONFLICT (session_id, round_number) DO NOTHING
        """, dict(sid=session["id"], rn=round_row["round_number"], hint=used_hint,
                  correct=is_correct, tms=time_taken_ms, sm=speed_mult, om=owner_mult, pts=points))
                  
        run_write_query("""
            UPDATE arena_sessions SET
              hints_used = hints_used + :hint_inc,
              total_score = total_score + :pts,
              correct_count = correct_count + :correct_inc,
              best_round_score = GREATEST(best_round_score, :pts),
              current_round = current_round + 1
            WHERE id = :sid
        """, dict(hint_inc=1 if used_hint else 0, pts=points,
                  correct_inc=1 if is_correct else 0, sid=session["id"]))
        return points

    def finalize_session(session_id: int):
        rows = run_write_query("""
            SELECT s.*, p.round_count, p.mode FROM arena_sessions s
            JOIN arena_pools p ON p.id = s.pool_id WHERE s.id = :id
        """, {"id": session_id})
        if not rows: return
        row = dict(rows[0])
        perfect = bool(row["hints_used"] == 0 and row["correct_count"] == row["round_count"])
        final_score = int(row["total_score"] * 1.2) if perfect else int(row["total_score"])
        run_write_query("""
            UPDATE arena_sessions SET status='completed', completed_at=now(),
              perfect_bonus_applied=:perfect, total_score=:score
            WHERE id=:id
        """, dict(perfect=perfect, score=final_score, id=session_id))

    def get_recap(session_id: int) -> dict:
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id = :id", {"id": session_id})
        session = dict(rows[0])
        pool = get_pool(int(session["pool_id"]))
        recap = dict(session=session, pool=pool, duel=None)
        
        if pool["mode"] == "friends":
            other_user_id = pool["friend_user_id"] if session["user_id"] == pool["host_user_id"] else pool["host_user_id"]
            other_rows = run_write_query("SELECT * FROM arena_sessions WHERE pool_id=:p AND user_id=:u",
                                         {"p": pool["id"], "u": other_user_id})
            if other_rows and other_rows[0]["status"] == "completed":
                cross = run_write_query("""
                    SELECT r.owner_user_id, a.session_id, a.is_correct
                    FROM arena_round_answers a
                    JOIN arena_pool_rounds r ON r.pool_id = :p AND r.round_number = a.round_number
                    WHERE a.session_id IN (:s1, :s2)
                """, {"p": pool["id"], "s1": session["id"], "s2": int(other_rows[0]["id"])})
                
                cross = cross or []
                my_items_friend_got = sum(1 for c in cross if c["session_id"] == other_rows[0]["id"] and c["owner_user_id"] == session["user_id"] and c["is_correct"])
                their_items_i_got = sum(1 for c in cross if c["session_id"] == session["id"] and c["owner_user_id"] == other_user_id and c["is_correct"])
                
                recap["duel"] = dict(
                    other_session=dict(other_rows[0]),
                    my_items_friend_got=my_items_friend_got,
                    their_items_i_got=their_items_i_got,
                )
        return recap

    # ─────────────────────────────────────────────────────────────────
    # Free-text matching
    # ─────────────────────────────────────────────────────────────────

    def _answer_matches(guess: str, correct: str) -> bool:
        g, c = guess.strip().lower(), correct.strip().lower()
        if not g: return False
        if g == c: return True
        return difflib.SequenceMatcher(None, g, c).ratio() >= FUZZY_MATCH_THRESHOLD

    # ─────────────────────────────────────────────────────────────────
    # JS: hidden-input pattern for timeout + MC tile clicks
    # ─────────────────────────────────────────────────────────────────

    def inject_arena_script():
        components.html("""
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.__arenaDelegated) return;
            doc.__arenaDelegated = true;

            function fire(inputSelector, value) {
                function trySubmit(retries) {
                    const input = doc.querySelector(inputSelector);
                    if (!input) {
                        if (retries > 0) setTimeout(function() { trySubmit(retries - 1); }, 60);
                        return;
                    }
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, value);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.focus({ preventScroll: true });
                    setTimeout(function() {
                        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                        input.blur();
                    }, 30);
                }
                trySubmit(5);
            }

            doc.addEventListener('click', function(e) {
                const opt = e.target.closest('.arena-mc-option');
                if (opt) {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = opt.dataset.idx;
                    fire('input[aria-label="arena_mc_input"]', idx + ':' + Date.now());
                }
            });
        })();
        </script>
        """, height=0)

    def render_round_timer_script(round_key: str, started_at_ms: float):
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const startedAt = {started_at_ms};
            const durationMs = {REVEAL_SECONDS * 1000};
            const roundKey = {json.dumps(round_key)};
            if (doc.__arenaRoundKey === roundKey) return;
            doc.__arenaRoundKey = roundKey;
            doc.__arenaTimedOut = false;
            if (doc.__arenaInterval) clearInterval(doc.__arenaInterval);

            function fireTimeout() {{
                function trySubmit(retries) {{
                    const inp = doc.querySelector('input[aria-label="arena_timeout_input"]');
                    if (!inp) {{ if (retries > 0) setTimeout(function(){{ trySubmit(retries - 1); }}, 80); return; }}
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                    setter.call(inp, roundKey + ':' + Date.now());
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    inp.focus({{ preventScroll: true }}); // <--- ΔΙΟΡΘΩΣΗ: Προστέθηκε Focus
                    setTimeout(function() {{
                        inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.blur(); // <--- ΔΙΟΡΘΩΣΗ: Προστέθηκε Blur
                    }}, 30);
                }}
                trySubmit(5);
            }}

            function tick() {{
                const now = Date.now();
                const frac = Math.min((now - startedAt) / durationMs, 1);
                const bar = doc.getElementById('arena-progress-bar');
                const img = doc.getElementById('arena-reveal-img');
                if (bar) bar.style.width = ((1 - frac) * 100) + '%';
                if (img) img.style.filter = 'blur(' + (22 * (1 - frac)) + 'px)';
                if (frac >= 1 && !doc.__arenaTimedOut) {{
                    doc.__arenaTimedOut = true;
                    clearInterval(doc.__arenaInterval);
                    fireTimeout();
                }}
            }}
            doc.__arenaInterval = setInterval(tick, 150);
            tick();
        }})();
        </script>
        """, height=0)

    def render_reveal_continue_script(round_key: str, delay_ms: int = 1400):
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const key = {json.dumps("reveal_" + round_key)};
            if (doc.__arenaRevealKey === key) return;
            doc.__arenaRevealKey = key;

            function fireContinue() {{
                function trySubmit(retries) {{
                    const inp = doc.querySelector('input[aria-label="arena_reveal_continue_input"]');
                    if (!inp) {{ if (retries > 0) setTimeout(function(){{ trySubmit(retries - 1); }}, 80); return; }}
                    const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                    setter.call(inp, key + ':' + Date.now());
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    inp.focus({{ preventScroll: true }}); // <--- ΔΙΟΡΘΩΣΗ: Προστέθηκε Focus
                    setTimeout(function() {{
                        inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                        inp.blur(); // <--- ΔΙΟΡΘΩΣΗ: Προστέθηκε Blur
                    }}, 30);
                }}
                trySubmit(5);
            }}
            setTimeout(fireContinue, {delay_ms});
        }})();
        </script>
        """, height=0)

    # ─────────────────────────────────────────────────────────────────
    # Hidden-input workers
    # ─────────────────────────────────────────────────────────────────

    def arena_hidden_worker():
        def _current_context():
            pool_id = st.session_state.get("arena_pool_id")
            session_id = st.session_state.get("arena_session_id")
            if not pool_id or not session_id: return None
            pool = get_pool(pool_id)
            rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
            if not rows: return None
            session = dict(rows[0])
            round_row = get_round(pool_id, session["current_round"])
            return pool, session, round_row

        def _resolve(is_correct: bool, used_hint: bool, time_taken_ms: int,
                     advance_view: bool = True, ctx=None):
            if ctx is None:
                ctx = _current_context()
            if not ctx: return None
            pool, session, round_row = ctx
            if round_row is None: return None
            points = submit_round_answer(session, pool, round_row, is_correct, used_hint, time_taken_ms)
            st.session_state["_arena_last_points"] = points
            st.session_state["_arena_last_correct"] = is_correct
            is_last = session["current_round"] >= pool["round_count"]
            if is_last:
                finalize_session(session["id"])
                if advance_view:
                    st.query_params["arena_view"] = "recap"
            return points, is_last

        def on_timeout():
            val = st.session_state.get("arena_timeout_state")
            if not val: return
            ctx = _current_context()
            pool = ctx[0] if ctx else None
            if pool and pool.get("difficulty") == "easy":
                hint_active = False
            else:
                hint_active = st.session_state.get(
                    f"arena_hint_{st.session_state.get('arena_session_id')}_"
                    f"{st.session_state.get('arena_round_no', 1)}", False
                )
            _resolve(is_correct=False, used_hint=hint_active, time_taken_ms=REVEAL_SECONDS * 1000)

        st.text_input("arena_timeout_input", key="arena_timeout_state",
                       label_visibility="collapsed", on_change=on_timeout)

        def on_mc_click():
            val = st.session_state.get("arena_mc_state")
            if not val: return
            parts = val.split(":")
            if len(parts) < 2: return
            idx = int(parts[0])
            ctx = _current_context()
            if not ctx: return
            pool, session, round_row = ctx
            if round_row is None: return
            options = st.session_state.get("_arena_mc_options", [])
            correct_name = round_row["item_name"]
            is_correct = 0 <= idx < len(options) and options[idx] == correct_name
            start_key = f"arena_round_start_{session['id']}_{session['current_round']}"
            started_at = st.session_state.get(start_key, time.time())
            elapsed_ms = int((time.time() - started_at) * 1000)
            # In hard mode, multiple-choice is only reachable via a spent hint.
            # In easy mode, multiple-choice IS the base mode, so it's not a "hint".
            used_hint = pool.get("difficulty") != "easy"
            round_key = f"{session['id']}_{session['current_round']}"
            result = _resolve(is_correct=is_correct, used_hint=used_hint, time_taken_ms=elapsed_ms,
                               advance_view=False, ctx=(pool, session, round_row))
            if result is None: return
            points, is_last = result
            # Hold on this round one extra beat so the player sees right/wrong before advancing.
            st.session_state["_arena_mc_reveal"] = dict(
                round_key=round_key, options=options, chosen_idx=idx,
                correct_name=correct_name, is_correct=is_correct,
                points=points, is_last=is_last,
            )

        def on_reveal_continue():
            val = st.session_state.get("arena_reveal_continue_state")
            if not val: return
            reveal = st.session_state.pop("_arena_mc_reveal", None)
            if reveal and reveal.get("is_last"):
                st.query_params["arena_view"] = "recap"

        st.text_input("arena_reveal_continue_input", key="arena_reveal_continue_state",
                       label_visibility="collapsed", on_change=on_reveal_continue)

        st.text_input("arena_mc_input", key="arena_mc_state",
                       label_visibility="collapsed", on_change=on_mc_click)

    # ─────────────────────────────────────────────────────────────────
    # UI & CSS
    # ─────────────────────────────────────────────────────────────────

    _MODAL_CSS = f"""
    <style>
    body:has(.st-key-arena_modal_overlay) .stApp > div,
    body:has(.st-key-arena_modal_overlay) section.main > div.block-container,
    body:has(.st-key-arena_modal_overlay) [data-testid="stVerticalBlock"] > div,
    body:has(.st-key-arena_modal_overlay) div.element-container {{
        transform: none !important;
        animation: none !important;
        filter: none !important;
        perspective: none !important;
        will-change: auto !important;
    }}

    div.element-container:has(.st-key-arena_modal_overlay) {{
        position: fixed !important;
        top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
        width: 100vw !important; height: 100vh !important;
        z-index: 999999 !important;
    }}

    div.st-key-arena_modal_overlay {{
        position: fixed !important;
        top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
        width: 100vw !important; height: 100vh !important;
        background: rgba(0, 0, 0, 0.85) !important;
        backdrop-filter: blur(8px) !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        margin: 0 !important;
        z-index: 999999 !important;
    }}

    @keyframes arenaModalIn {{
        from {{ opacity: 0; transform: translateY(18px) scale(0.97); }}
        to   {{ opacity: 1; transform: translateY(0) scale(1); }}
    }}
    @keyframes arenaGlowPulse {{
        0%, 100% {{ opacity: 0.55; }}
        50%      {{ opacity: 1; }}
    }}

    div.st-key-arena_modal_content {{
        position: relative !important;
        background:
            radial-gradient(circle at 18% -12%, {GREEN}26 0%, transparent 42%),
            linear-gradient(165deg, {CARD} 0%, #0b0b0d 130%) !important;
        border: 1px solid {BORDER} !important;
        border-radius: 22px !important;
        padding: 2.6rem 2.5rem 2.5rem !important;
        max-width: 550px !important;
        width: 90% !important;
        max-height: 85vh !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        box-shadow: 0 30px 70px -12px rgba(0, 0, 0, 1.0), inset 0 1px 0 rgba(255,255,255,0.04) !important;
        z-index: 9999999 !important;
        margin: auto !important;
        animation: arenaModalIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) both !important;
    }}
    div.st-key-arena_modal_content::before {{
        content: '';
        position: absolute;
        top: 0; left: 12%; right: 12%;
        height: 3px;
        border-radius: 0 0 8px 8px;
        background: linear-gradient(90deg, transparent 0%, {GREEN} 50%, transparent 100%);
        animation: arenaGlowPulse 2.6s ease-in-out infinite;
    }}

    .arena-kicker-wrap {{ text-align: center; margin-bottom: 0.9rem; }}
    .arena-kicker {{
        display: inline-block;
        font-size: 0.66rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: {GREEN};
        background: rgba(29,185,84,0.10);
        border: 1px solid rgba(29,185,84,0.32);
        padding: 5px 14px;
        border-radius: 999px;
    }}

    .arena-title {{ font-size: 1.8rem; font-weight: 800; color: {TEXT}; margin-bottom: 0.25rem; text-align: center; }}
    .arena-subtitle {{ font-size: 0.95rem; color: {TEXT_MID}; margin-bottom: 2rem; text-align: center; }}
    .arena-progress-track {{ width: 100%; height: 6px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; margin-bottom: 1rem; }}
    .arena-progress-bar {{ height: 100%; width: 100%; background: {GREEN}; transition: width 0.15s linear; }}
    .arena-reveal-frame {{ width: 100%; aspect-ratio: 1; max-width: 280px; margin: 0 auto 1.5rem; border-radius: 16px; overflow: hidden; background: {BG}; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
    .arena-reveal-frame img {{ width: 100%; height: 100%; object-fit: cover; transition: filter 0.15s linear; }}
    .arena-mc-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin: 1rem 0 1.6rem; }}
    .arena-mc-option {{
        background: rgba(255,255,255,0.05); border: 1px solid {BORDER}; border-radius: 12px;
        padding: 1rem; text-align: center; font-weight: 600; color: {TEXT}; cursor: pointer;
        transition: all 0.15s ease;
    }}
    .arena-mc-option:hover {{ border-color: {GREEN}; background: rgba(29,185,84,0.12); transform: translateY(-2px); }}

    /* ΝΕΟ: οθόνη αποκάλυψης απάντησης (σωστό/λάθος) */
    .arena-reveal-msg {{
        text-align: center; font-weight: 700; font-size: 1.05rem;
        padding: 0.7rem 1rem; border-radius: 12px; margin-bottom: 1.1rem;
        animation: arenaModalIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) both;
    }}
    .arena-reveal-correct {{ background: rgba(29,185,84,0.14); color: {GREEN}; border: 1px solid rgba(29,185,84,0.4); }}
    .arena-reveal-wrong {{ background: rgba(239,68,68,0.12); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }}
    .arena-reveal-option {{
        background: rgba(255,255,255,0.05); border: 1px solid {BORDER}; border-radius: 12px;
        padding: 1rem; text-align: center; font-weight: 600; color: {TEXT}; cursor: default;
        transition: all 0.2s ease;
    }}
    .arena-reveal-correct-tile {{ background: rgba(29,185,84,0.18) !important; border-color: {GREEN} !important; color: {GREEN} !important; }}
    .arena-reveal-wrong-tile {{ background: rgba(239,68,68,0.16) !important; border-color: #ef4444 !important; color: #f87171 !important; }}

    /* ΝΕΟ: Κεντραρισμένο κείμενο στο input πεδίο */
    div.st-key-arena_modal_content div[data-testid="stTextInput"] input {{
        text-align: center !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        padding: 1rem !important;
    }}

    /* ΝΕΟ: Segmented-control labels/spacing (αντικατάσταση των st.radio) */
    .arena-segment-label {{
        font-size: 0.78rem;
        font-weight: 700;
        color: {TEXT_DIM};
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 0 0 0.6rem 2px;
    }}
    .arena-segment-caption {{
        font-size: 0.85rem;
        color: {TEXT_MID};
        text-align: left;
        margin: 0.5rem 0 0 2px;
    }}
    div.st-key-arena_modal_content div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button {{
        border-radius: 10px !important;
        font-weight: 700 !important;
        transition: all 0.15s ease !important;
    }}
    div.st-key-arena_modal_content div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button:hover {{
        transform: translateY(-1px);
    }}

    /* ΝΕΟ: κυκλικό, "αιωρούμενο" κουμπί κλεισίματος πάνω-δεξιά αντί για ολόκληρη σειρά */
    div.st-key-arena_close_btn {{
        position: absolute !important;
        top: 1.15rem !important;
        right: 1.15rem !important;
        width: auto !important;
        z-index: 30 !important;
    }}
    div.st-key-arena_close_btn button {{
        width: 34px !important;
        height: 34px !important;
        min-width: 34px !important;
        padding: 0 !important;
        border-radius: 50% !important;
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid {BORDER} !important;
        color: {TEXT_MID} !important;
        font-size: 0.85rem !important;
        transition: all 0.2s ease !important;
    }}
    div.st-key-arena_close_btn button:hover {{
        background: rgba(255,255,255,0.14) !important;
        color: {TEXT} !important;
        transform: rotate(90deg) !important;
    }}

    body:has(.st-key-arena_modal_overlay) {{ overflow: hidden !important; }}
    </style>
    """

    def _close_arena():
        st.query_params.pop("arena", None)
        st.query_params.pop("arena_view", None)
        for k in list(st.session_state.keys()):
            if k.startswith("arena_") or k.startswith("_arena_"):
                del st.session_state[k]
        st.rerun()

    def render_modal(selected_user_id: int, user_dict: dict):
        if st.query_params.get("arena") != "1":
            return

        st.markdown(_MODAL_CSS, unsafe_allow_html=True)
        view = st.query_params.get("arena_view", "mode")

        with st.container(key="arena_modal_overlay"):
            with st.container(key="arena_modal_content"):

                # Κουμπί κλεισίματος — αιωρούμενο πάνω-δεξιά (θέση μέσω CSS)
                if st.button("✕", key="arena_close_btn"):
                    _close_arena()

                # Περιεχόμενο
                if view == "mode":
                    _render_mode_select(selected_user_id)
                elif view == "game":
                    _render_game_select(selected_user_id)
                elif view == "rounds":
                    _render_rounds_select(selected_user_id, user_dict)
                elif view == "play":
                    _render_gameplay(selected_user_id)
                elif view == "recap":
                    _render_recap(selected_user_id)

    def _modal_header(kicker: str, title: str, subtitle: str | None = None):
        sub_html = f'<div class="arena-subtitle">{subtitle}</div>' if subtitle else ""
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{kicker}</span></div>'
            f'<div class="arena-title">{title}</div>'
            f'{sub_html}',
            unsafe_allow_html=True
        )

    def _render_mode_select(user_id: int):
        _modal_header("🎧 Suggestify", "🕹️ Arena",
                      "Guessing games built from your own listening history.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎮 Single player", key="arena_mode_solo", use_container_width=True):
                st.session_state["arena_mode"] = "solo"
                st.query_params["arena_view"] = "game"
                st.rerun()
        with c2:
            if st.button("🤝 Play with friends", key="arena_mode_friends", use_container_width=True):
                st.session_state["arena_mode"] = "friends"
                st.query_params["arena_view"] = "game"
                st.rerun()

    def _render_game_select(user_id: int):
        _modal_header("🎧 Suggestify", "Choose a game")
        eligible = is_arena_eligible(user_id)
        for game_type, meta in GAME_META.items():
            ok = eligible.get(game_type, False)
            with st.container():
                cols = st.columns([4, 1])
                cols[0].markdown(
                    f"**{meta['icon']} {meta['label']}**  \n"
                    f"<span style='color:{TEXT_MID};font-size:0.85rem;'>{meta['desc']}</span>",
                    unsafe_allow_html=True
                )
                disabled = not ok
                if cols[1].button("Play" if ok else "Not enough data", key=f"arena_game_{game_type}", disabled=disabled):
                    st.session_state["arena_game_type"] = game_type
                    st.query_params["arena_view"] = "rounds"
                    st.rerun()

    def _segment_control(label: str, options: list[tuple], state_key: str, default,
                          accent_colors: dict | None = None):
        """Renders a row of toggle buttons standing in for a radio group.
        options: list of (value, display_label) tuples.
        accent_colors: optional {value: hex_color} for the selected state — falls back to GREEN."""
        if state_key not in st.session_state:
            st.session_state[state_key] = default
        accent_colors = accent_colors or {}
        st.markdown(f'<div class="arena-segment-label">{escape(label)}</div>', unsafe_allow_html=True)
        cols = st.columns(len(options))
        selected_css = ""
        for col, (value, disp) in zip(cols, options):
            btn_key = f"{state_key}_opt_{value}"
            selected = st.session_state[state_key] == value
            if selected:
                color = accent_colors.get(value, GREEN)
                selected_css += f"""
                div.st-key-{btn_key} button {{
                    background: linear-gradient(135deg, {color} 0%, {color}cc 100%) !important;
                    border-color: {color} !important;
                    color: #05130a !important;
                    box-shadow: 0 6px 18px {color}4d !important;
                }}
                """
            with col:
                if st.button(disp, key=btn_key, type="secondary", use_container_width=True):
                    st.session_state[state_key] = value
                    st.rerun()
        if selected_css:
            st.markdown(f"<style>{selected_css}</style>", unsafe_allow_html=True)
        return st.session_state[state_key]

    def _render_rounds_select(user_id: int, user_dict: dict):
        game_type = st.session_state.get("arena_game_type", "cover")
        meta = GAME_META.get(game_type, GAME_META["cover"])
        _modal_header(f'{meta["icon"]} {meta["label"]}', "Set up your match")
        mode = st.session_state.get("arena_mode", "solo")
        friend_user_id = None

        if mode == "friends":
            other_usernames = [u for u in user_dict.keys() if user_dict[u] != user_id]
            if not other_usernames:
                st.info("No other users to duel yet.")
                return
            friend_username = st.selectbox("Duel who?", other_usernames, key="arena_friend_select")
            friend_user_id = user_dict[friend_username]

        round_count = _segment_control(
            "How many rounds?",
            [(5, "5"), (10, "10"), (20, "20")],
            "arena_round_count_seg", 10,
        )

        st.markdown("<div style='height:1.4rem;'></div>", unsafe_allow_html=True)

        difficulty = _segment_control(
            "Difficulty",
            [("easy", "🟢 Easy"), ("hard", "🔴 Hard")],
            "arena_difficulty_seg", "hard",
            accent_colors={"easy": GREEN, "hard": "#ef4444"},
        )
        caption = ("Always 4 multiple-choice options — no typing required."
                   if difficulty == "easy" else
                   "Type the exact name. Stuck? Spend a hint to reveal 4 options.")
        st.markdown(f'<div class="arena-segment-caption">{caption}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Start Game", key="arena_start_btn", type="primary", use_container_width=True):
            game_type = st.session_state["arena_game_type"]
            pool_id = create_pool(user_id, game_type, round_count, mode, friend_user_id, difficulty)
            session = get_or_create_session(pool_id, user_id)
            st.session_state["arena_pool_id"] = pool_id
            st.session_state["arena_session_id"] = session["id"]
            st.query_params["arena_view"] = "play"
            st.rerun()

    def _render_mc_reveal(pool: dict, session: dict, reveal: dict):
        answered_round_no = session["current_round"] - 1
        round_row = get_round(pool["id"], answered_round_no)
        game_meta = GAME_META.get(pool.get("game_type"), GAME_META["cover"])

        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">Round {answered_round_no} <span style="font-size: 1.2rem; color: {TEXT_DIM};">/ {pool["round_count"]}</span></div>',
            unsafe_allow_html=True
        )

        if reveal["is_correct"]:
            st.markdown(
                f'<div class="arena-reveal-msg arena-reveal-correct">✅ Correct! +{reveal.get("points", 0)} pts</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="arena-reveal-msg arena-reveal-wrong">❌ Not quite — it was <b>{escape(reveal["correct_name"])}</b></div>',
                unsafe_allow_html=True
            )

        if round_row:
            st.markdown(
                f'<div class="arena-reveal-frame"><img src="{escape(round_row["image_url"] or "")}" /></div>',
                unsafe_allow_html=True
            )

        opts_html = ""
        for i, o in enumerate(reveal["options"]):
            cls = "arena-reveal-option"
            if o == reveal["correct_name"]:
                cls += " arena-reveal-correct-tile"
            elif i == reveal["chosen_idx"]:
                cls += " arena-reveal-wrong-tile"
            opts_html += f'<div class="{cls}">{escape(o)}</div>'
        st.markdown(f'<div class="arena-mc-grid">{opts_html}</div>', unsafe_allow_html=True)

        render_reveal_continue_script(reveal["round_key"])

    def _render_gameplay(user_id: int):
        pool_id = st.session_state.get("arena_pool_id")
        session_id = st.session_state.get("arena_session_id")
        if not pool_id or not session_id:
            st.query_params["arena_view"] = "mode"
            st.rerun()
            return

        pool = get_pool(pool_id)
        
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
        session = dict(rows[0])

        # A multiple-choice answer was just submitted — show right/wrong before moving on.
        reveal = st.session_state.get("_arena_mc_reveal")
        if reveal and reveal.get("round_key") == f"{session_id}_{session['current_round'] - 1}":
            _render_mc_reveal(pool, session, reveal)
            return

        if session["current_round"] > pool["round_count"]:
            finalize_session(session_id)
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        round_row = get_round(pool_id, session["current_round"])
        st.session_state["arena_round_no"] = session["current_round"]

        hint_budget = pool["hint_budget"]
        hints_used = session["hints_used"]
        easy_mode = pool.get("difficulty") == "easy"

        if easy_mode:
            subtitle = f'Score: <b>{session["total_score"]}</b>'
        else:
            subtitle = (f'Score: <b>{session["total_score"]}</b> &nbsp;·&nbsp; '
                        f'Hints left: <b>{hint_budget - hints_used}</b>')

        game_meta = GAME_META.get(pool.get("game_type"), GAME_META["cover"])
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">Round {session["current_round"]} <span style="font-size: 1.2rem; color: {TEXT_DIM};">/ {pool["round_count"]}</span></div>'
            f'<div class="arena-subtitle">{subtitle}</div>',
            unsafe_allow_html=True
        )

        start_key = f"arena_round_start_{session_id}_{session['current_round']}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown(f'''
        <div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>
        <div class="arena-reveal-frame"><img id="arena-reveal-img" src="{escape(round_row["image_url"] or "")}" /></div>
        ''', unsafe_allow_html=True)

        round_key = f"{session_id}_{session['current_round']}"
        render_round_timer_script(round_key, started_at * 1000)

        hint_key = f"arena_hint_{session_id}_{session['current_round']}"
        hint_active = st.session_state.get(hint_key, False)
        show_mc = easy_mode or hint_active

        if not show_mc:
            guess = st.text_input("Your guess", key=f"arena_guess_{round_key}", label_visibility="collapsed",
                                   placeholder="Type the exact name…")
            
            # Δυναμικό κεντραρισμένο layout για τα κουμπιά
            cols = st.columns(3) if hints_used < hint_budget else st.columns(2)
            
            with cols[0]:
                if st.button("Submit", key=f"arena_submit_{round_key}", type="primary", use_container_width=True):
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    is_correct = _answer_matches(guess, round_row["item_name"])
                    
                    if is_correct:
                        points = submit_round_answer(session, pool, round_row, True, False, elapsed_ms)
                        st.toast(f"+{points} pts ✅", icon="🎯")
                        if session["current_round"] >= pool["round_count"]:
                            finalize_session(session_id)
                            st.query_params["arena_view"] = "recap"
                        st.rerun()
                    else:
                        st.toast("Not quite — try again!", icon="❌")
                        
            with cols[1]:
                if st.button("⏭️ Pass", key=f"arena_pass_{round_key}", use_container_width=True):
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    points = submit_round_answer(session, pool, round_row, False, False, elapsed_ms)
                    st.toast("Round Skipped!", icon="⏭️")
                    if session["current_round"] >= pool["round_count"]:
                        finalize_session(session_id)
                        st.query_params["arena_view"] = "recap"
                    st.rerun()
                    
            if hints_used < hint_budget:
                with cols[2]:
                    if st.button("💡 Hint", key=f"arena_hint_btn_{round_key}", use_container_width=True):
                        st.session_state[hint_key] = True
                        st.rerun()
        else:
            options = round_row["distractor_names"][:3] + [round_row["item_name"]]
            random.shuffle(options)
            st.session_state["_arena_mc_options"] = options
            opts_html = "".join(
                f'<div class="arena-mc-option" data-idx="{i}">{escape(o)}</div>' for i, o in enumerate(options)
            )
            st.markdown(f'<div class="arena-mc-grid">{opts_html}</div>', unsafe_allow_html=True)

            _, c_pass, _ = st.columns([1, 2, 1])
            with c_pass:
                if st.button("⏭️ Pass", key=f"arena_pass_mc_{round_key}", use_container_width=True):
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    # Only counts as a "spent hint" in hard mode; in easy mode MC is the default.
                    points = submit_round_answer(session, pool, round_row, False, not easy_mode, elapsed_ms)
                    st.toast("Round Skipped!", icon="⏭️")
                    if session["current_round"] >= pool["round_count"]:
                        finalize_session(session_id)
                        st.query_params["arena_view"] = "recap"
                    st.rerun()

    def _render_recap(user_id: int):
        session_id = st.session_state.get("arena_session_id")
        if not session_id:
            st.query_params["arena_view"] = "mode"
            st.rerun()
            return
        recap = get_recap(session_id)
        session, pool = recap["session"], recap["pool"]

        recap_meta = GAME_META.get(pool.get("game_type"), GAME_META["cover"])
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{recap_meta["icon"]} {recap_meta["label"]}</span></div>'
            f'<div class="arena-title">🏁 Match Recap</div><br>',
            unsafe_allow_html=True
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Score", session["total_score"])
        c2.metric("Correct", f"{session['correct_count']}/{pool['round_count']}")
        c3.metric("Best Round", session["best_round_score"])
        if pool.get("difficulty") == "easy":
            c4.metric("Difficulty", "🟢 Easy")
        else:
            c4.metric("Hints Used", f"{session['hints_used']}/{pool['hint_budget']}")

        if session["perfect_bonus_applied"]:
            st.success("✨ Flawless Victory! +20% score bonus applied.")

        if pool["mode"] == "friends":
            duel = recap.get("duel")
            if duel:
                st.markdown("### 🤝 Head-to-head")
                d1, d2 = st.columns(2)
                d1.metric("Your library, they got", duel["my_items_friend_got"])
                d2.metric("Their library, you got", duel["their_items_i_got"])
            else:
                st.info("⏳ Waiting on your friend to finish their side of the duel.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Play Again", key="arena_play_again_btn", type="primary", use_container_width=True):
            st.query_params["arena_view"] = "mode"
            for k in ("arena_pool_id", "arena_session_id", "arena_mode", "arena_game_type",
                      "arena_round_count_seg", "arena_difficulty_seg"):
                st.session_state.pop(k, None)
            st.rerun()

    return SimpleNamespace(
        inject_arena_script=inject_arena_script,
        arena_hidden_worker=arena_hidden_worker,
        render_modal=render_modal,
        is_arena_eligible=is_arena_eligible,
        create_pool=create_pool,
    )