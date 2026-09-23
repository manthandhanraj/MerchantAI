package com.manthan.ade.repository;

import com.manthan.ade.domain.DriftType;
import com.manthan.ade.domain.MigrationLog;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface MigrationLogRepository extends JpaRepository<MigrationLog, Long> {

    List<MigrationLog> findByDatasetIdOrderByIdDesc(Long datasetId);

    List<MigrationLog> findTop20ByOrderByIdDesc();

    /** Used to avoid re-planning the same drift (and re-calling the LLM). */
    Optional<MigrationLog> findFirstByDatasetIdAndFromVersionAndStatusOrderByIdDesc(
            Long datasetId, Integer fromVersion, String status);
}
