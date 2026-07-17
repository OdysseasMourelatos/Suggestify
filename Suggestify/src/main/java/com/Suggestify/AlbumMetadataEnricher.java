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
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class AlbumMetadataEnricher {

    private static final int THREAD_POOL_SIZE = 8;
    private static final int BATCH_SIZE = 1000;

    private static final Pattern TRACK_COUNT_PATTERN = Pattern.compile("\"trackCount\"\\s*:\\s*(\\d+)");
    private static final Pattern DATE_PATTERN = Pattern.compile("\"releaseDate\"\\s*:\\s*\"([0-9]{4}-[0-9]{2}-[0-9]{2})");
    private static final Pattern GENRE_PATTERN = Pattern.compile("\"primaryGenreName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern EXPLICIT_PATTERN = Pattern.compile("\"collectionExplicitness\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern LABEL_PATTERN = Pattern.compile("\"copyright\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern ARTIST_NAME_PATTERN = Pattern.compile("\"artistName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern COLLECTION_NAME_PATTERN = Pattern.compile("\"collectionName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern RESULT_COUNT_PATTERN = Pattern.compile("\"resultCount\"\\s*:\\s*(\\d+)");

    // ═══════════════════════════════════════════════════════════════
    // DATA HOLDERS
    // ═══════════════════════════════════════════════════════════════
    private static class AlbumRow {
        final int id;
        final String title;
        final String artist;

        AlbumRow(int id, String title, String artist) {
            this.id = id;
            this.title = title;
            this.artist = artist;
        }
    }

    private static class EnrichmentResult {
        final int albumId;
        final String artist;
        final String title;
        boolean success = false;
        Integer trackCount;
        String releaseDate;
        String genre;
        boolean explicit;
        String label;

        EnrichmentResult(int albumId, String artist, String title) {
            this.albumId = albumId;
            this.artist = artist;
            this.title = title;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // WORKER TASK — one iTunes lookup + strict validation
    // ═══════════════════════════════════════════════════════════════
    private static class AlbumTask implements Callable<EnrichmentResult> {
        private final AlbumRow row;
        private final HttpClient client;

        AlbumTask(AlbumRow row, HttpClient client) {
            this.row = row;
            this.client = client;
        }

        @Override
        public EnrichmentResult call() {
            String cleanTitle = row.title.replaceAll(
                    "(?i)\\s*\\(?(Deluxe|Expanded|Remastered|Bonus Track)(?:\\s+Edition|\\s+Version)?\\)?\\s*", "").trim();

            EnrichmentResult result = new EnrichmentResult(row.id, row.artist, cleanTitle);

            try {
                String query = row.artist + " " + cleanTitle;
                String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
                String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=album&limit=5";

                HttpRequest request = HttpRequest.newBuilder().uri(URI.create(apiUrl)).GET().build();
                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

                // Rate-limit protection — one sleep per worker thread per request
                Thread.sleep(250);

                if (response.statusCode() == 200) {
                    String json = response.body();
                    Integer resultCount = extractInt(RESULT_COUNT_PATTERN, json);

                    if (resultCount != null && resultCount > 0) {
                        List<String> candidates = splitResults(json);

                        for (String candidateJson : candidates) {
                            String itunesArtist = extractString(ARTIST_NAME_PATTERN, candidateJson);
                            String itunesAlbum = extractString(COLLECTION_NAME_PATTERN, candidateJson);

                            if (isMatchValid(row.artist, cleanTitle, itunesArtist, itunesAlbum)) {
                                Integer trackCount = extractInt(TRACK_COUNT_PATTERN, candidateJson);
                                if (trackCount != null && trackCount > 0) {
                                    result.trackCount = trackCount;
                                    result.releaseDate = extractString(DATE_PATTERN, candidateJson);
                                    result.genre = extractString(GENRE_PATTERN, candidateJson);
                                    String explicitness = extractString(EXPLICIT_PATTERN, candidateJson);
                                    result.explicit = "explicit".equalsIgnoreCase(explicitness);
                                    result.label = extractString(LABEL_PATTERN, candidateJson);
                                    result.success = true;
                                    break; // strict match found — stop scanning limit=5 candidates
                                }
                            }
                        }
                    }
                }
            } catch (Exception e) {
                System.out.println("⚠️ Error enriching album [" + row.id + "] " + row.artist + " - " + cleanTitle + ": " + e.getMessage());
            }

            return result;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // MAIN
    // ═══════════════════════════════════════════════════════════════
    public static void main(String[] args) {
        String targetUser = (args.length > 0) ? args[0] : null;

        System.out.println("💿 Starting iTunes Album Metadata Enricher (Multi-threaded, Strict Validation)...");
        if (targetUser != null) {
            System.out.println("👤 Prioritizing albums streamed by: " + targetUser);
        }

        // Βρίσκουμε τον Primary Artist κάθε άλμπουμ (αυτόν με τα περισσότερα τραγούδια),
        // με προτεραιότητα στα άλμπουμ που έχει ακούσει ο targetUser
        String selectAlbumsSQL = """
            WITH AlbumPrimaryArtists AS (
                SELECT so.album_id, a.name, COUNT(so.id) as cnt
                FROM songs so
                JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
                JOIN artists a ON a.id = sa.artist_id
                WHERE so.album_id IS NOT NULL
                GROUP BY so.album_id, a.name
            ),
            RankedArtists AS (
                SELECT album_id, name, RANK() OVER(PARTITION BY album_id ORDER BY cnt DESC) as rnk
                FROM AlbumPrimaryArtists
            )
            SELECT al.id, al.title, ra.name AS artist_name
            FROM albums al
            JOIN RankedArtists ra ON ra.album_id = al.id AND ra.rnk = 1
            LEFT JOIN songs so2 ON so2.album_id = al.id
            LEFT JOIN streams s ON s.song_id = so2.id
            WHERE al.total_tracks IS NULL
            GROUP BY al.id, al.title, ra.name
            ORDER BY SUM(CASE WHEN s.user_id = COALESCE((SELECT id FROM users WHERE username = ?), -1) THEN 1 ELSE 0 END) DESC,
                     COUNT(s.id) DESC
            LIMIT %d
        """.formatted(BATCH_SIZE);

        String updateAlbumSQL = "UPDATE albums SET total_tracks=?, release_date=?::date, primary_genre=?, is_explicit=?, label=? WHERE id=?";
        String markNotFoundSQL = "UPDATE albums SET total_tracks = 0 WHERE id = ?";

        ExecutorService executor = Executors.newFixedThreadPool(THREAD_POOL_SIZE);
        HttpClient client = HttpClient.newHttpClient();

        int totalSuccess = 0;
        int totalNotFound = 0;

        try (Connection conn = DatabaseManager.getConnection()) {
            conn.setAutoCommit(false);

            while (true) {
                List<AlbumRow> batch = new ArrayList<>();

                try (PreparedStatement selectStmt = conn.prepareStatement(selectAlbumsSQL)) {
                    selectStmt.setString(1, targetUser);
                    try (ResultSet rs = selectStmt.executeQuery()) {
                        while (rs.next()) {
                            batch.add(new AlbumRow(rs.getInt("id"), rs.getString("title"), rs.getString("artist_name")));
                        }
                    }
                }

                int batchSize = batch.size();
                if (batchSize == 0) {
                    System.out.println("No more missing albums...");
                    break;
                }

                System.out.println("📦 Processing batch of " + batchSize + " albums...");

                // Fan out to the thread pool
                List<Future<EnrichmentResult>> futures = new ArrayList<>(batchSize);
                for (AlbumRow row : batch) {
                    futures.add(executor.submit(new AlbumTask(row, client)));
                }

                int successCount = 0;
                int notFoundCount = 0;

                try (PreparedStatement updateStmt = conn.prepareStatement(updateAlbumSQL);
                     PreparedStatement notFoundStmt = conn.prepareStatement(markNotFoundSQL)) {

                    for (Future<EnrichmentResult> future : futures) {
                        EnrichmentResult result;
                        try {
                            result = future.get();
                        } catch (Exception e) {
                            e.printStackTrace();
                            continue;
                        }

                        if (result.success) {
                            updateStmt.setInt(1, result.trackCount);
                            if (result.releaseDate != null) updateStmt.setString(2, result.releaseDate); else updateStmt.setNull(2, Types.VARCHAR);
                            if (result.genre != null) updateStmt.setString(3, result.genre); else updateStmt.setNull(3, Types.VARCHAR);
                            updateStmt.setBoolean(4, result.explicit);
                            if (result.label != null) updateStmt.setString(5, result.label); else updateStmt.setNull(5, Types.VARCHAR);
                            updateStmt.setInt(6, result.albumId);
                            updateStmt.addBatch();

                            System.out.println("✅ Album Matched: " + result.artist + " - " + result.title + (result.explicit ? " [E]" : ""));
                            successCount++;
                        } else {
                            notFoundStmt.setInt(1, result.albumId);
                            notFoundStmt.addBatch();

                            System.out.println("⚠️ No Valid Match: " + result.artist + " - " + result.title);
                            notFoundCount++;
                        }
                    }

                    updateStmt.executeBatch();
                    notFoundStmt.executeBatch();
                    conn.commit();
                } catch (Exception e) {
                    conn.rollback();
                    throw e;
                }

                totalSuccess += successCount;
                totalNotFound += notFoundCount;
                System.out.println("📊 Batch complete — Updated: " + successCount + " | Not Found: " + notFoundCount);
            }

            System.out.println("🎉 Album Enrichment Complete! Updated: " + totalSuccess + " | Not Found: " + totalNotFound);

        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            executor.shutdown();
            try {
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException ie) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // STRICT VALIDATION
    // ═══════════════════════════════════════════════════════════════
    private static String sanitize(String s) {
        if (s == null) return "";
        return s.toLowerCase().replaceAll("[^a-z0-9]", "");
    }

    /**
     * Strips all non-alphanumeric characters from both target and iTunes artist/album
     * (case-insensitive) and checks for mutual containment before accepting a match.
     */
    private static boolean isMatchValid(String targetArtist, String targetAlbum, String itunesArtist, String itunesAlbum) {
        if (itunesArtist == null || itunesAlbum == null) return false;

        String tArtist = sanitize(targetArtist);
        String tAlbum = sanitize(targetAlbum);
        String iArtist = sanitize(itunesArtist);
        String iAlbum = sanitize(itunesAlbum);

        if (tArtist.isEmpty() || tAlbum.isEmpty() || iArtist.isEmpty() || iAlbum.isEmpty()) return false;

        boolean artistMatch = tArtist.contains(iArtist) || iArtist.contains(tArtist);
        boolean albumMatch = tAlbum.contains(iAlbum) || iAlbum.contains(tAlbum);

        return artistMatch && albumMatch;
    }

    // ═══════════════════════════════════════════════════════════════
    // JSON HELPERS (regex-based, no external dependency)
    // ═══════════════════════════════════════════════════════════════

    /**
     * Splits the top-level "results" array of an iTunes search response into
     * individual result object substrings, so each candidate (up to limit=5)
     * can be validated independently.
     */
    private static List<String> splitResults(String json) {
        List<String> results = new ArrayList<>();

        int keyIdx = json.indexOf("\"results\"");
        if (keyIdx == -1) return results;

        int arrStart = json.indexOf('[', keyIdx);
        if (arrStart == -1) return results;

        int depth = 0;
        int objStart = -1;
        int i = arrStart + 1;

        while (i < json.length()) {
            char c = json.charAt(i);
            if (c == '{') {
                if (depth == 0) objStart = i;
                depth++;
            } else if (c == '}') {
                depth--;
                if (depth == 0 && objStart != -1) {
                    results.add(json.substring(objStart, i + 1));
                    objStart = -1;
                }
            } else if (c == ']' && depth == 0) {
                break;
            }
            i++;
        }

        return results;
    }

    private static Integer extractInt(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? Integer.parseInt(m.group(1)) : null;
    }

    private static String extractString(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        // Για το πεδίο copyright (label) μπορεί να περιέχει unicode chars, τα κρατάμε ως έχουν
        return m.find() ? m.group(1).replace("\\u00a9", "©").replace("\\u2117", "℗") : null;
    }
}