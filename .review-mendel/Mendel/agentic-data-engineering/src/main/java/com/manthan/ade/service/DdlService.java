package com.manthan.ade.service;

import com.manthan.ade.domain.ColumnDef;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Executes physical DDL against the target database. Kept tiny and separate so
 * the executor's guardrail logic stays testable and the raw SQL surface is in
 * one place. Uses the same DataSource as JPA, so it participates in the caller's
 * transaction (DDL is transactional in PostgreSQL).
 */
@Service
public class DdlService {

    private final JdbcTemplate jdbc;

    public DdlService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** Create the physical table from a schema if it doesn't exist yet. */
    public void ensureTable(String table, List<ColumnDef> columns) {
        String cols = columns.stream()
                .map(c -> c.getName() + " " + c.getSqlType() + (c.isNullable() ? "" : " NOT NULL"))
                .collect(Collectors.joining(", "));
        jdbc.execute("CREATE TABLE IF NOT EXISTS " + table + " (" + cols + ")");
    }

    public void execute(String sql) {
        jdbc.execute(sql);
    }
}
