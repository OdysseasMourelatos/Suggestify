package com.Suggestify;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class EntityExtractor {

    // We use Maps to guarantee uniqueness. The Key is the Name or URI.
    private Map<String, Artist> uniqueArtists = new HashMap<>();
    private Map<String, Album> uniqueAlbums = new HashMap<>();
    private Map<String, Song> uniqueSongs = new HashMap<>();

    public void extractEntities(List<StreamingRecord> records) {
        System.out.println("Extracting unique entities from " + records.size() + " records...");

        for (StreamingRecord record : records) {
            // Data Cleaning: Skip records missing essential data
            if (record.getTrackName() == null || record.getArtistName() == null) {
                continue;
            }

            // 1. Extract or Create Artist
            String artistName = record.getArtistName();
            Artist artist = uniqueArtists.computeIfAbsent(artistName, name -> new Artist(name));

            // 2. Extract or Create Album
            String albumName = record.getAlbumName() != null ? record.getAlbumName() : "Unknown Album";
            String albumKey = albumName + "|||" + artistName;
            Album album = uniqueAlbums.computeIfAbsent(albumKey, key -> new Album(albumName, artist));

            // 3. Extract or Create Song
            String trackUri = record.getTrackUri();
            if (trackUri != null) {
                uniqueSongs.computeIfAbsent(trackUri, uri -> new Song(uri, record.getTrackName(), artist, album));
            }
        }

        System.out.println("Extraction Complete!");
        System.out.println("Total Unique Artists: " + uniqueArtists.size());
        System.out.println("Total Unique Albums: " + uniqueAlbums.size());
        System.out.println("Total Unique Songs: " + uniqueSongs.size());
        System.out.println(getUniqueArtists());
    }

    // Getters so we can retrieve the maps later
    public Map<String, Artist> getUniqueArtists() { return uniqueArtists; }
    public Map<String, Album> getUniqueAlbums() { return uniqueAlbums; }
    public Map<String, Song> getUniqueSongs() { return uniqueSongs; }
}
