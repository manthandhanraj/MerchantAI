package com.manthan.ade.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.manthan.ade.domain.ColumnDef;
import com.manthan.ade.domain.DriftType;
import com.manthan.ade.llm.LlmClient;
import org.junit.jupiter.api.Test;

import java.io.StringReader;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PlannerAndInferenceSafetyTest {

    @Test
    void llmSqlIsNeverUsedAsMigrationSql() {
        LlmClient malicious = new LlmClient() {
            @Override public boolean isAvailable() { return true; }
            @Override public String generateJson(String prompt) {
                return "{\"reasoning\":\"unsafe\",\"migrationSql\":[\"ALTER TABLE users ADD COLUMN hacked TEXT\"],"
                        + "\"rollbackSql\":[],\"warnings\":[]}";
            }
        };
        var planner = new LlmPlannerService(malicious, new ObjectMapper());
        var diff = new SchemaDiff(DriftType.ADDITIVE,
                List.of(new ColumnDef("phone", "TEXT", true)), List.of(), List.of(), null, "added phone");

        var plan = planner.plan("customers", List.of(), diff);

        assertEquals(List.of("ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone TEXT;"), plan.getMigrationSql());
        assertEquals("gemini-assisted/rule-based-sql", plan.getSource());
    }

    @Test
    void rejectsHeadersThatNormalizeToTheSameIdentifier() {
        var inference = new SchemaInferenceService();

        assertThrows(IllegalArgumentException.class,
                () -> inference.infer(new StringReader("First Name,first-name\nAda,Lovelace\n")));
    }
}
