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
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GenreEnricher {

    private static final String LASTFM_API_KEY = "9eee586b5f031e6b2740463c6d5f96a1";

    private static final Pattern TAG_PATTERN = Pattern.compile("\"name\":\"([^\"]+)\"");

    public void enrichArtists() {
        String selectArtistsSQL = """
            SELECT id, name FROM artists 
            WHERE id NOT IN (SELECT artist_id FROM artist_genres)
        """;

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement stmt = conn.prepareStatement(selectArtistsSQL);
             ResultSet rs = stmt.executeQuery()) {

            HttpClient client = HttpClient.newHttpClient();
            int count = 0;

            System.out.println("Ξεκινάει ο εμπλουτισμός Genres από το Last.fm...");

            while (rs.next()) {
                int artistId = rs.getInt("id");
                String artistName = rs.getString("name");

                List<String> topGenres = fetchTopGenresFromLastFm(client, artistName);

                if (!topGenres.isEmpty()) {
                    saveGenresToDatabase(conn, artistId, topGenres);
                    System.out.println("✅ " + artistName + " -> " + String.join(", ", topGenres));
                } else {
                    System.out.println("⚠️ Δεν βρέθηκαν genres για: " + artistName);
                    saveGenresToDatabase(conn, artistId, List.of("unknown"));
                }

                count++;

                Thread.sleep(200);
            }

            System.out.println("Ολοκληρώθηκε! Ενημερώθηκαν " + count + " καλλιτέχνες.");

        } catch (Exception e) {
            System.err.println("Σφάλμα κατά τον εμπλουτισμό: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private List<String> fetchTopGenresFromLastFm(HttpClient client, String artistName) {
        List<String> validGenres = new ArrayList<>();
        try {
            String encodedArtist = URLEncoder.encode(artistName, StandardCharsets.UTF_8);
            String url = "http://ws.audioscrobbler.com/2.0/?method=artist.gettoptags&artist=" +
                    encodedArtist + "&api_key=" + LASTFM_API_KEY + "&format=json";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                Matcher matcher = TAG_PATTERN.matcher(response.body());

                while (matcher.find() && validGenres.size() < 5) {
                    String tag = matcher.group(1).toLowerCase().trim();
                    if (isValidGenre(tag)) {
                        validGenres.add(tag);
                    }
                }
            }
        } catch (Exception e) {
            // Αγνοούμε τα μεμονωμένα errors για να μην σταματήσει το loop
        }
        return validGenres;
    }

    private boolean isValidGenre(String tag) {
        if (tag.length() < 3 || tag.length() > 25) return false;
        if (tag.matches(".*\\d.*")) return false; // Πετάμε tags με νούμερα (π.χ. "00s", "2010s")

        List<String> blacklist = List.of(
                "seen live", "awesome", "favorite", "love at first listen",
                "beautiful", "amazing", "canadian", "american", "british"
        );
        return !blacklist.contains(tag);
    }

    private void saveGenresToDatabase(Connection conn, int artistId, List<String> genres) throws Exception {
        String insertGenreSQL = "INSERT INTO genres (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectGenreSQL = "SELECT id FROM genres WHERE name = ?";
        String insertRelationSQL = "INSERT INTO artist_genres (artist_id, genre_id) VALUES (?, ?) ON CONFLICT DO NOTHING";

        for (String genreName : genres) {
            int genreId = -1;

            try (PreparedStatement insertStmt = conn.prepareStatement(insertGenreSQL)) {
                insertStmt.setString(1, genreName);
                insertStmt.executeUpdate();
            }

            try (PreparedStatement selectStmt = conn.prepareStatement(selectGenreSQL)) {
                selectStmt.setString(1, genreName);
                try (ResultSet rs = selectStmt.executeQuery()) {
                    if (rs.next()) {
                        genreId = rs.getInt("id");
                    }
                }
            }

            if (genreId != -1) {
                try (PreparedStatement relStmt = conn.prepareStatement(insertRelationSQL)) {
                    relStmt.setInt(1, artistId);
                    relStmt.setInt(2, genreId);
                    relStmt.executeUpdate();
                }
            }
        }
    }
}