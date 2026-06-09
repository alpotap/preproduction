"""YAML-backed runtime/model catalog configuration helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from toolkit.providers import (
    AZURE_AI_FOUNDRY_PROVIDER,
    LM_STUDIO_PROVIDER,
    OLLAMA_PROVIDER,
    fetch_lm_studio_models,
    fetch_ollama_models,
    get_foundry_provider_catalog,
)
from toolkit.utils import WORKSPACE_ROOT, load_config

CONFIG_YAML_PATH = WORKSPACE_ROOT / "config.yaml"

DEFAULT_CONFIG_YAML: dict = {
    "version": 1,
    "llm": {
        "active_provider": AZURE_AI_FOUNDRY_PROVIDER,
        "active_model_id": "primary",
        "providers": {
            OLLAMA_PROVIDER: {
                "refresh_models_on_startup": False,
                "models": [],
            },
            LM_STUDIO_PROVIDER: {
                "refresh_models_on_startup": False,
                "models": [],
            },
            AZURE_AI_FOUNDRY_PROVIDER: {
                "refresh_models_on_startup": False,
                "models": [],
            },
        }
    },
    "runtime": {
        "llm": {
            "max_passes": 1,
            "max_concurrent_requests": 3,
        },
        "files": {
            "max_parallel_files": 1,
        },
    },
}


def _normalize_provider_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in {OLLAMA_PROVIDER, LM_STUDIO_PROVIDER, AZURE_AI_FOUNDRY_PROVIDER}:
        return raw
    return ""


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _sanitize_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _sanitize_provider_models(models: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id", "")).strip()
        if not model_id:
            continue
        display_name = str(model.get("display_name", model_id)).strip() or model_id
        role = str(model.get("role", "secondary")).strip() or "secondary"
        enabled = bool(model.get("enabled", True))
        sanitized.append(
            {
                "id": model_id,
                "display_name": display_name,
                "role": role,
                "enabled": enabled,
            }
        )
    return sanitized


def _sanitize_config_yaml(payload: dict) -> dict:
    merged = _deep_merge(DEFAULT_CONFIG_YAML, payload if isinstance(payload, dict) else {})
    merged["version"] = _sanitize_int(merged.get("version", 1), default=1, minimum=1, maximum=999)

    llm_section = merged.setdefault("llm", {})
    providers = llm_section.setdefault("providers", {})
    for provider_key in (OLLAMA_PROVIDER, LM_STUDIO_PROVIDER, AZURE_AI_FOUNDRY_PROVIDER):
        bucket = providers.setdefault(provider_key, {"refresh_models_on_startup": False, "models": []})
        bucket["refresh_models_on_startup"] = bool(bucket.get("refresh_models_on_startup", False))
        bucket["models"] = _sanitize_provider_models(bucket.get("models", []))

    requested_provider = _normalize_provider_key(llm_section.get("active_provider", ""))
    requested_model_id = str(llm_section.get("active_model_id", "")).strip()
    selected_provider, selected_model_id = _resolve_explicit_or_fallback_active_selection(
        providers,
        requested_provider,
        requested_model_id,
    )
    llm_section["active_provider"] = selected_provider
    llm_section["active_model_id"] = selected_model_id

    runtime = merged.setdefault("runtime", {})
    llm_runtime = runtime.setdefault("llm", {})
    files_runtime = runtime.setdefault("files", {})
    llm_runtime["max_passes"] = _sanitize_int(llm_runtime.get("max_passes", 1), default=1, minimum=1, maximum=5)
    llm_runtime["max_concurrent_requests"] = _sanitize_int(
        llm_runtime.get("max_concurrent_requests", 3),
        default=3,
        minimum=1,
        maximum=20,
    )
    files_runtime["max_parallel_files"] = _sanitize_int(
        files_runtime.get("max_parallel_files", 1),
        default=1,
        minimum=1,
        maximum=8,
    )
    return merged


def save_runtime_yaml(config_yaml: dict) -> dict:
    sanitized = _sanitize_config_yaml(config_yaml)
    CONFIG_YAML_PATH.write_text(
        yaml.safe_dump(sanitized, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return sanitized


def load_runtime_yaml() -> dict:
    if not CONFIG_YAML_PATH.exists():
        return save_runtime_yaml(DEFAULT_CONFIG_YAML)
    try:
        parsed = yaml.safe_load(CONFIG_YAML_PATH.read_text(encoding="utf-8"))
    except Exception:
        return save_runtime_yaml(DEFAULT_CONFIG_YAML)
    return save_runtime_yaml(parsed or {})


def ensure_runtime_yaml_exists() -> dict:
    return load_runtime_yaml()


def _build_catalog_model(model_id: str, display_name: str, role: str = "secondary") -> dict:
    return {
        "id": model_id,
        "display_name": display_name,
        "role": role,
        "enabled": True,
    }


def _enabled_models(models: list[dict]) -> list[dict]:
    return [entry for entry in models if bool(entry.get("enabled", True))]


def scan_and_save_model_catalog(base_config: dict | None = None) -> dict:
    config = dict(base_config or load_config() or {})
    current = load_runtime_yaml()

    ollama_models = fetch_ollama_models()
    lm_studio_models = fetch_lm_studio_models(config)
    foundry_catalog = get_foundry_provider_catalog(config)

    current["llm"]["providers"][OLLAMA_PROVIDER]["models"] = [
        _build_catalog_model(model_id, model_id, role="primary" if idx == 0 else "secondary")
        for idx, model_id in enumerate(ollama_models)
    ]

    current["llm"]["providers"][LM_STUDIO_PROVIDER]["models"] = [
        _build_catalog_model(model_id, model_id, role="primary" if idx == 0 else "secondary")
        for idx, model_id in enumerate(lm_studio_models)
    ]

    foundry_models: list[dict] = []
    for bucket in foundry_catalog.values():
        for idx, model in enumerate(bucket.get("models", [])):
            model_value = str(model.get("value", "")).strip()
            if not model_value:
                continue
            display_name = str(model.get("label", model_value)).strip() or model_value
            foundry_models.append(
                _build_catalog_model(
                    model_value,
                    display_name,
                    role="primary" if idx == 0 and not foundry_models else "secondary",
                )
            )

    # De-duplicate by ID while preserving order.
    seen: set[str] = set()
    deduped_foundry: list[dict] = []
    for item in foundry_models:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped_foundry.append(item)

    current["llm"]["providers"][AZURE_AI_FOUNDRY_PROVIDER]["models"] = deduped_foundry

    providers = current.get("llm", {}).get("providers", {})
    requested_provider = _normalize_provider_key(current.get("llm", {}).get("active_provider", ""))
    requested_model_id = str(current.get("llm", {}).get("active_model_id", "")).strip()
    selected_provider, selected_model_id = _resolve_explicit_or_fallback_active_selection(
        providers,
        requested_provider,
        requested_model_id,
    )
    current["llm"]["active_provider"] = selected_provider
    current["llm"]["active_model_id"] = selected_model_id

    saved = save_runtime_yaml(current)

    return {
        "config": saved,
        "counts": {
            OLLAMA_PROVIDER: len(saved["llm"]["providers"][OLLAMA_PROVIDER]["models"]),
            LM_STUDIO_PROVIDER: len(saved["llm"]["providers"][LM_STUDIO_PROVIDER]["models"]),
            AZURE_AI_FOUNDRY_PROVIDER: len(saved["llm"]["providers"][AZURE_AI_FOUNDRY_PROVIDER]["models"]),
        },
    }


def _pick_primary_model(models: list[dict]) -> str:
    enabled = [entry for entry in models if entry.get("enabled", True)]
    if not enabled:
        return ""
    primaries = [entry for entry in enabled if str(entry.get("role", "")).lower() == "primary"]
    selected = primaries[0] if primaries else enabled[0]
    return str(selected.get("id", "")).strip()


def _resolve_explicit_or_fallback_active_selection(
    providers: dict,
    requested_provider: str,
    requested_model_id: str,
) -> tuple[str, str]:
    if requested_provider:
        requested_models = providers.get(requested_provider, {}).get("models", [])
        enabled_ids = {str(item.get("id", "")).strip() for item in _enabled_models(requested_models)}
        if requested_model_id and requested_model_id in enabled_ids:
            return requested_provider, requested_model_id

    provider_order = [AZURE_AI_FOUNDRY_PROVIDER, OLLAMA_PROVIDER, LM_STUDIO_PROVIDER]
    for provider_key in provider_order:
        models = providers.get(provider_key, {}).get("models", [])
        chosen_model = _pick_primary_model(models)
        if chosen_model:
            return provider_key, chosen_model

    return "", ""


def apply_runtime_yaml_overrides(config: dict, runtime_yaml: dict | None = None) -> dict:
    merged = dict(config or {})
    payload = runtime_yaml or load_runtime_yaml()

    runtime = payload.get("runtime", {}) if isinstance(payload, dict) else {}
    llm_runtime = runtime.get("llm", {}) if isinstance(runtime, dict) else {}
    files_runtime = runtime.get("files", {}) if isinstance(runtime, dict) else {}

    merged["llm_max_passes"] = _sanitize_int(llm_runtime.get("max_passes", merged.get("llm_max_passes", 1)), 1, 1, 5)
    merged["llm_max_concurrent_requests"] = _sanitize_int(
        llm_runtime.get("max_concurrent_requests", merged.get("llm_max_concurrent_requests", 3)),
        3,
        1,
        20,
    )
    merged["llm_max_parallel_files"] = _sanitize_int(
        files_runtime.get("max_parallel_files", merged.get("llm_max_parallel_files", 1)),
        1,
        1,
        8,
    )

    llm_section = payload.get("llm", {}) if isinstance(payload, dict) else {}
    selected_provider = _normalize_provider_key(llm_section.get("active_provider", ""))
    selected_model = str(llm_section.get("active_model_id", "")).strip()

    if selected_provider:
        merged["llm_provider"] = selected_provider
    if selected_provider and selected_model:
        merged["llm_model"] = selected_model
        if selected_provider == LM_STUDIO_PROVIDER:
            merged["lm_studio_model_name"] = selected_model

    return merged


def get_yaml_providers_and_models(runtime_yaml: dict | None = None) -> tuple[list[dict], dict[str, list[dict]]]:
    payload = runtime_yaml or load_runtime_yaml()
    providers_yaml = payload.get("llm", {}).get("providers", {}) if isinstance(payload, dict) else {}

    provider_labels = {
        OLLAMA_PROVIDER: "Ollama",
        LM_STUDIO_PROVIDER: "LM Studio",
        AZURE_AI_FOUNDRY_PROVIDER: "Azure AI Foundry",
    }

    provider_models: dict[str, list[dict]] = {}
    providers: list[dict] = []
    for key in (OLLAMA_PROVIDER, LM_STUDIO_PROVIDER, AZURE_AI_FOUNDRY_PROVIDER):
        raw_models = providers_yaml.get(key, {}).get("models", []) if isinstance(providers_yaml, dict) else []
        models = [
            {
                "value": str(model.get("id", "")).strip(),
                "label": str(model.get("display_name", model.get("id", "")).strip() or model.get("id", "")).strip(),
                "role": str(model.get("role", "secondary")),
                "enabled": bool(model.get("enabled", True)),
            }
            for model in raw_models
            if isinstance(model, dict) and str(model.get("id", "")).strip()
        ]
        models = [m for m in models if m["enabled"]]
        provider_models[key] = models
        if models:
            providers.append({"key": key, "label": provider_labels[key]})

    return providers, provider_models
