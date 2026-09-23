package com.manthan.ade.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * A record of one ingested CSV batch and the schema detected from it.
 * Phase 2 diffs {@code detectedColumns} against the active {@link SchemaVersion}.
 */
@Entity
@Table(name = "ingest_batch")
@Getter
@Setter
public class IngestBatch {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "dataset_id", nullable = false)
    private Dataset dataset;

    @Column(name = "source_file", length = 400)
    private String sourceFile;

    @Column(name = "row_count", nullable = false)
    private int rowCount;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "detected_columns", nullable = false, columnDefinition = "jsonb")
    private List<ColumnDef> detectedColumns;

    /** BASELINE = first batch (set schema v1), INGESTED = subsequent batch. */
    @Column(nullable = false, length = 40)
    private String status;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    void onCreate() {
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
