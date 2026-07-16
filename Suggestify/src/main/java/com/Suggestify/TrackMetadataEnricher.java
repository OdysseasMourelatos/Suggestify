package com.Suggestify;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class TrackMetadataEnricher {

    public static void main(String[] args) {
        System.out.println("🚀 Starting iTunes Track Metadata & Feature Hunter...");

        // ΒΕΛΤΙΩΣΗ 1: LIMIT 1000 για ταχύτητα. Φέρνει τα Top 1000 που ΔΕΝ έχουμε ελέγξει ακόμα.
        String selectOrphansSQL = """
            SELECT so.id, so.title, MAX(a.name) AS artist_name
            FROM songs so
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            JOIN streams s ON s.song_id = so.id
            WHERE so.duration_ms IS NULL
            GROUP BY so.id, so.title
            ORDER BY COUNT(s.id) DESC
            LIMIT 1000
        """;

        String updateSongSQL = "UPDATE songs SET duration_ms=?, release_date=?::date, primary_genre=?, is_explicit=?, preview_url=? WHERE id=?";
        
        // ΒΕΛΤΙΩΣΗ 2: Νέο query για να μαρκάρουμε όσα ΔΕΝ βρέθηκαν με duration_ms = 0
        String markNotFoundSQL = "UPDATE songs SET duration_ms = 0 WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement selectStmt = conn.prepareStatement(selectOrphansSQL);
             PreparedStatement updateStmt = conn.prepareStatement(updateSongSQL);
             PreparedStatement notFoundStmt = conn.prepareStatement(markNotFoundSQL);
             ResultSet rs = selectStmt.executeQuery()) {

            HttpClient client = HttpClient.newHttpClient();
            ObjectMapper mapper = new ObjectMapper();
            int successCount = 0;
            int notFoundCount = 0;

            while (rs.next()) {
                int songId = rs.getInt("id");
                String title = rs.getString("title");
                String artist = rs.getString("artist_name");

                String query = artist + " " + title;
                String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
                String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=song&limit=1";

                HttpRequest request = HttpRequest.newBuilder().uri(URI.create(apiUrl)).GET().build();
                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200) {
                    JsonNode root = mapper.readTree(response.body());

                    if (root.has("resultCount") && root.get("resultCount").asInt() > 0) {
                        JsonNode track = root.get("results").get(0);

                        int durationMs = track.has("trackTimeMillis") ? track.get("trackTimeMillis").asInt() : 0;
                        String releaseDate = track.has("releaseDate") ? track.get("releaseDate").asText().substring(0, 10) : null;
                        String genre = track.has("primaryGenreName") ? track.get("primaryGenreName").asText() : null;
                        boolean isExplicit = track.has("trackExplicitness") && track.get("trackExplicitness").asText().equals("explicit");
                        String previewUrl = track.has("previewUrl") ? track.get("previewUrl").asText() : null;
                        String itunesArtistName = track.has("artistName") ? track.get("artistName").asText() : null;

                        if (durationMs > 0) {
                            updateStmt.setInt(1, durationMs);
                            if (releaseDate != null) updateStmt.setString(2, releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                            if (genre != null) updateStmt.setString(3, genre); else updateStmt.setNull(3, java.sql.Types.VARCHAR);
                            updateStmt.setBoolean(4, isExplicit);
                            if (previewUrl != null) updateStmt.setString(5, previewUrl); else updateStmt.setNull(5, java.sql.Types.VARCHAR);
                            updateStmt.setInt(6, songId);
                            updateStmt.executeUpdate();

                            if (itunesArtistName != null && (itunesArtistName.contains("&") || itunesArtistName.contains(",") || itunesArtistName.toLowerCase().contains("feat"))) {
                                addMissingArtists(conn, songId, itunesArtistName);
                            }

                            System.out.println("✅ Updated: " + artist + " - " + title + (isExplicit ? " [E]" : ""));
                            successCount++;
                        } else {
                            // Το βρήκε αλλά δεν έχει duration, μαρκάρισμα ως 0
                            notFoundStmt.setInt(1, songId);
                            notFoundStmt.executeUpdate();
                        }
                    } else {
                        System.out.println("⚠️ Not found on iTunes: " + artist + " - " + title);
                        // ΒΕΛΤΙΩΣΗ 3: Μαρκάρουμε το τραγούδι με 0 για να μην ξανακολλήσει εδώ!
                        notFoundStmt.setInt(1, songId);
                        notFoundStmt.executeUpdate();
                        notFoundCount++;
                    }
                }
                Thread.sleep(120); // Rate Limit Protection
            }
            System.out.println("🎉 Metadata Enrichment Complete! Tracks Updated: " + successCount + " | Not Found: " + notFoundCount);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void addMissingArtists(Connection conn, int songId, String itunesArtistName) {
        String[] artists = itunesArtistName.split(",\\s*|\\s*&\\s*|\\s+(?i)feat\\.?\\s+|\\s+(?i)ft\\.?\\s+");

        String insertArtistSQL = "INSERT INTO artists (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectArtistSQL = "SELECT id FROM artists WHERE name = ?";
        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, TRUE) ON CONFLICT DO NOTHING";

        try {
            for (String artist : artists) {
                artist = artist.trim();
                if (artist.isEmpty()) continue;

                try (PreparedStatement insertStmt = conn.prepareStatement(insertArtistSQL)) {
                    insertStmt.setString(1, artist);
                    insertStmt.executeUpdate();
                }

                int artistId = -1;
                try (PreparedStatement selectStmt = conn.prepareStatement(selectArtistSQL)) {
                    selectStmt.setString(1, artist);
                    try (ResultSet rs = selectStmt.executeQuery()) {
                        if (rs.next()) artistId = rs.getInt("id");
                    }
                }

                if (artistId != -1) {
                    try (PreparedStatement relStmt = conn.prepareStatement(insertRelationSQL)) {
                        relStmt.setInt(1, songId);
                        relStmt.setInt(2, artistId);
                        relStmt.executeUpdate();
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("Failed to insert missing artist: " + e.getMessage());
        }
    }
}