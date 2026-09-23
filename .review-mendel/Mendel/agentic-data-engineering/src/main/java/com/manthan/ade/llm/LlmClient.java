package com.manthan.ade.llm;

/**
 * Minimal abstraction over an LLM text-generation call, so the planner is not
 * tied to a single provider. The prompt is expected to instruct the model to
 * return JSON only.
 */
public interface LlmClient {

    /** @return the model's raw text output (expected to be a JSON document). */
    String generateJson(String prompt);

    /** Whether the client is usable (e.g. an API key is present). */
    boolean isAvailable();
}
