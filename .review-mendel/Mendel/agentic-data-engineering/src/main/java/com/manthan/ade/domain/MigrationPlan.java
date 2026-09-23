package com.manthan.ade.domain;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * A proposed migration produced by the planner (Gemini, or the rule-based
 * fallback). Stored as jsonb in {@code migration_log.plan}. Never executed in
 * Phase 2 — the Migration Executor (Phase 3) validates and applies it.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class MigrationPlan {
    /** Why the planner chose these steps. */
    private String reasoning;
    /** low | medium | high */
    private String riskLevel;
    /** Forward DDL statements, in order. */
    private List<String> migrationSql;
    /** Statements that exactly reverse the migration, in order. */
    private List<String> rollbackSql;
    /** Any caveats the executor / a human should see. */
    private List<String> warnings;
    /** "gemini" or "rule-based" — which planner produced this. */
    private String source;
}
