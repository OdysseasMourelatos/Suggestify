package com.Suggestify;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DatabaseImporter {

    private static final Pattern FEAT_PATTERN = Pattern.compile("\\((?:feat\\.|ft\\.|with)\\s(.*?)\\)", Pattern.CASE_INSENSITIVE);
    private static final int BATCH_SIZE = 5000;

    private final Map<String, Integer> artistCache = new HashMap<>();
    private final Map<String, Integer> songCache = new HashMap<>();
    private final Map<String, Integer> albumCache = new HashMap<>();

    private void preloadCaches(Connection conn) throws Exception {
        System.out.println("Pre-loading caches to bypass network latency...");
        try (Statement stmt = conn.createStatement()) {
            try (ResultSet rs = stmt.executeQuery("SELECT id, name FROM artists")) {
                while (rs.next()) artistCache.put(rs.getString("name"), rs.getInt("id"));
            }
            try (ResultSet rs = stmt.executeQuery("SELECT id, title FROM albums")) {
                while (rs.next()) albumCache.put(rs.getString("title"), rs.getInt("id"));
            }
            try (ResultSet rs = stmt.executeQuery("SELECT s.id, s.title, s.track_uri, sa.artist_id FROM songs s LEFT JOIN song_artists sa ON s.id = sa.song_id AND sa.is_feature = FALSE")) {
                while (rs.next()) {
                    String uri = rs.getString("track_uri");
                    if (uri != null && !uri.isEmpty()) {
                        songCache.put(uri, rs.getInt("id"));
                    } else {
                        String title = rs.getString("title");
                        int artistId = rs.getInt("artist_id");
                        if (rs.wasNull()) artistId = -1;
                        songCache.put(title.toLowerCase() + "|" + artistId, rs.getInt("id"));
                    }
                }
            }
        }
        System.out.println("Caches loaded! Artists: " + artistCache.size() + ", Albums: " + albumCache.size());
    }

    public void importRecords(List<StreamingRecord> records, String username) {
        String insertStreamSQL = "INSERT INTO streams (user_id, song_id, played_at, ms_played) VALUES (?, ?, ?, ?)";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement streamStmt = conn.prepareStatement(insertStreamSQL)) {

            preloadCaches(conn);
            
            int userId = getOrCreateUser(conn, username);

            // Καθαρίζουμε το ιστορικό του χρήστη πριν ανεβάσουμε το νέο ZIP
            try (PreparedStatement clearStmt = conn.prepareStatement("DELETE FROM streams WHERE user_id = ?")) {
                clearStmt.setInt(1, userId);
                clearStmt.executeUpdate();
            }
            // ----------------------------------------

            conn.setAutoCommit(false);
            int count = 0;

            for (StreamingRecord record : records) {

                if (record.getTrackName() == null || record.getArtistName() == null || record.getTimestamp() == null) {
                    continue;
                }

                List<String> extractedArtists = new ArrayList<>();

                String[] mainArtists = record.getArtistName().split(",\\s*|\\s*&\\s*");
                for (String artist : mainArtists) {
                    extractedArtists.add(artist.trim());
                }

                String cleanTrackName = record.getTrackName();
                Matcher matcher = FEAT_PATTERN.matcher(record.getTrackName());
                if (matcher.find()) {
                    String[] featArtists = matcher.group(1).split(",\\s*|\\s*(?:&|and)\\s*");
                    for (String feat : featArtists) {
                        extractedArtists.add(feat.trim());
                    }
                    cleanTrackName = record.getTrackName().replace(matcher.group(0), "").trim();
                }

                List<Integer> artistIds = new ArrayList<>();
                for (String artistName : extractedArtists) {
                    artistIds.add(getOrCreateArtist(conn, artistName));
                }

                int albumId = getOrCreateAlbum(conn, record.getAlbumName());
                int songId = getOrCreateSong(conn, cleanTrackName, artistIds, albumId, record.getTrackUri());

                streamStmt.setInt(1, userId);
                streamStmt.setInt(2, songId);
                streamStmt.setTimestamp(3, Timestamp.from(record.getTimestamp()));
                streamStmt.setInt(4, record.getMsPlayed());
                streamStmt.addBatch();

                count++;
                if (count % BATCH_SIZE == 0) {
                    streamStmt.executeBatch();
                    conn.commit();
                }
            }

            streamStmt.executeBatch();
            conn.commit();

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private int getOrCreateArtist(Connection conn, String artistName) throws Exception {
        if (artistCache.containsKey(artistName)) return artistCache.get(artistName);

        String selectSQL = "SELECT id FROM artists WHERE name = ?";
        try (PreparedStatement stmt = conn.prepareStatement(selectSQL)) {
            stmt.setString(1, artistName);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    artistCache.put(artistName, rs.getInt("id"));
                    return rs.getInt("id");
                }
            }
        }

        String insertSQL = "INSERT INTO artists (name) VALUES (?)";
        try (PreparedStatement stmt = conn.prepareStatement(insertSQL, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setString(1, artistName);
            stmt.executeUpdate();
            try (ResultSet rs = stmt.getGeneratedKeys()) {
                if (rs.next()) {
                    int id = rs.getInt(1);
                    artistCache.put(artistName, id);
                    return id;
                }
            }
        }
        return -1;
    }

    private int getOrCreateSong(Connection conn, String songTitle, List<Integer> artistIds, int albumId, String trackUri) throws Exception {
        String cacheKey = (trackUri != null && !trackUri.isEmpty()) ?
                trackUri :
                (songTitle.toLowerCase() + "|" + (artistIds.isEmpty() ? -1 : artistIds.get(0)));

        if (songCache.containsKey(cacheKey)) return songCache.get(cacheKey);

        if (trackUri != null && !trackUri.isEmpty()) {
            String selectUriSQL = "SELECT id FROM songs WHERE track_uri = ?";
            try (PreparedStatement stmt = conn.prepareStatement(selectUriSQL)) {
                stmt.setString(1, trackUri);
                try (ResultSet rs = stmt.executeQuery()) {
                    if (rs.next()) {
                        int foundId = rs.getInt("id");
                        songCache.put(cacheKey, foundId);
                        return foundId;
                    }
                }
            }
        }

        int primaryArtistId = artistIds.isEmpty() ? -1 : artistIds.get(0);
        String selectFallbackSQL = "SELECT s.id FROM songs s " +
                "JOIN song_artists sa ON s.id = sa.song_id " +
                "WHERE s.title = ? AND sa.artist_id = ? AND sa.is_feature = FALSE";

        try (PreparedStatement stmt = conn.prepareStatement(selectFallbackSQL)) {
            stmt.setString(1, songTitle);
            stmt.setInt(2, primaryArtistId);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    int foundId = rs.getInt("id");
                    songCache.put(cacheKey, foundId);
                    return foundId;
                }
            }
        }

        String insertSongSQL = "INSERT INTO songs (title, album_id, track_uri) VALUES (?, ?, ?)";
        int songId = -1;
        try (PreparedStatement stmt = conn.prepareStatement(insertSongSQL, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setString(1, songTitle);

            if (albumId != -1) {
                stmt.setInt(2, albumId);
            } else {
                stmt.setNull(2, java.sql.Types.INTEGER);
            }

            stmt.setString(3, trackUri);

            stmt.executeUpdate();
            try (ResultSet rs = stmt.getGeneratedKeys()) {
                if (rs.next()) {
                    songId = rs.getInt(1);
                }
            }
        }

        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, ?) ON CONFLICT (song_id, artist_id) DO NOTHING";
        try (PreparedStatement relationStmt = conn.prepareStatement(insertRelationSQL)) {
            for (int i = 0; i < artistIds.size(); i++) {
                relationStmt.setInt(1, songId);
                relationStmt.setInt(2, artistIds.get(i));
                relationStmt.setBoolean(3, i > 0);
                relationStmt.addBatch();
            }
            relationStmt.executeBatch();
        }

        songCache.put(cacheKey, songId);
        return songId;
    }
    
    private int getOrCreateAlbum(Connection conn, String albumTitle) throws Exception {
        if (albumTitle == null || albumTitle.trim().isEmpty()) return -1; // Handling για null albums
        if (albumCache.containsKey(albumTitle)) return albumCache.get(albumTitle);

        String selectSQL = "SELECT id FROM albums WHERE title = ?";
        try (PreparedStatement stmt = conn.prepareStatement(selectSQL)) {
            stmt.setString(1, albumTitle);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    albumCache.put(albumTitle, rs.getInt("id"));
                    return rs.getInt("id");
                }
            }
        }

        String insertSQL = "INSERT INTO albums (title) VALUES (?) ON CONFLICT (title) DO NOTHING";
        try (PreparedStatement stmt = conn.prepareStatement(insertSQL, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setString(1, albumTitle);
            stmt.executeUpdate();
            try (ResultSet rs = stmt.getGeneratedKeys()) {
                if (rs.next()) {
                    int id = rs.getInt(1);
                    albumCache.put(albumTitle, id);
                    return id;
                }
            }
        }

        try (PreparedStatement stmt = conn.prepareStatement(selectSQL)) {
            stmt.setString(1, albumTitle);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) return rs.getInt("id");
            }
        }
        return -1;
    }

    private String fetchImageUrl(String trackUri) {
        if (trackUri == null || trackUri.isEmpty()) return null;

        String oembedUrl = "https://open.spotify.com/oembed?url=" + trackUri;

        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(oembedUrl))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            // Αν το response είναι 200 OK, τραβάμε το thumbnail_url
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

    private int getOrCreateUser(Connection conn, String username) throws Exception {
        String selectSQL = "SELECT id FROM users WHERE username = ?";
        try (PreparedStatement stmt = conn.prepareStatement(selectSQL)) {
            stmt.setString(1, username);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) return rs.getInt("id");
            }
        }
        String insertSQL = "INSERT INTO users (username) VALUES (?)";
        try (PreparedStatement stmt = conn.prepareStatement(insertSQL, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setString(1, username);
            stmt.executeUpdate();
            try (ResultSet rs = stmt.getGeneratedKeys()) {
                if (rs.next()) return rs.getInt(1);
            }
        }
        return -1;
    }
}