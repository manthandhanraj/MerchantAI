package com.manthan.ade.service;

/** Raised when a migration is blocked by a safety guardrail (needs confirmation or is unsafe). */
public class GuardrailException extends RuntimeException {
    public GuardrailException(String message) {
        super(message);
    }
}
