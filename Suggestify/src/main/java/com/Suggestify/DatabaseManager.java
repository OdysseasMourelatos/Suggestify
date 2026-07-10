package com.Suggestify;

import java.net.URI;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

public class DatabaseManager {

    public static Connection getConnection() throws Exception {
        String envDbUrl = System.getenv("DATABASE_URL");

        if (envDbUrl != null && !envDbUrl.trim().isEmpty()) {
            URI dbUri = new URI(envDbUrl);
            String username = dbUri.getUserInfo().split(":")[0];
            String password = dbUri.getUserInfo().split(":")[1];
            int port = dbUri.getPort() != -1 ? dbUri.getPort() : 5432;

            String dbUrl = "jdbc:postgresql://" + dbUri.getHost() + ":" + port + dbUri.getPath() + "?reWriteBatchedInserts=true&prepareThreshold=0";

            return DriverManager.getConnection(dbUrl, username, password);
        } else {
            String URL = "jdbc:postgresql://localhost:5432/spotify_db";
            String USER = "postgres";
            String PASSWORD = "secret";
            return DriverManager.getConnection("jdbc:postgresql://localhost:5432/spotify_db?reWriteBatchedInserts=true", "postgres", "secret");
        }
    }

    public static void initializeSchema() {
        //String dropTables = "DROP TABLE IF EXISTS streams, album_genres, genres, song_artists, songs, artists, albums, users CASCADE;";

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

            //stmt.execute(dropTables);

            stmt.execute(createUsersTable);
            stmt.execute(createArtistsTable);
            stmt.execute(createAlbumsTable);
            stmt.execute(createSongsTable);
            stmt.execute(createSongArtistsTable);
            stmt.execute(createGenresTable);
            stmt.execute(createAlbumGenresTable);
            stmt.execute(createStreamsTable);

            stmt.execute("ALTER TABLE songs ADD CONSTRAINT unique_song_uri UNIQUE (track_uri);");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}