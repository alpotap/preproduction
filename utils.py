import re
from pathlib import Path
import csv
from datetime import datetime

def load_config():
    """Loads configuration from the readme.md file."""
    config = {
        'language': 'en-US',
        'input_dir': 'input',
        'output_dir': 'output',
        'highlight_corrections': True,
        'add_comments': True,
        'active_prompt': 'default',
        'llm_model': 'local-model',
        'llm_temperature': 0.1,
        'llm_max_tokens': 1000,
        'default_output_format': 'md'
    }
    readme_path = Path(__file__).parent / 'readme.md'
    if not readme_path.exists():
        return config
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find Project Scope section
    match = re.search(r'## Configuration\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if match:
        scope_text = match.group(1)
        for line in scope_text.split('\n'):
            line = line.strip()
            if ': ' in line:
                key, value = line.split(': ', 1)
                key = key.lower().replace(' ', '_')
                if key == 'input_directory': key = 'input_dir'
                if key == 'output_directory': key = 'output_dir'
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
    readme_path = Path(__file__).parent / 'readme.md'
    if not readme_path.exists():
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_lines = []
    in_scope_section = False
    for line in lines:
        if '## Configuration' in line:
            in_scope_section = True
        elif in_scope_section and 'Configuration' not in line and line.startswith('##'):
            in_scope_section = False
        
        if in_scope_section and ': ' in line:
            key_str, value = line.split(': ', 1)
            py_key = key_str.lower().replace(' ', '_')
            if py_key in config_to_save:
                updated_lines.append(f"{key_str}: {config_to_save[py_key]}\n")
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
        "llm_generation_time_s", "tokens_generated", "avg_tokens_per_sec"
    ]

    row = [
        stats_data['timestamp'], stats_data['document_name'], stats_data['model_used'],
        f"{stats_data['total_doc_time']:.2f}", stats_data['total_text_size'],
        f"{stats_data['total_llm_time']:.2f}", stats_data['total_tokens_generated'],
        f"{stats_data['tokens_per_second']:.2f}"
    ]

    with open(log_file_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists: writer.writerow(header)
        writer.writerow(row)