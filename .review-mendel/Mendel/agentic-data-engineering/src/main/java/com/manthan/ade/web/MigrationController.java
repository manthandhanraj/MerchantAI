package com.manthan.ade.web;

import com.manthan.ade.repository.MigrationLogRepository;
import com.manthan.ade.service.MetadataRegistryService;
import com.manthan.ade.service.MigrationExecutorService;
import com.manthan.ade.web.dto.MigrationResponse;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api")
public class MigrationController {

    private final MigrationLogRepository migrationRepo;
    private final MetadataRegistryService registry;
    private final MigrationExecutorService executor;

    public MigrationController(MigrationLogRepository migrationRepo,
                              MetadataRegistryService registry,
                              MigrationExecutorService executor) {
        this.migrationRepo = migrationRepo;
        this.registry = registry;
        this.executor = executor;
    }

    @GetMapping("/datasets/{id}/migrations")
    public List<MigrationResponse> forDataset(@PathVariable Long id) {
        registry.getDataset(id); // validates existence
        return migrationRepo.findByDatasetIdOrderByIdDesc(id).stream()
                .map(MigrationResponse::from)
                .toList();
    }

    @GetMapping("/migrations/{id}")
    public MigrationResponse one(@PathVariable Long id) {
        return migrationRepo.findById(id)
                .map(MigrationResponse::from)
                .orElseThrow(() -> new IllegalArgumentException("Migration not found: " + id));
    }

    /** Apply a planned migration. High-risk changes require ?confirm=true. */
    @PostMapping("/migrations/{id}/apply")
    public MigrationResponse apply(@PathVariable Long id,
                                   @RequestParam(defaultValue = "false") boolean confirm) {
        return MigrationResponse.from(executor.apply(id, confirm));
    }

    /** Roll an applied migration back and restore the previous schema version. */
    @PostMapping("/migrations/{id}/rollback")
    public MigrationResponse rollback(@PathVariable Long id) {
        return MigrationResponse.from(executor.rollback(id));
    }
}
