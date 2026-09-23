package com.manthan.ade.llm;

import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * Calls the Gemini generateContent endpoint and returns the model's text output.
 * Uses {@code responseMimeType=application/json} so the model replies with JSON
 * only. Any transport/HTTP failure is surfaced as {@link LlmException} so the
 * planner can fall back to its rule-based path.
 */
@Component
public class GeminiClient implements LlmClient {

    private static final Logger log = LoggerFactory.getLogger(GeminiClient.class);

    private final GeminiProperties props;
    private final RestClient http;

    public GeminiClient(GeminiProperties props) {
        this.props = props;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(30_000);
        this.http = RestClient.builder().requestFactory(factory).build();
    }

    @Override
    public boolean isAvailable() {
        return props.isConfigured();
    }

    @Override
    public String generateJson(String prompt) {
        if (!isAvailable()) {
            throw new LlmException("Gemini API key not configured");
        }
        String url = props.getBaseUrl() + "/models/" + props.getModel()
                + ":generateContent?key=" + props.getApiKey();

        Map<String, Object> body = Map.of(
                "contents", List.of(Map.of("parts", List.of(Map.of("text", prompt)))),
                "generationConfig", Map.of(
                        "temperature", 0.2,
                        "responseMimeType", "application/json"
                )
        );

        try {
            JsonNode resp = http.post()
                    .uri(url)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(JsonNode.class);

            if (resp == null) {
                throw new LlmException("Empty response from Gemini");
            }
            JsonNode text = resp.path("candidates").path(0)
                    .path("content").path("parts").path(0).path("text");
            if (text.isMissingNode() || text.asText().isBlank()) {
                throw new LlmException("Gemini response had no text part: " + resp);
            }
            return text.asText();
        } catch (LlmException e) {
            throw e;
        } catch (Exception e) {
            log.warn("Gemini call failed: {}", e.getMessage());
            throw new LlmException("Gemini call failed: " + e.getMessage(), e);
        }
    }
}
