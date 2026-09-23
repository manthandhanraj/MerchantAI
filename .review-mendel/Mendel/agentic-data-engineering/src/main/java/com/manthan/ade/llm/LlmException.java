package com.manthan.ade.llm;

/** Raised when an LLM call cannot produce a usable result. */
public class LlmException extends RuntimeException {
    public LlmException(String message) {
        super(message);
    }

    public LlmException(String message, Throwable cause) {
        super(message, cause);
    }
}
