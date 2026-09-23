package com.manthan.ade.web.dto;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.service.PipelineMonitorService.IngestOutcome;

import java.util.List;

/**
 * Returned by the ingest endpoint: the recorded batch plus any drift the
 * evolution engine detected and the id of the migration it planned.
 */
public record IngestResultResponse(
        Long batchId,
        String status,
        int rowCount,
        List<ColumnDef> detectedColumns,
        String driftType,
        Long migrationId,
        String riskLevel
) {
    public static IngestResultResponse from(IngestOutcome o) {
        return new IngestResultResponse(
                o.batch().getId(),
                o.batch().getStatus(),
                o.batch().getRowCount(),
                o.batch().getDetectedColumns(),
                o.driftType() == null ? null : o.driftType().name(),
                o.migrationId(),
                o.riskLevel()
        );
    }
}
