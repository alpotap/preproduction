#!/usr/bin/env python3
"""Interactive Azure AI Foundry environment setup for Windows.

Provides a menu to list, add, edit, remove, and test model configurations.
By default, values are stored in both HKCU\\Environment (USER scope) and
HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\Environment
(MACHINE scope) for consistent multi-user behavior.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from getpass import getpass

from toolkit.runtime_yaml import scan_and_save_model_catalog


DEFAULT_API_VERSION = "2025-01-01-preview"
PROFILE_IDS_VAR = "AZURE_AI_FOUNDRY_PROFILE_IDS"
PROFILE_SUFFIXES = (
    "API_KEY",
    "ENDPOINT",
    "API_VERSION",
    "MODEL_NAME",
    "DISPLAY_NAME",
    "VENDOR",
)
ENV_SCOPE_USER = "user"
ENV_SCOPE_MACHINE = "machine"
ENV_SCOPE_BOTH = "both"


def _read_registry_env(name: str, root: int, subkey: str) -> str:
    try:
        import winreg

        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip()
    except Exception:
        return ""


def get_env_value(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    if os.name != "nt":
        return ""
    import winreg

    user_value = _read_registry_env(name, root=winreg.HKEY_CURRENT_USER, subkey=r"Environment")
    if user_value:
        return user_value
    machine_value = _read_registry_env(
        name,
        root=winreg.HKEY_LOCAL_MACHINE,
        subkey=r"System\CurrentControlSet\Control\Session Manager\Environment",
    )
    if machine_value:
        return machine_value
    return ""


def get_profile_ids() -> list[str]:
    """Merge profile IDs from process, USER, and MACHINE sources."""
    raw_values: list[str] = []
    process_value = (os.getenv(PROFILE_IDS_VAR) or "").strip()
    if process_value:
        raw_values.append(process_value)

    if os.name == "nt":
        import winreg

        user_value = _read_registry_env(PROFILE_IDS_VAR, winreg.HKEY_CURRENT_USER, r"Environment")
        if user_value:
            raw_values.append(user_value)
        machine_value = _read_registry_env(
            PROFILE_IDS_VAR,
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
        )
        if machine_value:
            raw_values.append(machine_value)

    merged: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for item in raw.split(","):
            profile = normalize_profile_id(item)
            if profile and profile not in seen:
                seen.add(profile)
                merged.append(profile)
    return merged


def normalize_profile_id(name: str) -> str:
    candidate = re.sub(r"[^a-z0-9_]", "_", (name or "").strip().lower()).strip("_")
    return candidate or "profile"


def _set_registry_env(name: str, value: str, scope: str) -> None:
    if os.name != "nt":
        return
    import winreg

    if scope == ENV_SCOPE_USER:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
        return

    if scope == ENV_SCOPE_MACHINE:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
        return

    raise ValueError(f"Unsupported scope: {scope}")


def set_scoped_and_process_env(name: str, value: str, scope: str) -> None:
    """Set env var in current process and requested persistent scope(s)."""
    os.environ[name] = value
    if os.name != "nt":
        return

    try:
        if scope == ENV_SCOPE_BOTH:
            _set_registry_env(name, value, ENV_SCOPE_USER)
            _set_registry_env(name, value, ENV_SCOPE_MACHINE)
        else:
            _set_registry_env(name, value, scope)
    except PermissionError:
        target = "MACHINE" if scope in {ENV_SCOPE_MACHINE, ENV_SCOPE_BOTH} else "USER"
        raise RuntimeError(
            f"Failed to write {target} environment variable '{name}': "
            "Administrator privileges are required for MACHINE scope. "
            "Either run as Administrator, or rerun with --scope user."
        )
    except Exception as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"Failed to write scoped environment variable '{name}': {exc}") from exc


def _delete_registry_env(name: str, scope: str) -> None:
    import winreg

    if scope == ENV_SCOPE_USER:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        return

    if scope == ENV_SCOPE_MACHINE:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        return

    raise ValueError(f"Unsupported scope: {scope}")


def delete_scoped_and_process_env(name: str, scope: str) -> None:
    os.environ.pop(name, None)
    if os.name != "nt":
        return
    try:
        if scope == ENV_SCOPE_BOTH:
            _delete_registry_env(name, ENV_SCOPE_USER)
            _delete_registry_env(name, ENV_SCOPE_MACHINE)
        else:
            _delete_registry_env(name, scope)
    except PermissionError:
        target = "MACHINE" if scope in {ENV_SCOPE_MACHINE, ENV_SCOPE_BOTH} else "USER"
        raise RuntimeError(
            f"Failed to remove {target} environment variable '{name}': "
            "Administrator privileges are required for MACHINE scope. "
            "Either run as Administrator, or rerun with --scope user."
        )
    except Exception as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"Failed to remove scoped environment variable '{name}': {exc}") from exc


def _contains_non_ascii(value: str) -> bool:
    return any(ord(ch) > 127 for ch in value)


def prompt_non_empty(prompt: str, *, secret: bool = False) -> str:
    while True:
        value = (getpass(prompt + ": ") if secret else input(prompt + ": ")).strip()
        if value:
            return value
        print("Value is required.")


def prompt_with_default(prompt: str, default: str, *, secret: bool = False, allow_empty: bool = False) -> str:
    while True:
        if secret:
            value = getpass(prompt + ": ").strip()
        else:
            label = f"{prompt} [{default}]" if default else prompt
            value = input(label + ": ").strip()
        if value:
            return value
        if allow_empty:
            return ""
        if default:
            return default
        print("Value is required.")


def normalize_api_key(value: str) -> str:
    return (value or "").strip().strip("`\"'")


def mask_secret(value: str) -> str:
    raw = normalize_api_key(value)
    if not raw:
        return ""
    if len(raw) == 1:
        return raw
    if len(raw) == 2:
        return raw[0] + "*"
    return raw[0] + ("*" * (len(raw) - 2)) + raw[-1]


def load_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    profile_ids = get_profile_ids()

    for profile in profile_ids:
        up = profile.upper()
        model_name = get_env_value(f"AZURE_AI_FOUNDRY_{up}_MODEL_NAME")
        api_key = normalize_api_key(get_env_value(f"AZURE_AI_FOUNDRY_{up}_API_KEY"))
        endpoint = get_env_value(f"AZURE_AI_FOUNDRY_{up}_ENDPOINT")
        if not model_name or not api_key or not endpoint:
            continue
        entries.append(
            {
                "profile": profile,
                "display_name": get_env_value(f"AZURE_AI_FOUNDRY_{up}_DISPLAY_NAME") or model_name,
                "model_name": model_name,
                "api_key": api_key,
                "endpoint": endpoint,
                "api_version": get_env_value(f"AZURE_AI_FOUNDRY_{up}_API_VERSION") or DEFAULT_API_VERSION,
                "vendor": get_env_value(f"AZURE_AI_FOUNDRY_{up}_VENDOR") or "Azure",
            }
        )

    if entries:
        return entries

    # Backward-compatible bootstrap from legacy single-profile variables.
    model_name = get_env_value("AZURE_AI_FOUNDRY_MODEL_NAME")
    api_key = normalize_api_key(get_env_value("AZURE_AI_FOUNDRY_API_KEY"))
    endpoint = get_env_value("AZURE_AI_FOUNDRY_ENDPOINT")
    if model_name and api_key and endpoint:
        entries.append(
            {
                "profile": "default",
                "display_name": model_name,
                "model_name": model_name,
                "api_key": api_key,
                "endpoint": endpoint,
                "api_version": get_env_value("AZURE_AI_FOUNDRY_API_VERSION") or DEFAULT_API_VERSION,
                "vendor": "Azure",
            }
        )
    return entries


def print_entries(entries: list[dict[str, str]]) -> None:
    print("")
    print("Current model setups:")
    if not entries:
        print("  (none configured)")
        return
    for idx, item in enumerate(entries, start=1):
        print(
            f"  {idx}. vendor='{item['vendor']}', display='{item['display_name']}', "
            f"model='{item['model_name']}', profile='{item['profile']}', "
            f"key='{mask_secret(item['api_key'])}', endpoint='{item['endpoint']}', "
            f"apiVersion='{item['api_version']}'"
        )


def pick_entry_index(entries: list[dict[str, str]], action: str) -> int:
    if not entries:
        print("No models configured yet.")
        return -1
    print_entries(entries)
    while True:
        raw = input(f"Select model number to {action} (or Enter to cancel): ").strip()
        if not raw:
            return -1
        try:
            idx = int(raw) - 1
        except ValueError:
            print("Please enter a valid number.")
            continue
        if 0 <= idx < len(entries):
            return idx
        print("Selection out of range.")


def ensure_unique_profile(entries: list[dict[str, str]], desired: str, *, excluding: str = "") -> str:
    existing = {entry["profile"] for entry in entries if entry["profile"] != excluding}
    profile = normalize_profile_id(desired)
    suffix = 2
    base = profile
    while profile in existing:
        profile = f"{base}_{suffix}"
        suffix += 1
    return profile


def add_entry(entries: list[dict[str, str]]) -> None:
    print("")
    print("Add model")
    display_name = prompt_non_empty("Display name (shown in list and dropdowns)")
    model_name = prompt_non_empty("Model/deployment name (actual API model)")
    api_key = normalize_api_key(prompt_non_empty("API key", secret=True))
    if _contains_non_ascii(api_key):
        raise ValueError("API key contains non-ASCII characters. Paste the raw key from Azure portal.")
    if any(ch.isspace() for ch in api_key):
        raise ValueError("API key contains whitespace. Paste key without spaces/newlines.")
    endpoint = prompt_non_empty("Endpoint (example: https://your-resource.cognitiveservices.azure.com/)")
    api_version = prompt_with_default("API version", DEFAULT_API_VERSION)
    vendor = prompt_with_default("Vendor category", "Azure")

    profile = ensure_unique_profile(entries, display_name)
    entries.append(
        {
            "profile": profile,
            "display_name": display_name,
            "model_name": model_name,
            "api_key": api_key,
            "endpoint": endpoint,
            "api_version": api_version,
            "vendor": vendor,
        }
    )
    print(f"Added model as profile '{profile}'.")


def _normalize_azure_endpoint(endpoint: str) -> str:
    value = (endpoint or "").strip()
    if "?" in value:
        value = value[: value.index("?")]
    value = value.rstrip("/")
    for prefix in ("/openai/deployments", "/openai/v1", "/openai", "/models"):
        idx = value.lower().find(prefix)
        if idx != -1:
            value = value[:idx]
            break
    return value.rstrip("/")


def _normalize_ai_services_openai_base(endpoint: str) -> str:
    value = (endpoint or "").strip()
    if "?" in value:
        value = value[: value.index("?")]
    value = value.rstrip("/")
    if "/openai/v1" in value.lower():
        idx = value.lower().find("/openai/v1")
        return value[: idx + len("/openai/v1")]
    return _normalize_azure_endpoint(value) + "/openai/v1"


def _is_ai_services_endpoint(endpoint: str) -> bool:
    host = (endpoint or "").strip().lower().split("/")[2] if "//" in (endpoint or "") else ""
    return host.endswith("services.ai.azure.com")


def _extract_azure_deployment_from_endpoint(endpoint: str) -> str:
    """Extract deployment name from Azure OpenAI endpoint paths when present."""
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
    return rest.split("/", 1)[0].split("?", 1)[0].strip()


def _is_max_tokens_unsupported_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "unsupported parameter" in message
        and "max_tokens" in message
        and "max_completion_tokens" in message
    )


def test_entry(entry: dict[str, str]) -> None:
    print("")
    print(f"Testing '{entry['display_name']}'...")
    try:
        from openai import OpenAI, AzureOpenAI
    except Exception as exc:
        print(f"Cannot import openai package: {exc}")
        print("Install dependencies first (example: py -m pip install -r requirements.txt).")
        return

    base_endpoint = _normalize_azure_endpoint(entry["endpoint"])
    try:
        request_model = entry["model_name"]
        if _is_ai_services_endpoint(entry["endpoint"]):
            client = OpenAI(
                api_key=normalize_api_key(entry["api_key"]),
                base_url=_normalize_ai_services_openai_base(entry["endpoint"]),
            )
        else:
            # For Azure OpenAI endpoints that include a deployment path,
            # the deployment name is the effective model identifier.
            request_model = _extract_azure_deployment_from_endpoint(entry["endpoint"]) or entry["model_name"]
            client = AzureOpenAI(
                api_key=normalize_api_key(entry["api_key"]),
                azure_endpoint=base_endpoint,
                api_version=entry["api_version"],
            )

        try:
            response = client.chat.completions.create(
                model=request_model,
                messages=[{"role": "user", "content": "Reply with: OK"}],
                max_tokens=10,
            )
        except Exception as exc:
            if not _is_max_tokens_unsupported_error(exc):
                raise
            response = client.chat.completions.create(
                model=request_model,
                messages=[{"role": "user", "content": "Reply with: OK"}],
                max_completion_tokens=10,
            )
        content = ""
        if response.choices:
            content = (response.choices[0].message.content or "").strip()
        print(f"Test succeeded. Response: {content or '(empty)'}")
    except Exception as exc:
        print(f"Test failed: {exc}")


def edit_entry(entries: list[dict[str, str]]) -> None:
    idx = pick_entry_index(entries, "edit")
    if idx < 0:
        return
    entry = entries[idx]

    while True:
        print("")
        print(f"Editing '{entry['display_name']}' (profile: {entry['profile']})")
        print("  1. Display name (list/dropdown label)")
        print("  2. Model/deployment name (API model)")
        print("  3. Vendor category")
        print("  4. API key")
        print("  5. Endpoint")
        print("  6. API version")
        print("  7. Test model")
        print("  8. Back")
        choice = input("Choose action (1-8): ").strip()

        if choice == "1":
            entry["display_name"] = prompt_with_default("Display name", entry["display_name"])
        elif choice == "2":
            entry["model_name"] = prompt_with_default("Model/deployment name", entry["model_name"])
        elif choice == "3":
            entry["vendor"] = prompt_with_default("Vendor category", entry["vendor"] or "Azure")
        elif choice == "4":
            new_key = prompt_with_default("API key (leave blank to keep current)", "", secret=True, allow_empty=True)
            if new_key:
                if _contains_non_ascii(new_key):
                    raise ValueError("API key contains non-ASCII characters. Paste the raw key from Azure portal.")
                if any(ch.isspace() for ch in new_key):
                    raise ValueError("API key contains whitespace. Paste key without spaces/newlines.")
                entry["api_key"] = new_key
        elif choice == "5":
            entry["endpoint"] = prompt_with_default("Endpoint", entry["endpoint"])
        elif choice == "6":
            entry["api_version"] = prompt_with_default("API version", entry["api_version"])
        elif choice == "7":
            test_entry(entry)
        elif choice == "8":
            return
        else:
            print("Invalid selection.")


def remove_entry(entries: list[dict[str, str]]) -> None:
    idx = pick_entry_index(entries, "remove")
    if idx < 0:
        return
    removed = entries.pop(idx)
    print(f"Removed '{removed['display_name']}'.")


def save_entries(entries: list[dict[str, str]], scope: str) -> None:
    existing_profiles = get_profile_ids()
    current_profiles = [entry["profile"] for entry in entries]

    set_scoped_and_process_env(PROFILE_IDS_VAR, ",".join(current_profiles), scope)

    for entry in entries:
        up = entry["profile"].upper()
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_API_KEY", entry["api_key"], scope)
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_ENDPOINT", entry["endpoint"], scope)
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_API_VERSION", entry["api_version"], scope)
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_MODEL_NAME", entry["model_name"], scope)
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_DISPLAY_NAME", entry["display_name"], scope)
        set_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_VENDOR", entry["vendor"], scope)

    removed_profiles = [profile for profile in existing_profiles if profile not in current_profiles]
    for profile in removed_profiles:
        up = profile.upper()
        for suffix in PROFILE_SUFFIXES:
            delete_scoped_and_process_env(f"AZURE_AI_FOUNDRY_{up}_{suffix}", scope)

    if entries:
        first = entries[0]
        set_scoped_and_process_env("AZURE_AI_FOUNDRY_API_KEY", first["api_key"], scope)
        set_scoped_and_process_env("AZURE_AI_FOUNDRY_ENDPOINT", first["endpoint"], scope)
        set_scoped_and_process_env("AZURE_AI_FOUNDRY_API_VERSION", first["api_version"], scope)
        set_scoped_and_process_env("AZURE_AI_FOUNDRY_MODEL_NAME", first["model_name"], scope)
    else:
        delete_scoped_and_process_env("AZURE_AI_FOUNDRY_API_KEY", scope)
        delete_scoped_and_process_env("AZURE_AI_FOUNDRY_ENDPOINT", scope)
        delete_scoped_and_process_env("AZURE_AI_FOUNDRY_API_VERSION", scope)
        delete_scoped_and_process_env("AZURE_AI_FOUNDRY_MODEL_NAME", scope)

    print("")
    print(f"Saved Azure AI Foundry environment variables to scope: {scope}.")
    if entries:
        print(f"Profiles: {','.join(current_profiles)}")
    else:
        print("Profiles: (none)")



def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Azure AI Foundry environment setup")
    parser.add_argument(
        "--scope",
        choices=(ENV_SCOPE_USER, ENV_SCOPE_MACHINE, ENV_SCOPE_BOTH),
        default=ENV_SCOPE_BOTH,
        help="Environment write scope: both (default), user, or machine.",
    )
    parser.add_argument(
        "--scan-models",
        action="store_true",
        help="Scan providers and save model catalog to config.yaml, then exit.",
    )
    args = parser.parse_args()

    if args.scan_models:
        result = scan_and_save_model_catalog()
        counts = result.get("counts", {})
        print("Model scan complete. Saved to config.yaml")
        print(
            "Counts: "
            f"ollama={counts.get('ollama', 0)}, "
            f"lm_studio={counts.get('lm_studio', 0)}, "
            f"azure_ai_foundry={counts.get('azure_ai_foundry', 0)}"
        )
        return 0

    if os.name != "nt":
        print("This setup helper is intended for Windows.")

    print("Azure AI Foundry setup")
    print(f"Write scope: {args.scope}")
    if args.scope in {ENV_SCOPE_MACHINE, ENV_SCOPE_BOTH}:
        print("IMPORTANT: MACHINE scope requires administrator privileges.")
        print("If you see 'Access Denied' errors, rerun as Administrator.")
        print("Use --scope user only for local, single-user scenarios.")
    else:
        print("USER scope does not require administrator privileges.")
        print("Note: USER-only writes can cause differences across users on the same host.")
    print("")

    entries = load_entries()

    while True:
        print_entries(entries)
        print("")
        print("Menu:")
        print("  1. Add model")
        print("  2. Edit model")
        print("  3. Remove model")
        print("  4. Test model")
        print("  5. Scan and save models to config.yaml")
        print("  6. Save and exit")
        print("  7. Exit without saving")
        choice = input("Choose action (1-7): ").strip()

        if choice == "1":
            add_entry(entries)
        elif choice == "2":
            edit_entry(entries)
        elif choice == "3":
            remove_entry(entries)
        elif choice == "4":
            idx = pick_entry_index(entries, "test")
            if idx >= 0:
                test_entry(entries[idx])
        elif choice == "5":
            result = scan_and_save_model_catalog()
            counts = result.get("counts", {})
            print(
                "Model scan complete. "
                f"ollama={counts.get('ollama', 0)}, "
                f"lm_studio={counts.get('lm_studio', 0)}, "
                f"azure_ai_foundry={counts.get('azure_ai_foundry', 0)}"
            )
        elif choice == "6":
            save_entries(entries, args.scope)
            break
        elif choice == "7":
            print("No changes were saved.")
            break
        else:
            print("Invalid selection.")

    print("")
    if args.scope in {ENV_SCOPE_MACHINE, ENV_SCOPE_BOTH}:
        print("IMPORTANT: Restart the Windows service for MACHINE-scope variables to take effect:")
        print("  Restart-Service DocumentCorrectionToolkitWeb")
        print("")
    print("Restart the app (or open a new terminal) to use updated variables in local mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
