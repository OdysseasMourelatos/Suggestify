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
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
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

    // Ρυθμίσεις Ταχύτητας (Max ~20-25 requests/sec για να μην φάμε block από την Apple)
    private static final int THREAD_POOL_SIZE = 8; 
    private static final int API_DELAY_MS = 300; 

    // Βοηθητική Κλάση για να κρατάμε τα δεδομένα πριν τη Βάση
    static class EnrichmentResult {
        int songId; boolean success; String artist; String cleanTitle;
        Integer durationMs; String releaseDate; String genre;
        boolean isExplicit; String previewUrl; String artistsToParse;
    }

    public static void main(String[] args) {
        System.out.println("🚀 Starting FAST Multi-Threaded iTunes Metadata Enricher...");

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

            // Γυρνάμε το AutoCommit σε false για απίστευτη ταχύτητα εγγραφής στη DB
            conn.setAutoCommit(false);

            HttpClient client = HttpClient.newHttpClient();
            ExecutorService executor = Executors.newFixedThreadPool(THREAD_POOL_SIZE);
            List<Future<EnrichmentResult>> futures = new ArrayList<>();

            System.out.println("📦 Fetching up to 1000 tracks from database...");

            // 1. Διαβάζουμε ΟΛΑ τα tracks που θέλουν update και τα αναθέτουμε στα Threads
            while (rs.next()) {
                final int songId = rs.getInt("id");
                final String title = rs.getString("title");
                final String artist = rs.getString("artist_name");

                futures.add(executor.submit(() -> fetchFromItunes(client, songId, artist, title)));
            }

            System.out.println("⚡ Firing concurrent HTTP requests to Apple iTunes API...");

            int successCount = 0;
            int notFoundCount = 0;

            // 2. Περιμένουμε τα αποτελέσματα από τα Threads και χτίζουμε τα SQL Batches
            for (Future<EnrichmentResult> future : futures) {
                EnrichmentResult res = future.get(); // Εδώ περιμένει αν το thread δεν έχει τελειώσει

                if (res.success) {
                    updateStmt.setInt(1, res.durationMs);
                    if (res.releaseDate != null) updateStmt.setString(2, res.releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                    if (res.genre != null) updateStmt.setString(3, res.genre); else updateStmt.setNull(3, java.sql.Types.VARCHAR);
                    updateStmt.setBoolean(4, res.isExplicit);
                    if (res.previewUrl != null) updateStmt.setString(5, res.previewUrl); else updateStmt.setNull(5, java.sql.Types.VARCHAR);
                    updateStmt.setInt(6, res.songId);
                    updateStmt.addBatch(); // Αντί για execute, το βάζουμε στο πακέτο!

                    // Το Feature Hunter τρέχει σειριακά για να μην κρασάρει τη βάση
                    if (res.artistsToParse != null && (res.artistsToParse.contains("&") || res.artistsToParse.contains(",") || res.artistsToParse.toLowerCase().contains("feat"))) {
                        addMissingArtists(conn, res.songId, res.artistsToParse);
                    }
                    successCount++;
                } else {
                    notFoundStmt.setInt(1, res.songId);
                    notFoundStmt.addBatch();
                    notFoundCount++;
                }
            }

            // Κλείνουμε το pool
            executor.shutdown();

            System.out.println("💾 Writing batches to Database...");
            // 3. Εκτελούμε όλα τα SQL Queries με τη μία!
            updateStmt.executeBatch();
            notFoundStmt.executeBatch();
            conn.commit(); // Σώζουμε τις αλλαγές

            System.out.println("🎉 Batch Complete! Updated: " + successCount + " | Not Found: " + notFoundCount);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // Η συνάρτηση που εκτελείται από τα πολλαπλά Threads παράλληλα!
    private static EnrichmentResult fetchFromItunes(HttpClient client, int songId, String artist, String title) {
        EnrichmentResult res = new EnrichmentResult();
        res.songId = songId;
        res.artist = artist;
        res.success = false;

        String cleanTitle = title;
        if (cleanTitle.contains(" - ")) {
            cleanTitle = cleanTitle.substring(0, cleanTitle.indexOf(" - "));
        }
        res.cleanTitle = cleanTitle;

        try {
            String query = artist + " " + cleanTitle;
            String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
            String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=song&limit=1";

            HttpRequest request = HttpRequest.newBuilder().uri(URI.create(apiUrl)).GET().build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 403) {
                System.out.println("⚠️ APPLE RATE LIMIT HIT! Slowing down...");
                Thread.sleep(5000); // Αν μας μπλοκάρουν, περιμένουμε 5 δευτερόλεπτα
                return res;
            }

            if (response.statusCode() == 200 && (response.body().contains("\"resultCount\":1") || response.body().contains("\"resultCount\": 1"))) {
                String json = response.body();

                Integer durationMs = extractInt(DURATION_PATTERN, json);
                if (durationMs != null && durationMs > 0) {
                    res.durationMs = durationMs;
                    res.releaseDate = extractString(DATE_PATTERN, json);
                    res.genre = extractString(GENRE_PATTERN, json);
                    String explicitness = extractString(EXPLICIT_PATTERN, json);
                    res.isExplicit = "explicit".equalsIgnoreCase(explicitness);
                    res.previewUrl = extractString(PREVIEW_PATTERN, json);
                    
                    String itunesArtistName = extractString(ARTIST_PATTERN, json);
                    String itunesTrackName = extractString(TRACK_NAME_PATTERN, json);

                    StringBuilder combinedArtists = new StringBuilder();
                    if (itunesArtistName != null) combinedArtists.append(itunesArtistName);
                    
                    if (itunesTrackName != null) {
                        Matcher featMatcher = Pattern.compile("(?i)\\((?:feat\\.|ft\\.|with|featuring)\\s+([^)]+)\\)").matcher(itunesTrackName);
                        while (featMatcher.find()) {
                            combinedArtists.append(", ").append(featMatcher.group(1));
                        }
                    }
                    res.artistsToParse = combinedArtists.toString();
                    res.success = true;
                    System.out.println("✅ Found: " + artist + " - " + cleanTitle);
                }
            } else {
                System.out.println("❌ Not found: " + artist + " - " + cleanTitle);
            }

            // Προστασία από IP Block! Κάθε Thread κοιμάται για λίγο μετά από κάθε request
            Thread.sleep(API_DELAY_MS);

        } catch (Exception e) {
            // Αν πέσει το δίκτυο
        }
        return res;
    }

    private static void addMissingArtists(Connection conn, int songId, String artistString) {
        String[] artists = artistString.split(",\\s*|\\s*&\\s*|\\s+(?i)feat\\.?\\s+|\\s+(?i)ft\\.?\\s+|\\s+(?i)featuring\\s+");
        String insertArtistSQL = "INSERT INTO artists (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String selectArtistSQL = "SELECT id FROM artists WHERE name = ?";
        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, TRUE) ON CONFLICT DO NOTHING";

        try {
            for (String artist : artists) {
                artist = artist.trim();
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