package com.Suggestify;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

@JsonIgnoreProperties(ignoreUnknown = true)
public class StreamingRecord {

    @JsonProperty("ts")
    private Instant timestamp;

    @JsonProperty("platform")
    private String platform;

    @JsonProperty("ms_played")
    private int msPlayed;

    @JsonProperty("master_metadata_track_name")
    private String trackName;

    @JsonProperty("master_metadata_album_artist_name")
    private String artistName;

    @JsonProperty("master_metadata_album_album_name")
    private String albumName;

    @JsonProperty("spotify_track_uri")
    private String trackUri;

    @JsonProperty("reason_start")
    private String reasonStart;

    @JsonProperty("reason_end")
    private String reasonEnd;

    @JsonProperty("shuffle")
    private boolean shuffle;

    @JsonProperty("skipped")
    private boolean skipped;

    // Getters
    public Instant getTimestamp() { return timestamp; }
    public String getPlatform() { return platform; }
    public int getMsPlayed() { return msPlayed; }
    public String getTrackName() { return trackName; }
    public String getArtistName() { return artistName; }
    public String getAlbumName() { return albumName; }
    public String getTrackUri() { return trackUri; }
    public String getReasonStart() { return reasonStart; }
    public String getReasonEnd() { return reasonEnd; }
    public boolean isShuffle() { return shuffle; }
    public boolean isSkipped() { return skipped; }
}