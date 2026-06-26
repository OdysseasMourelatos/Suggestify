package com.Suggestify;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.FileInputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class SpotifyParser {
    public static void main(String[] args) {

        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.configure(JsonParser.Feature.AUTO_CLOSE_SOURCE, false);

        String zipFilePath = "C:\\Users\\spmou\\Downloads\\my_spotify_data.zip";
        List<StreamingRecord> allRecords = new ArrayList<>();

        System.out.println("Opening ZIP file in memory...");

        try (ZipInputStream zis = new ZipInputStream(new FileInputStream(zipFilePath))) {
            ZipEntry entry;

            while ((entry = zis.getNextEntry()) != null) {
                String fileName = entry.getName();

                if (fileName.contains("Streaming_History_Audio_") && fileName.endsWith(".json")) {
                    System.out.println("Reading file: " + fileName);

                    List<StreamingRecord> fileRecords = mapper.readValue(
                            zis,
                            new TypeReference<List<StreamingRecord>>() {}
                    );
                    allRecords.addAll(fileRecords);
                }
                zis.closeEntry();
            }

            EntityExtractor extractor = new EntityExtractor();
            extractor.extractEntities(allRecords);

            DatabaseManager.initializeSchema();
            DatabaseImporter dbImporter = new DatabaseImporter();
            dbImporter.importRecords(allRecords);

        } catch (Exception e) {
            System.err.println("Error reading ZIP file. Please verify the file path.");
            e.printStackTrace();
        }
    }
}