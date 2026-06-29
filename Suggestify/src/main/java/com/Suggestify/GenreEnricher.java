package com.Suggestify;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GenreEnricher {

    private static final String LASTFM_API_KEY = "ΒΑΛΕ_ΕΔΩ_ΤΟ_API_KEY_ΣΟΥ"; // Μην το ξεχάσεις!
    private static final Pattern TAG_PATTERN = Pattern.compile("\"name\":\"([^\"]+)\"");

    public void enrichAlbums() {
        // Βρίσκουμε τα άλμπουμ χωρίς genre ΚΑΙ τον κύριο καλλιτέχνη τους
        String selectAlbumsSQL = """
            WITH AlbumArtist AS (
                SELECT so.album_id, a.name,
                       ROW_NUMBER() OVER(PARTITION BY so.album_id ORDER BY COUNT(so.id) DESC) as rnk
                FROM songs so
                JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE so.album_id IS NOT NULL
                GROUP BY so.album_id, a.name
            )
            SELECT al.id, al.title, aa.name AS artist_name
            FROM albums al
            JOIN AlbumArtist aa ON aa.album_id = al.id AND aa.rnk = 1
            WHERE al.id NOT IN (SELECT album_id FROM album_genres)
        """;

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement stmt = conn.prepareStatement(selectAlbumsSQL);
             ResultSet rs = stmt.executeQuery()) {

            HttpClient client = HttpClient.newHttpClient();
            int count = 0;

            System.out.println("Ξεκινάει ο εμπλουτισμός Genres για Albums από το Last.fm...");

            while (rs.next()) {
                int albumId = rs.getInt("id");
                String albumTitle = rs.getString("title");
                String artistName = rs.getString("artist_name");

                List<String> topGenres = fetchTopAlbumGenres(client, artistName, albumTitle);

                if (!topGenres.isEmpty()) {
                    saveAlbumGenresToDatabase(conn, albumId, topGenres);
                    System.out.println("✅ " + albumTitle + " -> " + String.join(", ", topGenres));
                } else {
                    System.out.println("⚠️ No genres: " + albumTitle);
                    saveAlbumGenresToDatabase(conn, albumId, List.of("unknown"));
                }

                count++;
                Thread.sleep(200); // Rate Limiting
            }
            System.out.println("Ολοκληρώθηκε! Ενημερώθηκαν " + count + " albums.");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private List<String> fetchTopAlbumGenres(HttpClient client, String artistName, String albumTitle) {
        List<String> validGenres = new ArrayList<>();
        try {
            String encodedArtist = URLEncoder.encode(artistName, StandardCharsets.UTF_8);
            String encodedAlbum = URLEncoder.encode(albumTitle, StandardCharsets.UTF_8);
            // ΝΕΟ ENDPOINT: album.gettoptags
            String url = "http://ws.audioscrobbler.com/2.0/?method=album.gettoptags&artist=" +
                    encodedArtist + "&album=" + encodedAlbum + "&api_key=" + LASTFM_API_KEY + "&format=json";

            HttpRequest request = HttpRequest.newBuilder().uri(URI.create(url)).GET().build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                Matcher matcher = TAG_PATTERN.matcher(response.body());
                while (matcher.find() && validGenres.size() < 3) {
                    String tag = matcher.group(1).toLowerCase().trim();
                    if (isValidGenre(tag)) validGenres.add(tag);
                }
            }
        } catch (Exception e) {}
        return validGenres;
    }

    private boolean isValidGenre(String tag) {
        if (tag.length() < 3 || tag.length() > 25) return false;
        if (tag.matches(".*\\d.*")) return false;
        List<String> blacklist = List.of(
                "seen live", "awesome", "favorite", "love at first listen", "albums i own",
                "beautiful", "amazing", "canadian", "american", "british", "masterpiece"
        );
        return !blacklist.contains(tag);
    }

    private void saveAlbumGenresToDatabase(Connection conn, int albumId, List<String> genres) throws Exception {
        String insertGenreSQL = "INSERT INTO genres (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectGenreSQL = "SELECT id FROM genres WHERE name = ?";
        String insertRelationSQL = "INSERT INTO album_genres (album_id, genre_id) VALUES (?, ?) ON CONFLICT DO NOTHING";

        for (String genreName : genres) {
            int genreId = -1;
            try (PreparedStatement insertStmt = conn.prepareStatement(insertGenreSQL)) {
                insertStmt.setString(1, genreName);
                insertStmt.executeUpdate();
            }
            try (PreparedStatement selectStmt = conn.prepareStatement(selectGenreSQL)) {
                selectStmt.setString(1, genreName);
                try (ResultSet rs = selectStmt.executeQuery()) {
                    if (rs.next()) genreId = rs.getInt("id");
                }
            }
            if (genreId != -1) {
                try (PreparedStatement relStmt = conn.prepareStatement(insertRelationSQL)) {
                    relStmt.setInt(1, albumId);
                    relStmt.setInt(2, genreId);
                    relStmt.executeUpdate();
                }
            }
        }
    }
}