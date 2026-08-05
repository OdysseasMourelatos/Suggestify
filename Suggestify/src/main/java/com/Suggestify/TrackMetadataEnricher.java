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
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.Optional;

public class TrackMetadataEnricher {

    private static final int THREAD_POOL_SIZE = 3;
    // Το Spotify αντέχει πολλά requests. 100ms delay = ~10 requests το δευτερόλεπτο ανά thread
    private static final int API_DELAY_MS = 100; 
    
    // Global rate limiting variables
    private static long lastRequestTime = 0;
    private static volatile long penaltyEndTime = 0;

    static class EnrichmentResult {
        int songId; 
        boolean success; 
        String artist; 
        String cleanTitle;
        
        Integer durationMs; 
        String releaseDate; 
        boolean isExplicit; 
        String previewUrl;
        
        // Νέα Spotify Πεδία
        String spotifyId;
        int popularity;
        Double tempo;
        Double energy;
        Double danceability;
        Double valence;
        Double acousticness;
        
        boolean rateLimited = false;
    }

    public static void main(String[] args) {
        String targetUser = args.length > 0 ? args[0] : "";
        System.out.println("🚀 Starting Spotify Metadata & Audio Features Enricher for user: " + targetUser);

        // Βρίσκουμε τραγούδια που δεν έχουν πάρει ακόμα Spotify ID
        String selectOrphansSQL = """
            SELECT so.id, so.title, MAX(a.name) AS artist_name
            FROM songs so
            JOIN song_artists sa ON sa.song_id = so.id AND sa.is_feature = FALSE
            JOIN artists a ON a.id = sa.artist_id
            JOIN streams s ON s.song_id = so.id
            WHERE so.spotify_id IS NULL
            GROUP BY so.id, so.title
            ORDER BY 
                SUM(CASE WHEN s.user_id = COALESCE((SELECT id FROM users WHERE username = ?), -1) THEN 1 ELSE 0 END) DESC,
                COUNT(s.id) DESC
            LIMIT 1000
        """;

        String updateSongSQL = """
            UPDATE songs 
            SET duration_ms=?, release_date=?::date, is_explicit=?, preview_url=?, 
                spotify_id=?, popularity=?, tempo=?, energy=?, danceability=?, valence=?, acousticness=? 
            WHERE id=?
        """;
        
        // Αν δεν το βρει στο Spotify, βάζουμε dummy τιμές για να μην το ξαναψάξει στο επόμενο run
        String markNotFoundSQL = "UPDATE songs SET duration_ms = 0, spotify_id = 'NOT_FOUND_' || id WHERE id = ?";

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

                        futures.add(executor.submit(() -> fetchFromSpotify(client, mapper, songId, artist, title)));
                    }
                }

                if (batchSize == 0) {
                    System.out.println("🏁 NO MORE MISSING TRACKS! We are 100% caught up.");
                    break;
                }

                int successCount = 0;
                int notFoundCount = 0;

                List<EnrichmentResult> processedResults = new ArrayList<>();
                for (Future<EnrichmentResult> future : futures) {
                    processedResults.add(future.get());
                }

                processedResults.sort(Comparator.comparingInt(a -> a.songId));

                for (EnrichmentResult res : processedResults) {
                    if (res.success && res.spotifyId != null) {
                        updateStmt.setInt(1, res.durationMs);
                        if (res.releaseDate != null) updateStmt.setString(2, res.releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                        updateStmt.setBoolean(3, res.isExplicit);
                        if (res.previewUrl != null) updateStmt.setString(4, res.previewUrl); else updateStmt.setNull(4, java.sql.Types.VARCHAR);
                        updateStmt.setString(5, res.spotifyId);
                        updateStmt.setInt(6, res.popularity);
                        
                        if (res.tempo != null) updateStmt.setDouble(7, res.tempo); else updateStmt.setNull(7, java.sql.Types.NUMERIC);
                        if (res.energy != null) updateStmt.setDouble(8, res.energy); else updateStmt.setNull(8, java.sql.Types.NUMERIC);
                        if (res.danceability != null) updateStmt.setDouble(9, res.danceability); else updateStmt.setNull(9, java.sql.Types.NUMERIC);
                        if (res.valence != null) updateStmt.setDouble(10, res.valence); else updateStmt.setNull(10, java.sql.Types.NUMERIC);
                        if (res.acousticness != null) updateStmt.setDouble(11, res.acousticness); else updateStmt.setNull(11, java.sql.Types.NUMERIC);
                        
                        updateStmt.setInt(12, res.songId);
                        updateStmt.addBatch();

                        successCount++;
                    } else if (!res.rateLimited) {
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
                
                if (successCount == 0 && notFoundCount == 0 && batchSize > 0) {
                    System.out.println("⚠️ Entire cycle was rate-limited. Idling before next DB fetch...");
                    Thread.sleep(10000); 
                } else {
                    System.out.println("✅ Cycle #" + cycle + " Complete! Enriched: " + successCount + " | Not Found: " + notFoundCount);
                }
                cycle++;
            }

            executor.shutdown();
            System.out.println("🎉 FULL SPOTIFY ENRICHMENT COMPLETE! Grand Total Updated: " + totalSuccess);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static synchronized void enforceGlobalRateLimit() throws InterruptedException {
        long now = System.currentTimeMillis();
        if (now < penaltyEndTime) {
            Thread.sleep(penaltyEndTime - now);
            now = System.currentTimeMillis();
        }
        
        long elapsed = now - lastRequestTime;
        if (elapsed < API_DELAY_MS) {
            Thread.sleep(API_DELAY_MS - elapsed);
        }
        lastRequestTime = System.currentTimeMillis();
    }

    private static synchronized void triggerPenaltyBackoff(Optional<String> retryAfterHeader) {
        long now = System.currentTimeMillis();
        if (penaltyEndTime < now) {
            int waitSeconds = retryAfterHeader.map(Integer::parseInt).orElse(30);
            System.out.println("🛑 SPOTIFY RATE LIMIT (429) DETECTED: Pausing all requests globally for " + waitSeconds + " seconds...");
            penaltyEndTime = now + (waitSeconds * 1000L);
        }
    }

    private static EnrichmentResult fetchFromSpotify(HttpClient client, ObjectMapper mapper, int songId, String targetArtist, String title) {
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
            String accessToken = SpotifyAuthManager.getAccessToken();
            if (accessToken == null) {
                res.rateLimited = true;
                return res;
            }

            // 1. ΑΝΑΖΗΤΗΣΗ ΤΡΑΓΟΥΔΙΟΥ (Search API)
            String query = targetArtist + " " + cleanTitle;
            String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
            String searchUrl = "https://api.spotify.com/v1/search?q=" + encodedQuery + "&type=track&limit=1";

            HttpRequest searchReq = HttpRequest.newBuilder()
                    .uri(URI.create(searchUrl))
                    .header("Authorization", "Bearer " + accessToken)
                    .GET()
                    .build();

            enforceGlobalRateLimit();
            HttpResponse<String> searchResp = client.send(searchReq, HttpResponse.BodyHandlers.ofString());

            if (searchResp.statusCode() == 429) {
                triggerPenaltyBackoff(searchResp.headers().firstValue("Retry-After"));
                res.rateLimited = true; 
                return res;
            }

            if (searchResp.statusCode() == 200) {
                JsonNode root = mapper.readTree(searchResp.body());
                JsonNode items = root.path("tracks").path("items");
                
                if (items.isArray() && items.size() > 0) {
                    JsonNode track = items.get(0);
                    
                    res.spotifyId = track.get("id").asText();
                    res.durationMs = track.get("duration_ms").asInt();
                    res.isExplicit = track.get("explicit").asBoolean();
                    res.popularity = track.path("popularity").asInt(0);
                    res.previewUrl = track.hasNonNull("preview_url") ? track.get("preview_url").asText() : null;
                    
                    // Διορθώνουμε το Release Date Format για την PostgreSQL (αν είναι π.χ. "2016" το κάνουμε "2016-01-01")
                    JsonNode albumNode = track.path("album");
                    String rDate = albumNode.path("release_date").asText(null);
                    String precision = albumNode.path("release_date_precision").asText("");
                    
                    if (rDate != null) {
                        if (precision.equals("year")) rDate += "-01-01";
                        else if (precision.equals("month")) rDate += "-01";
                        res.releaseDate = rDate;
                    }

                    // 2. AUDIO FEATURES API (Χρησιμοποιώντας το spotifyId που μόλις πήραμε)
                    String featuresUrl = "https://api.spotify.com/v1/audio-features/" + res.spotifyId;
                    HttpRequest featuresReq = HttpRequest.newBuilder()
                            .uri(URI.create(featuresUrl))
                            .header("Authorization", "Bearer " + accessToken)
                            .GET()
                            .build();

                    enforceGlobalRateLimit();
                    HttpResponse<String> featuresResp = client.send(featuresReq, HttpResponse.BodyHandlers.ofString());

                    if (featuresResp.statusCode() == 429) {
                        triggerPenaltyBackoff(featuresResp.headers().firstValue("Retry-After"));
                        res.rateLimited = true;
                        return res; // Επιστρέφουμε rateLimited για να το ξαναδοκιμάσει στο επόμενο cycle
                    }

                    if (featuresResp.statusCode() == 200) {
                        JsonNode fNode = mapper.readTree(featuresResp.body());
                        if (fNode.hasNonNull("tempo")) {
                            res.tempo = fNode.get("tempo").asDouble();
                            res.energy = fNode.get("energy").asDouble();
                            res.danceability = fNode.get("danceability").asDouble();
                            res.valence = fNode.get("valence").asDouble();
                            res.acousticness = fNode.get("acousticness").asDouble();
                        }
                    }
                    
                    res.success = true;
                    System.out.println("✅ Spotify Linked: " + targetArtist + " - " + cleanTitle + " (BPM: " + res.tempo + ")");
                    return res;
                }
            }
        } catch (Exception e) {
            // Σιωπηρή αγνόηση για να μην κρασάρει το thread
        }
        return res;
    }
}