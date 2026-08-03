"""
arena.py — "Arena" minigame hub for Suggestify.
"""

from __future__ import annotations

import json
import random
import time
import difflib
import datetime
import re
import unicodedata
from html import escape
from types import SimpleNamespace

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

# === ΧΡΟΝΟΣ ΑΝΑ ΓΥΡΟ ===
REVEAL_SECONDS_DEFAULT = 25
REVEAL_SECONDS_TRACKS = 150     # Πολύ περισσότερος χρόνος για το Tracks mode
RALLY_TURN_SECONDS = 60         # Letter Roulette / Discography Duel — Rally: seconds per turn
BLITZ_SECONDS = 120             # Letter Roulette / Discography Duel — Blitz: single countdown
LETTER_MIN_POOL = 6             # a letter needs >= this many eligible songs to be selectable
DISCOG_MIN_POOL = 6             # an artist needs >= this many eligible songs to be selectable
STATS_MIN_SONGS = 12            # min distinct streamed songs before Streaming Stats unlocks

ELIGIBILITY_FLOOR = 15          # min eligible items per game_type before Arena unlocks for a user
HINT_BUDGET = {5: 1, 10: 2, 20: 4}
TIER_TARGET_FRAC = {"core": 0.35, "regular": 0.35, "deep_cut": 0.30}
TIER_BASE_POINTS = {"core": 50, "regular": 100, "deep_cut": 200}
FUZZY_MATCH_THRESHOLD = 0.82    # difflib ratio for free-text answers
EASY_SCORE_MULTIPLIER = 0.8     # slight point discount for the always-multiple-choice mode
PERFECT_ALBUM_BONUS_FRAC = 0.2  # +20% bonus points when 100% of an album's tracks are found

STATS_QUESTION_POINTS = {
    "most": 100,       # "which of these have you streamed the most?"
    "least": 100,      # "...the least?"
    "threshold": 120,  # "which of these have you streamed more than N times?"
    "exact": 150,      # "how many times have you streamed X?"
}

GAME_META = {
    "cover":  {"icon": "🖼️", "label": "Guess the Cover",  "desc": "Album art, progressively revealed."},
    "artist": {"icon": "🎤", "label": "Guess the Artist", "desc": "Artist photos, progressively revealed."},
    "tracks": {"icon": "📀", "label": "Guess the Album Tracks", "desc": "Name every track on a full album before the clock runs out."},
    "letter": {"icon": "🔤", "label": "Letter Roulette", "desc": "Name songs starting with a random letter before time runs out."},
    "discog": {"icon": "🎙️", "label": "Discography Duel", "desc": "Name as many songs as you can by a random artist from your library before time runs out."},
    "stats":  {"icon": "📊", "label": "Streaming Stats", "desc": "Multiple-choice trivia about your own streaming numbers."},
}

def get_round_duration(game_type: str) -> int:
    return REVEAL_SECONDS_TRACKS if game_type == "tracks" else REVEAL_SECONDS_DEFAULT

# ─────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS arena_pools (
    id              BIGSERIAL PRIMARY KEY,
    mode            VARCHAR(20) NOT NULL CHECK (mode IN ('solo','friends')),
    game_type       VARCHAR(20) NOT NULL,
    round_count     INT NOT NULL,
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
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS reveal_mode VARCHAR(20) NOT NULL DEFAULT 'blurred';
ALTER TABLE arena_stats_questions ADD COLUMN IF NOT EXISTS option_counts JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS arena_pool_rounds (
    id                BIGSERIAL PRIMARY KEY,
    pool_id           BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    round_number      INT NOT NULL,
    item_type         VARCHAR(20) NOT NULL,
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
    status                 VARCHAR(20) NOT NULL DEFAULT 'in_progress',
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

-- Κεντρικά Check Constraints 
ALTER TABLE arena_pools DROP CONSTRAINT IF EXISTS arena_pools_game_type_check;
ALTER TABLE arena_pools ADD CONSTRAINT arena_pools_game_type_check
    CHECK (game_type IN ('cover','artist','tracks','letter','discog','stats'));

ALTER TABLE arena_pools DROP CONSTRAINT IF EXISTS arena_pools_round_count_check;
ALTER TABLE arena_pools ADD CONSTRAINT arena_pools_round_count_check
    CHECK (round_count IN (0,5,10,20));

ALTER TABLE arena_pool_rounds DROP CONSTRAINT IF EXISTS arena_pool_rounds_item_type_check;
ALTER TABLE arena_pool_rounds ADD CONSTRAINT arena_pool_rounds_item_type_check
    CHECK (item_type IN ('album','artist','album_tracks'));

ALTER TABLE arena_sessions DROP CONSTRAINT IF EXISTS arena_sessions_status_check;
ALTER TABLE arena_sessions ADD CONSTRAINT arena_sessions_status_check
    CHECK (status IN ('in_progress','completed','abandoned','failed'));

-- Υποστηρικτικοί Πίνακες
CREATE TABLE IF NOT EXISTS arena_round_tracks (
    id                BIGSERIAL PRIMARY KEY,
    pool_id           BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    round_number      INT NOT NULL,
    track_id          INTEGER NOT NULL,
    track_name        VARCHAR(255) NOT NULL,
    track_number      INT NOT NULL,
    familiarity_tier  VARCHAR(20) NOT NULL CHECK (familiarity_tier IN ('core','regular','deep_cut')),
    base_points       INT NOT NULL,
    CONSTRAINT uq_arena_round_track UNIQUE (pool_id, round_number, track_id)
);
CREATE INDEX IF NOT EXISTS idx_arena_round_tracks_round ON arena_round_tracks(pool_id, round_number);

CREATE TABLE IF NOT EXISTS arena_track_answers (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES arena_sessions(id) ON DELETE CASCADE,
    round_number    INT NOT NULL,
    track_id        INTEGER NOT NULL,
    points_earned   INT NOT NULL DEFAULT 0,
    found_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_arena_track_answer UNIQUE (session_id, round_number, track_id)
);
CREATE INDEX IF NOT EXISTS idx_arena_track_answers_session ON arena_track_answers(session_id, round_number);

ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS target_letter CHAR(1);
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS valid_pool JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS pool_size INT NOT NULL DEFAULT 0;
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS letter_version VARCHAR(10) CHECK (letter_version IN ('rally','blitz'));
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS turn_number INT NOT NULL DEFAULT 1;
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS turn_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS loser_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

-- Discography Duel (shares the letter_version / turn_* / valid_pool plumbing above)
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS target_artist_id INTEGER REFERENCES artists(id) ON DELETE CASCADE;
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS target_artist_name VARCHAR(255);
ALTER TABLE arena_pools ADD COLUMN IF NOT EXISTS target_artist_image VARCHAR(500);

CREATE TABLE IF NOT EXISTS arena_letter_answers (
    id                BIGSERIAL PRIMARY KEY,
    pool_id           BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    session_id        BIGINT NOT NULL REFERENCES arena_sessions(id) ON DELETE CASCADE,
    song_id           INTEGER NOT NULL,
    song_name         VARCHAR(255) NOT NULL,
    familiarity_tier  VARCHAR(20) NOT NULL CHECK (familiarity_tier IN ('core','regular','deep_cut')),
    points_earned     INT NOT NULL DEFAULT 0,
    turn_number       INT,
    answered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_arena_letter_answer UNIQUE (pool_id, song_id)
);
CREATE INDEX IF NOT EXISTS idx_arena_letter_answers_pool    ON arena_letter_answers(pool_id);
CREATE INDEX IF NOT EXISTS idx_arena_letter_answers_session ON arena_letter_answers(session_id);

-- Streaming Stats — personal-profile trivia questions, generated per pool.
-- Answers/scoring reuse the generic arena_round_answers table (round_number
-- is a free-standing counter here, not an FK into arena_pool_rounds).
CREATE TABLE IF NOT EXISTS arena_stats_questions (
    id             BIGSERIAL PRIMARY KEY,
    pool_id        BIGINT NOT NULL REFERENCES arena_pools(id) ON DELETE CASCADE,
    round_number   INT NOT NULL,
    question_type  VARCHAR(30) NOT NULL,
    question_text  TEXT NOT NULL,
    options        JSONB NOT NULL DEFAULT '[]'::jsonb,
    correct_index  INT NOT NULL,
    base_points    INT NOT NULL,
    CONSTRAINT uq_arena_stats_question UNIQUE (pool_id, round_number)
);
CREATE INDEX IF NOT EXISTS idx_arena_stats_questions_pool ON arena_stats_questions(pool_id);
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

    def _eligible_albums_pool(user_id: int) -> pd.DataFrame:
        """Albums the user has actually listened to, that have more than 1 track (excludes singles)."""
        df = run_query("""
            WITH user_stream_counts AS (
                SELECT song_id, COUNT(*) AS stream_count
                FROM streams
                WHERE user_id = :uid
                GROUP BY song_id
            )
            SELECT al.id AS item_id, al.title AS item_name, MAX(so.image_url) AS image_url,
                   COUNT(DISTINCT so.id) AS total_tracks,
                   SUM(usc.stream_count) AS stream_count
            FROM songs so
            JOIN user_stream_counts usc ON usc.song_id = so.id
            JOIN albums al ON al.id = so.album_id
            WHERE so.image_url IS NOT NULL
            GROUP BY al.id, al.title
            HAVING COUNT(DISTINCT so.id) > 1 AND SUM(usc.stream_count) >= 10
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

    # ─────────────────────────────────────────────────────────────────
    # Letter Roulette — pool building
    # ─────────────────────────────────────────────────────────────────

    def _letter_uid_filter(user_ids: list[int]) -> tuple[str, dict]:
        if len(user_ids) == 1:
            return "= :uid0", {"uid0": int(user_ids[0])}
        return "IN (:uid0, :uid1)", {"uid0": int(user_ids[0]), "uid1": int(user_ids[1])}

    def _letter_counts_by_alpha(user_ids: list[int]) -> dict:
        clause, params = _letter_uid_filter(user_ids)
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

    def _letter_eligible_letters(user_ids: list[int]) -> list[str]:
        counts = _letter_counts_by_alpha(user_ids)
        return [l for l, c in counts.items() if c >= LETTER_MIN_POOL]

    def _letter_eligible_friend_ids(user_id: int, candidate_ids: list[int]) -> list[int]:
        return [fid for fid in candidate_ids if len(_letter_eligible_letters([user_id, fid])) > 0]

    def _letter_fetch_pool(user_ids: list[int], letter: str) -> list[dict]:
        clause, params = _letter_uid_filter(user_ids)
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
    # Discography Duel — pool building
    # ─────────────────────────────────────────────────────────────────
    # Mirrors the Letter Roulette plumbing above almost exactly, but the
    # "bucket" songs are grouped into is a random artist from the user's
    # (or the user+friend's) library rather than a starting letter.

    def _discog_counts_by_artist(user_ids: list[int]) -> pd.DataFrame:
        clause, params = _letter_uid_filter(user_ids)
        df = run_query(f"""
            WITH scoped_songs AS (
                SELECT DISTINCT s.song_id
                FROM streams s
                WHERE s.user_id {clause}
            )
            SELECT a.id AS artist_id, a.name AS artist_name, a.image_url AS artist_image,
                   COUNT(DISTINCT so.id) AS cnt
            FROM songs so
            JOIN scoped_songs ss ON ss.song_id = so.id
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            GROUP BY a.id, a.name, a.image_url
        """, params)
        return df

    def _discog_eligible_artists(user_ids: list[int]) -> pd.DataFrame:
        df = _discog_counts_by_artist(user_ids)
        if df.empty:
            return df
        return df[df["cnt"] >= DISCOG_MIN_POOL].reset_index(drop=True)

    def _discog_eligible_friend_ids(user_id: int, candidate_ids: list[int]) -> list[int]:
        return [fid for fid in candidate_ids if len(_discog_eligible_artists([user_id, fid])) > 0]

    def _discog_fetch_pool(user_ids: list[int], artist_id: int) -> list[dict]:
        clause, params = _letter_uid_filter(user_ids)
        params["aid"] = int(artist_id)
        df = run_query(f"""
            WITH scoped_streams AS (
                SELECT song_id, COUNT(*) AS stream_count
                FROM streams
                WHERE user_id {clause}
                GROUP BY song_id
            ),
            artist_songs AS (
                SELECT DISTINCT so.id AS song_id, so.title AS song_name
                FROM songs so
                JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                WHERE sa.artist_id = :aid
            ),
            joined AS (
                SELECT ars.song_id, ars.song_name, ss.stream_count
                FROM artist_songs ars
                JOIN scoped_streams ss ON ss.song_id = ars.song_id
            ),
            ranked AS (
                SELECT song_id, song_name, stream_count,
                       PERCENT_RANK() OVER (ORDER BY stream_count DESC) AS pct_rank
                FROM joined
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

    def is_arena_eligible(user_id: int) -> dict:
        out = {}
        for gt in ("cover", "artist"):
            pool = _eligible_pool(user_id, gt)
            out[gt] = len(pool) >= ELIGIBILITY_FLOOR
        out["tracks"] = len(_eligible_albums_pool(user_id)) >= ELIGIBILITY_FLOOR
        out["letter"] = len(_letter_eligible_letters([user_id])) > 0
        out["discog"] = len(_discog_eligible_artists([user_id])) > 0
        
        # --- ΠΡΟΣΘΗΚΗ ΓΙΑ ΤΟ STREAMING STATS ---
        st_df = run_query("SELECT COUNT(DISTINCT song_id) AS c FROM streams WHERE user_id = :uid", {"uid": user_id})
        out["stats"] = (st_df.iloc[0]["c"] if not st_df.empty else 0) >= STATS_MIN_SONGS
        
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
                     difficulty: str = "hard", letter_version: str | None = None,
                     reveal_mode: str = "blurred") -> int | None:
        if difficulty not in ("easy", "hard"):
            difficulty = "hard"

        if game_type == "letter":
            lv = letter_version if letter_version in ("rally", "blitz") else "blitz"
            user_ids = [host_user_id] if mode == "solo" else [host_user_id, friend_user_id]
            letters = _letter_eligible_letters(user_ids)
            if not letters:
                return None
            target_letter = random.choice(letters)
            letter_pool = _letter_fetch_pool(user_ids, target_letter)
            if len(letter_pool) < LETTER_MIN_POOL:
                return None

            rows = run_write_query("""
                INSERT INTO arena_pools
                    (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id,
                     target_letter, valid_pool, pool_size, letter_version, turn_user_id, reveal_mode)
                VALUES (:mode, 'letter', 0, 'hard', 0, :host, :friend,
                        :letter, :pool, :psize, :lv, :turn_user, :rmode)
                RETURNING id
            """, dict(mode=mode, host=host_user_id, friend=friend_user_id,
                      letter=target_letter, pool=json.dumps(letter_pool), psize=len(letter_pool),
                      lv=lv, turn_user=host_user_id if lv == "rally" else None, rmode=reveal_mode))
            return rows[0]["id"]

        if game_type == "discog":
            lv = letter_version if letter_version in ("rally", "blitz") else "blitz"
            user_ids = [host_user_id] if mode == "solo" else [host_user_id, friend_user_id]
            artists = _discog_eligible_artists(user_ids)
            if artists.empty:
                return None
            chosen_artist = artists.sample(n=1).iloc[0]
            artist_id = int(chosen_artist["artist_id"])
            artist_name = chosen_artist["artist_name"]
            artist_image = chosen_artist["artist_image"]
            discog_pool = _discog_fetch_pool(user_ids, artist_id)
            if len(discog_pool) < DISCOG_MIN_POOL:
                return None

            rows = run_write_query("""
                INSERT INTO arena_pools
                    (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id,
                     target_artist_id, target_artist_name, target_artist_image,
                     valid_pool, pool_size, letter_version, turn_user_id, reveal_mode)
                VALUES (:mode, 'discog', 0, 'hard', 0, :host, :friend,
                        :aid, :aname, :aimg, :pool, :psize, :lv, :turn_user, :rmode)
                RETURNING id
            """, dict(mode=mode, host=host_user_id, friend=friend_user_id,
                      aid=artist_id, aname=artist_name, aimg=artist_image,
                      pool=json.dumps(discog_pool), psize=len(discog_pool),
                      lv=lv, turn_user=host_user_id if lv == "rally" else None, rmode=reveal_mode))
            return rows[0]["id"]

        hint_budget = HINT_BUDGET[round_count]

        if game_type == "tracks":
            host_albums_pool = _eligible_albums_pool(host_user_id)
            if mode == "friends" and friend_user_id:
                friend_albums_pool = _eligible_albums_pool(friend_user_id)
                n_host = round_count // 2
                n_friend = round_count - n_host
                host_items = _stratified_sample(host_albums_pool, n_host)
                friend_items = _stratified_sample(friend_albums_pool, n_friend)
                for it in host_items:
                    it["owner_user_id"] = host_user_id
                for it in friend_items:
                    it["owner_user_id"] = friend_user_id
                chosen = host_items + friend_items
                random.shuffle(chosen)
            else:
                chosen = _stratified_sample(host_albums_pool, round_count)
                for it in chosen:
                    it["owner_user_id"] = host_user_id

            tracklists_by_item = {}
            for uid in set(it["owner_user_id"] for it in chosen):
                u_aids = tuple(int(it["item_id"]) for it in chosen if it["owner_user_id"] == uid)
                if not u_aids: continue
                
                if len(u_aids) == 1:
                    df_tracks = run_query("""
                    WITH user_streams AS (
                        SELECT song_id, COUNT(*) as stream_count
                        FROM streams
                        WHERE user_id = :uid
                        GROUP BY song_id
                    )
                    SELECT so.album_id, so.id AS track_id, so.title AS track_name,
                           us.stream_count
                    FROM songs so
                    JOIN user_streams us ON us.song_id = so.id
                    WHERE so.album_id IN :aids
                """, {"uid": uid, "aids": tuple(u_aids)})
                else:
                    df_tracks = run_query("""
                        SELECT so.album_id, so.id AS track_id, so.title AS track_name,
                               (SELECT COUNT(*) FROM streams WHERE song_id = so.id AND user_id = :uid) AS stream_count
                        FROM songs so
                        WHERE so.album_id IN :aids
                    """, {"uid": uid, "aids": tuple(u_aids)})
                    
                if not df_tracks.empty:
                    for aid, group in df_tracks.groupby("album_id"):
                        group = group.sort_values("stream_count", ascending=False).reset_index(drop=True)
                        n = len(group)
                        tiers = []
                        for idx in range(n):
                            pct = idx / max(1, n)
                            if pct < 0.20: tiers.append("core")
                            elif pct < 0.70: tiers.append("regular")
                            else: tiers.append("deep_cut")
                        group["tier"] = tiers
                        tracklists_by_item[(uid, aid)] = group.to_dict("records")

            rows = run_write_query("""
                INSERT INTO arena_pools (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id, reveal_mode)
                VALUES (:mode, :game_type, :round_count, :difficulty, :hint_budget, :host_user_id, :friend_user_id, :reveal_mode)
                RETURNING id
            """, dict(mode=mode, game_type=game_type, round_count=round_count, difficulty=difficulty,
                      hint_budget=hint_budget, host_user_id=host_user_id, friend_user_id=friend_user_id, reveal_mode=reveal_mode))
            pool_id = rows[0]["id"]

            for i, item in enumerate(chosen, start=1):
                run_write_query("""
                    INSERT INTO arena_pool_rounds
                        (pool_id, round_number, item_type, item_id, item_name, image_url,
                         owner_user_id, familiarity_tier, base_points, distractor_names)
                    VALUES (:pool_id, :round_number, 'album_tracks', :item_id, :item_name, :image_url,
                            :owner_user_id, :tier, 0, '{}')
                """, dict(pool_id=pool_id, round_number=i,
                          item_id=int(item["item_id"]), item_name=item["item_name"], image_url=item["image_url"],
                          owner_user_id=item["owner_user_id"], tier=item["tier"]))

                tracklist = tracklists_by_item.get((item["owner_user_id"], int(item["item_id"])), [])
                for pos, trk in enumerate(tracklist, start=1):
                    run_write_query("""
                        INSERT INTO arena_round_tracks
                            (pool_id, round_number, track_id, track_name, track_number, familiarity_tier, base_points)
                        VALUES (:pool_id, :round_number, :track_id, :track_name, :track_number, :tier, :base_points)
                    """, dict(pool_id=pool_id, round_number=i, track_id=int(trk["track_id"]),
                              track_name=trk["track_name"], track_number=pos, tier=trk["tier"],
                              base_points=TIER_BASE_POINTS[trk["tier"]]))
            return pool_id
        
        if game_type == "stats":
            rows = run_write_query("""
                INSERT INTO arena_pools (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id, reveal_mode)
                VALUES (:mode, :game_type, :round_count, :difficulty, :hint_budget, :host_user_id, :friend_user_id, :reveal_mode)
                RETURNING id
            """, dict(mode=mode, game_type=game_type, round_count=round_count, difficulty=difficulty,
                      hint_budget=hint_budget, host_user_id=host_user_id, friend_user_id=friend_user_id, reveal_mode=reveal_mode))
            pool_id = rows[0]["id"]

            # 1. Φέρνουμε Top Artists, Songs και Albums
            top_artists_df = run_query("""
                SELECT a.name, COUNT(*) as c 
                FROM streams s 
                JOIN song_artists sa ON sa.song_id = s.song_id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE s.user_id = :uid 
                GROUP BY a.id 
                ORDER BY c DESC LIMIT 40
            """, {"uid": host_user_id})
            top_artists = top_artists_df.to_dict('records') if not top_artists_df.empty else []

            top_songs_df = run_query("""
                SELECT so.title as name, COUNT(*) as c 
                FROM streams s 
                JOIN songs so ON so.id = s.song_id
                WHERE s.user_id = :uid 
                GROUP BY so.id 
                ORDER BY c DESC LIMIT 40
            """, {"uid": host_user_id})
            top_songs = top_songs_df.to_dict('records') if not top_songs_df.empty else []

            top_albums_df = run_query("""
                SELECT al.title as name, COUNT(*) as c 
                FROM streams s 
                JOIN songs so ON so.id = s.song_id
                JOIN albums al ON al.id = so.album_id
                WHERE s.user_id = :uid 
                GROUP BY al.id 
                ORDER BY c DESC LIMIT 40
            """, {"uid": host_user_id})
            top_albums = top_albums_df.to_dict('records') if not top_albums_df.empty else []

            for i in range(1, round_count + 1):
                valid_cats = []
                if len(top_artists) >= 4: valid_cats.append(("artist", top_artists))
                if len(top_songs) >= 4: valid_cats.append(("song", top_songs))
                if len(top_albums) >= 4: valid_cats.append(("album", top_albums))

                if not valid_cats:
                    q_type, q_text = "most", "Not enough listening history yet!"
                    options, option_counts, correct_idx, base_pts = ["N/A"] * 4, [0] * 4, 0, 100
                else:
                    cat_name, cat_data = random.choice(valid_cats)
                    sample = random.sample(cat_data, 4)
                    sample.sort(key=lambda x: x['c'], reverse=True) # Highest to lowest streams
                    
                    q_type = random.choice(["most", "least", "exact", "threshold"])
                    option_counts = []
                    
                    if q_type == "most":
                        correct_name = sample[0]['name']
                        q_text = f"Which of these {cat_name}s have you streamed the MOST?"
                        
                        random.shuffle(sample)
                        options = [s['name'] for s in sample]
                        option_counts = [s['c'] for s in sample]
                        correct_idx = options.index(correct_name)
                        base_pts = STATS_QUESTION_POINTS["most"]
                        
                    elif q_type == "least":
                        correct_name = sample[-1]['name']
                        q_text = f"Which of these {cat_name}s have you streamed the LEAST?"
                        
                        random.shuffle(sample)
                        options = [s['name'] for s in sample]
                        option_counts = [s['c'] for s in sample]
                        correct_idx = options.index(correct_name)
                        base_pts = STATS_QUESTION_POINTS["least"]
                        
                    elif q_type == "exact":
                        target = sample[0]
                        exact_ans = target['c']
                        rounded_ans = int(round(exact_ans, -1)) if exact_ans >= 10 else exact_ans
                        
                        q_text = f"Approximately how many times have you streamed the {cat_name} '{target['name']}'?"
                        
                        wrong_opts = [
                            rounded_ans + random.choice([10, 20, 50]), 
                            max(1, rounded_ans - random.choice([10, 20])), 
                            int(rounded_ans * random.choice([1.5, 2.0]))
                        ]
                        opts_set = {rounded_ans}
                        for w in wrong_opts:
                            while w in opts_set: w += 10
                            opts_set.add(w)
                            
                        options_ints = list(opts_set)
                        random.shuffle(options_ints)
                        options = [str(x) for x in options_ints]
                        option_counts = [exact_ans] * 4 # Pass exact number strictly for the reveal UI
                        correct_idx = options_ints.index(rounded_ans)
                        base_pts = STATS_QUESTION_POINTS["exact"]
                        
                    else: # threshold
                        if random.choice([True, False]) and sample[0]['c'] > sample[1]['c']:
                            target = sample[0]
                            exact_t = random.randint(sample[1]['c'] + 1, target['c'])
                            if exact_t == target['c']: exact_t -= 1
                            t = int(round(exact_t, -1)) if exact_t >= 20 else exact_t
                            if t >= target['c'] or t <= sample[1]['c']: t = exact_t
                            
                            q_text = f"Which of these {cat_name}s have you streamed MORE than {max(1, t)} times?"
                            correct_name = target['name']
                        elif sample[-2]['c'] > sample[-1]['c']:
                            target = sample[-1]
                            exact_t = random.randint(target['c'] + 1, sample[-2]['c'])
                            t = int(round(exact_t, -1)) if exact_t >= 20 else exact_t
                            if t <= target['c'] or t >= sample[-2]['c']: t = exact_t
                            
                            q_text = f"Which of these {cat_name}s have you streamed LESS than {t} times?"
                            correct_name = target['name']
                        else:
                            q_text = f"Which of these {cat_name}s have you streamed the MOST?"
                            correct_name = sample[0]['name']
                            
                        random.shuffle(sample)
                        options = [s['name'] for s in sample]
                        option_counts = [s['c'] for s in sample]
                        correct_idx = options.index(correct_name)
                        base_pts = STATS_QUESTION_POINTS["threshold"]

                run_write_query("""
                    INSERT INTO arena_stats_questions (pool_id, round_number, question_type, question_text, options, correct_index, base_points, option_counts)
                    VALUES (:pid, :rn, :qtype, :qtext, :opts, :cidx, :bpts, :ocounts)
                """, dict(pid=pool_id, rn=i, qtype=q_type, qtext=q_text, opts=json.dumps(options), cidx=correct_idx, bpts=base_pts, ocounts=json.dumps(option_counts)))
            return pool_id
        
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
            INSERT INTO arena_pools (mode, game_type, round_count, difficulty, hint_budget, host_user_id, friend_user_id, reveal_mode)
            VALUES (:mode, :game_type, :round_count, :difficulty, :hint_budget, :host_user_id, :friend_user_id, :reveal_mode)
            RETURNING id
        """, dict(mode=mode, game_type=game_type, round_count=round_count, difficulty=difficulty,
                  hint_budget=hint_budget, host_user_id=host_user_id, friend_user_id=friend_user_id, reveal_mode=reveal_mode))
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

    def _get_session_row(pool_id: int, user_id: int) -> dict | None:
        rows = run_write_query("SELECT * FROM arena_sessions WHERE pool_id=:p AND user_id=:u", {"p": pool_id, "u": user_id})
        return dict(rows[0]) if rows else None

    def get_round(pool_id: int, round_number: int) -> dict | None:
        rows = run_write_query("""
            SELECT * FROM arena_pool_rounds WHERE pool_id=:p AND round_number=:rn
        """, {"p": pool_id, "rn": round_number})
        return dict(rows[0]) if rows else None

    # Add the missing stats question fetcher here:
    def get_stats_question(pool_id: int, round_number: int) -> dict | None:
        rows = run_write_query("""
            SELECT * FROM arena_stats_questions 
            WHERE pool_id=:p AND round_number=:rn
        """, {"p": pool_id, "rn": round_number})
        return dict(rows[0]) if rows else None

    def get_round_tracks(pool_id: int, round_number: int) -> list[dict]:
        rows = run_write_query("""
            SELECT * FROM arena_round_tracks WHERE pool_id=:p AND round_number=:rn ORDER BY track_number
        """, {"p": pool_id, "rn": round_number})
        return [dict(r) for r in rows] if rows else []

    def get_track_answers_map(session_id: int, round_number: int) -> dict:
        rows = run_write_query("""
            SELECT track_id, points_earned FROM arena_track_answers
            WHERE session_id=:sid AND round_number=:rn
        """, {"sid": session_id, "rn": round_number})
        return {r["track_id"]: dict(r) for r in rows} if rows else {}

    def _score_answer(pool: dict, round_row: dict, session_user_id: int,
                       is_correct: bool, used_hint: bool, time_taken_ms: int):
        if not is_correct: return 0.0, 1.0, 0
        dur_sec = get_round_duration(pool.get("game_type", "cover"))
        frac = min(max(time_taken_ms / (dur_sec * 1000), 0.0), 1.0)
        
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

    def _score_track_answer(pool: dict, round_row: dict, track_row: dict, session_user_id: int) -> int:
        owner_mult = 1.3 if (pool["mode"] == "friends" and round_row["owner_user_id"] != session_user_id) else 1.0
        return round(track_row["base_points"] * owner_mult)

    def submit_track_answer(session: dict, pool: dict, round_row: dict, track_row: dict, time_taken_ms: int) -> int:
        existing = run_write_query(
            "SELECT id FROM arena_track_answers WHERE session_id=:sid AND round_number=:rn AND track_id=:tid",
            {"sid": session["id"], "rn": round_row["round_number"], "tid": track_row["track_id"]}
        )
        if existing:
            return 0

        points = _score_track_answer(pool, round_row, track_row, session["user_id"])
        run_write_query("""
            INSERT INTO arena_track_answers (session_id, round_number, track_id, points_earned)
            VALUES (:sid, :rn, :tid, :pts)
            ON CONFLICT (session_id, round_number, track_id) DO NOTHING
        """, dict(sid=session["id"], rn=round_row["round_number"], tid=track_row["track_id"], pts=points))
        run_write_query("""
            UPDATE arena_sessions SET total_score = total_score + :pts WHERE id = :sid
        """, dict(pts=points, sid=session["id"]))
        return points

    def finalize_track_round(session: dict, pool: dict, round_row: dict, timed_out: bool = False):
        existing = run_write_query(
            "SELECT id FROM arena_round_answers WHERE session_id=:sid AND round_number=:rn",
            {"sid": session["id"], "rn": round_row["round_number"]}
        )
        if existing:
            return

        tracks = get_round_tracks(pool["id"], round_row["round_number"])
        found_map = get_track_answers_map(session["id"], round_row["round_number"])
        is_perfect = len(tracks) > 0 and len(found_map) == len(tracks)
        round_points = sum(f["points_earned"] for f in found_map.values())

        bonus = round(round_points * PERFECT_ALBUM_BONUS_FRAC) if (is_perfect and not timed_out) else 0

        run_write_query("""
            INSERT INTO arena_round_answers
              (session_id, round_number, used_hint, is_correct, time_taken_ms,
               speed_multiplier, ownership_multiplier, points_earned)
            VALUES (:sid, :rn, FALSE, :correct, NULL, 1.0, 1.0, :bonus)
            ON CONFLICT (session_id, round_number) DO NOTHING
        """, dict(sid=session["id"], rn=round_row["round_number"], correct=is_perfect, bonus=bonus))

        run_write_query("""
            UPDATE arena_sessions SET
              correct_count = correct_count + :found_inc,
              total_score = total_score + :bonus,
              best_round_score = GREATEST(best_round_score, :round_pts),
              current_round = current_round + 1
            WHERE id = :sid
        """, dict(found_inc=len(found_map), bonus=bonus, round_pts=round_points + bonus, sid=session["id"]))

    def get_tracks_totals(pool_id: int, session_id: int) -> tuple[int, int]:
        total_rows = run_write_query("SELECT COUNT(*) AS c FROM arena_round_tracks WHERE pool_id=:p", {"p": pool_id})
        found_rows = run_write_query("SELECT COUNT(*) AS c FROM arena_track_answers WHERE session_id=:s", {"s": session_id})
        total = total_rows[0]["c"] if total_rows else 0
        found = found_rows[0]["c"] if found_rows else 0
        return found, total

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
    # Letter Roulette / Discography Duel — in-memory validation + scoring
    # writes. These helpers are agnostic to which of the two "duel" game
    # types (letter or discog) the pool belongs to — they only rely on the
    # generic pool_id / valid_pool / turn_* / status columns, so both games
    # share this exact code path.
    # ─────────────────────────────────────────────────────────────────

    _DUEL_GAME_TYPES = ("letter", "discog")
    _SOLO_ONLY_GAME_TYPES = ("stats",)

    def _load_letter_pool(pool: dict) -> list[dict]:
        key = f"arena_letter_pool_{pool['id']}"
        if key not in st.session_state:
            vp = pool["valid_pool"]
            if isinstance(vp, str):
                vp = json.loads(vp)
            st.session_state[key] = vp
        return st.session_state[key]

    def _get_used_letter_song_ids(pool_id: int) -> set:
        rows = run_write_query("SELECT song_id FROM arena_letter_answers WHERE pool_id=:p", {"p": pool_id})
        return {r["song_id"] for r in rows} if rows else set()

    def _find_letter_match(guess: str, pool_songs: list[dict], used_ids: set) -> dict | None:
        if not guess.strip():
            return None
        for song in pool_songs:
            if song["song_id"] in used_ids:
                continue
            if _answer_matches(guess, song["song_name"]):
                return song
        return None

    def _record_letter_answer(pool_id: int, session_id: int, song: dict, turn_number: int | None) -> bool:
        rows = run_write_query("""
            INSERT INTO arena_letter_answers
                (pool_id, session_id, song_id, song_name, familiarity_tier, points_earned, turn_number)
            VALUES (:p, :s, :sid, :sname, :tier, :pts, :turn)
            ON CONFLICT (pool_id, song_id) DO NOTHING
            RETURNING id
        """, dict(p=pool_id, s=session_id, sid=song["song_id"], sname=song["song_name"],
                  tier=song["familiarity_tier"], pts=song["points"], turn=turn_number))
        if not rows:
            return False
        run_write_query("""
            UPDATE arena_sessions SET total_score = total_score + :pts, correct_count = correct_count + 1
            WHERE id = :sid
        """, dict(pts=song["points"], sid=session_id))
        return True

    def _advance_letter_turn(pool: dict):
        next_user = pool["host_user_id"]
        if pool["mode"] == "friends":
            next_user = pool["friend_user_id"] if pool["turn_user_id"] == pool["host_user_id"] else pool["host_user_id"]
        run_write_query("""
            UPDATE arena_pools SET turn_number = turn_number + 1, turn_user_id = :nu WHERE id = :id
        """, {"nu": next_user, "id": pool["id"]})

    def _end_letter_rally(pool: dict, loser_user_id: int | None):
        run_write_query("""
            UPDATE arena_pools SET status='completed', loser_user_id=:loser WHERE id=:id
        """, {"loser": loser_user_id, "id": pool["id"]})
        for uid in {pool["host_user_id"], pool["friend_user_id"]}:
            if uid is None:
                continue
            status = "failed" if uid == loser_user_id else "completed"
            run_write_query("""
                UPDATE arena_sessions SET status=:s, completed_at=now()
                WHERE pool_id=:p AND user_id=:u
            """, {"s": status, "p": pool["id"], "u": uid})

    def _end_letter_blitz_session(pool_id: int, user_id: int):
        run_write_query("""
            UPDATE arena_sessions SET status='completed', completed_at=now()
            WHERE pool_id=:p AND user_id=:u
        """, {"p": pool_id, "u": user_id})

    # ─────────────────────────────────────────────────────────────────
    # Free-text matching (Fuzzy + Regex Normalization)
    # ─────────────────────────────────────────────────────────────────

    def _remove_accents(input_str: str) -> str:
        """Αφαιρεί τόνους και διακριτικά (π.χ. é -> e, ά -> α)"""
        nfkd_form = unicodedata.normalize('NFKD', input_str)
        return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

    def _normalize_string(text: str) -> str:
        t = text.lower()
        t = re.sub(r'\(.*?\)', '', t)
        t = re.sub(r'\[.*?\]', '', t)
        t = re.sub(r'\b(?:feat\.?|ft\.?)\b.*', '', t)
        t = _remove_accents(t)
        return t.strip()

    def _answer_matches(guess: str, correct: str) -> bool:
        if not guess.strip(): return False
        
        # 1. Αφαιρούμε τόνους από τη μαντεψιά
        g_clean = _remove_accents(guess.lower())
        
        # 2. Το \w κρατάει γράμματα από ΟΛΕΣ τις γλώσσες και αριθμούς. 
        # Αφαιρούμε σημεία στίξης και κενά.
        g = re.sub(r'[^\w]', '', g_clean).replace('_', '')
        if not g: return False

        # 3. Καθαρίζουμε τον σωστό τίτλο και τον σπάμε σε κομμάτια (αν έχει / ή -)
        c_norm = _normalize_string(correct)
        c_parts = [c_norm] + re.split(r'[/|\-]', c_norm)
        
        for part in c_parts:
            p = re.sub(r'[^\w]', '', part).replace('_', '')
            if not p: continue
            
            if g == p: 
                return True
            if difflib.SequenceMatcher(None, g, p).ratio() >= FUZZY_MATCH_THRESHOLD:
                return True
                
        return False

    # ─────────────────────────────────────────────────────────────────
    # JS: hidden-input pattern for timeout, MC tile clicks, and SEAMLESS INPUT
    # ─────────────────────────────────────────────────────────────────

    def inject_arena_script():
        # Εξαφανίζει τα κρυφά inputs και τα zero-height iframes από το UI
        st.markdown("""
        <style>
        /* Κρύβει τα text inputs των workers χωρίς να σπάει το JS focus */
        div[data-testid="stTextInput"]:has(input[aria-label^="arena_"]) {
            position: absolute !important;
            opacity: 0 !important;
            width: 1px !important;
            height: 1px !important;
            overflow: hidden !important;
            pointer-events: none !important;
            z-index: -999 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        
        /* Αφαιρεί το κενό που αφήνουν τα zero-height iframes */
        div.element-container:has(iframe[height="0"]) {
            display: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        components.html("""
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.__arenaDelegated) return;
            doc.__arenaDelegated = true;

            // -- Seamless Input Global Setup --
            if (!window.parent.__arenaSeamlessInput) {
                const inp = doc.createElement('input');
                inp.id = 'arena-seamless-input';
                inp.type = 'text';
                inp.autocomplete = 'off';
                inp.placeholder = 'Type your guess and press Enter...';
                
                // Copy exact CSS from standard inputs
                inp.style.cssText = `
                    width: 100%;
                    padding: 1rem !important;
                    border-radius: 8px;
                    border: 1px solid rgba(255,255,255,0.2);
                    background: rgba(0,0,0,0.2);
                    color: white;
                    font-size: 1.1rem !important;
                    text-align: center !important;
                    font-weight: 600 !important;
                    outline: none;
                    transition: all 0.2s ease;
                    box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 1rem;
                `;
                
                inp.addEventListener('focus', () => {
                    inp.style.borderColor = '#1DB954';
                    inp.style.background = 'rgba(255,255,255,0.05)';
                    inp.style.boxShadow = '0 0 0 2px rgba(29,185,84,0.2)';
                });
                inp.addEventListener('blur', () => {
                    inp.style.borderColor = 'rgba(255,255,255,0.2)';
                    inp.style.background = 'rgba(0,0,0,0.2)';
                    inp.style.boxShadow = 'inset 0 2px 4px rgba(0,0,0,0.1)';
                });

                inp.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        const val = inp.value.trim();
                        if (!val) return;
                        
                        // Instant visual reset - no Streamlit blocking
                        inp.value = '';
                        
                        // Pass value to Streamlit
                        fire('input[aria-label="arena_hidden_guess_input"]', val + '::' + Date.now());
                    }
                });
                window.parent.__arenaSeamlessInput = inp;
            }

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
                    
                    // Do not steal focus back from the seamless input!
                    if (inputSelector !== 'input[aria-label="arena_hidden_guess_input"]') {
                        input.focus({ preventScroll: true });
                        setTimeout(function() {
                            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                            input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                            input.blur();
                        }, 30);
                    } else {
                        input.focus({ preventScroll: true });
                        setTimeout(function() {
                            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                            input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
                            
                            // Επιστροφή του focus στο custom πεδίο που γράφεις
                            if (window.parent.__arenaSeamlessInput) {
                                window.parent.__arenaSeamlessInput.focus({ preventScroll: true });
                            }
                        }, 10);
                    }
                }
                trySubmit(5);
            }

            doc.addEventListener('click', function(e) {
                const sopt = e.target.closest('.arena-stats-mc-option');
                if (sopt) {
                    e.preventDefault();
                    e.stopPropagation();
                    const sidx = sopt.dataset.idx;
                    fire('input[aria-label="arena_stats_mc_input"]', sidx + ':' + Date.now());
                    return;
                }
                const opt = e.target.closest('.arena-mc-option');
                if (opt) {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = opt.dataset.idx;
                    fire('input[aria-label="arena_mc_input"]', idx + ':' + Date.now());
                }
            });
            window.parent.__arenaFire = fire;
        })();
        </script>
        """, height=0)

    def render_seamless_input_container():
        st.markdown('<div id="seamless-input-container"></div>', unsafe_allow_html=True)
        components.html("""
        <script>
        (function(){
            const doc = window.parent.document;
            const container = doc.getElementById('seamless-input-container');
            const inp = window.parent.__arenaSeamlessInput;
            if(container && inp && inp.parentElement !== container) {
                inp.style.display = 'block';
                container.appendChild(inp);
                setTimeout(() => inp.focus(), 10);
            }
        })();
        </script>
        """, height=0)

    def render_round_timer_script(round_key: str, started_at_ms: float, duration_sec: int, game_type: str,
                                   reveal_mode: str = "blurred", corner: str = "top left", input_aria: str = "arena_timeout_input"):
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const startedAt = {started_at_ms};
            const durationMs = {duration_sec * 1000};
            const roundKey = {json.dumps(round_key)};
            const gameType = {json.dumps(game_type)};
            const revealMode = {json.dumps(reveal_mode)};
            const corner = {json.dumps(corner)};
            
            if (doc.__arenaRoundKey !== roundKey) {{
                doc.__arenaRoundKey = roundKey;
                doc.__arenaTimedOut = false;
            }}
            
            if (doc.__arenaInterval) clearInterval(doc.__arenaInterval);

            function fireTimeout() {{
                if (window.parent.__arenaFire) {{
                    window.parent.__arenaFire('input[aria-label="{input_aria}"]', roundKey + ':' + Date.now());
                }}
            }}

            function tick() {{
                const now = Date.now();
                const frac = Math.min((now - startedAt) / durationMs, 1);
                const bar = doc.getElementById('arena-progress-bar');
                const img = doc.getElementById('arena-reveal-img');
                
                if (bar) bar.style.width = ((1 - frac) * 100) + '%';
                
                if (img && (gameType === 'cover' || gameType === 'artist')) {{
                    if (revealMode === 'blurred') {{
                        img.style.filter = 'blur(' + (22 * (1 - frac)) + 'px)';
                    }} else if (revealMode === 'corners') {{
                        const currentScale = 1 + (3 * (1 - frac)); // Scales from 4.0 down to 1.0
                        img.style.transformOrigin = corner;
                        img.style.transform = 'scale(' + currentScale + ')';
                    }}
                }}
                
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
            
            if (doc.__arenaRevealKey !== key) {{
                doc.__arenaRevealKey = key;
            }}
            if (doc.__arenaRevealTimeout) clearTimeout(doc.__arenaRevealTimeout);

            function fireContinue() {{
                if (window.parent.__arenaFire) {{
                    window.parent.__arenaFire('input[aria-label="arena_reveal_continue_input"]', key + ':' + Date.now());
                }}
            }}
            doc.__arenaRevealTimeout = setTimeout(fireContinue, {delay_ms});
        }})();
        </script>
        """, height=0)

    def render_letter_poll_script(poll_key: str, every_ms: int = 3000):
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const key = {json.dumps("letter_poll_" + poll_key)};
            
            if (doc.__arenaLetterPollKey !== key) {{
                doc.__arenaLetterPollKey = key;
            }}
            if (doc.__arenaLetterPollInterval) clearInterval(doc.__arenaLetterPollInterval);

            function ping() {{
                if (window.parent.__arenaFire) {{
                    window.parent.__arenaFire('input[aria-label="arena_letter_poll_input"]', key + ':' + Date.now());
                }}
            }}
            doc.__arenaLetterPollInterval = setInterval(ping, {every_ms});
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
            if not ctx: return
            pool, session, round_row = ctx
            if round_row is None: return

            if pool.get("game_type") == "tracks":
                st.session_state["_arena_tracks_reveal"] = session["current_round"]
                finalize_track_round(session, pool, round_row, timed_out=True)
                return

            if pool and pool.get("difficulty") == "easy":
                hint_active = False
            else:
                hint_active = st.session_state.get(
                    f"arena_hint_{st.session_state.get('arena_session_id')}_{st.session_state.get('arena_round_no', 1)}", False
                )
            dur_sec = get_round_duration(pool.get("game_type", "cover"))
            _resolve(is_correct=False, used_hint=hint_active, time_taken_ms=dur_sec * 1000)

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
            used_hint = pool.get("difficulty") != "easy"
            round_key = f"{session['id']}_{session['current_round']}"
            result = _resolve(is_correct=is_correct, used_hint=used_hint, time_taken_ms=elapsed_ms,
                               advance_view=False, ctx=(pool, session, round_row))
            if result is None: return
            points, is_last = result
            st.session_state["_arena_mc_reveal"] = dict(
                round_key=round_key, options=options, chosen_idx=idx,
                correct_name=correct_name, is_correct=is_correct,
                points=points, is_last=is_last,
            )

        def on_reveal_continue():
            val = st.session_state.get("arena_reveal_continue_state")
            if not val: return
            reveal = st.session_state.pop("_arena_mc_reveal", None)
            if reveal is None:
                reveal = st.session_state.pop("_arena_stats_reveal", None)
            if reveal and reveal.get("is_last"):
                st.query_params["arena_view"] = "recap"

        st.text_input("arena_reveal_continue_input", key="arena_reveal_continue_state",
                       label_visibility="collapsed", on_change=on_reveal_continue)

        st.text_input("arena_mc_input", key="arena_mc_state",
                       label_visibility="collapsed", on_change=on_mc_click)

        # ---- Streaming Stats: MC-click + timeout ----

        def _current_stats_context():
            pool_id = st.session_state.get("arena_pool_id")
            session_id = st.session_state.get("arena_session_id")
            if not pool_id or not session_id: return None
            pool = get_pool(pool_id)
            if not pool or pool.get("game_type") != "stats": return None
            rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
            if not rows: return None
            session = dict(rows[0])
            q = get_stats_question(pool_id, session["current_round"])
            return pool, session, q

        def on_stats_mc_click():
            val = st.session_state.get("arena_stats_mc_state")
            if not val: return
            parts = val.split(":")
            if len(parts) < 2: return
            idx = int(parts[0])
            ctx = _current_stats_context()
            if not ctx: return
            pool, session, q = ctx
            if q is None: return
            round_key = f"{session['id']}_{session['current_round']}"
            if st.session_state.get("_arena_stats_reveal", {}).get("round_key") == round_key:
                return
            is_correct = idx == q["correct_index"]
            start_key = f"arena_round_start_{session['id']}_{session['current_round']}"
            started_at = st.session_state.get(start_key, time.time())
            elapsed_ms = int((time.time() - started_at) * 1000)
            synth_round = {"round_number": session["current_round"],
                           "base_points": q["base_points"], "owner_user_id": session["user_id"]}
            points = submit_round_answer(session, pool, synth_round, is_correct, False, elapsed_ms)
            is_last = session["current_round"] >= pool["round_count"]
            if is_last:
                finalize_session(session["id"])
            raw_counts = q.get("option_counts", "[]")
            opt_counts = json.loads(raw_counts) if isinstance(raw_counts, str) else raw_counts
            
            st.session_state["_arena_stats_reveal"] = dict(
                round_key=round_key, options=q["options"], option_counts=opt_counts, chosen_idx=idx,
                correct_index=q["correct_index"], is_correct=is_correct,
                points=points, is_last=is_last, question_text=q["question_text"], question_type=q.get("question_type", "")
            )

        def on_stats_timeout():
            val = st.session_state.get("arena_stats_timeout_state")
            if not val: return
            ctx = _current_stats_context()
            if not ctx: return
            pool, session, q = ctx
            if q is None: return
            round_key = f"{session['id']}_{session['current_round']}"
            if st.session_state.get("_arena_stats_reveal", {}).get("round_key") == round_key:
                return
            dur_sec = get_round_duration(pool.get("game_type", "stats"))
            synth_round = {"round_number": session["current_round"],
                           "base_points": q["base_points"], "owner_user_id": session["user_id"]}
            points = submit_round_answer(session, pool, synth_round, False, False, dur_sec * 1000)
            is_last = session["current_round"] >= pool["round_count"]
            if is_last:
                finalize_session(session["id"])
            raw_counts = q.get("option_counts", "[]")
            opt_counts = json.loads(raw_counts) if isinstance(raw_counts, str) else raw_counts

            st.session_state["_arena_stats_reveal"] = dict(
                round_key=round_key, options=q["options"], option_counts=opt_counts, chosen_idx=-1,
                correct_index=q["correct_index"], is_correct=False,
                points=points, is_last=is_last, question_text=q["question_text"], question_type=q.get("question_type", "")
            )

        st.text_input("arena_stats_mc_input", key="arena_stats_mc_state",
                       label_visibility="collapsed", on_change=on_stats_mc_click)
        st.text_input("arena_stats_timeout_input", key="arena_stats_timeout_state",
                       label_visibility="collapsed", on_change=on_stats_timeout)

        # ---- Letter Roulette / Discography Duel: rally timeout / blitz timeout / turn poll ----

        def on_letter_rally_timeout():
            val = st.session_state.get("arena_letter_rally_timeout_state")
            if not val: return
            ctx = _current_context()
            if not ctx: return
            pool, session, _round_row = ctx
            if pool.get("game_type") not in _DUEL_GAME_TYPES or pool.get("letter_version") != "rally":
                return
            if pool["status"] != "active":
                return
            if pool["turn_user_id"] != session["user_id"]:
                return
            _end_letter_rally(pool, loser_user_id=session["user_id"])
            st.rerun()

        def on_letter_blitz_timeout():
            val = st.session_state.get("arena_letter_blitz_timeout_state")
            if not val: return
            ctx = _current_context()
            if not ctx: return
            pool, session, _round_row = ctx
            if pool.get("game_type") not in _DUEL_GAME_TYPES or pool.get("letter_version") != "blitz":
                return
            if session["status"] == "in_progress":
                _end_letter_blitz_session(pool["id"], session["user_id"])
            st.rerun()

        def on_letter_poll():
            pass

        st.text_input("arena_letter_rally_timeout_input", key="arena_letter_rally_timeout_state",
                       label_visibility="collapsed", on_change=on_letter_rally_timeout)
        st.text_input("arena_letter_blitz_timeout_input", key="arena_letter_blitz_timeout_state",
                       label_visibility="collapsed", on_change=on_letter_blitz_timeout)
        st.text_input("arena_letter_poll_input", key="arena_letter_poll_state",
                       label_visibility="collapsed", on_change=on_letter_poll)

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
    .arena-reveal-frame img {{ width: 100%; height: 100%; object-fit: cover; transition: filter 0.15s linear, transform 0.15s linear; }}
    .arena-mc-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; margin: 1rem 0 1.6rem; }}
    .arena-mc-option, .arena-stats-mc-option {{
        background: rgba(255,255,255,0.05); border: 1px solid {BORDER}; border-radius: 12px;
        padding: 1rem; text-align: center; font-weight: 600; color: {TEXT}; cursor: pointer;
        transition: all 0.15s ease;
    }}
    .arena-mc-option:hover, .arena-stats-mc-option:hover {{ border-color: {GREEN}; background: rgba(29,185,84,0.12); transform: translateY(-2px); }}

    .arena-stats-question {{
        font-size: 1.08rem;
        font-weight: 700;
        color: {TEXT};
        text-align: center;
        line-height: 1.45;
        margin: 0.2rem 0 1.4rem;
        padding: 0.9rem 1rem;
        border-radius: 14px;
        background: rgba(255,255,255,0.035);
        border: 1px solid {BORDER};
    }}

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

    div.st-key-arena_modal_content div[data-testid="stTextInput"] input {{
        text-align: center !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        padding: 1rem !important;
    }}
    
    /* HIDE THE HIDDEN SEAMLESS STREAMLIT INPUT */
    /* HIDE THE HIDDEN SEAMLESS STREAMLIT INPUT */
    div[data-testid="stTextInput"]:has(input[aria-label="arena_hidden_guess_input"]) {{
        position: absolute !important;
        opacity: 0 !important;
        width: 1px !important;
        height: 1px !important;
        overflow: hidden !important;
        pointer-events: none !important;
        z-index: -999 !important;
    }}

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
    /* 🔴 ΑΠΕΝΕΡΓΟΠΟΙΗΣΗ ΤΟΥ STREAMLIT "RERUN DIMMING" 🔴 */
    [data-stale="true"] {{
        opacity: 1 !important;
        filter: none !important;
        pointer-events: auto !important;
        transition: none !important;
    }}

    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stVerticalBlock"],
    div[data-testid="stElementContainer"] {{
        opacity: 1 !important;
        transition: none !important;
    }}

    .arena-track-list {{
        display: flex; flex-direction: column; gap: 0.5rem;
        margin: 1.2rem 0 1.4rem; max-height: 260px; overflow-y: auto; padding-right: 4px;
    }}
    .arena-track-row {{
        display: flex; align-items: center; gap: 0.7rem;
        background: rgba(255,255,255,0.04); border: 1px solid {BORDER}; border-radius: 10px;
        padding: 0.55rem 0.9rem; transition: all 0.2s ease;
    }}
    .arena-track-num {{ color: {TEXT_DIM}; font-weight: 700; font-size: 0.8rem; width: 22px; flex-shrink: 0; }}
    .arena-track-name {{ color: {TEXT}; font-weight: 600; font-size: 0.9rem; flex: 1; text-align: left; }}
    .arena-track-hidden {{ color: {TEXT_DIM}; letter-spacing: 0.1em; }}
    .arena-track-pts {{ color: {GREEN}; font-weight: 800; font-size: 0.8rem; }}
    .arena-track-found {{ background: rgba(29,185,84,0.10); border-color: rgba(29,185,84,0.35); }}
    .arena-track-missed {{ background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.35); }}
    .arena-track-missed .arena-track-name {{ color: #f87171; }}

    .arena-letter-badge {{
        width: 84px; height: 84px; margin: 0 auto 1.4rem; border-radius: 20px;
        background: linear-gradient(135deg, {GREEN} 0%, #12793a 100%);
        display: flex; align-items: center; justify-content: center;
        font-size: 2.6rem; font-weight: 900; color: #05130a;
        box-shadow: 0 10px 30px rgba(29,185,84,0.35);
    }}

    /* ─── Reveal spin: plays once when the badge (letter / artist) first
       appears, so choosing the round feels like a little roulette spin ─── */
    .arena-badge-spin-wrap {{
        position: relative;
        width: 84px; height: 84px;
        margin: 0 auto 1.4rem;
    }}
    .arena-badge-spin-wrap .arena-letter-badge {{
        margin: 0;
        position: relative;
        z-index: 2;
    }}
    .arena-badge-spin-ring {{
        position: absolute;
        inset: -12px;
        border-radius: 26px;
        background: conic-gradient(from 0deg, transparent 0%, {GREEN} 35%, #ffffff 50%, {GREEN} 65%, transparent 100%);
        opacity: 0;
        z-index: 1;
        pointer-events: none;
    }}
    .arena-badge-spin-ring.arena-ring-active {{
        animation: arenaRingSpin 1.5s linear 1, arenaRingFade 1.6s ease-out 1;
    }}
    @keyframes arenaRingSpin {{
        from {{ transform: rotate(0deg); }}
        to   {{ transform: rotate(1080deg); }}
    }}
    @keyframes arenaRingFade {{
        0%   {{ opacity: 0; }}
        8%   {{ opacity: 1; }}
        75%  {{ opacity: 1; }}
        100% {{ opacity: 0; }}
    }}
    .arena-letter-badge.arena-badge-spin {{
        animation: arenaBadgeSpin 1.5s cubic-bezier(0.16, 0.86, 0.3, 1) 1;
    }}
    @keyframes arenaBadgeSpin {{
        0%   {{ transform: rotate(0deg) scale(1); filter: blur(0px); }}
        12%  {{ filter: blur(3px); }}
        55%  {{ transform: rotate(1080deg) scale(1.12); filter: blur(2px); }}
        85%  {{ transform: rotate(1440deg) scale(1.15); filter: blur(0px); }}
        100% {{ transform: rotate(1440deg) scale(1); filter: blur(0px); }}
    }}

    .arena-found-list {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.8rem 0 1.2rem; justify-content: center; }}
    .arena-found-chip {{
        background: rgba(29,185,84,0.12); border: 1px solid rgba(29,185,84,0.35); color: {GREEN};
        border-radius: 999px; padding: 0.3rem 0.75rem; font-size: 0.78rem; font-weight: 700;
    }}
    .arena-waiting {{ text-align: center; color: {TEXT_MID}; font-size: 0.95rem; padding: 1.2rem 0; }}

    body:has(.st-key-arena_modal_overlay) {{ overflow: hidden !important; }}
    </style>
    """
    def _render_tracks_reveal(pool: dict, session: dict, reveal_round_no: int):
        round_row = get_round(pool["id"], reveal_round_no)
        tracks = get_round_tracks(pool["id"], reveal_round_no)
        found_map = get_track_answers_map(session["id"], reveal_round_no)
        total_tracks, found_count = len(tracks), len(found_map)
        
        game_meta = GAME_META["tracks"]
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">{escape(round_row["item_name"])}</div>'
            f'<div class="arena-subtitle">Album {reveal_round_no} '
            f'<span style="color:{TEXT_DIM};">/ {pool["round_count"]}</span> &nbsp;·&nbsp; '
            f'Found: <b>{found_count}/{total_tracks}</b></div>',
            unsafe_allow_html=True
        )

        st.markdown(f'''
        <div class="arena-reveal-frame" style="max-width:180px;"><img src="{escape(round_row["image_url"] or "")}" /></div>
        ''', unsafe_allow_html=True)

        rows_html = ""
        for i, trk in enumerate(tracks, start=1):
            if trk["track_id"] in found_map:
                pts = found_map[trk["track_id"]]["points_earned"]
                rows_html += (
                    f'<div class="arena-track-row arena-track-found">'
                    f'<span class="arena-track-num">{i}.</span>'
                    f'<span class="arena-track-name">{escape(trk["track_name"])}</span>'
                    f'<span class="arena-track-pts">+{pts}</span>'
                    f'</div>'
                )
            else:
                rows_html += (
                    f'<div class="arena-track-row arena-track-missed">'
                    f'<span class="arena-track-num">{i}.</span>'
                    f'<span class="arena-track-name">{escape(trk["track_name"])}</span>'
                    f'<span class="arena-track-pts" style="color: #f87171;">Missed</span>'
                    f'</div>'
                )
        st.markdown(f'<div class="arena-track-list">{rows_html}</div><br>', unsafe_allow_html=True)

        is_last = reveal_round_no >= pool["round_count"]
        btn_label = "🏁 See Results" if is_last else "Continue ⏭️"
        
        _, c_btn, _ = st.columns([1, 2, 1])
        with c_btn:
            if st.button(btn_label, key=f"arena_tracks_continue_{reveal_round_no}", use_container_width=True, type="primary"):
                del st.session_state["_arena_tracks_reveal"]
                if is_last:
                    finalize_session(session["id"])
                    st.query_params["arena_view"] = "recap"
                st.rerun()
                
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

                if st.button("✕", key="arena_close_btn"):
                    _close_arena()

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
        mode = st.session_state.get("arena_mode", "solo")
        eligible = is_arena_eligible(user_id)
        for game_type, meta in GAME_META.items():
            ok = eligible.get(game_type, False)
            solo_only_blocked = game_type in _SOLO_ONLY_GAME_TYPES and mode == "friends"
            with st.container():
                cols = st.columns([4, 1])
                cols[0].markdown(
                    f"**{meta['icon']} {meta['label']}**  \n"
                    f"<span style='color:{TEXT_MID};font-size:0.85rem;'>{meta['desc']}</span>",
                    unsafe_allow_html=True
                )
                disabled = (not ok) or solo_only_blocked
                if solo_only_blocked:
                    btn_label = "Solo only"
                elif not ok:
                    btn_label = "Not enough data"
                else:
                    btn_label = "Play"
                if cols[1].button(btn_label, key=f"arena_game_{game_type}", disabled=disabled):
                    st.session_state["arena_game_type"] = game_type
                    st.query_params["arena_view"] = "rounds"
                    st.rerun()

    def _segment_control(label: str, options: list[tuple], state_key: str, default,
                          accent_colors: dict | None = None):
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

        if game_type in _DUEL_GAME_TYPES:
            if mode == "friends":
                other_usernames = [u for u in user_dict.keys() if user_dict[u] != user_id]
                candidate_ids = [user_dict[u] for u in other_usernames]
                if game_type == "letter":
                    playable_ids = set(_letter_eligible_friend_ids(user_id, candidate_ids))
                else:
                    playable_ids = set(_discog_eligible_friend_ids(user_id, candidate_ids))
                playable = [u for u in other_usernames if user_dict[u] in playable_ids]
                if not playable:
                    msg = ("No friend shares enough overlapping-letter listening history yet."
                           if game_type == "letter" else
                           "No friend shares enough listening history with a common artist yet.")
                    st.info(msg)
                    return
                friend_username = st.selectbox("Duel who?", playable, key="arena_friend_select")
                friend_user_id = user_dict[friend_username]

            version_key = "arena_letter_version_seg" if game_type == "letter" else "arena_discog_version_seg"
            letter_version = _segment_control(
                "Version",
                [("rally", "🏓 Rally"), ("blitz", "⚡ Blitz")],
                version_key, "blitz",
            )
            if game_type == "letter":
                caption = (
                    f"{RALLY_TURN_SECONDS}s per turn, alternating. Miss the clock, or run out "
                    f"of valid songs, and you're out."
                    if letter_version == "rally" else
                    f"{BLITZ_SECONDS}s on the clock. Rarer songs in your history score more."
                )
            else:
                caption = (
                    f"{RALLY_TURN_SECONDS}s per turn, alternating. Name a song by the chosen "
                    f"artist that hasn't been said yet, or you're out."
                    if letter_version == "rally" else
                    f"{BLITZ_SECONDS}s on the clock. Name as many songs by the artist as you "
                    f"can — rarer deep cuts score more."
                )
            st.markdown(f'<div class="arena-segment-caption">{caption}</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            btn_label = "Spin the Letter" if game_type == "letter" else "Pick an Artist"
            btn_key = "arena_letter_start_btn" if game_type == "letter" else "arena_discog_start_btn"
            if st.button(btn_label, key=btn_key, type="primary", use_container_width=True):
                pool_id = create_pool(user_id, game_type, 0, mode, friend_user_id, "hard", letter_version)
                if pool_id is None:
                    err = ("Couldn't find a letter with enough eligible songs — try again after streaming more."
                           if game_type == "letter" else
                           "Couldn't find an artist with enough eligible songs — try again after streaming more.")
                    st.error(err)
                    return
                session = get_or_create_session(pool_id, user_id)
                st.session_state["arena_pool_id"] = pool_id
                st.session_state["arena_session_id"] = session["id"]
                st.query_params["arena_view"] = "play"
                st.rerun()
            return

        if mode == "friends" and game_type not in _SOLO_ONLY_GAME_TYPES:
            other_usernames = [u for u in user_dict.keys() if user_dict[u] != user_id]
            if not other_usernames:
                st.info("No other users to duel yet.")
                return
            friend_username = st.selectbox("Duel who?", other_usernames, key="arena_friend_select")
            friend_user_id = user_dict[friend_username]

        round_count = _segment_control(
            "How many albums?" if game_type == "tracks" else
            ("How many questions?" if game_type == "stats" else "How many rounds?"),
            [(5, "5"), (10, "10"), (20, "20")],
            "arena_round_count_seg", 10,
        )

        difficulty = "hard"
        reveal_mode = "blurred"
        if game_type == "stats":
            st.markdown("<div style='height:1.4rem;'></div>", unsafe_allow_html=True)
            st.markdown(
                f'<div class="arena-segment-caption">Multiple-choice questions about your own streaming '
                f'numbers — songs, albums, and artists. Pick the right answer before the clock runs out.</div>',
                unsafe_allow_html=True
            )
        elif game_type != "tracks":
            st.markdown("<div style='height:1.4rem;'></div>", unsafe_allow_html=True)

            if game_type in ("cover", "artist"):
                c_diff, c_rev = st.columns(2)
                with c_diff:
                    difficulty = _segment_control("Difficulty", [("easy", "🟢 Easy"), ("hard", "🔴 Hard")], "arena_difficulty_seg", "hard", accent_colors={"easy": GREEN, "hard": "#ef4444"})
                with c_rev:
                    reveal_mode = _segment_control("Reveal Style", [("blurred", "💧 Blurred"), ("corners", "🔲 Corners")], "arena_reveal_mode_seg", "blurred")
            else:
                difficulty = _segment_control("Difficulty", [("easy", "🟢 Easy"), ("hard", "🔴 Hard")], "arena_difficulty_seg", "hard", accent_colors={"easy": GREEN, "hard": "#ef4444"})

            caption = ("Always 4 multiple-choice options — no typing required."
                       if difficulty == "easy" else
                       "Type the exact name. Stuck? Spend a hint to reveal 4 options.")
            st.markdown(f'<div class="arena-segment-caption">{caption}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="arena-segment-caption">Type every track name on each album before the '
                f'clock runs out. Rarely-played deep cuts are worth the most points.</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Start Game", key="arena_start_btn", type="primary", use_container_width=True):
            game_type = st.session_state["arena_game_type"]
            pool_id = create_pool(user_id, game_type, round_count, mode, friend_user_id, difficulty, None, reveal_mode)
            if pool_id is None:
                st.error("Couldn't build this round — try again after streaming a bit more.")
                return
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

    def _render_tracks_gameplay(user_id: int, pool_id: int, pool: dict, session_id: int):
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
        session = dict(rows[0])

        if session["current_round"] > pool["round_count"]:
            finalize_session(session_id)
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        round_row = get_round(pool_id, session["current_round"])
        tracks = get_round_tracks(pool_id, session["current_round"])
        found_map = get_track_answers_map(session_id, session["current_round"])
        total_tracks, found_count = len(tracks), len(found_map)

        game_meta = GAME_META["tracks"]
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">{escape(round_row["item_name"])}</div>'
            f'<div class="arena-subtitle">Album {session["current_round"]} '
            f'<span style="color:{TEXT_DIM};">/ {pool["round_count"]}</span> &nbsp;·&nbsp; '
            f'Score: <b>{session["total_score"]}</b> &nbsp;·&nbsp; Found: <b>{found_count}/{total_tracks}</b></div>',
            unsafe_allow_html=True
        )

        start_key = f"arena_round_start_{session_id}_{session['current_round']}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown(f'''
        <div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>
        <div class="arena-reveal-frame" style="max-width:180px;"><img id="arena-reveal-img" src="{escape(round_row["image_url"] or "")}" /></div>
        ''', unsafe_allow_html=True)

        round_key = f"{session_id}_{session['current_round']}"
        dur_sec = get_round_duration(pool.get("game_type", "tracks"))
        render_round_timer_script(round_key, started_at * 1000, dur_sec, pool.get("game_type", "tracks"))

        rows_html = ""
        for i, trk in enumerate(tracks, start=1):
            found = found_map.get(trk["track_id"])
            if found:
                rows_html += (
                    f'<div class="arena-track-row arena-track-found">'
                    f'<span class="arena-track-num">{i}.</span>'
                    f'<span class="arena-track-name">{escape(trk["track_name"])}</span>'
                    f'<span class="arena-track-pts">+{found["points_earned"]}</span>'
                    f'</div>'
                )
            else:
                rows_html += (
                    f'<div class="arena-track-row">'
                    f'<span class="arena-track-num">{i}.</span>'
                    f'<span class="arena-track-name arena-track-hidden">?????</span>'
                    f'</div>'
                )
        st.markdown(f'<div class="arena-track-list">{rows_html}</div>', unsafe_allow_html=True)

        # SEAMLESS INPUT PROCESSOR
        def _on_guess_change():
            val = st.session_state.get("arena_hidden_guess_tracks", "")
            if not val: return
            guess_val = val.split("::")[0].strip()
            if not guess_val: return
            
            for trk in tracks:
                if trk["track_id"] in found_map: continue
                if _answer_matches(guess_val, trk["track_name"]):
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    pts = submit_track_answer(session, pool, round_row, trk, elapsed_ms)
                    if pts > 0:
                        st.toast(f"✅ {trk['track_name']} (+{pts} pts)", icon="🎯")
                        found_map[trk["track_id"]] = {"points_earned": pts}
                        if len(found_map) >= len(tracks):
                            st.session_state["_arena_tracks_reveal"] = session["current_round"]
                            finalize_track_round(session, pool, round_row)
                    break
            st.session_state["arena_hidden_guess_tracks"] = ""

        # 1. HIDE the real Streamlit input via CSS
        st.text_input(
            "arena_hidden_guess_input", key="arena_hidden_guess_tracks",
            label_visibility="collapsed", on_change=_on_guess_change
        )
        # 2. Render the container for our seamless JS input
        render_seamless_input_container()

        _, c_pass, _ = st.columns([1, 2, 1])
        with c_pass:
            if st.button("🏳️ Give up on this album", key=f"arena_tracks_giveup_{round_key}", use_container_width=True):
                st.session_state["_arena_tracks_reveal"] = session["current_round"]
                finalize_track_round(session, pool, round_row)
                st.rerun()

    # ─────────────────────────────────────────────────────────────────
    # Streaming Stats — trivia about the user's own listening numbers
    # ─────────────────────────────────────────────────────────────────

    def _render_stats_reveal(pool: dict, session: dict, reveal: dict):
        game_meta = GAME_META["stats"]
        answered_round_no = session["current_round"] - 1
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">Question {answered_round_no} <span style="font-size: 1.2rem; color: {TEXT_DIM};">/ {pool["round_count"]}</span></div>',
            unsafe_allow_html=True
        )

        if reveal["is_correct"]:
            st.markdown(
                f'<div class="arena-reveal-msg arena-reveal-correct">✅ Correct! +{reveal.get("points", 0)} pts</div>',
                unsafe_allow_html=True
            )
        else:
            correct_text = reveal["options"][reveal["correct_index"]]
            st.markdown(
                f'<div class="arena-reveal-msg arena-reveal-wrong">❌ Not quite — it was <b>{escape(correct_text)}</b></div>',
                unsafe_allow_html=True
            )

        st.markdown(f'<div class="arena-stats-question">{escape(reveal["question_text"])}</div>', unsafe_allow_html=True)

        opts_html = ""
        opts_html = ""
        option_counts = reveal.get("option_counts", [])
        q_type = reveal.get("question_type", "")
        
        for i, o in enumerate(reveal["options"]):
            cls = "arena-reveal-option"
            if i == reveal["correct_index"]:
                cls += " arena-reveal-correct-tile"
            elif i == reveal["chosen_idx"]:
                cls += " arena-reveal-wrong-tile"
                
            count_html = ""
            if option_counts and len(option_counts) > i:
                if q_type == "exact":
                    if i == reveal["correct_index"]:
                        count_html = f'<div style="font-size:0.8rem; opacity:0.8; margin-top:0.3rem;">Exact: {option_counts[i]} streams</div>'
                else:
                    count_html = f'<div style="font-size:0.8rem; opacity:0.8; margin-top:0.3rem;">{option_counts[i]} streams</div>'
                    
            opts_html += f'<div class="{cls}">{escape(o)}{count_html}</div>'
            
        st.markdown(f'<div class="arena-mc-grid">{opts_html}</div>', unsafe_allow_html=True)
        render_reveal_continue_script(reveal["round_key"])

    def _render_stats_gameplay(user_id: int, pool_id: int, pool: dict, session_id: int):
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
        session = dict(rows[0])

        reveal = st.session_state.get("_arena_stats_reveal")
        if reveal and reveal.get("round_key") == f"{session_id}_{session['current_round'] - 1}":
            _render_stats_reveal(pool, session, reveal)
            return

        if session["current_round"] > pool["round_count"]:
            finalize_session(session_id)
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        q = get_stats_question(pool_id, session["current_round"])
        if q is None:
            finalize_session(session_id)
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        game_meta = GAME_META["stats"]
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} {game_meta["label"]}</span></div>'
            f'<div class="arena-title">Question {session["current_round"]} '
            f'<span style="font-size: 1.2rem; color: {TEXT_DIM};">/ {pool["round_count"]}</span></div>'
            f'<div class="arena-subtitle">Score: <b>{session["total_score"]}</b></div>',
            unsafe_allow_html=True
        )

        start_key = f"arena_round_start_{session_id}_{session['current_round']}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown('<div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>',
                    unsafe_allow_html=True)
        round_key = f"{session_id}_{session['current_round']}"
        render_round_timer_script(round_key, started_at * 1000, REVEAL_SECONDS_DEFAULT, "stats",
                                   input_aria="arena_stats_timeout_input")

        st.markdown(f'<div class="arena-stats-question">{escape(q["question_text"])}</div>', unsafe_allow_html=True)

        opts_html = "".join(
            f'<div class="arena-stats-mc-option" data-idx="{i}">{escape(o)}</div>'
            for i, o in enumerate(q["options"])
        )
        st.markdown(f'<div class="arena-mc-grid">{opts_html}</div>', unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────────────
    # Letter Roulette / Discography Duel — gameplay UI (Rally / Blitz)
    # ─────────────────────────────────────────────────────────────────

    def render_badge_spin_script(spin_key: str | int):
        """Plays the one-time reveal spin on the badge (letter tile / artist
        photo) the first time it mounts for this pool. Uses a flag stored on
        the parent document so it survives Streamlit reruns and never
        replays mid-game — only the very first time a player sees it."""
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const flagKey = '__arenaBadgeSpun_' + {json.dumps(str(spin_key))};
            if (doc[flagKey]) return;

            function trySpin(retries) {{
                const badge = doc.querySelector('.arena-badge-spin-wrap .arena-letter-badge');
                const ring = doc.querySelector('.arena-badge-spin-ring');
                if (!badge) {{
                    if (retries > 0) setTimeout(function() {{ trySpin(retries - 1); }}, 60);
                    return;
                }}
                doc[flagKey] = true;
                badge.classList.add('arena-badge-spin');
                if (ring) ring.classList.add('arena-ring-active');
                setTimeout(function() {{
                    badge.classList.remove('arena-badge-spin');
                    if (ring) ring.classList.remove('arena-ring-active');
                }}, 1650);
            }}
            trySpin(10);
        }})();
        </script>
        """, height=0)

    def _duel_badge_html(pool: dict) -> str:
        """Renders the round 'badge' — a big letter tile for Letter Roulette,
        or the artist's photo (falling back to initials) for Discography Duel.
        Wrapped so a one-time spin/reveal effect can be layered on top."""
        if pool.get("game_type") == "discog":
            name = pool.get("target_artist_name") or "?"
            img = pool.get("target_artist_image")
            if img:
                inner = (
                    f'<div class="arena-letter-badge" style="padding:0;overflow:hidden;">'
                    f'<img src="{escape(img)}" style="width:100%;height:100%;object-fit:cover;" />'
                    f'</div>'
                )
            else:
                initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
                inner = f'<div class="arena-letter-badge" style="font-size:1.7rem;">{escape(initials)}</div>'
        else:
            inner = f'<div class="arena-letter-badge">{escape(pool.get("target_letter") or "?")}</div>'
        return (
            f'<div class="arena-badge-spin-wrap">'
            f'<div class="arena-badge-spin-ring"></div>'
            f'{inner}'
            f'</div>'
        )

    def _duel_title_html(pool: dict) -> str:
        """Artist name caption shown under the badge for Discography Duel."""
        if pool.get("game_type") == "discog":
            name = escape(pool.get("target_artist_name") or "Unknown artist")
            return f'<div class="arena-subtitle" style="margin-bottom:0.6rem;">{name}</div>'
        return ""

    def _render_letter_rally(user_id: int, pool: dict):
        if pool["status"] == "completed":
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        pool_songs = _load_letter_pool(pool)
        used_ids = _get_used_letter_song_ids(pool["id"])
        is_my_turn = pool["turn_user_id"] == user_id
        opponent_id = pool["friend_user_id"] if pool["mode"] == "friends" else None
        game_meta = GAME_META.get(pool.get("game_type"), GAME_META["letter"])

        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} Rally</span></div>'
            f'<div class="arena-title">Turn {pool["turn_number"]}</div>',
            unsafe_allow_html=True
        )
        st.markdown(_duel_badge_html(pool), unsafe_allow_html=True)
        render_badge_spin_script(f"{pool['id']}")
        badge_caption = _duel_title_html(pool)
        if badge_caption:
            st.markdown(badge_caption, unsafe_allow_html=True)

        found_chips = "".join(
            f'<span class="arena-found-chip">{escape(s["song_name"])}</span>'
            for s in pool_songs if s["song_id"] in used_ids
        )
        if found_chips:
            st.markdown(f'<div class="arena-found-list">{found_chips}</div>', unsafe_allow_html=True)

        if len(used_ids) >= len(pool_songs):
            _end_letter_rally(pool, loser_user_id=None)
            st.rerun()
            return

        if not is_my_turn:
            other_label = "your friend" if opponent_id else "the timer"
            st.markdown(f'<div class="arena-waiting">⏳ Waiting on {other_label}\'s turn…</div>', unsafe_allow_html=True)
            render_letter_poll_script(f"{pool['id']}_{pool['turn_number']}")
            return

        start_key = f"arena_letter_turn_start_{pool['id']}_{pool['turn_number']}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown('<div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>',
                    unsafe_allow_html=True)
        turn_key = f"{pool['id']}_{pool['turn_number']}"
        render_round_timer_script(turn_key, started_at * 1000, RALLY_TURN_SECONDS, "letter_rally",
                                   input_aria="arena_letter_rally_timeout_input")

        session = get_or_create_session(pool["id"], user_id)
        
        # SEAMLESS INPUT PROCESSOR
        def _on_submit():
            val = st.session_state.get("arena_hidden_guess_rally", "")
            if not val: return
            guess_val = val.split("::")[0].strip()
            if not guess_val: return
            
            song = _find_letter_match(guess_val, pool_songs, used_ids)
            if not song:
                st.toast("Not a valid, unused song for this round.", icon="❌")
            else:
                ok = _record_letter_answer(pool["id"], session["id"], song, pool["turn_number"])
                if not ok:
                    st.toast("That one was just claimed — try another!", icon="⚠️")
                else:
                    st.toast(f"✅ {song['song_name']} (+{song['points']} pts)", icon="🎯")
                    _advance_letter_turn(pool)
            
            st.session_state["arena_hidden_guess_rally"] = ""

        st.text_input("arena_hidden_guess_input", key="arena_hidden_guess_rally", label_visibility="collapsed", on_change=_on_submit)
        render_seamless_input_container()

        if st.button("🏳️ I've got nothing", key=f"arena_letter_rally_giveup_{turn_key}", use_container_width=True):
            _end_letter_rally(pool, loser_user_id=user_id)
            st.rerun()

    def _render_letter_blitz(user_id: int, pool: dict, session_id: int):
        pool_songs = _load_letter_pool(pool)
        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
        session = dict(rows[0])

        if session["status"] != "in_progress":
            st.query_params["arena_view"] = "recap"
            st.rerun()
            return

        used_ids = _get_used_letter_song_ids(pool["id"])
        game_meta = GAME_META.get(pool.get("game_type"), GAME_META["letter"])

        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{game_meta["icon"]} Blitz</span></div>'
            f'<div class="arena-title">Score: {session["total_score"]}</div>'
            f'<div class="arena-subtitle">Found {session["correct_count"]} songs</div>',
            unsafe_allow_html=True
        )
        st.markdown(_duel_badge_html(pool), unsafe_allow_html=True)
        render_badge_spin_script(f"{pool['id']}_{user_id}")
        badge_caption = _duel_title_html(pool)
        if badge_caption:
            st.markdown(badge_caption, unsafe_allow_html=True)

        mine = run_write_query(
            "SELECT song_name FROM arena_letter_answers WHERE pool_id=:p AND session_id=:s ORDER BY answered_at",
            {"p": pool["id"], "s": session_id}
        )
        found_chips = "".join(f'<span class="arena-found-chip">{escape(r["song_name"])}</span>' for r in mine)
        if found_chips:
            st.markdown(f'<div class="arena-found-list">{found_chips}</div>', unsafe_allow_html=True)

        start_key = f"arena_letter_blitz_start_{pool['id']}_{user_id}"
        if start_key not in st.session_state:
            st.session_state[start_key] = time.time()
        started_at = st.session_state[start_key]

        st.markdown('<div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>',
                    unsafe_allow_html=True)
        blitz_key = f"{pool['id']}_{user_id}"
        render_round_timer_script(blitz_key, started_at * 1000, BLITZ_SECONDS, "letter_blitz",
                                   input_aria="arena_letter_blitz_timeout_input")

        if len(used_ids) >= len(pool_songs):
            _end_letter_blitz_session(pool["id"], user_id)
            st.rerun()
            return

        # SEAMLESS INPUT PROCESSOR
        def _on_submit():
            val = st.session_state.get("arena_hidden_guess_blitz", "")
            if not val: return
            guess_val = val.split("::")[0].strip()
            if not guess_val: return
            
            song = _find_letter_match(guess_val, pool_songs, used_ids)
            if song:
                if _record_letter_answer(pool["id"], session_id, song, None):
                    st.toast(f"✅ {song['song_name']} (+{song['points']} pts)", icon="🎯")
                else:
                    st.toast("That one was just claimed — keep going!", icon="⚠️")
                    
            st.session_state["arena_hidden_guess_blitz"] = ""

        st.text_input("arena_hidden_guess_input", key="arena_hidden_guess_blitz", label_visibility="collapsed", on_change=_on_submit)
        render_seamless_input_container()

    def _render_letter_gameplay(user_id: int, pool_id: int, pool: dict, session_id: int):
        if pool.get("letter_version") == "rally":
            _render_letter_rally(user_id, pool)
        else:
            _render_letter_blitz(user_id, pool, session_id)

    def _render_gameplay(user_id: int):
        pool_id = st.session_state.get("arena_pool_id")
        session_id = st.session_state.get("arena_session_id")
        if not pool_id or not session_id:
            st.query_params["arena_view"] = "mode"
            st.rerun()
            return

        pool = get_pool(pool_id)

        if pool.get("game_type") in _DUEL_GAME_TYPES:
            _render_letter_gameplay(user_id, pool_id, pool, session_id)
            return

        if pool.get("game_type") == "stats":
            _render_stats_gameplay(user_id, pool_id, pool, session_id)
            return

        tracks_reveal_no = st.session_state.get("_arena_tracks_reveal")
        if pool.get("game_type") == "tracks" and tracks_reveal_no:
            rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
            session = dict(rows[0])
            _render_tracks_reveal(pool, session, tracks_reveal_no)
            return

        if pool.get("game_type") == "tracks":
            _render_tracks_gameplay(user_id, pool_id, pool, session_id)
            return

        rows = run_write_query("SELECT * FROM arena_sessions WHERE id=:id", {"id": session_id})
        session = dict(rows[0])

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

        reveal_mode = pool.get("reveal_mode", "blurred")
        corner_key = f"arena_corner_{session_id}_{session['current_round']}"
        if corner_key not in st.session_state:
            st.session_state[corner_key] = random.choice(["top left", "top right", "bottom left", "bottom right"])
        corner = st.session_state[corner_key]

        img_style = ""
        if pool.get("game_type") in ("cover", "artist"):
            if reveal_mode == "blurred":
                img_style = "filter: blur(22px);"
            else:
                img_style = f"transform-origin: {corner}; transform: scale(4);"

        st.markdown(f'''
        <div class="arena-progress-track"><div class="arena-progress-bar" id="arena-progress-bar"></div></div>
        <div class="arena-reveal-frame"><img id="arena-reveal-img" src="{escape(round_row["image_url"] or "")}" style="{img_style}" /></div>
        ''', unsafe_allow_html=True)

        round_key = f"{session_id}_{session['current_round']}"
        dur_sec = get_round_duration(pool.get("game_type", "cover"))
        render_round_timer_script(round_key, started_at * 1000, dur_sec, pool.get("game_type", "cover"), reveal_mode, corner)

        hint_key = f"arena_hint_{session_id}_{session['current_round']}"
        hint_active = st.session_state.get(hint_key, False)
        show_mc = easy_mode or hint_active

        if not show_mc:
            guess = st.text_input("Your guess", key=f"arena_guess_{round_key}", label_visibility="collapsed",
                                   placeholder="Type the exact name…")
            
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
                    points = submit_round_answer(session, pool, round_row, False, not easy_mode, elapsed_ms)
                    st.toast("Round Skipped!", icon="⏭️")
                    if session["current_round"] >= pool["round_count"]:
                        finalize_session(session_id)
                        st.query_params["arena_view"] = "recap"
                    st.rerun()

    def _render_letter_recap(user_id: int, pool: dict, session: dict):
        meta = GAME_META.get(pool.get("game_type"), GAME_META["letter"])
        version_label = "🏓 Rally" if pool.get("letter_version") == "rally" else "⚡ Blitz"
        _modal_header(f'{meta["icon"]} {meta["label"]}', "🏁 Recap", version_label)

        if pool.get("letter_version") == "rally":
            if pool.get("loser_user_id") is None:
                st.success("✨ Full clear — you cleared the entire pool together!")
            elif pool["loser_user_id"] == user_id:
                st.error("💥 You missed a beat. Rally over.")
            else:
                st.success("🏆 Your opponent missed a beat — you win!")

            c1, c2 = st.columns(2)
            c1.metric("Your score", session["total_score"])
            c1.metric("Songs found", session["correct_count"])
            if pool["mode"] == "friends":
                other_uid = pool["friend_user_id"] if pool["host_user_id"] == user_id else pool["host_user_id"]
                opp = _get_session_row(pool["id"], other_uid)
                if opp:
                    c2.metric("Opponent score", opp["total_score"])
                    c2.metric("Opponent found", opp["correct_count"])
        else:
            c1, c2 = st.columns(2)
            c1.metric("Your score", session["total_score"])
            c1.metric("Songs found", session["correct_count"])
            if pool["mode"] == "friends":
                other_uid = pool["friend_user_id"] if pool["host_user_id"] == user_id else pool["host_user_id"]
                opp = _get_session_row(pool["id"], other_uid)
                if opp and opp["status"] == "completed":
                    c2.metric("Opponent score", opp["total_score"])
                    c2.metric("Opponent found", opp["correct_count"])
                    if opp["total_score"] > session["total_score"]:
                        st.info("Your friend edged you out this round!")
                    elif session["total_score"] > opp["total_score"]:
                        st.success("You beat your friend's score!")
                else:
                    st.info("⏳ Waiting on your friend to finish their Blitz run.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Play Again", key="arena_letter_play_again_btn", type="primary", use_container_width=True):
            st.query_params["arena_view"] = "mode"
            for k in ("arena_pool_id", "arena_session_id", "arena_mode", "arena_game_type",
                      "arena_letter_version_seg", "arena_discog_version_seg"):
                st.session_state.pop(k, None)
            st.rerun()

    def _render_recap(user_id: int):
        session_id = st.session_state.get("arena_session_id")
        if not session_id:
            st.query_params["arena_view"] = "mode"
            st.rerun()
            return
        recap = get_recap(session_id)
        session, pool = recap["session"], recap["pool"]

        if pool.get("game_type") in _DUEL_GAME_TYPES:
            _render_letter_recap(user_id, pool, session)
            return

        recap_meta = GAME_META.get(pool.get("game_type"), GAME_META["cover"])
        st.markdown(
            f'<div class="arena-kicker-wrap"><span class="arena-kicker">{recap_meta["icon"]} {recap_meta["label"]}</span></div>'
            f'<div class="arena-title">🏁 Match Recap</div><br>',
            unsafe_allow_html=True
        )
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Score", session["total_score"])
        if pool.get("game_type") == "tracks":
            found, total = get_tracks_totals(pool["id"], session["id"])
            c2.metric("Tracks Found", f"{found}/{total}")
        else:
            c2.metric("Correct", f"{session['correct_count']}/{pool['round_count']}")
        c3.metric("Best Round", session["best_round_score"])
        if pool.get("game_type") == "stats":
            accuracy = round(100 * session["correct_count"] / max(1, pool["round_count"]))
            c4.metric("Accuracy", f"{accuracy}%")
        elif pool.get("difficulty") == "easy":
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