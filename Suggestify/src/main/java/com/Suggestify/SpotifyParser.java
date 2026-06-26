package com.Suggestify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.core.type.TypeReference;
import java.io.File;
import java.util.List;

public class SpotifyParser {
    public static void main(String[] args) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            mapper.registerModule(new JavaTimeModule());
            File jsonFile = new File("src/main/resources/StreamingHistory.json");

            List<StreamingRecord> records = mapper.readValue(
                    jsonFile,
                    new TypeReference<List<StreamingRecord>>() {}
            );

            System.out.println("Read " + records.size() + " records.");
            System.out.println("First track: " + records.get(0).getTrackName());

        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}