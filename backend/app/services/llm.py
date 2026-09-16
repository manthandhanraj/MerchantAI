"""Isolated LLM adapter.

The only place in the codebase that talks to a model provider. Everything else
goes through `complete()`, so the assistant can be tested — and the whole app
run — with no network, no key and no provider package installed.

Two rules:

1. **Disabled by default.** `LLM_ENABLED` defaults to false, and a blank
   `LLM_API_KEY` also counts as disabled. Nothing here is reachable until both
   are set.
2. **Failures are contained.** Every provider error becomes an `LLMError` for
   the caller to handle. A model being down must never take the API with it.

Credentials come from the environment via `config.settings`; nothing is
hard-coded here.
"""

from __future__ import annotations

from backend.app.config import settings

# Kept modest: the assistant answers a merchant's question in a paragraph or
# two, not an essay.
MAX_OUTPUT_TOKENS = 700
REQUEST_TIMEOUT_SECONDS = 30.0

SUPPORTED_PROVIDERS = ("anthropic",)


class LLMError(RuntimeError):
    """Any failure reaching or using the configured provider."""


def is_enabled() -> bool:
    """Whether a live model call is possible at all.

    A key is required as well as the flag: `LLM_ENABLED=true` with no key would
    otherwise fail on every request instead of falling back cleanly.
    """
    return bool(settings.llm_enabled and settings.llm_api_key)


def describe() -> dict:
    """Configuration state, safe to expose — never includes the key itself."""
    return {
        "enabled": is_enabled(),
        "flag_set": bool(settings.llm_enabled),
        "key_present": bool(settings.llm_api_key),
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }


def complete(system: str, user: str) -> str:
    """Send one prompt to the configured provider and return the text reply.

    Raises `LLMError` for every failure mode — disabled, unsupported provider,
    missing package, network or API error — so callers need only catch one type.
    """
    if not is_enabled():
        raise LLMError(
            "The language model is disabled. Set LLM_ENABLED=true and provide "
            "LLM_API_KEY to enable it."
        )

    provider = (settings.llm_provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise LLMError(
            f"Unsupported LLM provider '{settings.llm_provider}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    # Imported lazily and deliberately: the package is not a runtime dependency
    # while the feature is off, and tests must not need it installed.
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise LLMError(
            "The 'anthropic' package is not installed. Add it to requirements.txt "
            "to enable the language model."
        ) from exc

    try:
        client = anthropic.Anthropic(
            api_key=settings.llm_api_key, timeout=REQUEST_TIMEOUT_SECONDS
        )
        message = client.messages.create(
            model=settings.llm_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:  # pragma: no cover - provider/network dependent
        raise LLMError(f"The language model request failed: {exc}") from exc

    text = "".join(
        block.text for block in getattr(message, "content", []) if getattr(block, "type", "") == "text"
    ).strip()

    if not text:
        raise LLMError("The language model returned an empty response.")
    return text
