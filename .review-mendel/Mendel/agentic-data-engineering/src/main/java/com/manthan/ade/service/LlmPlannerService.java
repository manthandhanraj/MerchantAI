package com.manthan.ade.service;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.MigrationPlan;
import com.manthan.ade.llm.LlmClient;
import com.manthan.ade.llm.LlmException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * Turns a detected {@link SchemaDiff} into a {@link MigrationPlan}. Tries the LLM
 * first; if it is unavailable or returns something unusable, falls back to a
 * deterministic rule-based planner so the platform still works offline and never
 * hard-fails a demo.
 *
 * IMPORTANT: this class only PLANS. It never runs SQL. The Migration Executor
 * (Phase 3) validates and applies the returned statements under guardrails.
 */
@Service
public class LlmPlannerService {

    private static final Logger log = LoggerFactory.getLogger(LlmPlannerService.class);

    private final LlmClient llm;
    private final ObjectMapper mapper;

    public LlmPlannerService(LlmClient llm, ObjectMapper springMapper) {
        this.llm = llm;
        this.mapper = springMapper.copy()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    public MigrationPlan plan(String table, List<ColumnDef> currentColumns, SchemaDiff diff) {
        // SQL is deliberately produced by the deterministic planner.  An LLM may
        // help explain a change, but it must never become an executable-SQL source.
        MigrationPlan safePlan = ruleBased(table, diff);
        if (llm.isAvailable()) {
            try {
                MigrationPlan p = mapper.readValue(llm.generateJson(buildPrompt(table, currentColumns, diff)),
                        MigrationPlan.class);
                if (p != null) {
                    if (p.getReasoning() != null && !p.getReasoning().isBlank()) {
                        safePlan.setReasoning(p.getReasoning());
                    }
                    if (p.getWarnings() != null) {
                        safePlan.getWarnings().addAll(p.getWarnings());
                    }
                    safePlan.setSource("gemini-assisted/rule-based-sql");
                    return safePlan;
                }
                log.warn("Gemini returned an unusable plan; using rule-based fallback");
            } catch (LlmException e) {
                log.warn("Planner falling back to rules: {}", e.getMessage());
            } catch (Exception e) {
                log.warn("Failed to parse Gemini plan; using rule-based fallback: {}", e.getMessage());
            }
        }
        return safePlan;
    }

    private boolean isUsable(MigrationPlan p) {
        return p != null && p.getMigrationSql() != null && !p.getMigrationSql().isEmpty();
    }

    private String buildPrompt(String table, List<ColumnDef> current, SchemaDiff diff) {
        StringBuilder cols = new StringBuilder();
        for (ColumnDef c : current) {
            cols.append("- ").append(c.getName()).append(' ').append(c.getSqlType())
                .append(c.isNullable() ? " NULL" : " NOT NULL").append('\n');
        }
        return """
            You are an autonomous data-engineering migration planner for a PostgreSQL database.
            Produce a SAFE migration plan for the detected schema drift, as JSON ONLY.

            Rules:
            - Prefer additive, non-destructive DDL.
            - New columns must be nullable (no NOT NULL without a default).
            - NEVER emit DROP COLUMN unless the drift is explicitly a removal; if you must, warn clearly.
            - For type changes use ALTER COLUMN ... TYPE ... USING, and warn if the cast may lose data.
            - Provide rollbackSql that exactly reverses each migration step, in reverse order.
            - Assess risk as one of: low, medium, high.

            Return ONLY this JSON shape, no prose, no markdown:
            {"reasoning": string, "riskLevel": "low|medium|high",
             "migrationSql": [string], "rollbackSql": [string], "warnings": [string]}

            Target table: %s
            Current columns:
            %s
            Detected drift (%s): %s
            """.formatted(table, cols.toString().trim(), diff.driftType(), diff.summary());
    }

    // ---------------- rule-based fallback ----------------

    private MigrationPlan ruleBased(String table, SchemaDiff diff) {
        List<String> up = new ArrayList<>();
        List<String> down = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        String reasoning;

        switch (diff.driftType()) {
            case ADDITIVE -> {
                for (ColumnDef c : diff.added()) {
                    up.add("ALTER TABLE " + table + " ADD COLUMN IF NOT EXISTS " + c.getName() + " " + c.getSqlType() + ";");
                    down.add(0, "ALTER TABLE " + table + " DROP COLUMN IF EXISTS " + c.getName() + ";");
                }
                reasoning = "Additive change: new nullable columns can be added without data loss.";
            }
            case TYPE_CHANGE -> {
                for (SchemaDiff.ColumnChange ch : diff.typeChanged()) {
                    up.add("ALTER TABLE " + table + " ALTER COLUMN " + ch.name()
                            + " TYPE " + ch.toType() + " USING " + ch.name() + "::" + ch.toType() + ";");
                    down.add(0, "ALTER TABLE " + table + " ALTER COLUMN " + ch.name()
                            + " TYPE " + ch.fromType() + " USING " + ch.name() + "::" + ch.fromType() + ";");
                    warnings.add("Type change on " + ch.name() + " (" + ch.fromType() + " -> " + ch.toType()
                            + ") may fail or lose data if values are incompatible.");
                }
                reasoning = "Type change: applied with an explicit USING cast; reversible if the cast is lossless.";
            }
            case RENAME_CANDIDATE -> {
                SchemaDiff.RenameCandidate r = diff.rename();
                up.add("ALTER TABLE " + table + " RENAME COLUMN " + r.from() + " TO " + r.to() + ";");
                down.add("ALTER TABLE " + table + " RENAME COLUMN " + r.to() + " TO " + r.from() + ";");
                warnings.add("Detected as a likely rename (" + r.from() + " -> " + r.to()
                        + ") by heuristic — confirm before applying.");
                reasoning = "One column dropped and one added with the same type; treated as a rename to avoid data loss.";
            }
            case BREAKING -> {
                for (ColumnDef c : diff.removed()) {
                    warnings.add("Column '" + c.getName() + "' disappeared from the source. NOT auto-dropping "
                            + "(data-loss risk) — manual review required.");
                }
                reasoning = "Breaking change (column removal). Held for human review; no destructive SQL generated.";
            }
            default -> reasoning = "No drift detected.";
        }

        MigrationPlan p = new MigrationPlan(reasoning, defaultRisk(diff), up, down, warnings, "rule-based");
        return p;
    }

    private String defaultRisk(SchemaDiff diff) {
        return switch (diff.driftType()) {
            case ADDITIVE -> "low";
            case TYPE_CHANGE -> "medium";
            case RENAME_CANDIDATE, BREAKING -> "high";
            default -> "low";
        };
    }
}
