package com.Suggestify;

import java.net.URI;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

public class DatabaseManager {

    public static Connection getConnection() throws Exception {
        String envDbUrl = System.getenv("DATABASE_URL");

        if (envDbUrl != null && !envDbUrl.trim().isEmpty()) {
            // Διαβάζει το URL από το Streamlit / Python
            URI dbUri = new URI(envDbUrl.replace("jdbc:", ""));

            String username = dbUri.getUserInfo() != null ? dbUri.getUserInfo().split(":")[0] : "postgres.pxpplxyszvrzubdqykmw";
            String password = dbUri.getUserInfo() != null ? dbUri.getUserInfo().split(":")[1] : "dKPJjO2jZtkmwjYh";
            int port = dbUri.getPort() != -1 ? dbUri.getPort() : 6543;

            // ΠΡΟΣΟΧΗ: Προστέθηκε το sslmode=require στο τέλος! Είναι απολύτως απαραίτητο για το Supabase.
            String dbUrl = "jdbc:postgresql://" + dbUri.getHost() + ":" + port + dbUri.getPath() + "?reWriteBatchedInserts=true&prepareThreshold=0&sslmode=require";

            return DriverManager.getConnection(dbUrl, username, password);
        } else {
            // Το σωστό Pooler URL με Transaction Port (6543) και sslmode
            String URL = "jdbc:postgresql://aws-0-eu-west-1.pooler.supabase.com:6543/postgres?reWriteBatchedInserts=true&prepareThreshold=0&sslmode=require";
            String USER = "postgres.pxpplxyszvrzubdqykmw";
            String PASSWORD = "dKPJjO2jZtkmwjYh";

            return DriverManager.getConnection(URL, USER, PASSWORD);
        }
    }

    public static void initializeSchema() {
        String createUsersTable = """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """;

        String createArtistsTable = "CREATE TABLE IF NOT EXISTS artists (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, image_url VARCHAR(500), spotify_id VARCHAR(50) UNIQUE, popularity INT DEFAULT 0, genres TEXT);";

        String createAlbumsTable = """
            CREATE TABLE IF NOT EXISTS albums (
                id SERIAL PRIMARY KEY, 
                title VARCHAR(255) UNIQUE NOT NULL,
                release_date DATE,
                primary_genre VARCHAR(100),
                total_tracks INT,
                label VARCHAR(255),
                is_explicit BOOLEAN DEFAULT FALSE,
                spotify_id VARCHAR(50) UNIQUE
            );
        """;

        String createSongsTable = """
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                album_id INT REFERENCES albums(id),
                track_uri VARCHAR(255),
                image_url VARCHAR(500),
                duration_ms INT,
                release_date DATE,
                primary_genre VARCHAR(100),
                is_explicit BOOLEAN DEFAULT FALSE,
                preview_url VARCHAR(500),
                spotify_id VARCHAR(50) UNIQUE,
                popularity INT DEFAULT 0,
                tempo NUMERIC(6,3),
                energy NUMERIC(4,3),
                danceability NUMERIC(4,3),
                valence NUMERIC(4,3),
                acousticness NUMERIC(4,3)
            );
        """;

        String createSongArtistsTable = """
            CREATE TABLE IF NOT EXISTS song_artists (
                song_id INT REFERENCES songs(id),
                artist_id INT REFERENCES artists(id),
                is_feature BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (song_id, artist_id)
            );
        """;

        String createGenresTable = """
            CREATE TABLE IF NOT EXISTS genres (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            );
        """;

        String createAlbumGenresTable = """
            CREATE TABLE IF NOT EXISTS album_genres (
                album_id INT REFERENCES albums(id) ON DELETE CASCADE,
                genre_id INT REFERENCES genres(id) ON DELETE CASCADE,
                PRIMARY KEY (album_id, genre_id)
            );
        """;

        String createStreamsTable = """
            CREATE TABLE IF NOT EXISTS streams (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                song_id INT REFERENCES songs(id),
                played_at TIMESTAMP NOT NULL,
                ms_played INT
            );
        """;

        // ── ΝΕΟΙ ΠΙΝΑΚΕΣ ΓΙΑ ΤΑ RATINGS ──────────────────────────────────────

        String createTriggerFunction = """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = now();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """;

        String createSongRatingsTable = """
            CREATE TABLE IF NOT EXISTS song_ratings (
                id          BIGSERIAL PRIMARY KEY,
                user_id     INTEGER  NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
                song_id     INTEGER  NOT NULL REFERENCES songs(id)  ON DELETE CASCADE,
                rating      NUMERIC(3,1) NOT NULL CHECK (rating > 0 AND rating <= 10),
                sort_weight DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
                review      TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_song_rating UNIQUE (user_id, song_id)
            );
            CREATE INDEX IF NOT EXISTS idx_song_ratings_song   ON song_ratings(song_id);
            CREATE INDEX IF NOT EXISTS idx_song_ratings_rating ON song_ratings(rating);
            CREATE INDEX IF NOT EXISTS idx_song_ratings_weight ON song_ratings(sort_weight);
            
            DROP TRIGGER IF EXISTS trg_song_ratings_updated_at ON song_ratings;
            CREATE TRIGGER trg_song_ratings_updated_at
                BEFORE UPDATE ON song_ratings
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """;

        String createAlbumRatingsTable = """
            CREATE TABLE IF NOT EXISTS album_ratings (
                id          BIGSERIAL PRIMARY KEY,
                user_id     INTEGER  NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
                album_id    INTEGER  NOT NULL REFERENCES albums(id)  ON DELETE CASCADE,
                rating      NUMERIC(3,1) NOT NULL CHECK (rating > 0 AND rating <= 10),
                sort_weight DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
                review      TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_album_rating UNIQUE (user_id, album_id)
            );
            CREATE INDEX IF NOT EXISTS idx_album_ratings_album  ON album_ratings(album_id);
            CREATE INDEX IF NOT EXISTS idx_album_ratings_rating ON album_ratings(rating);
            CREATE INDEX IF NOT EXISTS idx_album_ratings_weight ON album_ratings(sort_weight);
            
            DROP TRIGGER IF EXISTS trg_album_ratings_updated_at ON album_ratings;
            CREATE TRIGGER trg_album_ratings_updated_at
                BEFORE UPDATE ON album_ratings
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """;

        String createArtistRatingsTable = """
            CREATE TABLE IF NOT EXISTS artist_ratings (
                id          BIGSERIAL PRIMARY KEY,
                user_id     INTEGER  NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
                artist_id   INTEGER  NOT NULL REFERENCES artists(id)  ON DELETE CASCADE,
                rating      NUMERIC(3,1) NOT NULL CHECK (rating > 0 AND rating <= 10),
                sort_weight DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()),
                review      TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_artist_rating UNIQUE (user_id, artist_id)
            );
            CREATE INDEX IF NOT EXISTS idx_artist_ratings_artist  ON artist_ratings(artist_id);
            CREATE INDEX IF NOT EXISTS idx_artist_ratings_rating ON artist_ratings(rating);
            CREATE INDEX IF NOT EXISTS idx_artist_ratings_weight ON artist_ratings(sort_weight);
            
            DROP TRIGGER IF EXISTS trg_artist_ratings_updated_at ON artist_ratings;
            CREATE TRIGGER trg_artist_ratings_updated_at
                BEFORE UPDATE ON artist_ratings
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """;

        // ── ΝΕΟΙ ΠΙΝΑΚΕΣ ΓΙΑ ΤΟ ARENA ────────────────────────────────────────

        String createArenaPoolsTable = """
            CREATE TABLE IF NOT EXISTS arena_pools (
                id              BIGSERIAL PRIMARY KEY,
                mode            VARCHAR(20) NOT NULL CHECK (mode IN ('solo','friends')),
                game_type       VARCHAR(20) NOT NULL CHECK (game_type IN ('cover','artist')),
                round_count     INT NOT NULL CHECK (round_count IN (5,10,20)),
                hint_budget     INT NOT NULL,
                host_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                friend_user_id  INTEGER REFERENCES users(id) ON DELETE CASCADE,
                status          VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed')),
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_arena_pools_host   ON arena_pools(host_user_id);
            CREATE INDEX IF NOT EXISTS idx_arena_pools_friend ON arena_pools(friend_user_id);
        """;

        String createArenaPoolRoundsTable = """
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
        """;

        String createArenaSessionsTable = """
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
        """;

        String createArenaRoundAnswersTable = """
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
        """;

        try (Connection conn = getConnection();
             Statement stmt = conn.createStatement()) {

            stmt.execute(createUsersTable);
            stmt.execute(createArtistsTable);
            stmt.execute(createAlbumsTable);
            stmt.execute(createSongsTable);
            stmt.execute(createSongArtistsTable);
            stmt.execute(createGenresTable);
            stmt.execute(createAlbumGenresTable);
            stmt.execute(createStreamsTable);

            // Εκτέλεση των πινάκων για Ratings
            stmt.execute(createTriggerFunction);
            stmt.execute(createSongRatingsTable);
            stmt.execute(createAlbumRatingsTable);
            stmt.execute(createArtistRatingsTable);

            // ── ΕΚΤΕΛΕΣΗ ΤΩΝ ΠΙΝΑΚΩΝ ΓΙΑ ΤΟ ARENA ──
            stmt.execute(createArenaPoolsTable);
            stmt.execute(createArenaPoolRoundsTable);
            stmt.execute(createArenaSessionsTable);
            stmt.execute(createArenaRoundAnswersTable);

            try {
                stmt.execute("ALTER TABLE songs ADD CONSTRAINT unique_song_uri UNIQUE (track_uri);");
            } catch (Exception ignored) {
            }

            // ── MIGRATION: ΠΡΟΣΘΗΚΗ ΤΩΝ ΝΕΩΝ ΣΤΗΛΩΝ ΣΕ ΥΠΑΡΧΟΥΣΑ ΒΑΣΗ ──
            try {
                // 1. Βασικά Spotify IDs
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS spotify_id VARCHAR(50) UNIQUE;");
                stmt.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_id VARCHAR(50) UNIQUE;");
                stmt.execute("ALTER TABLE albums ADD COLUMN IF NOT EXISTS spotify_id VARCHAR(50) UNIQUE;");
                
                // 2. Audio Features (Spotify)
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS popularity INT DEFAULT 0;");
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS tempo NUMERIC(6,3);");
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS energy NUMERIC(4,3);");
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS danceability NUMERIC(4,3);");
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS valence NUMERIC(4,3);");
                stmt.execute("ALTER TABLE songs ADD COLUMN IF NOT EXISTS acousticness NUMERIC(4,3);");
                
                // 3. Artist Metadata (Spotify)
                stmt.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS popularity INT DEFAULT 0;");
                stmt.execute("ALTER TABLE artists ADD COLUMN IF NOT EXISTS genres TEXT;");
                
                // 4. Δημιουργία Indexes για ταχύτητα
                stmt.execute("CREATE INDEX IF NOT EXISTS idx_songs_spotify_id ON songs(spotify_id);");
                stmt.execute("CREATE INDEX IF NOT EXISTS idx_artists_spotify_id ON artists(spotify_id);");
                stmt.execute("CREATE INDEX IF NOT EXISTS idx_albums_spotify_id ON albums(spotify_id);");
                
                System.out.println("✅ Spotify Ultimate Migration completed successfully!");
            } catch (Exception e) {
                System.out.println("ℹ️ Spotify Migration check: " + e.getMessage());
            }

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}