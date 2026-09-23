package com.manthan.ade.repository;

import com.manthan.ade.domain.Dataset;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface DatasetRepository extends JpaRepository<Dataset, Long> {
    Optional<Dataset> findByName(String name);
    boolean existsByName(String name);
}
