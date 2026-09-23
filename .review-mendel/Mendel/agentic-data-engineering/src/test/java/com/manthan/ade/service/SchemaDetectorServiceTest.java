package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.DriftType;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SchemaDetectorServiceTest {

    private final SchemaDetectorService detector = new SchemaDetectorService();

    private ColumnDef col(String name, String type) {
        return new ColumnDef(name, type, true);
    }

    @Test
    void detectsAdditive() {
        var active = List.of(col("id", "BIGINT"), col("name", "TEXT"));
        var incoming = List.of(col("id", "BIGINT"), col("name", "TEXT"), col("email", "TEXT"));
        var diff = detector.diff(active, incoming);
        assertEquals(DriftType.ADDITIVE, diff.driftType());
        assertEquals(1, diff.added().size());
    }

    @Test
    void detectsTypeChange() {
        var active = List.of(col("signup_date", "TEXT"));
        var incoming = List.of(col("signup_date", "DATE"));
        assertEquals(DriftType.TYPE_CHANGE, detector.diff(active, incoming).driftType());
    }

    @Test
    void detectsRenameCandidate() {
        var active = List.of(col("id", "BIGINT"), col("fullname", "TEXT"));
        var incoming = List.of(col("id", "BIGINT"), col("name", "TEXT"));
        assertEquals(DriftType.RENAME_CANDIDATE, detector.diff(active, incoming).driftType());
    }

    @Test
    void detectsBreaking() {
        var active = List.of(col("id", "BIGINT"), col("name", "TEXT"), col("email", "TEXT"));
        var incoming = List.of(col("id", "BIGINT"));
        assertEquals(DriftType.BREAKING, detector.diff(active, incoming).driftType());
    }

    @Test
    void noDrift() {
        var cols = List.of(col("id", "BIGINT"), col("name", "TEXT"));
        assertEquals(DriftType.NONE, detector.diff(cols, cols).driftType());
    }
}
