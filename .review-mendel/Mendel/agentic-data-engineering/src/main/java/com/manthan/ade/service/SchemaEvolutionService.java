package com.manthan.ade.service;

import com.manthan.ade.domain.*;
import com.manthan.ade.repository.MigrationLogRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Ties the detector and planner together: given an incoming schema for a dataset
 * with an existing active version, it detects drift, plans a migration (Gemini or
 * fallback), and persists it as a PLANNED {@link MigrationLog}. Applying the plan
 * is Phase 3.
 */
@Service
public class SchemaEvolutionService {

    public static final String STATUS_PLANNED = "PLANNED";

    private final SchemaDetectorService detector;
    private final LlmPlannerService planner;
    private final MigrationLogRepository migrationRepo;

    public SchemaEvolutionService(SchemaDetectorService detector,
                                  LlmPlannerService planner,
                                  MigrationLogRepository migrationRepo) {
        this.detector = detector;
        this.planner = planner;
        this.migrationRepo = migrationRepo;
    }

    /** Result of evaluating one incoming batch against the active schema. */
    public record Evaluation(SchemaDiff diff, MigrationLog migration) {
        public DriftType driftType() {
            return diff.driftType();
        }
    }

    @Transactional
    public Evaluation evaluate(Dataset dataset, SchemaVersion active, List<ColumnDef> incoming) {
        SchemaDiff diff = detector.diff(active.getColumns(), incoming);
        if (!diff.hasDrift()) {
            return new Evaluation(diff, null);
        }

        // Don't re-plan (and re-call the LLM) for drift we've already planned for this version.
        var existing = migrationRepo.findFirstByDatasetIdAndFromVersionAndStatusOrderByIdDesc(
                dataset.getId(), active.getVersion(), STATUS_PLANNED);
        if (existing.isPresent() && java.util.Objects.equals(existing.get().getTargetColumns(), incoming)) {
            return new Evaluation(diff, existing.get());
        }

        MigrationPlan plan = planner.plan(dataset.getTargetTable(), active.getColumns(), diff);

        MigrationLog logEntry = new MigrationLog();
        logEntry.setDataset(dataset);
        logEntry.setFromVersion(active.getVersion());
        logEntry.setToVersion(active.getVersion() + 1);
        logEntry.setDriftType(diff.driftType());
        logEntry.setPlan(plan);
        logEntry.setTargetColumns(incoming);
        logEntry.setRiskLevel(plan.getRiskLevel());
        logEntry.setStatus(STATUS_PLANNED);
        MigrationLog saved = migrationRepo.save(logEntry);

        return new Evaluation(diff, saved);
    }
}
