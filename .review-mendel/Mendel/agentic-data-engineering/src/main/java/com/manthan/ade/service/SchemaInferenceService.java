package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.Reader;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Infers a column schema from a CSV: names from the header row, SQL types by
 * sampling values. Kept deliberately conservative — ambiguous columns fall back
 * to TEXT so a migration never fails on a type it guessed wrong.
 */
@Service
public class SchemaInferenceService {

    private static final int SAMPLE_ROWS = 200;

    public record InferenceResult(List<ColumnDef> columns, int rowCount) {}

    public InferenceResult infer(Reader reader) throws IOException {
        CSVFormat format = CSVFormat.DEFAULT.builder()
                .setHeader()
                .setSkipHeaderRecord(true)
                .setTrim(true)
                .setIgnoreEmptyLines(true)
                .build();

        try (CSVParser parser = format.parse(reader)) {
            List<String> headers = parser.getHeaderNames();
            if (headers.isEmpty()) {
                throw new IllegalArgumentException("CSV has no header row");
            }

            Map<String, List<String>> samples = new LinkedHashMap<>();
            Map<String, Boolean> nullable = new LinkedHashMap<>();
            for (String h : headers) {
                samples.put(h, new ArrayList<>());
                nullable.put(h, false);
            }

            int rowCount = 0;
            for (CSVRecord record : parser) {
                rowCount++;
                for (String h : headers) {
                    String v = record.isSet(h) ? record.get(h) : "";
                    if (v == null || v.isBlank()) {
                        nullable.put(h, true);
                    } else if (samples.get(h).size() < SAMPLE_ROWS) {
                        samples.get(h).add(v.trim());
                    }
                }
            }

            List<ColumnDef> columns = new ArrayList<>();
            Map<String, String> originalHeaders = new LinkedHashMap<>();
            for (String h : headers) {
                String name = sanitize(h);
                String prior = originalHeaders.putIfAbsent(name, h);
                if (prior != null) {
                    throw new IllegalArgumentException("CSV headers '" + prior + "' and '" + h
                            + "' both normalize to SQL column '" + name + "'");
                }
                columns.add(new ColumnDef(name, inferType(samples.get(h)), nullable.get(h)));
            }
            return new InferenceResult(columns, rowCount);
        }
    }

    /** Normalise a header into a safe SQL identifier. */
    private String sanitize(String header) {
        String s = header.trim().toLowerCase()
                .replaceAll("[^a-z0-9_]+", "_")
                .replaceAll("^_+|_+$", "");
        if (s.isEmpty()) {
            s = "col";
        }
        if (Character.isDigit(s.charAt(0))) {
            s = "c_" + s;
        }
        return s;
    }

    private String inferType(List<String> values) {
        if (values.isEmpty()) {
            return "TEXT";
        }
        boolean allInt = true, allDecimal = true, allBool = true, allDate = true, allTs = true;
        for (String v : values) {
            if (allInt && !isInteger(v)) allInt = false;
            if (allDecimal && !isDecimal(v)) allDecimal = false;
            if (allBool && !isBoolean(v)) allBool = false;
            if (allDate && !isDate(v)) allDate = false;
            if (allTs && !isTimestamp(v)) allTs = false;
        }
        if (allBool) return "BOOLEAN";
        if (allInt) return "BIGINT";
        if (allDecimal) return "DOUBLE PRECISION";
        if (allDate) return "DATE";
        if (allTs) return "TIMESTAMP";
        return "TEXT";
    }

    private boolean isInteger(String v) {
        try {
            Long.parseLong(v);
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private boolean isDecimal(String v) {
        try {
            Double.parseDouble(v);
            return v.matches("[-+]?\\d*\\.?\\d+([eE][-+]?\\d+)?");
        } catch (NumberFormatException e) {
            return false;
        }
    }

    private boolean isBoolean(String v) {
        return v.equalsIgnoreCase("true") || v.equalsIgnoreCase("false");
    }

    private boolean isDate(String v) {
        try {
            LocalDate.parse(v);
            return true;
        } catch (DateTimeParseException e) {
            return false;
        }
    }

    private boolean isTimestamp(String v) {
        try {
            OffsetDateTime.parse(v);
            return true;
        } catch (DateTimeParseException e) {
            try {
                LocalDateTime.parse(v);
                return true;
            } catch (DateTimeParseException e2) {
                return false;
            }
        }
    }
}
