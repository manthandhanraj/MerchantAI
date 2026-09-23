package com.manthan.ade.web.dto;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.IngestBatch;

import java.time.OffsetDateTime;
import java.util.List;

public record IngestBatchResponse(Long id, Long datasetId, String sourceFile, int rowCount,
                                  String status, List<ColumnDef> detectedColumns, OffsetDateTime createdAt) {
    public static IngestBatchResponse from(IngestBatch b) {
        return new IngestBatchResponse(b.getId(), b.getDataset().getId(), b.getSourceFile(),
                b.getRowCount(), b.getStatus(), b.getDetectedColumns(), b.getCreatedAt());
    }
}
