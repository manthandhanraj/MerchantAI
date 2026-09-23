package com.manthan.ade.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * A record of a proposed (and, from Phase 3, applied) migration for a dataset.
 * Status lifecycle: PLANNED -> APPLIED | FAILED | ROLLED_BACK.
 */
@Entity
@Table(name = "migration_log")
@Getter
@Setter
public class MigrationLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "dataset_id", nullable = false)
    private Dataset dataset;

    @Column(name = "from_version")
    private Integer fromVersion;

    @Column(name = "to_version")
    private Integer toVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "drift_type", length = 40)
    private DriftType driftType;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "plan", columnDefinition = "jsonb")
    private MigrationPlan plan;

    /** The schema the table should have AFTER this migration is applied. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "target_columns", columnDefinition = "jsonb")
    private List<ColumnDef> targetColumns;

    /** Populated by the executor (Phase 3) once actually applied. */
    @Column(name = "applied_sql")
    private String appliedSql;

    @Column(name = "rollback_sql")
    private String rollbackSql;

    @Column(name = "risk_level", length = 20)
    private String riskLevel;

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
