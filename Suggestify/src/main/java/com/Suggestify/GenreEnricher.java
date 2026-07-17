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
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GenreEnricher {

    private static final String LASTFM_API_KEY = "9eee586b5f031e6b2740463c6d5f96a1";
    private static final Pattern TAG_PATTERN = Pattern.compile("\"name\":\"([^\"]+)\"");
    
    // Ασφαλείς ρυθμίσεις για να μην μας μπλοκάρει το Last.fm
    private static final int THREAD_POOL_SIZE = 4;
    private static final int BATCH_SIZE = 1000;
    private static final int API_DELAY_MS = 250;

    static class AlbumRow {
        final int id;
        final String title;
        final String artist;

        AlbumRow(int id, String title, String artist) {
            this.id = id;
            this.title = title;
            this.artist = artist;
        }
    }

    static class EnrichmentResult {
        final int albumId;
        final String title;
        final List<String> genres;

        EnrichmentResult(int albumId, String title, List<String> genres) {
            this.albumId = albumId;
            this.title = title;
            this.genres = genres;
        }
    }

    // ΑΛΛΑΓΗ: Προσθήκη της μεθόδου main για να είναι εκτελέσιμο
    public static void main(String[] args) {
        System.out.println("🎸 Starting Last.fm Genre Enricher (Batch & Anti-Deadlock)...");

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
            LIMIT %d
        """.formatted(BATCH_SIZE);

        ExecutorService executor = Executors.newFixedThreadPool(THREAD_POOL_SIZE);
        HttpClient client = HttpClient.newHttpClient();
        int cycle = 1;
        int totalUpdated = 0;

        try (Connection conn = DatabaseManager.getConnection()) {
            conn.setAutoCommit(false);

            while (true) {
                List<AlbumRow> batch = new ArrayList<>();
                
                // Τραβάμε τα δεδομένα και ΚΛΕΙΝΟΥΜΕ το ResultSet αμέσως (καλή πρακτική)
                try (PreparedStatement selectStmt = conn.prepareStatement(selectAlbumsSQL);
                     ResultSet rs = selectStmt.executeQuery()) {
                    while (rs.next()) {
                        batch.add(new AlbumRow(rs.getInt("id"), rs.getString("title"), rs.getString("artist_name")));
                    }
                }

                if (batch.isEmpty()) {
                    System.out.println("🏁 No more albums without genres!");
                    break;
                }

                System.out.println("🔄 Starting Cycle #" + cycle + " (Processing " + batch.size() + " albums)...");

                List<Future<EnrichmentResult>> futures = new ArrayList<>();
                for (AlbumRow row : batch) {
                    futures.add(executor.submit(() -> fetchFromLastFm(client, row)));
                }

                List<EnrichmentResult> processedResults = new ArrayList<>();
                for (Future<EnrichmentResult> future : futures) {
                    try {
                        processedResults.add(future.get());
                    } catch (Exception e) {
                        e.printStackTrace();
                    }
                }

                // ΑΛΛΑΓΗ: ANTI-DEADLOCK FIX. Ταξινομούμε κατά ID πριν τη Βάση.
                processedResults.sort(Comparator.comparingInt(a -> a.albumId));

                int successCount = 0;
                for (EnrichmentResult res : processedResults) {
                    // Αν δεν βρήκε, βάζουμε 'unknown' για να μην το ξαναψάξει
                    if (res.genres.isEmpty()) {
                        res.genres.add("unknown");
                        System.out.println("⚠️ No genres found for: " + res.title + " (Marked as unknown)");
                    } else {
                        System.out.println("✅ " + res.title + " -> " + String.join(", ", res.genres));
                    }
                    
                    saveAlbumGenresToDatabase(conn, res.albumId, res.genres);
                    successCount++;
                }

                conn.commit();
                totalUpdated += successCount;
                System.out.println("✅ Cycle #" + cycle + " Complete! Saved genres for " + successCount + " albums.");
                cycle++;
            }

            System.out.println("🎉 FULL GENRE ENRICHMENT COMPLETE! Total Albums Updated: " + totalUpdated);

        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            executor.shutdown();
            try {
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
            }
        }
    }

    private static EnrichmentResult fetchFromLastFm(HttpClient client, AlbumRow row) {
        List<String> validGenres = new ArrayList<>();
        try {
            String encodedArtist = URLEncoder.encode(row.artist, StandardCharsets.UTF_8).replace("+", "%20");
            String encodedAlbum = URLEncoder.encode(row.title, StandardCharsets.UTF_8).replace("+", "%20");
            
            String url = "http://ws.audioscrobbler.com/2.0/?method=album.gettoptags&artist=" +
                    encodedArtist + "&album=" + encodedAlbum + "&api_key=" + LASTFM_API_KEY + "&format=json";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                Matcher matcher = TAG_PATTERN.matcher(response.body());
                while (matcher.find() && validGenres.size() < 3) {
                    String tag = matcher.group(1).toLowerCase().trim();
                    if (isValidGenre(tag)) validGenres.add(tag);
                }
            }
            
            Thread.sleep(API_DELAY_MS);

        } catch (Exception e) {
            // Αν σκάσει, επιστρέφει άδεια λίστα και παίρνει "unknown"
        }
        return new EnrichmentResult(row.id, row.title, validGenres);
    }

    private static boolean isValidGenre(String tag) {
        if (tag.length() < 3 || tag.length() > 25) return false;
        if (tag.matches(".*\\d.*")) return false;
        List<String> blacklist = List.of(
                "seen live", "awesome", "favorite", "love at first listen", "albums i own",
                "beautiful", "amazing", "canadian", "american", "british", "masterpiece"
        );
        return !blacklist.contains(tag);
    }

    private static void saveAlbumGenresToDatabase(Connection conn, int albumId, List<String> genres) throws Exception {
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