package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.DriftType;

import java.util.List;

/**
 * Structured result of comparing the active schema against an incoming one.
 */
public record SchemaDiff(
        DriftType driftType,
        List<ColumnDef> added,
        List<ColumnDef> removed,
        List<ColumnChange> typeChanged,
        RenameCandidate rename,
        String summary
) {
    public boolean hasDrift() {
        return driftType != DriftType.NONE;
    }

    public record ColumnChange(String name, String fromType, String toType) {}

    public record RenameCandidate(String from, String to, String type) {}
}
