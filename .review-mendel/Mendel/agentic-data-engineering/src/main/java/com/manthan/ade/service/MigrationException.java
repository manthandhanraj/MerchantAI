package com.manthan.ade.service;

/** Raised when a migration cannot be applied or rolled back (state or execution error). */
public class MigrationException extends RuntimeException {
    public MigrationException(String message) {
        super(message);
    }
}
