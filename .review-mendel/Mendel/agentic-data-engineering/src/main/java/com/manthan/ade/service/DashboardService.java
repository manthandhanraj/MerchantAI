package com.manthan.ade.service;

import com.manthan.ade.domain.Dataset;
import com.manthan.ade.domain.MigrationLog;
import com.manthan.ade.domain.SchemaVersion;
import com.manthan.ade.repository.DatasetRepository;
import com.manthan.ade.repository.MigrationLogRepository;
import com.manthan.ade.repository.SchemaVersionRepository;
import com.manthan.ade.web.dto.DashboardSummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Rolls up datasets, schema versions and migrations into the numbers the
 * dashboard shows — so the UI makes one call instead of stitching endpoints.
 */
@Service
public class DashboardService {

    private final DatasetRepository datasetRepo;
    private final MigrationLogRepository migrationRepo;
    private final SchemaVersionRepository schemaRepo;

    public DashboardService(DatasetRepository datasetRepo,
                            MigrationLogRepository migrationRepo,
                            SchemaVersionRepository schemaRepo) {
        this.datasetRepo = datasetRepo;
        this.migrationRepo = migrationRepo;
        this.schemaRepo = schemaRepo;
    }

    @Transactional(readOnly = true)
    public DashboardSummary summary() {
        List<Dataset> datasets = datasetRepo.findAll();
        List<MigrationLog> all = migrationRepo.findAll();

        long applied = countStatus(all, MigrationExecutorService.APPLIED);
        long failed = countStatus(all, MigrationExecutorService.FAILED);
        long planned = countStatus(all, MigrationExecutorService.PLANNED);
        long rolled = countStatus(all, MigrationExecutorService.ROLLED_BACK);
        int total = all.size();
        double health = total == 0 ? 100.0 : round1((1.0 - (double) failed / total) * 100.0);

        int activeSchemas = 0;
        List<DashboardSummary.DatasetHealth> rows = new ArrayList<>();
        for (Dataset d : datasets) {
            var active = schemaRepo.findByDatasetIdAndActiveTrue(d.getId());
            if (active.isPresent()) {
                activeSchemas++;
            }
            List<MigrationLog> dm = migrationRepo.findByDatasetIdOrderByIdDesc(d.getId());
            long a = countStatus(dm, MigrationExecutorService.APPLIED);
            long f = countStatus(dm, MigrationExecutorService.FAILED);
            double rate = (a + f) == 0 ? 100.0 : round1(a * 100.0 / (a + f));
            String status = dm.isEmpty() ? "Healthy" : mapStatus(dm.get(0).getStatus());
            OffsetDateTime last = dm.isEmpty()
                    ? active.map(SchemaVersion::getCreatedAt).orElse(d.getCreatedAt())
                    : dm.get(0).getCreatedAt();
            rows.add(new DashboardSummary.DatasetHealth(
                    d.getId(), d.getName(),
                    active.map(SchemaVersion::getVersion).orElse(null),
                    status, dm.size(), rate, last));
        }

        List<DashboardSummary.Activity> activity = migrationRepo.findTop20ByOrderByIdDesc().stream()
                .map(this::toActivity).toList();

        DashboardSummary.Stats stats = new DashboardSummary.Stats(
                datasets.size(), activeSchemas, total, total, applied, failed, planned, rolled);
        return new DashboardSummary(stats, health, rows, activity);
    }

    private long countStatus(List<MigrationLog> list, String status) {
        return list.stream().filter(m -> status.equals(m.getStatus())).count();
    }

    private String mapStatus(String status) {
        if (MigrationExecutorService.FAILED.equals(status)) return "Failed";
        if (MigrationExecutorService.PLANNED.equals(status)) return "Warning";
        return "Healthy";
    }

    private DashboardSummary.Activity toActivity(MigrationLog m) {
        String name = m.getDataset().getName();
        String level;
        String message;
        switch (m.getStatus()) {
            case MigrationExecutorService.APPLIED -> {
                level = "ok";
                message = name + ": auto-heal applied v" + m.getFromVersion() + " -> v" + m.getToVersion();
            }
            case MigrationExecutorService.FAILED -> {
                level = "err";
                message = name + ": migration failed";
            }
            case MigrationExecutorService.ROLLED_BACK -> {
                level = "warn";
                message = name + ": rolled back to v" + m.getFromVersion();
            }
            case MigrationExecutorService.PLANNED -> {
                level = "info";
                message = name + ": migration planned (" + m.getDriftType() + ")";
            }
            default -> {
                level = "info";
                message = name + ": " + m.getStatus();
            }
        }
        return new DashboardSummary.Activity(
                m.getCreatedAt(),
                m.getDriftType() == null ? null : m.getDriftType().name(),
                level, message);
    }

    private double round1(double v) {
        return Math.round(v * 10.0) / 10.0;
    }
}
