package com.manthan.ade.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/** Requires a configured API key for state-changing operations. */
@Component
public class ApiKeyGuard extends OncePerRequestFilter {
    @Value("${app.api-key:}")
    private String apiKey;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/") || "GET".equalsIgnoreCase(request.getMethod())
                || "OPTIONS".equalsIgnoreCase(request.getMethod());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (apiKey.isBlank() || !apiKey.equals(request.getHeader("X-API-Key"))) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "A valid X-API-Key is required");
            return;
        }
        chain.doFilter(request, response);
    }
}
