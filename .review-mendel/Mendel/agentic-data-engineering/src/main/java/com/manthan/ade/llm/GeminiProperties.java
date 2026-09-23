package com.manthan.ade.llm;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "llm.gemini")
@Getter
@Setter
public class GeminiProperties {
    private String apiKey = "";
    private String model = "gemini-2.0-flash";
    private String baseUrl = "https://generativelanguage.googleapis.com/v1beta";

    public boolean isConfigured() {
        return apiKey != null && !apiKey.isBlank();
    }
}
