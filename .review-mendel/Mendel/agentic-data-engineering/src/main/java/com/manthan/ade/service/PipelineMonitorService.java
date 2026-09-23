package com.manthan.ade.service;

import com.manthan.ade.domain.Dataset;
import com.manthan.ade.domain.DriftType;
import com.manthan.ade.domain.IngestBatch;
import com.manthan.ade.domain.SchemaVersion;
import com.manthan.ade.repository.IngestBatchRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.io.Reader;
import java.util.List;
import java.util.Optional;

/**
 * Ingests a CSV batch, extracts its schema, and records it. On the first batch
 * it registers the baseline (v1). On later batches it hands the incoming schema
 * to {@link SchemaEvolutionService}, which detects drift and plans a migration.
 */
@Service
public class PipelineMonitorService {

    private final SchemaInferenceService inference;
    private final MetadataRegistryService registry;
    private final SchemaEvolutionService evolution;
    private final IngestBatchRepository batchRepo;

    public PipelineMonitorService(SchemaInferenceService inference,
                                  MetadataRegistryService registry,
                                  SchemaEvolutionService evolution,
                                  IngestBatchRepository batchRepo) {
        this.inference = inference;
        this.registry = registry;
        this.evolution = evolution;
        this.batchRepo = batchRepo;
    }

    /** Outcome of an ingest: the stored batch plus any drift/plan produced. */
    public record IngestOutcome(IngestBatch batch, DriftType driftType, Long migrationId, String riskLevel) {}

    @Transactional
    public IngestOutcome ingest(Long datasetId, String sourceFile, Reader csv) throws IOException {
        Dataset dataset = registry.getDataset(datasetId);
        SchemaInferenceService.InferenceResult result = inference.infer(csv);

        Optional<SchemaVersion> active = registry.getActiveSchema(datasetId);
        DriftType drift = DriftType.NONE;
        Long migrationId = null;
        String risk = null;
        String status;

        if (active.isEmpty()) {
            registry.saveNewVersion(dataset, result.columns());
            status = "BASELINE";
        } else {
            SchemaEvolutionService.Evaluation eval = evolution.evaluate(dataset, active.get(), result.columns());
            drift = eval.driftType();
            if (eval.migration() != null) {
                migrationId = eval.migration().getId();
                risk = eval.migration().getRiskLevel();
            }
            status = (drift == DriftType.NONE) ? "INGESTED" : "DRIFT_DETECTED";
        }

        IngestBatch batch = new IngestBatch();
        batch.setDataset(dataset);
        batch.setSourceFile(sourceFile);
        batch.setRowCount(result.rowCount());
        batch.setDetectedColumns(result.columns());
        batch.setStatus(status);
        IngestBatch saved = batchRepo.save(batch);

        return new IngestOutcome(saved, drift, migrationId, risk);
    }

    @Transactional(readOnly = true)
    public List<IngestBatch> listBatches(Long datasetId) {
        registry.getDataset(datasetId); // validates existence
        return batchRepo.findByDatasetIdOrderByCreatedAtDesc(datasetId);
    }
}
