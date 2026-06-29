package com.Suggestify;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ImageUpdater {

    public static void update() {
        System.out.println("Starting PRIORITY background image updater...");

        // ΒΗΜΑ 1: Albums ταξινομημένα με βάση τα συνολικά streams των τραγουδιών τους!
        String selectAlbumsSQL = """
            SELECT so.album_id, MIN(so.track_uri) as track_uri 
            FROM songs so
            JOIN streams s ON s.song_id = so.id
            WHERE so.image_url IS NULL AND so.track_uri IS NOT NULL AND so.album_id IS NOT NULL 
            GROUP BY so.album_id
            ORDER BY COUNT(s.id) DESC
        """;

        String updateSongsSQL = "UPDATE songs SET image_url = ? WHERE album_id = ?";

        // ΒΗΜΑ 2: Singles (ορφανά τραγούδια) ταξινομημένα επίσης με βάση τα streams!
        String selectOrphansSQL = """
            SELECT so.id, so.track_uri 
            FROM songs so
            JOIN streams s ON s.song_id = so.id
            WHERE so.image_url IS NULL AND so.track_uri IS NOT NULL AND so.album_id IS NULL
            GROUP BY so.id, so.track_uri
            ORDER BY COUNT(s.id) DESC
        """;

        String updateOrphanSQL = "UPDATE songs SET image_url = ? WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection()) {
            HttpClient client = HttpClient.newHttpClient();
            int apiCalls = 0;
            int totalSongsUpdated = 0;

            // --- ΦΑΣΗ 1: Ενημέρωση ανά Album (Τα πιο δημοφιλή πρώτα) ---
            System.out.println("\n--- Processing Albums (Most Streamed First) ---");
            try (PreparedStatement selectStmt = conn.prepareStatement(selectAlbumsSQL);
                 PreparedStatement updateStmt = conn.prepareStatement(updateSongsSQL);
                 ResultSet rs = selectStmt.executeQuery()) {

                while (rs.next()) {
                    int albumId = rs.getInt("album_id");
                    String trackUri = rs.getString("track_uri");

                    String imageUrl = fetchImageUrl(client, trackUri);

                    if (imageUrl != null) {
                        updateStmt.setString(1, imageUrl);
                        updateStmt.setInt(2, albumId);
                        int updatedRows = updateStmt.executeUpdate();

                        totalSongsUpdated += updatedRows;
                        System.out.println("Album ID " + albumId + " fetch success -> " + updatedRows + " tracks updated!");
                    }
                    apiCalls++;
                    Thread.sleep(50); // Μικρό delay για να μην φάμε block
                }
            }

            // --- ΦΑΣΗ 2: Ενημέρωση ορφανών τραγουδιών (Τα πιο δημοφιλή πρώτα) ---
            System.out.println("\n--- Processing Orphan Tracks (Most Streamed First) ---");
            try (PreparedStatement selectStmt = conn.prepareStatement(selectOrphansSQL);
                 PreparedStatement updateStmt = conn.prepareStatement(updateOrphanSQL);
                 ResultSet rs = selectStmt.executeQuery()) {

                while (rs.next()) {
                    int songId = rs.getInt("id");
                    String trackUri = rs.getString("track_uri");

                    String imageUrl = fetchImageUrl(client, trackUri);

                    if (imageUrl != null) {
                        updateStmt.setString(1, imageUrl);
                        updateStmt.setInt(2, songId);
                        updateStmt.executeUpdate();
                        totalSongsUpdated++;
                        System.out.println("Track ID " + songId + " fetch success!");
                    }
                    apiCalls++;
                    Thread.sleep(50);
                }
            }

            System.out.println("\n✅ Finished! Made " + apiCalls + " API calls to Spotify.");
            System.out.println("🎉 Successfully added images to " + totalSongsUpdated + " tracks!");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static String fetchImageUrl(HttpClient client, String trackUri) {
        if (trackUri == null || trackUri.isEmpty()) return null;
        String oembedUrl = "https://open.spotify.com/oembed?url=" + trackUri;

        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(oembedUrl))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                Matcher m = Pattern.compile("\"thumbnail_url\"\\s*:\\s*\"([^\"]+)\"").matcher(response.body());
                if (m.find()) {
                    return m.group(1);
                }
            }
        } catch (Exception e) {
            System.out.println("Failed to fetch image for: " + trackUri);
        }
        return null;
    }
}