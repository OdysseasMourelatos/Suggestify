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

        String zipFilePath = args.length > 0 ? args[0] : "C:\\Users\\spmou\\Downloads\\my_spotify_data.zip";

        if (zipFilePath == null) {
            System.err.println("Error: No ZIP file path provided!");
            System.exit(1);
        }

        String username = args.length > 1 ? args[1] : "Ody"; // <--- Παίρνουμε το username

        String timeZoneStr = args.length > 2 ? args[2] : "Europe/Athens";

        List<StreamingRecord> allRecords = new ArrayList<>();

        System.out.println("Opening ZIP file in memory...");

        DatabaseManager.initializeSchema();

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

            DatabaseImporter importer = new DatabaseImporter();
            importer.importRecords(allRecords, username, timeZoneStr);
            System.out.println("✅ Import complete!");

        } catch (Exception e) {
            System.err.println("Error processing data.");
            e.printStackTrace();
            System.exit(1);
        }
    }
}