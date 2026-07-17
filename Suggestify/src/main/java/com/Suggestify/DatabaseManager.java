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

        String createArtistsTable = "CREATE TABLE IF NOT EXISTS artists (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, image_url VARCHAR(500));";

        String createAlbumsTable = """
            CREATE TABLE IF NOT EXISTS albums (
                id SERIAL PRIMARY KEY, 
                title VARCHAR(255) UNIQUE NOT NULL,
                release_date DATE,
                primary_genre VARCHAR(100),
                total_tracks INT,
                label VARCHAR(255),
                is_explicit BOOLEAN DEFAULT FALSE
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
                preview_url VARCHAR(500)
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
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_song_rating UNIQUE (user_id, song_id)
            );
            CREATE INDEX IF NOT EXISTS idx_song_ratings_song   ON song_ratings(song_id);
            CREATE INDEX IF NOT EXISTS idx_song_ratings_rating ON song_ratings(rating);
            
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
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_album_rating UNIQUE (user_id, album_id)
            );
            CREATE INDEX IF NOT EXISTS idx_album_ratings_album  ON album_ratings(album_id);
            CREATE INDEX IF NOT EXISTS idx_album_ratings_rating ON album_ratings(rating);
            
            DROP TRIGGER IF EXISTS trg_album_ratings_updated_at ON album_ratings;
            CREATE TRIGGER trg_album_ratings_updated_at
                BEFORE UPDATE ON album_ratings
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
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

            // Εκτέλεση των νέωνινάκων για Ratings
            stmt.execute(createTriggerFunction);
            stmt.execute(createSongRatingsTable);
            stmt.execute(createAlbumRatingsTable);

            try {
                stmt.execute("ALTER TABLE songs ADD CONSTRAINT unique_song_uri UNIQUE (track_uri);");
            } catch (Exception ignored) {
            }

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}