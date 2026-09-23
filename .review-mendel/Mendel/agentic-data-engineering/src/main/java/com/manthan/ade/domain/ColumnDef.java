package com.manthan.ade.domain;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * One column of an inferred/registered schema. Serialized as an element of a
 * jsonb array in {@code schema_version.columns} and {@code ingest_batch.detected_columns}.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class ColumnDef {
    private String name;
    private String sqlType;
    private boolean nullable;
}
