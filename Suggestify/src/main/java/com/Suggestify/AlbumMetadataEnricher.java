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

public class AlbumMetadataEnricher {

    private static final Pattern TRACK_COUNT_PATTERN = Pattern.compile("\"trackCount\"\\s*:\\s*(\\d+)");
    private static final Pattern DATE_PATTERN = Pattern.compile("\"releaseDate\"\\s*:\\s*\"([0-9]{4}-[0-9]{2}-[0-9]{2})");
    private static final Pattern GENRE_PATTERN = Pattern.compile("\"primaryGenreName\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern EXPLICIT_PATTERN = Pattern.compile("\"collectionExplicitness\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern LABEL_PATTERN = Pattern.compile("\"copyright\"\\s*:\\s*\"([^\"]+)\"");

    public static void main(String[] args) {
        System.out.println("💿 Starting iTunes Album Metadata Enricher...");

        // Βρίσκουμε τον Primary Artist κάθε άλμπουμ (αυτόν με τα περισσότερα τραγούδια)
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
            WHERE al.total_tracks IS NULL
            LIMIT 500
        """;

        String updateAlbumSQL = "UPDATE albums SET total_tracks=?, release_date=?::date, primary_genre=?, is_explicit=?, label=? WHERE id=?";
        String markNotFoundSQL = "UPDATE albums SET total_tracks = 0 WHERE id = ?";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement selectStmt = conn.prepareStatement(selectAlbumsSQL);
             PreparedStatement updateStmt = conn.prepareStatement(updateAlbumSQL);
             PreparedStatement notFoundStmt = conn.prepareStatement(markNotFoundSQL);
             ResultSet rs = selectStmt.executeQuery()) {

            HttpClient client = HttpClient.newHttpClient();
            int successCount = 0;
            int notFoundCount = 0;

            while (rs.next()) {
                int albumId = rs.getInt("id");
                String title = rs.getString("title");
                String artist = rs.getString("artist_name");

                // Καθαρισμός τίτλου άλμπουμ για καλύτερα αποτελέσματα
                String cleanTitle = title.replaceAll("(?i)\\s*\\(?(Deluxe|Expanded|Remastered|Bonus Track)(?:\\s+Edition|\\s+Version)?\\)?\\s*", "").trim();

                String query = artist + " " + cleanTitle;
                String encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8).replace("+", "%20");
                String apiUrl = "https://itunes.apple.com/search?term=" + encodedQuery + "&entity=album&limit=1";

                HttpRequest request = HttpRequest.newBuilder().uri(URI.create(apiUrl)).GET().build();
                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

                if (response.statusCode() == 200 && (response.body().contains("\"resultCount\":1") || response.body().contains("\"resultCount\": 1"))) {
                    String json = response.body();

                    Integer trackCount = extractInt(TRACK_COUNT_PATTERN, json);
                    if (trackCount != null && trackCount > 0) {
                        String releaseDate = extractString(DATE_PATTERN, json);
                        String genre = extractString(GENRE_PATTERN, json);
                        String explicitness = extractString(EXPLICIT_PATTERN, json);
                        boolean isExplicit = "explicit".equalsIgnoreCase(explicitness);
                        String label = extractString(LABEL_PATTERN, json);

                        updateStmt.setInt(1, trackCount);
                        if (releaseDate != null) updateStmt.setString(2, releaseDate); else updateStmt.setNull(2, java.sql.Types.VARCHAR);
                        if (genre != null) updateStmt.setString(3, genre); else updateStmt.setNull(3, java.sql.Types.VARCHAR);
                        updateStmt.setBoolean(4, isExplicit);
                        if (label != null) updateStmt.setString(5, label); else updateStmt.setNull(5, java.sql.Types.VARCHAR);
                        updateStmt.setInt(6, albumId);

                        updateStmt.executeUpdate();

                        System.out.println("✅ Album Updated: " + artist + " - " + cleanTitle + (isExplicit ? " [E]" : ""));
                        successCount++;
                    } else {
                        notFoundStmt.setInt(1, albumId);
                        notFoundStmt.executeUpdate();
                        notFoundCount++;
                    }
                } else {
                    System.out.println("⚠️ Album Not Found: " + artist + " - " + cleanTitle);
                    notFoundStmt.setInt(1, albumId);
                    notFoundStmt.executeUpdate();
                    notFoundCount++;
                }
                Thread.sleep(120); // Rate Limit Protection
            }
            System.out.println("🎉 Album Enrichment Complete! Updated: " + successCount + " | Not Found: " + notFoundCount);

        } catch (Exception e) {
            e.printStackTrace();
        }
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