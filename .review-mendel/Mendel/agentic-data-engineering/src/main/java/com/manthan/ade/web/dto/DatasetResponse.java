package com.manthan.ade.web.dto;

import com.manthan.ade.domain.Dataset;

import java.time.OffsetDateTime;

public record DatasetResponse(Long id, String name, String targetTable, OffsetDateTime createdAt) {
    public static DatasetResponse from(Dataset d) {
        return new DatasetResponse(d.getId(), d.getName(), d.getTargetTable(), d.getCreatedAt());
    }
}
