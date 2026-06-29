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

public class ArtistImageUpdater {

    public static void update() {
        System.out.println("Starting Artist Image Updater (via Deezer API)...");

        // Φέρνουμε τους καλλιτέχνες ταξινομημένους με βάση τα streams (Priority Loading!)
        String selectArtistsSQL = """
            SELECT a.id, a.name 
            FROM artists a
            JOIN song_artists sa ON sa.artist_id = a.id
            JOIN streams s ON s.song_id = sa.song_id
            WHERE a.image_url IS NULL
            GROUP BY a.id, a.name
            ORDER BY COUNT(s.id) DESC
        """;

        String updateArtistSQL = "UPDATE artists SET image_url = ? WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection()) {
            HttpClient client = HttpClient.newHttpClient();
            int apiCalls = 0;
            int totalUpdated = 0;

            try (PreparedStatement selectStmt = conn.prepareStatement(selectArtistsSQL);
                 PreparedStatement updateStmt = conn.prepareStatement(updateArtistSQL);
                 ResultSet rs = selectStmt.executeQuery()) {

                while (rs.next()) {
                    int artistId = rs.getInt("id");
                    String artistName = rs.getString("name");

                    String imageUrl = fetchArtistPhoto(client, artistName);

                    if (imageUrl != null) {
                        updateStmt.setString(1, imageUrl);
                        updateStmt.setInt(2, artistId);
                        updateStmt.executeUpdate();
                        totalUpdated++;
                        System.out.println("✅ Found photo for: " + artistName);
                    } else {
                        System.out.println("❌ No photo found for: " + artistName);
                    }

                    apiCalls++;
                    Thread.sleep(100); // 100ms delay για να είμαστε καλά παιδιά στο API του Deezer
                }
            }

            System.out.println("\n✅ Finished! Made " + apiCalls + " API calls.");
            System.out.println("🎉 Successfully added images to " + totalUpdated + " artists!");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static String fetchArtistPhoto(HttpClient client, String artistName) {
        try {
            String encodedName = URLEncoder.encode(artistName, StandardCharsets.UTF_8.toString());
            String url = "https://api.deezer.com/search/artist?q=" + encodedName + "&limit=1";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                Matcher m = Pattern.compile("\"picture_xl\"\\s*:\\s*\"([^\"]+)\"").matcher(response.body());
                if (m.find()) {
                    return m.group(1).replace("\\/", "/");
                }
            }
        } catch (Exception e) {
            System.out.println("Failed request for: " + artistName);
        }
        return null;
    }
}