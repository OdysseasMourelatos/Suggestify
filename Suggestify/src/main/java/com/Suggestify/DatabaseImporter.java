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
import java.util.stream.Collectors;

public class DatabaseImporter {

    private static final Pattern FEAT_PATTERN = Pattern.compile("\\((?:feat\\.|ft\\.|with)\\s(.*?)\\)", Pattern.CASE_INSENSITIVE);
    private static final int BATCH_SIZE = 5000;

    // Caches μόνο για τη διάρκεια αυτού του Import (για να μη διπλογράφουμε στο ίδιο batch)
    private final Map<String, Integer> localArtistCache = new HashMap<>();
    private final Map<String, Integer> localAlbumCache = new HashMap<>();
    private final Map<String, Integer> localSongCache = new HashMap<>();

    public void importRecords(List<StreamingRecord> records, String username, String timeZoneStr) {
        long totalStartTime = System.currentTimeMillis();
        System.out.println("🚀 Starting HIGH-PERFORMANCE Database Insertion...");

        try (Connection conn = DatabaseManager.getConnection()) {
            conn.setAutoCommit(false); // Κρίσιμο για ταχύτητα

            int userId = getOrCreateUser(conn, username);
            clearUserHistory(conn, userId);

            // ΒΗΜΑ 1: Συγκέντρωση και Bulk Insert Καλλιτεχνών & Άλμπουμ
            System.out.println("📦 Extracting & Inserting Artists and Albums (Bulk)...");
            processArtistsAndAlbumsBulk(conn, records);

            // Αφού μπήκαν, τραβάμε τα IDs τους για να τα χρησιμοποιήσουμε (πολύ πιο γρήγορο από το ένα-ένα)
            refreshLocalCaches(conn);

            // ΒΗΜΑ 2: Συγκέντρωση και Bulk Insert Τραγουδιών
            System.out.println("🎵 Extracting & Inserting Songs (Bulk)...");
            processSongsBulk(conn, records);
            refreshSongCache(conn);

            // ΒΗΜΑ 3: Bulk Insert Streams & Σχέσεων (Song_Artists)
            System.out.println("🌊 Inserting Streams and Relationships (Bulk)...");
            processStreamsAndRelationshipsBulk(conn, records, userId, timeZoneStr);

            // ----> ΝΕΟ ΒΗΜΑ 4: ΚΑΘΑΡΙΣΜΟΣ ΔΙΠΛΟΤΥΠΩΝ ΕΔΩ <----
            deduplicateSongs(conn);

            conn.commit(); // <-- Αμέσως πριν το commit
            long totalEndTime = System.currentTimeMillis();
            System.out.println("🎉 Import complete! Total time: " + (totalEndTime - totalStartTime) + "ms");

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void clearUserHistory(Connection conn, int userId) throws Exception {
        try (PreparedStatement clearStmt = conn.prepareStatement("DELETE FROM streams WHERE user_id = ?")) {
            clearStmt.setInt(1, userId);
            clearStmt.executeUpdate();
            conn.commit();
        }
    }

    // --- BULK INSERTS ---

    private void processArtistsAndAlbumsBulk(Connection conn, List<StreamingRecord> records) throws Exception {
        String insertArtistSQL = "INSERT INTO artists (name) VALUES (?) ON CONFLICT (name) DO NOTHING";
        String insertAlbumSQL = "INSERT INTO albums (title) VALUES (?) ON CONFLICT (title) DO NOTHING";

        try (PreparedStatement artistStmt = conn.prepareStatement(insertArtistSQL);
             PreparedStatement albumStmt = conn.prepareStatement(insertAlbumSQL)) {

            Map<String, Boolean> seenArtists = new HashMap<>();
            Map<String, Boolean> seenAlbums = new HashMap<>();

            for (StreamingRecord record : records) {
                if (record.getArtistName() == null || record.getTrackName() == null) continue;

                // Artists
                List<String> artists = extractAllArtists(record.getArtistName(), record.getTrackName());
                for (String artist : artists) {
                    if (!seenArtists.containsKey(artist)) {
                        seenArtists.put(artist, true);
                        artistStmt.setString(1, artist);
                        artistStmt.addBatch();
                    }
                }

                // Albums
                String albumName = record.getAlbumName();
                if (albumName != null && !albumName.trim().isEmpty() && !seenAlbums.containsKey(albumName)) {
                    seenAlbums.put(albumName, true);
                    albumStmt.setString(1, albumName);
                    albumStmt.addBatch();
                }
            }

            artistStmt.executeBatch();
            albumStmt.executeBatch();
            conn.commit();
        }
    }

    private void processSongsBulk(Connection conn, List<StreamingRecord> records) throws Exception {
        // Χρησιμοποιούμε ON CONFLICT (title, album_id) αν υπάρχει, αλλιώς αγνοούμε διπλότυπα με βάση URI ή Title
        String insertSongSQL = "INSERT INTO songs (title, album_id, track_uri) VALUES (?, ?, ?) ON CONFLICT DO NOTHING";

        try (PreparedStatement songStmt = conn.prepareStatement(insertSongSQL)) {
            Map<String, Boolean> seenSongs = new HashMap<>();

            for (StreamingRecord record : records) {
                if (record.getArtistName() == null || record.getTrackName() == null) continue;

                String cleanTrackName = cleanTrackName(record.getTrackName());
                String uri = record.getTrackUri();

                // Δημιουργία ενός μοναδικού κλειδιού για να μη στείλουμε το ίδιο τραγούδι 2 φορές στο ίδιο batch
                String uniqueKey = (uri != null && !uri.isEmpty()) ? uri : cleanTrackName.toLowerCase();

                if (!seenSongs.containsKey(uniqueKey)) {
                    seenSongs.put(uniqueKey, true);

                    songStmt.setString(1, cleanTrackName);

                    String albumName = record.getAlbumName();
                    Integer albumId = localAlbumCache.get(albumName);
                    if (albumId != null) {
                        songStmt.setInt(2, albumId);
                    } else {
                        songStmt.setNull(2, java.sql.Types.INTEGER);
                    }

                    songStmt.setString(3, uri);
                    songStmt.addBatch();
                }
            }
            songStmt.executeBatch();
            conn.commit();
        }
    }

    private void processStreamsAndRelationshipsBulk(Connection conn, List<StreamingRecord> records, int userId, String timeZoneStr) throws Exception {
        String insertStreamSQL = "INSERT INTO streams (user_id, song_id, played_at, ms_played) VALUES (?, ?, ?, ?)";
        String insertRelationSQL = "INSERT INTO song_artists (song_id, artist_id, is_feature) VALUES (?, ?, ?) ON CONFLICT (song_id, artist_id) DO NOTHING";

        java.time.ZoneId userZoneId = java.time.ZoneId.of(timeZoneStr);
        
        try (PreparedStatement streamStmt = conn.prepareStatement(insertStreamSQL);
             PreparedStatement relationStmt = conn.prepareStatement(insertRelationSQL)) {

            int count = 0;
            Map<String, Boolean> seenRelations = new HashMap<>();

            for (StreamingRecord record : records) {
                if (record.getArtistName() == null || record.getTrackName() == null || record.getTimestamp() == null) continue;

                String cleanTrackName = cleanTrackName(record.getTrackName());
                String uri = record.getTrackUri();
                List<String> artistNames = extractAllArtists(record.getArtistName(), record.getTrackName());

                // Εύρεση Song ID
                String songCacheKey = (uri != null && !uri.isEmpty()) ? uri : cleanTrackName.toLowerCase();
                Integer songId = localSongCache.get(songCacheKey);

                // Fallback: Αν δε βρέθηκε με URI/Όνομα, ψάχνουμε με Βασικό Καλλιτέχνη
                if (songId == null && !artistNames.isEmpty()) {
                    Integer primaryArtistId = localArtistCache.get(artistNames.get(0));
                    if (primaryArtistId != null) {
                        songId = localSongCache.get(cleanTrackName.toLowerCase() + "|" + primaryArtistId);
                    }
                }

                if (songId == null) continue; // Αν παρόλα αυτά δε βρεθεί, το προσπερνάμε για να μη σκάσει

                java.time.Instant utcInstant = record.getTimestamp();
                java.time.LocalDateTime localTime = utcInstant.atZone(userZoneId).toLocalDateTime();

                streamStmt.setInt(1, userId);
                streamStmt.setInt(2, songId);
                streamStmt.setTimestamp(3, Timestamp.valueOf(localTime)); // <-- Χρησιμοποιούμε τη δυναμική τοπική ώρα
                streamStmt.setInt(4, record.getMsPlayed());
                streamStmt.addBatch();

                // Song_Artists Batch
                for (int i = 0; i < artistNames.size(); i++) {
                    Integer artistId = localArtistCache.get(artistNames.get(i));
                    if (artistId != null) {
                        String relationKey = songId + "-" + artistId;
                        if (!seenRelations.containsKey(relationKey)) {
                            seenRelations.put(relationKey, true);
                            relationStmt.setInt(1, songId);
                            relationStmt.setInt(2, artistId);
                            relationStmt.setBoolean(3, i > 0);
                            relationStmt.addBatch();
                        }
                    }
                }

                count++;
                if (count % BATCH_SIZE == 0) {
                    streamStmt.executeBatch();
                    relationStmt.executeBatch();
                    conn.commit();
                    System.out.println("✅ Inserted " + count + " streams...");
                }
            }

            streamStmt.executeBatch();
            relationStmt.executeBatch();
            conn.commit();
        }
    }


    // --- HELPERS ---

    private void refreshLocalCaches(Connection conn) throws Exception {
        localArtistCache.clear();
        localAlbumCache.clear();
        try (Statement stmt = conn.createStatement()) {
            try (ResultSet rs = stmt.executeQuery("SELECT id, name FROM artists")) {
                while (rs.next()) localArtistCache.put(rs.getString("name"), rs.getInt("id"));
            }
            try (ResultSet rs = stmt.executeQuery("SELECT id, title FROM albums")) {
                while (rs.next()) localAlbumCache.put(rs.getString("title"), rs.getInt("id"));
            }
        }
    }

    private void refreshSongCache(Connection conn) throws Exception {
        localSongCache.clear();
        try (Statement stmt = conn.createStatement()) {
            try (ResultSet rs = stmt.executeQuery("SELECT s.id, s.title, s.track_uri, sa.artist_id FROM songs s LEFT JOIN song_artists sa ON s.id = sa.song_id AND sa.is_feature = FALSE")) {
                while (rs.next()) {
                    String uri = rs.getString("track_uri");
                    if (uri != null && !uri.isEmpty()) {
                        localSongCache.put(uri, rs.getInt("id"));
                    } else {
                        String title = rs.getString("title");
                        int artistId = rs.getInt("artist_id");
                        if (rs.wasNull()) artistId = -1;
                        localSongCache.put(title.toLowerCase(), rs.getInt("id"));
                        localSongCache.put(title.toLowerCase() + "|" + artistId, rs.getInt("id"));
                    }
                }
            }
        }
    }


    private List<String> extractAllArtists(String mainArtistString, String trackName) {
        List<String> extractedArtists = new ArrayList<>();
        String[] mainArtists = mainArtistString.split(",\\s*|\\s*&\\s*");
        for (String artist : mainArtists) {
            extractedArtists.add(artist.trim());
        }

        Matcher matcher = FEAT_PATTERN.matcher(trackName);
        if (matcher.find()) {
            String[] featArtists = matcher.group(1).split(",\\s*|\\s*(?:&|and)\\s*");
            for (String feat : featArtists) {
                extractedArtists.add(feat.trim());
            }
        }
        return extractedArtists;
    }

    private String cleanTrackName(String trackName) {
        Matcher matcher = FEAT_PATTERN.matcher(trackName);
        if (matcher.find()) {
            return trackName.replace(matcher.group(0), "").trim();
        }
        return trackName;
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

    private void deduplicateSongs(Connection conn) throws Exception {
        System.out.println("🧹 Cleaning up duplicate song versions (Clean/Explicit) within albums...");

        // 1. Ενημέρωση των streams: Δένουμε τα streams των διπλότυπων πάνω στο αρχικό (MIN id) τραγούδι
        String updateStreams = """
            UPDATE streams s
            SET song_id = ps.min_id
            FROM songs so
            JOIN (
                SELECT MIN(id) as min_id, title, album_id
                FROM songs
                WHERE album_id IS NOT NULL
                GROUP BY title, album_id
                HAVING COUNT(*) > 1
            ) ps ON so.title = ps.title AND so.album_id = ps.album_id
            WHERE s.song_id = so.id AND so.id != ps.min_id
        """;

        // 2. Διαγραφή των relationships (ώστε να μη χτυπήσει το Foreign Key κατά τη διαγραφή)
        String deleteSongArtists = """
            DELETE FROM song_artists sa
            USING songs so
            JOIN (
                SELECT MIN(id) as min_id, title, album_id
                FROM songs
                WHERE album_id IS NOT NULL
                GROUP BY title, album_id
                HAVING COUNT(*) > 1
            ) ps ON so.title = ps.title AND so.album_id = ps.album_id
            WHERE sa.song_id = so.id AND so.id != ps.min_id
        """;

        // 3. Διαγραφή των διπλότυπων τραγουδιών
        String deleteSongs = """
            DELETE FROM songs so
            USING (
                SELECT MIN(id) as min_id, title, album_id
                FROM songs
                WHERE album_id IS NOT NULL
                GROUP BY title, album_id
                HAVING COUNT(*) > 1
            ) ps
            WHERE so.title = ps.title AND so.album_id = ps.album_id AND so.id != ps.min_id
        """;

        try (Statement stmt = conn.createStatement()) {
            stmt.executeUpdate(updateStreams);
            stmt.executeUpdate(deleteSongArtists);
            int deleted = stmt.executeUpdate(deleteSongs);

            if (deleted > 0) {
                System.out.println("✨ Merged " + deleted + " duplicate track versions into a single entry!");
            }
        }
    }
}