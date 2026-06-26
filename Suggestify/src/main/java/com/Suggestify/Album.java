package com.Suggestify;
import java.time.LocalDate;

public class Album {
    private String id; // Spotify Album ID
    private String name;
    private Artist primaryArtist;
    private LocalDate releaseDate;

    public Album(String name, Artist primaryArtist) {
        this.name = name;
        this.primaryArtist = primaryArtist;
    }

}