"""Shared configuration and path helpers for the toolkit."""

import csv
import ctypes
import json
import os
from pathlib import Path
import re


def _workspace_root() -> Path:
    return Path(__file__).resolve().parent.parent


WORKSPACE_ROOT = _workspace_root()
PATHS_CONFIG_PATH = WORKSPACE_ROOT / 'paths.json'
DEFAULT_INPUT_DIR = 'input'
DEFAULT_OUTPUT_DIR = 'output'


def set_windows_hidden(path: Path | str, hidden: bool = True) -> bool:
    """Set or clear the Windows hidden attribute on a file or directory.

    Returns True when the attribute operation succeeds, otherwise False.
    No-op on non-Windows platforms.
    """
    target = Path(path)
    if not target.exists():
        return False
    if os.name != "nt":
        return False

    FILE_ATTRIBUTE_HIDDEN = 0x2
    INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(target))
    if attrs == INVALID_FILE_ATTRIBUTES:
        return False

    if hidden:
        new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN
    else:
        new_attrs = attrs & ~FILE_ATTRIBUTE_HIDDEN

    return bool(ctypes.windll.kernel32.SetFileAttributesW(str(target), new_attrs))


def _normalize_directory_path(raw_value, default_name):
    value = str(raw_value or '').strip() or default_name
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate
    return candidate


def load_path_config():
    """Load input/output roots from the dedicated editable path config file."""
    defaults = {
        'input_dir': str(_normalize_directory_path(DEFAULT_INPUT_DIR, DEFAULT_INPUT_DIR)),
        'output_dir': str(_normalize_directory_path(DEFAULT_OUTPUT_DIR, DEFAULT_OUTPUT_DIR)),
    }
    if not PATHS_CONFIG_PATH.exists():
        return defaults

    try:
        with open(PATHS_CONFIG_PATH, 'r', encoding='utf-8') as file_handle:
            payload = json.load(file_handle)
    except Exception:
        return defaults

    if not isinstance(payload, dict):
        return defaults

    return {
        'input_dir': str(_normalize_directory_path(payload.get('input_dir'), DEFAULT_INPUT_DIR)),
        'output_dir': str(_normalize_directory_path(payload.get('output_dir'), DEFAULT_OUTPUT_DIR)),
    }


def get_input_root() -> Path:
    return Path(load_path_config()['input_dir'])


def get_output_root() -> Path:
    return Path(load_path_config()['output_dir'])


def format_path_for_display(path: Path, base_dir: Path | None = None) -> str:
    """Return a readable relative path when possible, else an absolute path."""
    candidate = Path(path)
    root = Path(base_dir) if base_dir is not None else WORKSPACE_ROOT
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()

def load_config():
    """Loads configuration from the readme.md file."""
    config = {
        'language': 'en-US',
        'input_dir': str(get_input_root()),
        'output_dir': str(get_output_root()),
        'highlight_corrections': True,
        'add_comments': True,
        'active_prompt': 'default',
        'llm_provider': 'ollama',
        'llm_model': 'local-model',
        'lm_studio_base_url': 'http://127.0.0.1:1234/v1',
        'lm_studio_model_name': '',
        'llm_temperature': 0.1,
        'llm_max_tokens': 1000,
        'output_types': 'inline, track_changes, hybrid'
    }
    readme_path = WORKSPACE_ROOT / 'readme.md'
    if not readme_path.exists():
        return config
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find Runtime Configuration section
    match = re.search(r'## Runtime Configuration\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if match:
        scope_text = match.group(1)
        for line in scope_text.split('\n'):
            line = line.strip()
            if ': ' in line:
                key, value = line.split(': ', 1)
                key = key.lower().replace(' ', '_')
                if key in config:
                    if isinstance(config[key], bool):
                        config[key] = value.lower() == 'true'
                    elif isinstance(config[key], float):
                        config[key] = float(value)
                    elif isinstance(config[key], int):
                        config[key] = int(value)
                    else:
                        config[key] = value
    return config

def save_config(config_to_save):
    """Updates specific keys in the readme.md configuration."""
    readme_path = WORKSPACE_ROOT / 'readme.md'
    if not readme_path.exists():
        return

    filtered_config = {
        key: value
        for key, value in config_to_save.items()
        if key not in {'input_dir', 'output_dir'}
    }
    if not filtered_config:
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_lines = []
    in_scope_section = False
    for line in lines:
        if '## Runtime Configuration' in line:
            in_scope_section = True
        elif in_scope_section and 'Runtime Configuration' not in line and line.startswith('##'):
            in_scope_section = False
        
        if in_scope_section and ': ' in line:
            key_str, value = line.split(': ', 1)
            py_key = key_str.lower().replace(' ', '_')
            if py_key in filtered_config:
                updated_lines.append(f"{key_str}: {filtered_config[py_key]}\n")
                continue
        updated_lines.append(line)

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

def log_performance_stats(log_file_path, stats_data):
    """Appends performance statistics to a CSV log file."""
    file_exists = log_file_path.exists()
    header = [
        "timestamp", "document_name", "model_used",
        "total_processing_time_s", "text_size_chars",
        "llm_generation_time_s", "input_tokens", "tokens_generated", "avg_tokens_per_sec"
    ]

    row = [
        stats_data['timestamp'], stats_data['document_name'], stats_data['model_used'],
        f"{stats_data['total_doc_time']:.2f}", stats_data['total_text_size'],
        f"{stats_data['total_llm_time']:.2f}", stats_data.get('total_input_tokens', 0),
        stats_data['total_tokens_generated'],
        f"{stats_data['tokens_per_second']:.2f}"
    ]

    with open(log_file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists: writer.writerow(header)
        writer.writerow(row)
    set_windows_hidden(log_file_path, hidden=True)