package com.manthan.ade.repository;

import com.manthan.ade.domain.SchemaVersion;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface SchemaVersionRepository extends JpaRepository<SchemaVersion, Long> {

    Optional<SchemaVersion> findByDatasetIdAndActiveTrue(Long datasetId);

    Optional<SchemaVersion> findByDatasetIdAndVersion(Long datasetId, Integer version);

    List<SchemaVersion> findByDatasetIdOrderByVersionAsc(Long datasetId);

    @Query("select coalesce(max(sv.version), 0) from SchemaVersion sv where sv.dataset.id = :datasetId")
    int findMaxVersion(@Param("datasetId") Long datasetId);
}
