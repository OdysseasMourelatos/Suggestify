package com.Suggestify;

import java.net.URI;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

public class DatabaseManager {

    public static Connection getConnection() throws Exception {
        String envDbUrl = System.getenv("DATABASE_URL");

        if (envDbUrl != null && !envDbUrl.trim().isEmpty()) {
            // Διαβάζει το URL από την Python
            URI dbUri = new URI(envDbUrl.replace("jdbc:", "")); 
            
            String username = dbUri.getUserInfo() != null ? dbUri.getUserInfo().split(":")[0] : "postgres.pxpplxyszvrzubdqykmw";
            String password = dbUri.getUserInfo() != null ? dbUri.getUserInfo().split(":")[1] : "dKPJjO2jZtkmwjYh";
            int port = dbUri.getPort() != -1 ? dbUri.getPort() : 5432;

            String dbUrl = "jdbc:postgresql://" + dbUri.getHost() + ":" + port + dbUri.getPath() + "?reWriteBatchedInserts=true&prepareThreshold=0";

            return DriverManager.getConnection(dbUrl, username, password);
        } else {
            // Hardcoded Fallback (Supabase Session Pooler IPv4)
            String URL = "jdbc:postgresql://aws-0-eu-west-1.pooler.supabase.com:5432/postgres?reWriteBatchedInserts=true&prepareThreshold=0";
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
                title VARCHAR(255) UNIQUE NOT NULL
            );
        """;

        String createSongsTable = """
            CREATE TABLE IF NOT EXISTS songs (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                album_id INT REFERENCES albums(id),
                track_uri VARCHAR(255),
                image_url VARCHAR(500)
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

            // Προσθήκη του constraint σιωπηλά, αγνοώντας το σφάλμα αν υπάρχει ήδη
            try {
                stmt.execute("ALTER TABLE songs ADD CONSTRAINT unique_song_uri UNIQUE (track_uri);");
            } catch (Exception ignored) {
                // Η βάση έχει ήδη το constraint, προχωράμε κανονικά
            }

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}