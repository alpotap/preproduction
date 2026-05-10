"""Loads prompt templates and metadata from filesystem-backed prompt catalogs."""

import json
import re
from pathlib import Path

DEFAULT_PROMPT_KEY = "default"
PROMPT_VERSION_DEFAULT = "1.0"
STAGING_PROMPT_CATEGORY = "staging"
STAGING_KEY_PREFIX = "staging::"
PROMPT_MARKDOWN_SUFFIX = ".prompt.md"
PROMPT_FILE_PRIORITY = {
    PROMPT_MARKDOWN_SUFFIX: 2,
    ".json": 1,
}

PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts"
PROD_PROMPTS_DIR = PROMPTS_ROOT / "prod"
STAGING_PROMPTS_DIR = PROMPTS_ROOT / "staging"
GENERATED_PROMPTS_DIR = PROMPTS_ROOT / "generated"
GENERATED_PROD_PROMPTS_DIR = GENERATED_PROMPTS_DIR / "prod"
GENERATED_STAGING_PROMPTS_DIR = GENERATED_PROMPTS_DIR / "staging"


def _canonical_prompt_key_with_version(prompt_key, version):
    lineage = _lineage_key(prompt_key)
    major_raw, minor_raw = _sanitize_version(version).split(".", 1)
    return f"{lineage}_v{int(major_raw)}_{int(minor_raw)}"


def _list_prompt_markdown_files(directory):
    if not directory.exists():
        return []

    files = []
    for file_path in sorted(directory.iterdir()):
        if not file_path.is_file():
            continue
        name = file_path.name
        lower_name = name.lower()
        if lower_name == "readme.md":
            continue
        if name.endswith(PROMPT_MARKDOWN_SUFFIX):
            files.append(file_path)
            continue
        if re.match(r"^.+\.prompt[ _-]\d+(?:[._]\d+)?\.md$", name):
            files.append(file_path)
    return files


def _serialize_prompt_json_payload(file_key, payload):
    json_payload = dict(payload)
    template = str(json_payload.get("template") or "")
    if not template.strip():
        raise ValueError("Prompt template is required")
    json_payload["template"] = template.rstrip() + "\n"
    json_payload["key"] = file_key
    return json_payload


def _sync_markdown_to_json_directory(source_directory, target_directory):
    if not source_directory.exists():
        return 0

    target_directory.mkdir(parents=True, exist_ok=True)

    written = 0
    rename_count = 0
    markdown_files = _list_prompt_markdown_files(source_directory)
    for md_path in markdown_files:
        file_key = _prompt_key_from_path(md_path)
        payload = _load_prompt_markdown(md_path)

        if source_directory == STAGING_PROMPTS_DIR:
            canonical_key = _canonical_prompt_key_with_version(file_key, payload.get("version"))
            canonical_path = source_directory / f"{canonical_key}{PROMPT_MARKDOWN_SUFFIX}"
            if md_path != canonical_path:
                md_path.replace(canonical_path)
                md_path = canonical_path
                file_key = canonical_key
                rename_count += 1

        json_payload = _serialize_prompt_json_payload(file_key, payload)
        json_path = target_directory / f"{file_key}.json"
        json_text = json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n"

        current_text = ""
        if json_path.exists():
            current_text = json_path.read_text(encoding="utf-8")
        if current_text != json_text:
            json_path.write_text(json_text, encoding="utf-8")
            written += 1

    if rename_count:
        print(f"[prompts] normalized {rename_count} staging filename(s) with explicit versions")
    return written


def sync_markdown_prompts_to_json():
    """Ensure json prompt artifacts are generated from markdown catalogs."""
    total_written = _sync_markdown_to_json_directory(PROD_PROMPTS_DIR, GENERATED_PROD_PROMPTS_DIR)
    total_written += _sync_markdown_to_json_directory(STAGING_PROMPTS_DIR, GENERATED_STAGING_PROMPTS_DIR)
    return total_written


def _sanitize_version(value):
    raw = str(value or "").strip()
    if not raw:
        return PROMPT_VERSION_DEFAULT
    match = re.match(r"^(\d+)\.(\d+)$", raw)
    if not match:
        return PROMPT_VERSION_DEFAULT
    return f"{int(match.group(1))}.{int(match.group(2))}"


def _version_sort_key(version):
    major_raw, minor_raw = _sanitize_version(version).split(".", 1)
    return int(major_raw), int(minor_raw)


def _version_from_key(prompt_key):
    key = str(prompt_key or "").strip()
    for pattern in (r".+__v(?P<major>\d+)(?:[._](?P<minor>\d+))?$", r".+_v(?P<major>\d+)(?:[._](?P<minor>\d+))?$"):
        match = re.match(pattern, key)
        if not match:
            continue
        major = int(match.group("major"))
        minor = int(match.group("minor") or 0)
        return f"{major}.{minor}"
    return ""


def _lineage_key(prompt_key):
    key = str(prompt_key or "").strip()
    for pattern in (r"^(?P<base>.+?)__v\d+(?:[._]\d+)?$", r"^(?P<base>.+?)_v\d+(?:[._]\d+)?$"):
        match = re.match(pattern, key)
        if match:
            return match.group("base")
    return key


def _prompt_key_from_path(file_path):
    file_name = file_path.name
    if file_name.endswith(PROMPT_MARKDOWN_SUFFIX):
        return file_name[: -len(PROMPT_MARKDOWN_SUFFIX)]

    match = re.match(r"^(?P<base>.+?)\.prompt[ _-](?P<major>\d+)(?:[._](?P<minor>\d+))?\.md$", file_name)
    if match:
        major = int(match.group("major"))
        minor = int(match.group("minor") or 0)
        return f"{match.group('base')}_v{major}_{minor}"

    return file_path.stem


def _coerce_prompt_metadata(payload):
    normalized = dict(payload)
    for int_key in ("max_input_words", "max_tokens_override"):
        if int_key not in normalized:
            continue
        try:
            normalized[int_key] = int(str(normalized[int_key]).strip())
        except (TypeError, ValueError):
            normalized.pop(int_key, None)
    return normalized


def _load_prompt_markdown(file_path):
    raw_text = file_path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    if not lines:
        raise ValueError(f"Prompt file is empty: {file_path}")

    if lines[0].strip() != "---":
        raise ValueError(f"Prompt markdown front matter must start with '---': {file_path}")

    metadata = {}
    body_start = None
    for idx in range(1, len(lines)):
        line = lines[idx]
        stripped = line.strip()
        if stripped == "---":
            body_start = idx + 1
            break
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"Invalid front matter line '{line}' in {file_path}")
        metadata[key.strip()] = value.strip()

    if body_start is None:
        raise ValueError(f"Prompt markdown front matter is not closed in {file_path}")

    template = "\n".join(lines[body_start:]).rstrip()
    payload = _coerce_prompt_metadata(metadata)
    payload["template"] = template
    return payload


def _load_prompt_payload(file_path):
    if file_path.name.endswith(PROMPT_MARKDOWN_SUFFIX):
        return _load_prompt_markdown(file_path)

    if file_path.suffix.lower() == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Prompt file must contain an object: {file_path}")
        return _coerce_prompt_metadata(payload)

    raise ValueError(f"Unsupported prompt file extension: {file_path}")


def _load_prompt_file(file_path, *, is_staging):
    payload = _load_prompt_payload(file_path)

    # File stem is the source of truth so manual copy/rename promotions do not require JSON edits.
    file_key = str(_prompt_key_from_path(file_path)).strip()
    if not file_key:
        raise ValueError(f"Prompt key is required: {file_path}")

    template = str(payload.get("template") or "")
    if not template.strip():
        raise ValueError(f"Prompt template is required: {file_path}")

    definition = dict(payload)
    parsed_key_version = _version_from_key(file_key)
    definition["version"] = _sanitize_version(parsed_key_version or definition.get("version"))
    source_category = str(definition.get("prompt_category", "copy_editing")).strip() or "copy_editing"
    display_name = str(definition.get("name") or file_key).strip() or file_key
    if display_name.endswith("(Staging)"):
        display_name = display_name[: -len("(Staging)")].rstrip()

    version_tag = f"v{definition['version']}"
    if version_tag.lower() not in display_name.lower():
        display_name = f"{display_name} {version_tag}".strip()

    if is_staging:
        display_name = f"{display_name} (Staging)"
    definition["name"] = display_name

    if is_staging:
        runtime_key = f"{STAGING_KEY_PREFIX}{file_key}"
        definition["staging"] = True
        definition["source_prompt_key"] = file_key
        definition["source_prompt_category"] = source_category
        definition["prompt_category"] = STAGING_PROMPT_CATEGORY
    else:
        runtime_key = file_key
        definition["staging"] = False
        definition["source_prompt_key"] = file_key
        definition["prompt_category"] = source_category

    return runtime_key, definition


def _load_prompt_directory(directory, *, is_staging):
    catalog = {}
    if not directory.exists():
        return catalog

    candidates = {}
    for file_path in sorted(directory.iterdir()):
        if not file_path.is_file():
            continue
        suffix = PROMPT_MARKDOWN_SUFFIX if file_path.name.endswith(PROMPT_MARKDOWN_SUFFIX) else file_path.suffix.lower()
        if suffix not in PROMPT_FILE_PRIORITY:
            continue
        prompt_key = _prompt_key_from_path(file_path)
        chosen = candidates.get(prompt_key)
        if chosen is None or PROMPT_FILE_PRIORITY[suffix] > PROMPT_FILE_PRIORITY[chosen[0]]:
            candidates[prompt_key] = (suffix, file_path)

    for _suffix, file_path in sorted(candidates.values(), key=lambda item: item[1].name):
        try:
            runtime_key, definition = _load_prompt_file(file_path, is_staging=is_staging)
        except Exception as exc:  # pragma: no cover - defensive path
            print(f"[!] Skipping invalid prompt file '{file_path}': {exc}")
            continue
        catalog[runtime_key] = definition
    return catalog


def _load_prompt_catalog_from_files():
    prod_catalog = _load_prompt_directory(PROD_PROMPTS_DIR, is_staging=False)
    staging_catalog = _load_prompt_directory(STAGING_PROMPTS_DIR, is_staging=True)
    return {**prod_catalog, **staging_catalog}


PROMPT_DEFINITIONS = {}
PROMPTS = {}


def reload_prompt_catalog():
    """Reload prompt catalogs from disk and update shared dictionaries in-place."""
    synced_count = sync_markdown_prompts_to_json()
    if synced_count:
        print(f"[prompts] regenerated {synced_count} json artifact(s) from markdown")
    loaded = _load_prompt_catalog_from_files()
    PROMPT_DEFINITIONS.clear()
    PROMPT_DEFINITIONS.update(loaded)

    PROMPTS.clear()
    PROMPTS.update(
        {
            key: definition["template"]
            for key, definition in PROMPT_DEFINITIONS.items()
            if str(definition.get("template") or "").strip()
        }
    )
    return PROMPT_DEFINITIONS


reload_prompt_catalog()


def get_prompt_definitions_by_category(category_key):
    """Return prompt entries filtered by prompt_category."""
    category = str(category_key or "").strip().lower()
    return {
        key: definition
        for key, definition in PROMPT_DEFINITIONS.items()
        if str(definition.get("prompt_category", "")).strip().lower() == category
    }


def get_selectable_prompt_definitions():
    """Return latest production versions plus all staging prompts for user selection."""
    reload_prompt_catalog()
    latest_by_lineage = {}
    staging = {}

    for prompt_key, definition in PROMPT_DEFINITIONS.items():
        category = str(definition.get("prompt_category", "")).strip().lower()
        if category == STAGING_PROMPT_CATEGORY:
            staging[prompt_key] = definition
            continue

        lineage = _lineage_key(definition.get("source_prompt_key") or prompt_key)
        current = latest_by_lineage.get(lineage)
        if current is None:
            latest_by_lineage[lineage] = (prompt_key, definition)
            continue

        _, current_definition = current
        if _version_sort_key(definition.get("version")) > _version_sort_key(current_definition.get("version")):
            latest_by_lineage[lineage] = (prompt_key, definition)

    selectable = {key: definition for key, definition in latest_by_lineage.values()}
    selectable.update(staging)
    return dict(sorted(selectable.items(), key=lambda item: item[0]))


def get_prompt_definition(prompt_key):
    """Returns prompt metadata for a key, falling back to default prompt."""
    reload_prompt_catalog()
    if prompt_key in PROMPT_DEFINITIONS:
        return PROMPT_DEFINITIONS[prompt_key]

    if DEFAULT_PROMPT_KEY in PROMPT_DEFINITIONS:
        return PROMPT_DEFINITIONS[DEFAULT_PROMPT_KEY]

    if PROMPT_DEFINITIONS:
        first_key = next(iter(PROMPT_DEFINITIONS.keys()))
        return PROMPT_DEFINITIONS[first_key]

    return {}


def get_prompt_max_input_words(prompt_key, fallback=500):
    """Returns prompt-specific max input size in words used for batching."""
    definition = get_prompt_definition(prompt_key)
    value = definition.get("max_input_words", fallback)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = fallback
    return max(1, value)


def get_prompt_output_mode(prompt_key):
    """Returns the output_mode for a prompt key. Defaults to 'corrections' for standard JSON-diff prompts."""
    definition = get_prompt_definition(prompt_key)
    return definition.get("output_mode", "corrections")


def get_prompt_abbreviation(prompt_key, fallback="GEN"):
    """Returns prompt-specific abbreviation for output filenames."""
    definition = get_prompt_definition(prompt_key)
    value = str(definition.get("abbr", fallback)).strip()
    if not value:
        return fallback
    return "".join(ch for ch in value if ch.isalnum()) or fallback
