package com.manthan.ade.web;

import com.manthan.ade.service.MetadataRegistryService;
import com.manthan.ade.service.PipelineMonitorService;
import com.manthan.ade.web.dto.CreateDatasetRequest;
import com.manthan.ade.web.dto.DatasetResponse;
import com.manthan.ade.web.dto.IngestBatchResponse;
import com.manthan.ade.web.dto.IngestResultResponse;
import com.manthan.ade.web.dto.SchemaVersionResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.List;

@RestController
@RequestMapping("/api/datasets")
public class DatasetController {

    private final MetadataRegistryService registry;
    private final PipelineMonitorService monitor;

    public DatasetController(MetadataRegistryService registry, PipelineMonitorService monitor) {
        this.registry = registry;
        this.monitor = monitor;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DatasetResponse create(@Valid @RequestBody CreateDatasetRequest req) {
        return DatasetResponse.from(registry.registerDataset(req.name(), req.targetTable()));
    }

    @GetMapping
    public List<DatasetResponse> list() {
        return registry.listDatasets().stream().map(DatasetResponse::from).toList();
    }

    @GetMapping("/{id}")
    public DatasetResponse get(@PathVariable Long id) {
        return DatasetResponse.from(registry.getDataset(id));
    }

    @GetMapping("/{id}/schema")
    public SchemaVersionResponse activeSchema(@PathVariable Long id) {
        registry.getDataset(id);
        return registry.getActiveSchema(id)
                .map(SchemaVersionResponse::from)
                .orElseThrow(() -> new IllegalArgumentException(
                        "No active schema yet for dataset " + id + " — ingest a CSV first"));
    }

    @GetMapping("/{id}/schema/history")
    public List<SchemaVersionResponse> schemaHistory(@PathVariable Long id) {
        registry.getDataset(id);
        return registry.getSchemaHistory(id).stream().map(SchemaVersionResponse::from).toList();
    }

    @PostMapping(value = "/{id}/ingest", consumes = "multipart/form-data")
    public IngestResultResponse ingest(@PathVariable Long id, @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("Uploaded file is empty");
        }
        try (var reader = new InputStreamReader(file.getInputStream(), StandardCharsets.UTF_8)) {
            return IngestResultResponse.from(monitor.ingest(id, file.getOriginalFilename(), reader));
        }
    }

    @GetMapping("/{id}/batches")
    public List<IngestBatchResponse> batches(@PathVariable Long id) {
        return monitor.listBatches(id).stream().map(IngestBatchResponse::from).toList();
    }
}
