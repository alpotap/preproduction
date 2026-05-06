#!/usr/bin/env python3
"""Interactive Azure AI Foundry environment setup for Windows.

Asks for 4 fields per AI entry and writes the required environment variables
to HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\Environment (MACHINE scope).
Machine scope ensures Windows services can access these variables.
It also mirrors values to current process.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from getpass import getpass


DEFAULT_API_VERSION = "2025-01-01-preview"


def normalize_profile_id(name: str) -> str:
    candidate = re.sub(r"[^a-z0-9_]", "_", (name or "").strip().lower()).strip("_")
    return candidate or "profile"


def set_user_and_process_env(name: str, value: str) -> None:
    """Set environment variable in MACHINE scope (registry) and current process.
    
    MACHINE scope (HKLM) is required so Windows services can access these variables.
    Services run under different accounts and cannot read USER-scoped (HKCU) variables.
    
    Note: Requires administrative privileges to write to HKLM.
    """
    os.environ[name] = value
    if os.name != "nt":
        return

    try:
        import winreg

        # Write to MACHINE scope (HKLM) so Windows services can read these vars
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
    except PermissionError:
        raise RuntimeError(
            f"Failed to write MACHINE environment variable '{name}': "
            "This wizard requires administrator privileges. "
            "Please run this script as Administrator (right-click > Run as administrator)."
        )
    except Exception as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"Failed to write MACHINE environment variable '{name}': {exc}") from exc


def _contains_non_ascii(value: str) -> bool:
    return any(ord(ch) > 127 for ch in value)


def prompt_non_empty(prompt: str, *, secret: bool = False) -> str:
    while True:
        value = (getpass(prompt + ": ") if secret else input(prompt + ": ")).strip()
        if value:
            return value
        print("Value is required.")


def prompt_count() -> int:
    while True:
        raw = input("How many AI entries do you want to configure? (1-5): ").strip()
        try:
            count = int(raw)
        except ValueError:
            print("Please enter a number between 1 and 5.")
            continue
        if 1 <= count <= 5:
            return count
        print("Please enter a number between 1 and 5.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Azure AI Foundry environment setup")
    parser.parse_args()

    if os.name != "nt":
        print("This setup helper is intended for Windows.")

    print("Azure AI Foundry setup")
    print("This wizard stores values in MACHINE environment variables (system-wide scope).")
    print("IMPORTANT: This wizard requires administrator privileges.")
    print("If you see 'Access Denied' errors, please run as Administrator (right-click > Run as administrator).")
    print("")

    count = prompt_count()
    entries = []
    used_profiles = set()

    for index in range(1, count + 1):
        print("")
        print(f"AI entry #{index}")

        name = prompt_non_empty("Name (example: gpt-4o-mini)")
        api_key = prompt_non_empty("API key", secret=True)
        if _contains_non_ascii(api_key):
            raise ValueError(
                "API key contains non-ASCII characters. Re-run setup and paste the raw key from Azure portal."
            )
        if any(ch.isspace() for ch in api_key):
            raise ValueError("API key contains whitespace. Re-run setup and paste key without spaces/newlines.")

        api_version = input(f"API version [{DEFAULT_API_VERSION}]: ").strip() or DEFAULT_API_VERSION
        endpoint = prompt_non_empty(
            "Endpoint (example: https://your-resource.cognitiveservices.azure.com/)"
        )

        base_profile = normalize_profile_id(name)
        profile = base_profile
        suffix = 2
        while profile in used_profiles:
            profile = f"{base_profile}_{suffix}"
            suffix += 1
        used_profiles.add(profile)

        entries.append(
            {
                "profile": profile,
                "name": name,
                "api_key": api_key,
                "api_version": api_version,
                "endpoint": endpoint,
            }
        )

    profile_ids = ",".join(item["profile"] for item in entries)
    set_user_and_process_env("AZURE_AI_FOUNDRY_PROFILE_IDS", profile_ids)

    for item in entries:
        up = item["profile"].upper()
        set_user_and_process_env(f"AZURE_AI_FOUNDRY_{up}_API_KEY", item["api_key"])
        set_user_and_process_env(f"AZURE_AI_FOUNDRY_{up}_ENDPOINT", item["endpoint"])
        set_user_and_process_env(f"AZURE_AI_FOUNDRY_{up}_API_VERSION", item["api_version"])
        set_user_and_process_env(f"AZURE_AI_FOUNDRY_{up}_MODEL_NAME", item["name"])

    # Keep legacy single-profile keys aligned with the first entry.
    first = entries[0]
    set_user_and_process_env("AZURE_AI_FOUNDRY_API_KEY", first["api_key"])
    set_user_and_process_env("AZURE_AI_FOUNDRY_ENDPOINT", first["endpoint"])
    set_user_and_process_env("AZURE_AI_FOUNDRY_API_VERSION", first["api_version"])
    set_user_and_process_env("AZURE_AI_FOUNDRY_MODEL_NAME", first["name"])

    print("")
    print("Saved Azure AI Foundry environment variables to MACHINE scope (system-wide).")
    print(f"Profiles: {profile_ids}")
    for item in entries:
        print(
            f"- {item['profile']}: model='{item['name']}', endpoint='{item['endpoint']}', apiVersion='{item['api_version']}'"
        )
    print("")
    print("IMPORTANT: Restart the Windows service for these variables to take effect:")
    print("  Restart-Service DocumentCorrectionToolkitWeb")
    print("")
    print("Alternatively, restart the app (or open a new terminal) to use new variables in local mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
