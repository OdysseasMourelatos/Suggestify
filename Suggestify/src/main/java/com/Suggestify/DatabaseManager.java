package com.Suggestify;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

public class DatabaseManager {

    private static final String URL = "jdbc:postgresql://localhost:5432/spotify_db";
    private static final String USER = "postgres";
    private static final String PASSWORD = "secret";

    public static Connection getConnection() throws Exception {
        return DriverManager.getConnection(URL, USER, PASSWORD);
    }

    public static void initializeSchema() {
        String createArtistsTable = "CREATE TABLE IF NOT EXISTS artists (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, image_url VARCHAR(500));";
        String dropTables = "DROP TABLE IF EXISTS streams, song_artists, songs, artists, albums CASCADE;";


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

        String createStreamsTable = """
            CREATE TABLE IF NOT EXISTS streams (
                id SERIAL PRIMARY KEY,
                song_id INT REFERENCES songs(id),
                played_at TIMESTAMP NOT NULL,
                ms_played INT
            );
        """;

        try (Connection conn = getConnection();
             Statement stmt = conn.createStatement()) {
            stmt.execute(dropTables);

            stmt.execute(createArtistsTable);
            stmt.execute(createAlbumsTable);
            stmt.execute(createSongsTable);
            stmt.execute(createSongArtistsTable);
            stmt.execute(createStreamsTable);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}