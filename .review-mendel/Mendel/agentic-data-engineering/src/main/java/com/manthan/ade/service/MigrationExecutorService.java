package com.manthan.ade.service;

import com.manthan.ade.domain.*;
import com.manthan.ade.repository.MigrationLogRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Applies and rolls back planned migrations. Every apply runs inside a single
 * transaction that spans BOTH the physical DDL and the metadata updates, so the
 * database and the schema registry can never drift apart: if any statement
 * fails, the whole thing rolls back and the migration is marked FAILED.
 *
 * Guardrails run before any SQL executes — high-risk changes need explicit
 * confirmation, and only ALTER/CREATE statements that target the dataset's own
 * table are allowed through.
 */
@Service
public class MigrationExecutorService {

    private static final Logger log = LoggerFactory.getLogger(MigrationExecutorService.class);

    public static final String APPLIED = "APPLIED";
    public static final String FAILED = "FAILED";
    public static final String ROLLED_BACK = "ROLLED_BACK";
    public static final String PLANNED = "PLANNED";

    private static final List<String> FORBIDDEN = List.of(
            "DROP TABLE", "DROP DATABASE", "DROP SCHEMA",
            "TRUNCATE ", "DELETE FROM", "GRANT ", "REVOKE ", "ALTER SYSTEM");
    private static final String IDENTIFIER = "[a-z][a-z0-9_]*";
    private static final String SQL_TYPE = "(?:TEXT|BIGINT|DOUBLE PRECISION|BOOLEAN|DATE|TIMESTAMP)";

    private final MigrationLogRepository migrationRepo;
    private final MetadataRegistryService registry;
    private final DdlService ddl;
    private final TransactionTemplate tx;
    private final TransactionTemplate txNew;

    public MigrationExecutorService(MigrationLogRepository migrationRepo,
                                    MetadataRegistryService registry,
                                    DdlService ddl,
                                    PlatformTransactionManager txManager) {
        this.migrationRepo = migrationRepo;
        this.registry = registry;
        this.ddl = ddl;
        this.tx = new TransactionTemplate(txManager);
        this.txNew = new TransactionTemplate(txManager);
        this.txNew.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public MigrationLog apply(Long id, boolean confirm) {
        try {
            return tx.execute(status -> applyInTx(id, confirm));
        } catch (GuardrailException | MigrationException e) {
            throw e; // safe failures — nothing was executed
        } catch (RuntimeException e) {
            String msg = rootMessage(e);
            log.warn("Migration {} failed, rolled back: {}", id, msg);
            markFailed(id, msg);
            throw new MigrationException("Migration failed and was rolled back: " + msg);
        }
    }

    private MigrationLog applyInTx(Long id, boolean confirm) {
        MigrationLog m = load(id);
        if (!PLANNED.equals(m.getStatus())) {
            throw new MigrationException("Migration " + id + " is " + m.getStatus() + ", not PLANNED");
        }
        Dataset dataset = m.getDataset();
        String table = dataset.getTargetTable();
        MigrationPlan plan = m.getPlan();

        guardrails(m, plan, table, confirm);

        SchemaVersion active = registry.getActiveSchema(dataset.getId())
                .orElseThrow(() -> new MigrationException("No active schema for dataset " + dataset.getId()));
        if (!active.getVersion().equals(m.getFromVersion())) {
            throw new MigrationException("Migration was planned from schema v" + m.getFromVersion()
                    + ", but active schema is v" + active.getVersion() + "; create a new plan");
        }

        // Materialise the table from the current (from) schema if it's not there yet,
        // then apply the forward statements.
        ddl.ensureTable(table, active.getColumns());
        for (String sql : plan.getMigrationSql()) {
            ddl.execute(sql);
        }

        // Register the post-migration schema as the new active version.
        List<ColumnDef> target = m.getTargetColumns();
        if (target == null || target.isEmpty()) {
            throw new MigrationException("Migration " + id + " has no recorded target schema");
        }
        registry.saveNewVersion(dataset, target);

        m.setStatus(APPLIED);
        m.setAppliedSql(String.join("\n", plan.getMigrationSql()));
        if (plan.getRollbackSql() != null) {
            m.setRollbackSql(String.join("\n", plan.getRollbackSql()));
        }
        return migrationRepo.save(m);
    }

    public MigrationLog rollback(Long id) {
        return tx.execute(status -> rollbackInTx(id));
    }

    private MigrationLog rollbackInTx(Long id) {
        MigrationLog m = load(id);
        if (!APPLIED.equals(m.getStatus())) {
            throw new MigrationException("Only APPLIED migrations can be rolled back (current: " + m.getStatus() + ")");
        }
        MigrationPlan plan = m.getPlan();
        List<String> rb = plan == null ? null : plan.getRollbackSql();
        if (rb == null || rb.isEmpty()) {
            throw new MigrationException("No rollback SQL recorded for migration " + id);
        }
        SchemaVersion active = registry.getActiveSchema(m.getDataset().getId())
                .orElseThrow(() -> new MigrationException("No active schema for dataset " + m.getDataset().getId()));
        if (!active.getVersion().equals(m.getToVersion())) {
            throw new MigrationException("Migration cannot be rolled back because active schema is v"
                    + active.getVersion() + ", not v" + m.getToVersion());
        }
        validateStatements(rb, m.getDataset().getTargetTable());
        for (String sql : rb) {
            ddl.execute(sql);
        }
        registry.activateVersion(m.getDataset().getId(), m.getFromVersion());
        m.setStatus(ROLLED_BACK);
        return migrationRepo.save(m);
    }

    // ---------------- guardrails ----------------

    private void guardrails(MigrationLog m, MigrationPlan plan, String table, boolean confirm) {
        if (plan == null || plan.getMigrationSql() == null || plan.getMigrationSql().isEmpty()) {
            if (m.getDriftType() == DriftType.BREAKING) {
                throw new GuardrailException(
                        "Breaking change (column removal) is not auto-applicable — manual review required");
            }
            throw new GuardrailException("No migration SQL to apply");
        }

        boolean highRisk = "high".equalsIgnoreCase(m.getRiskLevel())
                || m.getDriftType() == DriftType.BREAKING
                || m.getDriftType() == DriftType.RENAME_CANDIDATE;
        if (highRisk && !confirm) {
            throw new GuardrailException(
                    "High-risk migration (" + m.getDriftType() + ", risk=" + m.getRiskLevel()
                            + ") requires confirm=true");
        }

        validateStatements(plan.getMigrationSql(), table);
    }

    private void validateStatements(List<String> statements, String table) {
        String quotedTable = Pattern.quote(table);
        Pattern add = Pattern.compile("(?i)^ALTER\\s+TABLE\\s+" + quotedTable
                + "\\s+ADD\\s+COLUMN\\s+(?:IF\\s+NOT\\s+EXISTS\\s+)?" + IDENTIFIER
                + "\\s+" + SQL_TYPE + "\\s*;?$");
        Pattern drop = Pattern.compile("(?i)^ALTER\\s+TABLE\\s+" + quotedTable
                + "\\s+DROP\\s+COLUMN\\s+(?:IF\\s+EXISTS\\s+)?" + IDENTIFIER + "\\s*;?$");
        Pattern rename = Pattern.compile("(?i)^ALTER\\s+TABLE\\s+" + quotedTable
                + "\\s+RENAME\\s+COLUMN\\s+" + IDENTIFIER + "\\s+TO\\s+" + IDENTIFIER + "\\s*;?$");
        Pattern type = Pattern.compile("(?i)^ALTER\\s+TABLE\\s+" + quotedTable
                + "\\s+ALTER\\s+COLUMN\\s+(" + IDENTIFIER + ")\\s+TYPE\\s+(" + SQL_TYPE
                + ")\\s+USING\\s+\\1::\\2\\s*;?$");

        for (String raw : statements) {
            String sql = raw.trim();
            String up = sql.toUpperCase();

            if (!up.startsWith("ALTER TABLE")) {
                throw new GuardrailException("Blocked non-DDL/unsafe statement: " + truncate(sql));
            }
            // No statement chaining (allow a single trailing semicolon only).
            String body = up.endsWith(";") ? up.substring(0, up.length() - 1) : up;
            if (body.contains(";")) {
                throw new GuardrailException("Multiple statements are not allowed: " + truncate(sql));
            }
            for (String bad : FORBIDDEN) {
                if (up.contains(bad)) {
                    throw new GuardrailException("Blocked dangerous operation (" + bad.trim() + "): " + truncate(sql));
                }
            }
            if (!(add.matcher(sql).matches() || drop.matcher(sql).matches()
                    || rename.matcher(sql).matches() || type.matcher(sql).matches())) {
                throw new GuardrailException("Statement is outside the approved migration grammar: " + truncate(sql));
            }
        }
    }

    // ---------------- helpers ----------------

    private MigrationLog load(Long id) {
        return migrationRepo.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Migration not found: " + id));
    }

    private void markFailed(Long id, String message) {
        txNew.executeWithoutResult(status -> migrationRepo.findById(id).ifPresent(m -> {
            m.setStatus(FAILED);
            if (m.getPlan() != null) {
                List<String> warnings = m.getPlan().getWarnings() != null
                        ? new ArrayList<>(m.getPlan().getWarnings()) : new ArrayList<>();
                warnings.add("apply failed: " + message);
                m.getPlan().setWarnings(warnings);
            }
            migrationRepo.save(m);
        }));
    }

    private String rootMessage(Throwable e) {
        Throwable c = e;
        while (c.getCause() != null && c.getCause() != c) {
            c = c.getCause();
        }
        return c.getMessage() == null ? c.toString() : c.getMessage();
    }

    private String truncate(String s) {
        return s.length() > 80 ? s.substring(0, 80) + "…" : s;
    }
}
