package com.manthan.ade.web.dto;

import com.manthan.ade.domain.MigrationLog;
import com.manthan.ade.domain.MigrationPlan;

import java.time.OffsetDateTime;

public record MigrationResponse(
        Long id,
        Long datasetId,
        Integer fromVersion,
        Integer toVersion,
        String driftType,
        String riskLevel,
        String status,
        MigrationPlan plan,
        OffsetDateTime createdAt
) {
    public static MigrationResponse from(MigrationLog m) {
        return new MigrationResponse(
                m.getId(),
                m.getDataset().getId(),
                m.getFromVersion(),
                m.getToVersion(),
                m.getDriftType() == null ? null : m.getDriftType().name(),
                m.getRiskLevel(),
                m.getStatus(),
                m.getPlan(),
                m.getCreatedAt()
        );
    }
}
