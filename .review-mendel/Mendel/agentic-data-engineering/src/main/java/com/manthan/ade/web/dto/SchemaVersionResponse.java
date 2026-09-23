package com.manthan.ade.web.dto;

import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.SchemaVersion;

import java.time.OffsetDateTime;
import java.util.List;

public record SchemaVersionResponse(Long id, Long datasetId, Integer version, boolean active,
                                    List<ColumnDef> columns, OffsetDateTime createdAt) {
    public static SchemaVersionResponse from(SchemaVersion sv) {
        return new SchemaVersionResponse(sv.getId(), sv.getDataset().getId(), sv.getVersion(),
                sv.isActive(), sv.getColumns(), sv.getCreatedAt());
    }
}
