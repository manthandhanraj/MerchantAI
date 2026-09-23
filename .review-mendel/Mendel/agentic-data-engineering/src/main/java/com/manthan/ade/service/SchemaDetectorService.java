package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.DriftType;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Compares the active schema with an incoming one and classifies the drift.
 * Pure function — no side effects, so it's trivial to unit-test.
 */
@Service
public class SchemaDetectorService {

    public SchemaDiff diff(List<ColumnDef> active, List<ColumnDef> incoming) {
        Map<String, ColumnDef> activeByName = index(active);
        Map<String, ColumnDef> incomingByName = index(incoming);

        List<ColumnDef> added = new ArrayList<>();
        for (ColumnDef c : incoming) {
            if (!activeByName.containsKey(c.getName())) {
                added.add(c);
            }
        }

        List<ColumnDef> removed = new ArrayList<>();
        for (ColumnDef c : active) {
            if (!incomingByName.containsKey(c.getName())) {
                removed.add(c);
            }
        }

        List<SchemaDiff.ColumnChange> typeChanged = new ArrayList<>();
        for (ColumnDef c : active) {
            ColumnDef other = incomingByName.get(c.getName());
            if (other != null && !c.getSqlType().equalsIgnoreCase(other.getSqlType())) {
                typeChanged.add(new SchemaDiff.ColumnChange(c.getName(), c.getSqlType(), other.getSqlType()));
            }
        }

        // Heuristic rename: exactly one column dropped and one added, same type.
        SchemaDiff.RenameCandidate rename = null;
        if (removed.size() == 1 && added.size() == 1
                && removed.get(0).getSqlType().equalsIgnoreCase(added.get(0).getSqlType())) {
            rename = new SchemaDiff.RenameCandidate(
                    removed.get(0).getName(), added.get(0).getName(), removed.get(0).getSqlType());
        }

        DriftType type = classify(added, removed, typeChanged, rename);
        return new SchemaDiff(type, added, removed, typeChanged, rename,
                summarise(type, added, removed, typeChanged, rename));
    }

    private DriftType classify(List<ColumnDef> added, List<ColumnDef> removed,
                               List<SchemaDiff.ColumnChange> typeChanged, SchemaDiff.RenameCandidate rename) {
        if (rename != null) return DriftType.RENAME_CANDIDATE;
        if (!removed.isEmpty()) return DriftType.BREAKING;
        if (!typeChanged.isEmpty()) return DriftType.TYPE_CHANGE;
        if (!added.isEmpty()) return DriftType.ADDITIVE;
        return DriftType.NONE;
    }

    private String summarise(DriftType type, List<ColumnDef> added, List<ColumnDef> removed,
                             List<SchemaDiff.ColumnChange> typeChanged, SchemaDiff.RenameCandidate rename) {
        List<String> parts = new ArrayList<>();
        if (rename != null) {
            parts.add("rename " + rename.from() + " -> " + rename.to());
        } else {
            if (!added.isEmpty()) parts.add("added " + added.stream().map(ColumnDef::getName).toList());
            if (!removed.isEmpty()) parts.add("removed " + removed.stream().map(ColumnDef::getName).toList());
        }
        for (SchemaDiff.ColumnChange c : typeChanged) {
            parts.add("type " + c.name() + " " + c.fromType() + " -> " + c.toType());
        }
        return parts.isEmpty() ? "no drift" : String.join("; ", parts);
    }

    private Map<String, ColumnDef> index(List<ColumnDef> cols) {
        Map<String, ColumnDef> m = new LinkedHashMap<>();
        if (cols != null) {
            for (ColumnDef c : cols) {
                m.put(c.getName(), c);
            }
        }
        return m;
    }
}
