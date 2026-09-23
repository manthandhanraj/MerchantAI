package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.Dataset;
import com.manthan.ade.domain.SchemaVersion;
import com.manthan.ade.repository.DatasetRepository;
import com.manthan.ade.repository.SchemaVersionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

/**
 * Owns dataset registration and the versioned schema history. The active
 * schema version is the platform's source of truth for what a dataset "should"
 * look like — everything downstream diffs against it.
 */
@Service
public class MetadataRegistryService {

    private final DatasetRepository datasetRepo;
    private final SchemaVersionRepository schemaRepo;

    public MetadataRegistryService(DatasetRepository datasetRepo, SchemaVersionRepository schemaRepo) {
        this.datasetRepo = datasetRepo;
        this.schemaRepo = schemaRepo;
    }

    @Transactional
    public Dataset registerDataset(String name, String targetTable) {
        if (datasetRepo.existsByName(name)) {
            throw new IllegalArgumentException("Dataset already exists: " + name);
        }
        Dataset d = new Dataset();
        d.setName(name);
        d.setTargetTable(targetTable != null && !targetTable.isBlank() ? sanitizeTable(targetTable) : sanitizeTable(name));
        return datasetRepo.save(d);
    }

    @Transactional(readOnly = true)
    public Dataset getDataset(Long id) {
        return datasetRepo.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Dataset not found: " + id));
    }

    @Transactional(readOnly = true)
    public List<Dataset> listDatasets() {
        return datasetRepo.findAll();
    }

    @Transactional(readOnly = true)
    public Optional<SchemaVersion> getActiveSchema(Long datasetId) {
        return schemaRepo.findByDatasetIdAndActiveTrue(datasetId);
    }

    @Transactional(readOnly = true)
    public List<SchemaVersion> getSchemaHistory(Long datasetId) {
        return schemaRepo.findByDatasetIdOrderByVersionAsc(datasetId);
    }

    /** Deactivates the current active version (if any) and records a new active one. */
    @Transactional
    public SchemaVersion saveNewVersion(Dataset dataset, List<ColumnDef> columns) {
        schemaRepo.findByDatasetIdAndActiveTrue(dataset.getId()).ifPresent(prev -> {
            prev.setActive(false);
            schemaRepo.save(prev);
        });
        int next = schemaRepo.findMaxVersion(dataset.getId()) + 1;
        SchemaVersion sv = new SchemaVersion();
        sv.setDataset(dataset);
        sv.setVersion(next);
        sv.setColumns(columns);
        sv.setActive(true);
        return schemaRepo.save(sv);
    }

    /** Rollback support: make a specific prior version active again. */
    @Transactional
    public void activateVersion(Long datasetId, Integer version) {
        SchemaVersion target = schemaRepo.findByDatasetIdAndVersion(datasetId, version)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Schema version " + version + " not found for dataset " + datasetId));
        schemaRepo.findByDatasetIdAndActiveTrue(datasetId).ifPresent(current -> {
            if (!current.getId().equals(target.getId())) {
                current.setActive(false);
                schemaRepo.save(current);
            }
        });
        target.setActive(true);
        schemaRepo.save(target);
    }

    private String sanitizeTable(String name) {
        String t = name.trim().toLowerCase().replaceAll("[^a-z0-9_]+", "_").replaceAll("^_+|_+$", "");
        return t.isEmpty() ? "dataset_table" : t;
    }
}
