package com.Suggestify;

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

    public void importRecords(List<StreamingRecord> records) {
        String insertStreamSQL = "INSERT INTO streams (song_id, played_at, ms_played) VALUES (?, ?, ?)";

        try (Connection conn = DatabaseManager.getConnection();
             PreparedStatement streamStmt = conn.prepareStatement(insertStreamSQL)) {

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
                int songId = getOrCreateSong(conn, cleanTrackName, artistIds, albumId);

                streamStmt.setInt(1, songId);
                streamStmt.setTimestamp(2, Timestamp.from(record.getTimestamp()));
                streamStmt.setInt(3, record.getMsPlayed());
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

    private int getOrCreateSong(Connection conn, String songTitle, List<Integer> artistIds, int albumId) throws Exception {
        if (songCache.containsKey(songTitle)) return songCache.get(songTitle);

        String selectSQL = "SELECT id FROM songs WHERE title = ?";
        try (PreparedStatement stmt = conn.prepareStatement(selectSQL)) {
            stmt.setString(1, songTitle);
            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    songCache.put(songTitle, rs.getInt("id"));
                    return rs.getInt("id");
                }
            }
        }

        String insertSongSQL = "INSERT INTO songs (title, album_id) VALUES (?, ?)";
        int songId = -1;
        try (PreparedStatement stmt = conn.prepareStatement(insertSongSQL, Statement.RETURN_GENERATED_KEYS)) {
            stmt.setString(1, songTitle);
            if (albumId != -1) {
                stmt.setInt(2, albumId);
            } else {
                stmt.setNull(2, java.sql.Types.INTEGER);
            }

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

        songCache.put(songTitle, songId);
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
}