package com.manthan.ade.repository;

import com.manthan.ade.domain.IngestBatch;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface IngestBatchRepository extends JpaRepository<IngestBatch, Long> {
    List<IngestBatch> findByDatasetIdOrderByCreatedAtDesc(Long datasetId);
}
