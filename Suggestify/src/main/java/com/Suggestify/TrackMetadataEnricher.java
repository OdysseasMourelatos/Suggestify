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
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TrackMetadataEnricher {

    private static final int THREAD_POOL_SIZE = 8;
    private static final int API_DELAY_MS = 300;

    static class EnrichmentResult {
        int songId; boolean success; String artist; String cleanTitle;
        Integer durationMs; String releaseDate; String genre;
        boolean isExplicit; String previewUrl; String artistsToParse;
        boolean rateLimited = false; // Προστέθηκε για να σώσουμε τη βάση από τα 0
    }

    public static void main(String[] args) {
        String targetUser = args.length > 0 ? args[0] : "";
        System.out.println("🚀 Starting Strict-Validation iTunes Metadata Enricher for user: " + targetUser);

        String selectOrphansSQL = """
            SELECT so.id, so.title, MAX(a.name) AS artist_name
            FROM songs so
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            JOIN streams s ON s.song_id = so.id
            WHERE so.duration_ms IS NULL
            GROUP BY so.id, so.title
            ORDER BY 
                SUM(CASE WHEN s.user_id = COALESCE((SELECT id FROM users WHERE username = ?), -1) THEN 1 ELSE 0 END) DESC,
                COUNT(s.id) DESC
            LIMIT 1000
        """;

        String updateSongSQL = "UPDATE songs SET duration_ms=?, release_date=?::date, primary_genre=?, is_explicit=?, preview_url=? WHERE id=?";
        String markNotFoundSQL = "UPDATE songs SET duration_ms = 0 WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement selectStmt = conn.prepareStatement(selectOrphansSQL);
             PreparedStatement updateStmt = conn.prepareStatement(updateSongSQL);
             PreparedStatement notFoundStmt = conn.prepareStatement(markNotFoundSQL)) {

            conn.setAutoCommit(false);
            selectStmt.setString(1, targetUser);

            HttpClient client = HttpClient.newHttpClient();
            ObjectMapper mapper = new ObjectMapper();
            ExecutorService executor = Executors.newFixedThreadPool(THREAD_POOL_SIZE);

            int totalSuccess = 0;
            int totalNotFound = 0;
            int cycle = 1;

            while (true) {
                System.out.println("🔄 Starting Cycle #" + cycle + " (Fetching next 1000 tracks)...");
                List<Future<EnrichmentResult>> futures = new ArrayList<>();
                int batchSize = 0;

                try (ResultSet rs = selectStmt.executeQuery()) {
                    while (rs.next()) {
                        batchSize++;
                        final int songId = rs.getInt("id");
                        final String title = rs.getString("title");
                        final String artist = rs.getString("artist_name");

                        futures.add(executor.submit(() -> fetchFromItunesWithValidation(client, mapper, songId, artist, title)));
                    }
                }

                if (batchSize == 0) {
                    System.out.println("🏁 NO MORE MISSING TRACKS! We are 100% caught up.");
                    break;
                }

                int successCount = 0;
                int notFoundCount = 0;

                for (Future<EnrichmentResult> future : futures) {
                    EnrichmentResult res = future.get();

                    if (res.success) {
                        updateStmt.setInt(1, res.durationMs);
                        if (res.releaseDate != null) updateStmt.setString(2, res.releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                        if (res.genre != null) updateStmt.setString(3, res.genre); else updateStmt.setNull(3, java.sql.Types.VARCHAR);
                        updateStmt.setBoolean(4, res.isExplicit);
                        if (res.previewUrl != null) updateStmt.setString(5, res.previewUrl); else updateStmt.setNull(5, java.sql.Types.VARCHAR);
                        updateStmt.setInt(6, res.songId);
                        updateStmt.addBatch();

                        if (res.artistsToParse != null && (res.artistsToParse.contains("&") || res.artistsToParse.contains(",") || res.artistsToParse.toLowerCase().contains("feat"))) {
                            addMissingArtists(conn, res.songId, res.artistsToParse);
                        }
                        successCount++;
                    } else if (!res.rateLimited) {
                        // ΜΟΝΟ αν ΔΕΝ φάγαμε Rate Limit μαρκάρουμε το τραγούδι με 0!
                        notFoundStmt.setInt(1, res.songId);
                        notFoundStmt.addBatch();
                        notFoundCount++;
                    }
                }

                updateStmt.executeBatch();
                notFoundStmt.executeBatch();
                conn.commit();

                totalSuccess += successCount;
                totalNotFound += notFoundCount;
                System.out.println("✅ Cycle #" + cycle + " Complete! Validated: " + successCount + " | Rejected: " + notFoundCount);
                cycle++;
            }

            executor.shutdown();
            System.out.println("🎉 FULL ENRICHMENT COMPLETE! Grand Total Updated: " + totalSuccess + " | Rejected/Not Found: " + totalNotFound);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static EnrichmentResult fetchFromItunesWithValidation(HttpClient client, ObjectMapper mapper, int songId, String targetArtist, String title) {
        EnrichmentResult res = new EnrichmentResult();
        res.songId = songId;
        res.artist = targetArtist;
        res.success = false;
        res.rateLimited = false;

        String cleanTitle = title;
        if (cleanTitle.contains(" - ")) {
            cleanTitle = cleanTitle.substring(0, cleanTitle.indexOf(" - "));
        }
        res.cleanTitle = cleanTitle;

        try {
            String query = targetArtist + " " + cleanTitle;
            String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");

            // ΑΛΛΑΓΗ: 25 αποτελέσματα αντί για 5
            String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=song&limit=25";

            // ΑΛΛΑΓΗ: Μάσκα Chrome Browser για να μην μας κόβει η Apple
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(apiUrl))
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 403 || response.statusCode() == 429) {
                System.out.println("🛑 BLOCKED BY APPLE (403): " + targetArtist + " - " + cleanTitle);
                res.rateLimited = true; 
                Thread.sleep(3000);
                return res;
            }

            if (response.statusCode() == 200) {
                JsonNode root = mapper.readTree(response.body());
                if (root.has("results")) {
                    JsonNode results = root.get("results");
                    if (results.size() == 0) {
                        System.out.println("⚠️ API ZERO RESULTS: " + targetArtist + " - " + cleanTitle);
                        return res;
                    }

                    for (JsonNode track : results) {
                        String itunesArtist = track.has("artistName") ? track.get("artistName").asText() : "";
                        String itunesTrack = track.has("trackName") ? track.get("trackName").asText() : "";

                        if (isMatchValid(targetArtist, cleanTitle, itunesArtist, itunesTrack)) {
                            int durationMs = track.has("trackTimeMillis") ? track.get("trackTimeMillis").asInt() : 0;
                            if (durationMs > 0) {
                                res.durationMs = durationMs;
                                res.releaseDate = track.has("releaseDate") ? track.get("releaseDate").asText().substring(0, 10) : null;
                                res.genre = track.has("primaryGenreName") ? track.get("primaryGenreName").asText() : null;
                                String explicitness = track.has("trackExplicitness") ? track.get("trackExplicitness").asText() : "";
                                res.isExplicit = "explicit".equalsIgnoreCase(explicitness);
                                res.previewUrl = track.has("previewUrl") ? track.get("previewUrl").asText() : null;

                                StringBuilder combinedArtists = new StringBuilder(itunesArtist);
                                Matcher featMatcher = Pattern.compile("(?i)\\((?:feat\\.|ft\\.|with|featuring)\\s+([^)]+)\\)").matcher(itunesTrack);
                                while (featMatcher.find()) {
                                    combinedArtists.append(", ").append(featMatcher.group(1));
                                }
                                res.artistsToParse = combinedArtists.toString();
                                res.success = true;

                                System.out.println("✅ MATCH VERIFIED: " + targetArtist + " - " + cleanTitle);
                                return res;
                            }
                        }
                    }
                    
                    // ΑΛΛΑΓΗ: Debugging αν βρήκε αποτελέσματα αλλά κανένα δεν πέρασε το isMatchValid!
                    System.out.println("❌ VALIDATION REJECTED: " + targetArtist + " - " + cleanTitle);
                    System.out.println("   ↳ Top API Result was: " + results.get(0).get("artistName").asText() + " - " + results.get(0).get("trackName").asText());
                }
            }

            Thread.sleep(API_DELAY_MS);

        } catch (Exception e) {
            System.out.println("❌ EXCEPTION for: " + cleanTitle + " -> " + e.getMessage());
        }
        return res;
    }

    private static String cleanString(String s) {
        if (s == null) return "";
        String cleaned = s.toLowerCase();
        cleaned = cleaned.replaceAll("\\([^)]*\\)", "").replaceAll("\\[[^\\]]*\\]", "");
        // Αφαίρεσα το 'with' γιατί δημιουργούσε πρόβλημα σε τίτλους όπως 'Without Me'
        cleaned = cleaned.replaceAll("\\b(feat\\.|ft\\.|featuring|remix|deluxe|edition)\\b.*", "");
        return cleaned.replaceAll("[^a-z0-9]", "");
    }

    private static boolean isMatchValid(String targetArtist, String targetTitle, String itunesArtist, String itunesTitle) {
        if (itunesArtist == null || itunesTitle == null) return false;

        String tArtist = cleanString(targetArtist);
        String tTitle = cleanString(targetTitle);
        String iArtist = cleanString(itunesArtist);
        String iTitle = cleanString(itunesTitle);

        if (tArtist.isEmpty() || tTitle.isEmpty()) return false;

        boolean titleOk = iTitle.contains(tTitle) || tTitle.contains(iTitle);
        boolean artistOk = iArtist.contains(tArtist) || tArtist.contains(iArtist);

        return titleOk && artistOk;
    }

    private static void addMissingArtists(Connection conn, int songId, String artistString) {
        // [Παραμένει ίδια η μέθοδος addMissingArtists όπως την είχες]
        String[] artists = artistString.split(",\\s*|\\s*&\\s*|\\s+(?i)feat\\.?\\s+|\\s+(?i)ft\\.?\\s+|\\s+(?i)featuring\\s+");
        String insertArtistSQL = "INSERT INTO artists (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectArtistSQL = "SELECT id FROM artists WHERE name = ?";
        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, TRUE) ON CONFLICT DO NOTHING";

        try {
            for (String artist : artists) {
                artist = artist.trim().replaceAll("[()\"]", "");
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