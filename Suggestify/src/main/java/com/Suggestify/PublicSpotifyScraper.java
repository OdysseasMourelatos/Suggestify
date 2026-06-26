package com.Suggestify;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class PublicSpotifyScraper {
    public static void main(String[] args) {
        // Το URI που βρήκες στο JSON σου
        String trackUri = "spotify:track:3GlQVf7QbQv1bro2mPL3K4";

        // Το δημόσιο endpoint του Spotify
        String oembedUrl = "https://open.spotify.com/oembed?url=" + trackUri;

        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(oembedUrl))
                .GET() // Απλό GET request, χωρίς Headers, χωρίς Tokens!
                .build();

        try {
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println(response.body());
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}