"""Converts prompt catalogs between JSON and human-readable markdown files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROMPT_MARKDOWN_SUFFIX = ".prompt.md"
PROMPT_ROOT = Path(__file__).resolve().parent.parent / "prompts"
METADATA_FIELD_ORDER = (
    "name",
    "abbr",
    "prompt_category",
    "summary",
    "max_input_words",
    "output_mode",
    "max_tokens_override",
    "version",
)
EXCLUDED_FIELDS = {
    "template",
    "key",
    "staging",
    "source_prompt_key",
    "source_prompt_category",
}


def _json_to_markdown(json_path: Path, markdown_path: Path, *, is_staging: bool) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Prompt JSON must contain an object: {json_path}")

    template = str(payload.get("template", "")).strip("\n")
    if not template.strip():
        raise ValueError(f"Prompt JSON is missing template text: {json_path}")

    name = str(payload.get("name", "")).strip()
    if is_staging and name.endswith("(Staging)"):
        payload["name"] = name[: -len("(Staging)")].rstrip()

    metadata = {k: v for k, v in payload.items() if k not in EXCLUDED_FIELDS}

    lines = ["---"]
    ordered_keys = [key for key in METADATA_FIELD_ORDER if key in metadata]
    ordered_keys.extend(sorted(key for key in metadata.keys() if key not in set(METADATA_FIELD_ORDER)))

    for key in ordered_keys:
        value = metadata[key]
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        lines.append(f"{key}: {text}")
    lines.extend(["---", "", template, ""])

    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def convert_json_catalog_to_markdown(prompt_root: Path, remove_json: bool, overwrite: bool) -> tuple[int, int]:
    converted = 0
    skipped = 0

    for folder_name in ("prod", "staging"):
        folder = prompt_root / folder_name
        if not folder.exists():
            continue

        for json_path in sorted(folder.glob("*.json")):
            markdown_path = folder / f"{json_path.stem}{PROMPT_MARKDOWN_SUFFIX}"
            if markdown_path.exists() and not overwrite:
                skipped += 1
                continue

            _json_to_markdown(json_path, markdown_path, is_staging=(folder_name == "staging"))
            converted += 1

            if remove_json:
                json_path.unlink()

    return converted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert prompt JSON files into .prompt.md files.")
    parser.add_argument(
        "--prompt-root",
        default=str(PROMPT_ROOT),
        help="Path to prompts root containing prod/ and staging/ directories.",
    )
    parser.add_argument(
        "--remove-json",
        action="store_true",
        help="Delete source JSON files after markdown conversion.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing markdown files.",
    )
    args = parser.parse_args()

    prompt_root = Path(args.prompt_root).resolve()
    converted, skipped = convert_json_catalog_to_markdown(
        prompt_root,
        remove_json=args.remove_json,
        overwrite=args.overwrite,
    )
    print(f"Converted: {converted}")
    print(f"Skipped (already existed): {skipped}")
    print(f"Prompt root: {prompt_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
