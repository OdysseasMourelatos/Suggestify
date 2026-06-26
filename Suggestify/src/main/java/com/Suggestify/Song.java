package com.Suggestify;

public class Song {
    private String trackUri; // From JSON: spotify_track_uri
    private String name;
    private Album album;
    private Artist artist;
    private int durationMs;
    private int popularity;

    public Song(String trackUri, String name, Artist artist, Album album) {
        this.trackUri = trackUri;
        this.name = name;
        this.artist = artist;
        this.album = album;
    }

    // Getters and Setters...
}