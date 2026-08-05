package com.Suggestify;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class SpotifyAuthManager {

    // Διαβάζουμε τα κλειδιά δυναμικά από τα Environment Variables που μας περνάει η Python!
    private static final String CLIENT_ID = System.getenv("SPOTIFY_CLIENT_ID");
    private static final String CLIENT_SECRET = System.getenv("SPOTIFY_CLIENT_SECRET");
    
    private static final String TOKEN_URL = "https://accounts.spotify.com/api/token";
    
    private static String currentAccessToken = null;
    private static long tokenExpirationTime = 0; // Σε milliseconds
    
    private static final HttpClient client = HttpClient.newHttpClient();
    private static final ObjectMapper mapper = new ObjectMapper();

    /**
     * Επιστρέφει ένα έγκυρο Bearer Token. Αν το υπάρχον έχει λήξει (ή λήγει σε < 5 λεπτά),
     * κάνει αυτόματα request για καινούργιο!
     */
    public static synchronized String getAccessToken() {
        if (CLIENT_ID == null || CLIENT_SECRET == null) {
            System.err.println("❌ ERROR: Spotify Credentials not found in Environment Variables!");
            return null;
        }

        // Αν δεν έχουμε token ή λήγει σε λιγότερο από 5 λεπτά (300.000 ms), ζητάμε νέο
        if (currentAccessToken == null || System.currentTimeMillis() > (tokenExpirationTime - 300000)) {
            refreshAccessToken();
        }
        return currentAccessToken;
    }

    private static void refreshAccessToken() {
        try {
            System.out.println("🔐 Requesting new Spotify Access Token...");
            
            // Το Spotify απαιτεί Base64 encoded: "ClientId:ClientSecret"
            String authString = CLIENT_ID + ":" + CLIENT_SECRET;
            String encodedAuth = Base64.getEncoder().encodeToString(authString.getBytes(StandardCharsets.UTF_8));
            
            // Body του request (Client Credentials Flow)
            String requestBody = "grant_type=client_credentials";
            
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(TOKEN_URL))
                    .header("Authorization", "Basic " + encodedAuth)
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                    .build();
                    
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() == 200) {
                JsonNode root = mapper.readTree(response.body());
                currentAccessToken = root.get("access_token").asText();
                
                // Το expiresIn είναι συνήθως 3600 δευτερόλεπτα (1 ώρα)
                int expiresIn = root.get("expires_in").asInt(); 
                tokenExpirationTime = System.currentTimeMillis() + (expiresIn * 1000L);
                
                System.out.println("✅ Spotify Token acquired successfully! Expires in: " + expiresIn + " seconds.");
            } else {
                System.err.println("❌ Failed to get Spotify Token. HTTP " + response.statusCode());
                System.err.println("Response: " + response.body());
            }
            
        } catch (Exception e) {
            System.err.println("❌ Exception during Spotify Auth: " + e.getMessage());
        }
    }
}
