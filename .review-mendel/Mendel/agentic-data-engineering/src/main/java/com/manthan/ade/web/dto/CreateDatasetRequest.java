package com.manthan.ade.web.dto;

import jakarta.validation.constraints.NotBlank;

public record CreateDatasetRequest(
        @NotBlank String name,
        String targetTable
) {}
