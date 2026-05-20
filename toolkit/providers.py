"""Provider configuration and client factory helpers for LLM backends."""

import os
from openai import OpenAI, AzureOpenAI

OLLAMA_PROVIDER = "ollama"
LM_STUDIO_PROVIDER = "lm_studio"
AZURE_AI_FOUNDRY_PROVIDER = "azure_ai_foundry"
DEFAULT_AZURE_AI_FOUNDRY_API_VERSION = "2025-01-01-preview"
FOUNDRY_DEFAULT_PROFILE = "default"
FOUNDRY_MODEL_DELIMITER = "::"
FOUNDRY_VENDOR_PROVIDER_PREFIX = "foundry_vendor_"
DEFAULT_FOUNDRY_VENDOR = "azure"


def _normalize_api_key(value):
    return (value or "").strip().strip("`\"'")


def _read_env_var(name):
    """Read env var from process, then Windows HKCU/HKLM registry fallbacks."""
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    if os.name != "nt":
        return ""
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            reg_value, _ = winreg.QueryValueEx(key, name)
            user_value = str(reg_value).strip()
            if user_value:
                return user_value
    except Exception:
        pass
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            reg_value, _ = winreg.QueryValueEx(key, name)
            return str(reg_value).strip()
    except Exception:
        return ""


def normalize_provider(provider):
    """Normalize persisted provider labels to supported provider keys."""
    provider = (provider or "").strip().lower()
    if provider.startswith(FOUNDRY_VENDOR_PROVIDER_PREFIX):
        return AZURE_AI_FOUNDRY_PROVIDER
    if provider.startswith("azure") or provider in {"github", "foundry"}:
        return AZURE_AI_FOUNDRY_PROVIDER
    if provider in {"lm_studio", "lmstudio", "local", "local_lm_studio"}:
        return LM_STUDIO_PROVIDER
    return OLLAMA_PROVIDER


def normalize_vendor_id(vendor):
    """Normalize a vendor category key for provider routing."""
    raw_vendor = (vendor or "").strip().lower()
    cleaned = "".join(ch for ch in raw_vendor if ch.isalnum() or ch == "_")
    return cleaned or DEFAULT_FOUNDRY_VENDOR


def provider_key_for_vendor(vendor):
    """Map Foundry vendor ID to a provider key."""
    vendor_id = normalize_vendor_id(vendor)
    if vendor_id == DEFAULT_FOUNDRY_VENDOR:
        return AZURE_AI_FOUNDRY_PROVIDER
    return f"{FOUNDRY_VENDOR_PROVIDER_PREFIX}{vendor_id}"


def vendor_from_provider_key(provider):
    """Resolve vendor ID from provider key when it points to Foundry."""
    raw = (provider or "").strip().lower()
    if raw == AZURE_AI_FOUNDRY_PROVIDER or raw.startswith("azure") or raw in {"github", "foundry"}:
        return DEFAULT_FOUNDRY_VENDOR
    if raw.startswith(FOUNDRY_VENDOR_PROVIDER_PREFIX):
        return normalize_vendor_id(raw[len(FOUNDRY_VENDOR_PROVIDER_PREFIX) :])
    return ""


def provider_label_for_vendor(vendor_label, vendor_id):
    """Return a display label for vendor-specific Foundry providers."""
    if normalize_vendor_id(vendor_id) == DEFAULT_FOUNDRY_VENDOR:
        return "Azure AI Foundry"
    normalized_label = (vendor_label or "").strip() or vendor_id
    return f"Foundry: {normalized_label}"


def _normalize_profile_id(raw_profile):
    profile = (raw_profile or "").strip().lower()
    cleaned = "".join(ch for ch in profile if ch.isalnum() or ch == "_")
    return cleaned


def _parse_profile_ids():
    merged_raw_values = []
    process_value = (os.getenv("AZURE_AI_FOUNDRY_PROFILE_IDS") or "").strip()
    if process_value:
        merged_raw_values.append(process_value)

    if os.name == "nt":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                user_value, _ = winreg.QueryValueEx(key, "AZURE_AI_FOUNDRY_PROFILE_IDS")
                user_value = str(user_value).strip()
                if user_value:
                    merged_raw_values.append(user_value)
        except Exception:
            pass
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"System\CurrentControlSet\Control\Session Manager\Environment",
            ) as key:
                machine_value, _ = winreg.QueryValueEx(key, "AZURE_AI_FOUNDRY_PROFILE_IDS")
                machine_value = str(machine_value).strip()
                if machine_value:
                    merged_raw_values.append(machine_value)
        except Exception:
            pass

    profiles = []
    seen = set()
    for raw in merged_raw_values:
        for item in raw.split(","):
            profile = _normalize_profile_id(item)
            if profile and profile not in seen:
                seen.add(profile)
                profiles.append(profile)
    return profiles


def _build_legacy_foundry_profile():
    api_key = _normalize_api_key(_read_env_var("AZURE_AI_FOUNDRY_API_KEY"))
    endpoint = _read_env_var("AZURE_AI_FOUNDRY_ENDPOINT")
    api_version = _read_env_var("AZURE_AI_FOUNDRY_API_VERSION") or DEFAULT_AZURE_AI_FOUNDRY_API_VERSION
    raw_models = _read_env_var("AZURE_AI_FOUNDRY_MODEL_NAME")
    model_names = [model.strip() for model in raw_models.split(",") if model.strip()]
    if not any([api_key, endpoint, model_names]):
        return None
    return {
        "profile": FOUNDRY_DEFAULT_PROFILE,
        "api_key": api_key,
        "endpoint": endpoint,
        "api_version": api_version,
        "model_names": model_names,
        "vendor": DEFAULT_FOUNDRY_VENDOR,
        "vendor_label": "Azure",
        "display_names": list(model_names),
    }


def _build_profile_entry(profile):
    profile_upper = profile.upper()
    api_key = _normalize_api_key(_read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_API_KEY"))
    endpoint = _read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_ENDPOINT")
    api_version = (
        _read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_API_VERSION")
        or DEFAULT_AZURE_AI_FOUNDRY_API_VERSION
    ).strip()
    raw_models = _read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_MODEL_NAME")
    model_names = [model.strip() for model in raw_models.split(",") if model.strip()]
    raw_display_names = _read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_DISPLAY_NAME")
    parsed_display_names = [name.strip() for name in raw_display_names.split(",") if name.strip()]
    display_names = [
        parsed_display_names[idx] if idx < len(parsed_display_names) else model_name
        for idx, model_name in enumerate(model_names)
    ]
    vendor_label = _read_env_var(f"AZURE_AI_FOUNDRY_{profile_upper}_VENDOR") or "Azure"
    vendor_id = normalize_vendor_id(vendor_label)
    if not api_key or not endpoint or not model_names:
        return None
    return {
        "profile": profile,
        "api_key": api_key,
        "endpoint": endpoint,
        "api_version": api_version,
        "model_names": model_names,
        "display_names": display_names,
        "vendor": vendor_id,
        "vendor_label": vendor_label,
    }


def parse_foundry_model_value(value):
    """Return (profile, model_name) when encoded as profile::model; else (None, raw)."""
    raw = (value or "").strip()
    if not raw:
        return None, ""
    if FOUNDRY_MODEL_DELIMITER not in raw:
        return None, raw
    profile, model_name = raw.split(FOUNDRY_MODEL_DELIMITER, 1)
    return _normalize_profile_id(profile), model_name.strip()


def encode_foundry_model_value(profile, model_name):
    """Encode a Foundry model selector value for UI and config transport."""
    return f"{profile}{FOUNDRY_MODEL_DELIMITER}{model_name}" if profile else model_name


def resolve_model_for_request(provider, configured_model, config):
    """Resolve the concrete model name to pass to the LLM API."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        settings = get_azure_ai_foundry_settings(config)
        selected_profile, selected_model = parse_foundry_model_value(configured_model)
        if selected_model:
            selected_entry = None
            if selected_profile:
                selected_entry = next(
                    (entry for entry in settings.get("entries", []) if entry.get("profile") == selected_profile),
                    None,
                )
            if selected_entry is None and settings.get("entries"):
                selected_entry = settings["entries"][0]
            deployment_name = _extract_azure_deployment_from_endpoint(
                selected_entry.get("endpoint", "") if selected_entry else ""
            )
            if deployment_name:
                return deployment_name
            return selected_model
        if selected_profile and settings.get("entries"):
            for entry in settings["entries"]:
                if entry["profile"] == selected_profile and entry["model_names"]:
                    deployment_name = _extract_azure_deployment_from_endpoint(entry.get("endpoint", ""))
                    if deployment_name:
                        return deployment_name
                    return entry["model_names"][0]
        deployment_name = _extract_azure_deployment_from_endpoint(settings.get("endpoint", ""))
        if deployment_name:
            return deployment_name
        return settings.get("model_name", "")
    return (configured_model or "").strip()


def get_azure_ai_foundry_settings(config):
    """Load Azure AI Foundry settings from environment variables, including multi-profile entries."""
    requested_provider = normalize_provider(config.get("llm_provider", ""))
    requested_vendor = vendor_from_provider_key(config.get("llm_provider", ""))
    requested_profile, requested_model = parse_foundry_model_value(config.get("llm_model", ""))

    configured_profiles = _parse_profile_ids()
    entries = []
    for profile in configured_profiles:
        entry = _build_profile_entry(profile)
        if entry:
            entries.append(entry)

    legacy_entry = _build_legacy_foundry_profile()
    # When explicit profiles are configured, do not append legacy single-profile entry
    # to avoid duplicate model options in UI dropdowns.
    if legacy_entry and not configured_profiles:
        entries.append(legacy_entry)

    filtered_entries = [
        entry for entry in entries if not requested_vendor or entry.get("vendor") == normalize_vendor_id(requested_vendor)
    ]
    if not filtered_entries and requested_vendor:
        filtered_entries = entries

    selected_entry = None
    selected_model = ""

    if requested_provider == AZURE_AI_FOUNDRY_PROVIDER:
        if requested_profile:
            selected_entry = next((entry for entry in filtered_entries if entry["profile"] == requested_profile), None)
            if selected_entry and requested_model in selected_entry["model_names"]:
                selected_model = requested_model
        if selected_entry is None and requested_model:
            for entry in filtered_entries:
                if requested_model in entry["model_names"]:
                    selected_entry = entry
                    selected_model = requested_model
                    break

    if selected_entry is None and filtered_entries:
        selected_entry = filtered_entries[0]
    if selected_entry and not selected_model:
        selected_model = selected_entry["model_names"][0] if selected_entry["model_names"] else ""

    model_options = []
    for entry in filtered_entries:
        provider_key = provider_key_for_vendor(entry.get("vendor"))
        provider_label = provider_label_for_vendor(entry.get("vendor_label"), entry.get("vendor"))
        for index, model_name in enumerate(entry["model_names"]):
            display_name = entry.get("display_names", [])[index] if index < len(entry.get("display_names", [])) else model_name
            label_suffix = "" if entry["profile"] == FOUNDRY_DEFAULT_PROFILE else f" [{entry['profile']}]"
            model_options.append(
                {
                    "value": encode_foundry_model_value(entry["profile"], model_name),
                    "model_name": model_name,
                    "display_name": display_name,
                    "profile": entry["profile"],
                    "vendor": entry.get("vendor", DEFAULT_FOUNDRY_VENDOR),
                    "vendor_label": entry.get("vendor_label", "Azure"),
                    "provider_key": provider_key,
                    "provider_label": provider_label,
                    "label": f"{display_name}{label_suffix}",
                }
            )

    return {
        "api_key": selected_entry["api_key"] if selected_entry else "",
        "endpoint": selected_entry["endpoint"] if selected_entry else "",
        "api_version": selected_entry["api_version"] if selected_entry else DEFAULT_AZURE_AI_FOUNDRY_API_VERSION,
        "profile": selected_entry["profile"] if selected_entry else "",
        "model_name": selected_model,
        "model_names": selected_entry["model_names"] if selected_entry else [],
        "model_options": model_options,
        "entries": filtered_entries,
        "selected_value": encode_foundry_model_value(selected_entry["profile"], selected_model)
        if selected_entry and selected_model
        else "",
    }


def get_foundry_provider_catalog(config):
    """Return provider buckets for configured Foundry vendors."""
    settings = get_azure_ai_foundry_settings({**config, "llm_provider": ""})
    catalog = {}
    for item in settings.get("model_options", []):
        provider_key = item.get("provider_key") or AZURE_AI_FOUNDRY_PROVIDER
        bucket = catalog.setdefault(
            provider_key,
            {
                "key": provider_key,
                "label": item.get("provider_label") or "Azure AI Foundry",
                "models": [],
            },
        )
        bucket["models"].append(item)
    return catalog


def _normalize_azure_endpoint(endpoint):
    """Normalize an Azure endpoint to scheme+host only.

    Accepts both plain base URLs and full Azure portal endpoint strings that include
    deployment paths and query strings, e.g.:
      https://my-resource.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=...
      https://my-resource.services.ai.azure.com/models/chat/completions?api-version=...
    All such paths are stripped so only the base URL is returned.
    """
    value = (endpoint or "").strip()
    # Drop query string
    if "?" in value:
        value = value[: value.index("?")]
    value = value.rstrip("/")
    # Strip known Azure API path prefixes (leftmost match wins)
    for prefix in ("/openai/deployments", "/openai/v1", "/openai", "/models"):
        idx = value.lower().find(prefix)
        if idx != -1:
            value = value[:idx]
            break
    return value.rstrip("/")


def _normalize_ai_services_openai_base(endpoint):
    """Normalize an Azure AI Services endpoint to its OpenAI-compatible /openai/v1 base."""
    value = (endpoint or "").strip()
    if "?" in value:
        value = value[: value.index("?")]
    value = value.rstrip("/")
    lower_value = value.lower()
    marker = "/openai/v1"
    if marker in lower_value:
        idx = lower_value.find(marker)
        return value[: idx + len(marker)]
    return _normalize_azure_endpoint(value) + marker


def _extract_azure_deployment_from_endpoint(endpoint):
    """Extract deployment name from full Azure OpenAI endpoint paths when present."""
    value = (endpoint or "").strip()
    if not value:
        return ""
    marker = "/openai/deployments/"
    lower_value = value.lower()
    start = lower_value.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    rest = value[start:]
    if not rest:
        return ""
    # First segment after the deployments marker is the deployment name.
    return rest.split("/", 1)[0].split("?", 1)[0].strip()


def _is_ai_services_endpoint(endpoint):
    """Return True if the endpoint is an Azure AI Services (serverless) endpoint.

    Azure AI Foundry serverless endpoints use the `services.ai.azure.com` domain and
    expose a /models inference path rather than the Azure OpenAI /openai/deployments path.
    """
    host = (endpoint or "").strip().lower().split("/")[2] if "//" in (endpoint or "") else ""
    return host.endswith("services.ai.azure.com")


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
    if normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["model_name"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_MODEL_NAME environment variable.")
        if not foundry_settings["api_key"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_API_KEY environment variable.")
        if not foundry_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_ENDPOINT environment variable.")
    elif normalized_provider == LM_STUDIO_PROVIDER and not config.get("llm_model", "").strip():
        raise RuntimeError("Missing LM Studio model selection. Choose a model from the wizard.")


def create_client(provider, config):
    """Create an LLM client for the selected provider."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        foundry_settings = get_azure_ai_foundry_settings(config)
        if not foundry_settings["api_key"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_API_KEY environment variable.")
        if not foundry_settings["endpoint"]:
            raise RuntimeError("Missing AZURE_AI_FOUNDRY_ENDPOINT environment variable.")

        if _is_ai_services_endpoint(foundry_settings["endpoint"]):
            # Azure AI Services (serverless) endpoints use the OpenAI-compatible /openai/v1 path.
            return OpenAI(
                api_key=foundry_settings["api_key"],
                base_url=_normalize_ai_services_openai_base(foundry_settings["endpoint"]),
            )

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
    if normalized_provider == AZURE_AI_FOUNDRY_PROVIDER:
        profile, resolved_model = parse_foundry_model_value(model_name)
        provider_vendor = vendor_from_provider_key(provider)
        provider_label = provider_label_for_vendor(provider_vendor.capitalize(), provider_vendor) if provider_vendor else "Azure AI Foundry"
        if profile and resolved_model:
            model_name = f"{resolved_model} [{profile}]"
    elif normalized_provider == LM_STUDIO_PROVIDER:
        provider_label = "LM Studio"
    else:
        provider_label = "Ollama"
    return f"{model_name} ({provider_label})"
