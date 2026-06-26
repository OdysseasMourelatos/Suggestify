package com.Suggestify;
import java.util.List;

public class Artist {
    private String id; // Spotify Artist ID
    private String name;
    private List<String> genres;
    private int popularity;

    public Artist(String name) {
        this.name = name;
    }

    // Getters and Setters...
}
