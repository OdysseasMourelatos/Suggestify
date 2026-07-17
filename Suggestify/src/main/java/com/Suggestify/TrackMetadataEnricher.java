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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TrackMetadataEnricher {

    private static final Pattern DURATION_PATTERN = Pattern.compile("\"trackTimeMillis\"\\s*:\\s*(\\d+)");
    private static final Pattern DATE_PATTERN = Pattern.compile("\"releaseDate\"\\s*:\\s*\"([0-9]{4}-[0-9]{2}-[0-9]{2})");
    private static final Pattern GENRE_PATTERN = Pattern.compile("\"primaryGenreName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern EXPLICIT_PATTERN = Pattern.compile("\"trackExplicitness\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern PREVIEW_PATTERN = Pattern.compile("\"previewUrl\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern ARTIST_PATTERN = Pattern.compile("\"artistName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern TRACK_NAME_PATTERN = Pattern.compile("\"trackName\"\\s*:\\s*\"([^\"]+)\"");

    public static void main(String[] args) {
        System.out.println("🚀 Starting iTunes Track Metadata & Advanced Feature Hunter...");

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
        String markNotFoundSQL = "UPDATE songs SET duration_ms = 0 WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement selectStmt = conn.prepareStatement(selectOrphansSQL);
             PreparedStatement updateStmt = conn.prepareStatement(updateSongSQL);
             PreparedStatement notFoundStmt = conn.prepareStatement(markNotFoundSQL);
             ResultSet rs = selectStmt.executeQuery()) {

            HttpClient client = HttpClient.newHttpClient();
            int successCount = 0;
            int notFoundCount = 0;

            while (rs.next()) {
                int songId = rs.getInt("id");
                String title = rs.getString("title");
                String artist = rs.getString("artist_name");

                // ΕΞΥΠΝΟΣ ΚΑΘΑΡΙΣΜΟΣ ΤΙΤΛΟΥ (αφαιρεί τα "- From SR3MM", "- Remastered" κλπ)
                String cleanTitle = title;
                if (cleanTitle.contains(" - ")) {
                    cleanTitle = cleanTitle.substring(0, cleanTitle.indexOf(" - "));
                }

                String query = artist + " " + cleanTitle;
                String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
                String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=song&limit=1";

                HttpRequest request = HttpRequest.newBuilder().uri(URI.create(apiUrl)).GET().build();
                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200 && (response.body().contains("\"resultCount\":1") || response.body().contains("\"resultCount\": 1"))) {
                    String json = response.body();

                    Integer durationMs = extractInt(DURATION_PATTERN, json);
                    if (durationMs != null && durationMs > 0) {
                        String releaseDate = extractString(DATE_PATTERN, json);
                        String genre = extractString(GENRE_PATTERN, json);
                        String explicitness = extractString(EXPLICIT_PATTERN, json);
                        boolean isExplicit = "explicit".equalsIgnoreCase(explicitness);
                        String previewUrl = extractString(PREVIEW_PATTERN, json);
                        
                        String itunesArtistName = extractString(ARTIST_PATTERN, json);
                        String itunesTrackName = extractString(TRACK_NAME_PATTERN, json);

                        // Ενημέρωση του πίνακα τραγουδιών
                        updateStmt.setInt(1, durationMs);
                        if (releaseDate != null) updateStmt.setString(2, releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                        if (genre != null) updateStmt.setString(3, genre); else updateStmt.setNull(3, java.sql.Types.VARCHAR);
                        updateStmt.setBoolean(4, isExplicit);
                        if (previewUrl != null) updateStmt.setString(5, previewUrl); else updateStmt.setNull(5, java.sql.Types.VARCHAR);
                        updateStmt.setInt(6, songId);
                        updateStmt.executeUpdate();

                        // --- ADVANCED FEATURE HUNTER ---
                        StringBuilder combinedArtists = new StringBuilder();
                        if (itunesArtistName != null) combinedArtists.append(itunesArtistName);
                        
                        // Ψάχνει για (feat. Swae Lee) ή (ft. Trippie Redd) μέσα στον ΤΙΤΛΟ του τραγουδιού
                        if (itunesTrackName != null) {
                            Matcher featMatcher = Pattern.compile("(?i)\\((?:feat\\.|ft\\.|with|featuring)\\s+([^)]+)\\)").matcher(itunesTrackName);
                            while (featMatcher.find()) {
                                combinedArtists.append(", ").append(featMatcher.group(1));
                            }
                        }

                        String artistsToParse = combinedArtists.toString();
                        if (artistsToParse.contains("&") || artistsToParse.contains(",") || artistsToParse.toLowerCase().contains("feat")) {
                            addMissingArtists(conn, songId, artistsToParse);
                        }

                        System.out.println("✅ Updated: " + artist + " - " + cleanTitle + (isExplicit ? " [E]" : ""));
                        successCount++;
                    } else {
                        notFoundStmt.setInt(1, songId);
                        notFoundStmt.executeUpdate();
                        notFoundCount++;
                    }
                } else {
                    System.out.println("⚠️ Not found on iTunes: " + artist + " - " + cleanTitle);
                    notFoundStmt.setInt(1, songId);
                    notFoundStmt.executeUpdate();
                    notFoundCount++;
                }
                Thread.sleep(120); // Προστασία από Rate Limits
            }
            System.out.println("🎉 Metadata Enrichment Complete! Tracks Updated: " + successCount + " | Not Found: " + notFoundCount);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void addMissingArtists(Connection conn, int songId, String artistString) {
        String[] artists = artistString.split(",\\s*|\\s*&\\s*|\\s+(?i)feat\\.?\\s+|\\s+(?i)ft\\.?\\s+|\\s+(?i)featuring\\s+");
        String insertArtistSQL = "INSERT INTO artists (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectArtistSQL = "SELECT id FROM artists WHERE name = ?";
        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, TRUE) ON CONFLICT DO NOTHING";

        try {
            for (String artist : artists) {
                artist = artist.trim();
                // Καθαρίζει τυχόν σκουπίδια στο όνομα (π.χ. παρενθέσεις που ξέμειναν)
                artist = artist.replaceAll("[()\"]", "").trim();
                
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

    private static Integer extractInt(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? Integer.parseInt(m.group(1)) : null;
    }

    private static String extractString(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? m.group(1) : null;
    }
}