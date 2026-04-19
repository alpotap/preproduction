"""Provider configuration and client factory helpers for LLM backends."""

import os
from openai import OpenAI, AzureOpenAI

OLLAMA_PROVIDER = "ollama"
LM_STUDIO_PROVIDER = "lm_studio"
AZURE_PROVIDER = "azure_openai"
AZURE_AI_FOUNDRY_PROVIDER = "azure_ai_foundry"


def normalize_provider(provider):
    """Normalize persisted provider labels to supported provider keys."""
    provider = (provider or "").strip().lower()
    if provider in {"azure", "azure_openai", "github"}:
        return AZURE_PROVIDER
    if provider in {"azure_ai_foundry", "foundry"}:
        return AZURE_AI_FOUNDRY_PROVIDER
    if provider in {"lm_studio", "lmstudio", "local", "local_lm_studio"}:
        return LM_STUDIO_PROVIDER
    return OLLAMA_PROVIDER


def get_azure_settings(config):
    """Load Azure OpenAI settings from env/config."""
    return {
        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION") or config.get("azure_api_version", "2024-10-21"),
        "deployment_name": config.get("azure_deployment_name", "").strip(),
    }


def get_azure_ai_foundry_settings(config):
    """Load Azure AI Foundry settings from env/config."""
    raw = config.get("azure_ai_foundry_model_name", "") or ""
    model_names = [m.strip() for m in raw.split(",") if m.strip()]
    return {
        "api_key": os.getenv("AZURE_AI_FOUNDRY_API_KEY"),
        "endpoint": os.getenv("AZURE_AI_FOUNDRY_ENDPOINT"),
        "api_version": os.getenv("AZURE_AI_FOUNDRY_API_VERSION") or config.get("azure_ai_foundry_api_version", "2025-01-01-preview"),
        "model_name": model_names[0] if model_names else "",
        "model_names": model_names,
    }


def _normalize_azure_endpoint(endpoint):
    """Normalize Azure endpoint for AzureOpenAI client usage."""
    value = (endpoint or "").strip().rstrip("/")
    if value.lower().endswith("/openai/v1"):
        value = value[: -len("/openai/v1")]
    return value


def get_lm_studio_settings(config):
    """Load LM Studio settings from env/config."""
    base_url = (
        os.getenv("LM_STUDIO_BASE_URL")
        or config.get("lm_studio_base_url", "http://127.0.0.1:1234/v1")
    ).strip()
    if base_url and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    return {
        "base_url": base_url.rstrip("/"),
        "model_name": config.get("lm_studio_model_name", "").strip(),
    }


def validate_provider_config(provider, config):
    """Validate provider-specific configuration before processing."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if not azure_settings["deployment_name"]:
            raise RuntimeError("Missing Azure Deployment Name in configuration.")
    elif normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["model_name"]:
            raise RuntimeError("Missing Azure AI Foundry Model Name in configuration.")
    elif normalized_provider == LM_STUDIO_PROVIDER and not config.get("llm_model", "").strip():
        raise RuntimeError("Missing LM Studio model selection. Choose a model from the wizard.")


def create_client(provider, config):
    """Create an LLM client for the selected provider."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        azure_settings = get_azure_settings(config)
        if not azure_settings["api_key"]:
            raise RuntimeError("Missing AZURE_OPENAI_API_KEY environment variable.")
        if not azure_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT environment variable.")

        return AzureOpenAI(
            api_key=azure_settings["api_key"],
            azure_endpoint=azure_settings["endpoint"],
            api_version=azure_settings["api_version"],
        )

    if normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["api_key"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_API_KEY environment variable.")
        if not foundry_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_ENDPOINT environment variable.")

        return AzureOpenAI(
            api_key=foundry_settings["api_key"],
            azure_endpoint=_normalize_azure_endpoint(foundry_settings["endpoint"]),
            api_version=foundry_settings["api_version"],
        )

    if normalized_provider == LM_STUDIO_PROVIDER:
        lm_studio_settings = get_lm_studio_settings(config)
        if not lm_studio_settings["base_url"]:
            raise RuntimeError("Missing LM Studio base URL in configuration.")
        return OpenAI(
            api_key=os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
            base_url=lm_studio_settings["base_url"],
        )

    return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


def fetch_ollama_models():
    """Fetch available model IDs from Ollama."""
    try:
        client = create_client(OLLAMA_PROVIDER, {})
        models_response = client.models.list()
        return [m.id for m in models_response.data] if models_response.data else []
    except Exception as e:
        print(f"Could not fetch models from Ollama: {e}")
        return []


def fetch_lm_studio_models(config):
    """Fetch available model IDs from LM Studio."""
    try:
        client = create_client(LM_STUDIO_PROVIDER, config)
        models_response = client.models.list()
        return [m.id for m in models_response.data] if models_response.data else []
    except Exception as e:
        print(f"Could not fetch models from LM Studio: {e}")
        return []


def format_model_label(model_name, provider):
    """Return a user-friendly model label including provider."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_PROVIDER:
        provider_label = "Azure OpenAI"
    elif normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        provider_label = "Azure AI Foundry"
    elif normalized_provider == LM_STUDIO_PROVIDER:
        provider_label = "LM Studio"
    else:
        provider_label = "Ollama"
    return f"{model_name} ({provider_label})"
