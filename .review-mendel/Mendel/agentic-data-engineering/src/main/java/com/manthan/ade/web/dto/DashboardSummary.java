package com.manthan.ade.web.dto;

import java.time.OffsetDateTime;
import java.util.List;

/** Aggregated data the dashboard needs, in one call. */
public record DashboardSummary(
        Stats stats,
        double systemHealth,
        List<DatasetHealth> datasets,
        List<Activity> activity
) {
    public record Stats(
            int totalDatasets,
            int activeSchemas,
            int schemaChanges,
            int aiDecisions,
            long autoHealed,
            long failedJobs,
            long pendingPlans,
            long rolledBack
    ) {}

    public record DatasetHealth(
            Long id,
            String name,
            Integer activeVersion,
            String status,          // Healthy | Warning | Failed
            int migrationCount,
            double successRate,
            OffsetDateTime lastChange
    ) {}

    public record Activity(
            OffsetDateTime ts,
            String type,            // drift type, if any
            String level,           // ok | info | warn | err
            String message
    ) {}
}
