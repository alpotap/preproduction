"""Benchmark helper for running the processor against multiple local models."""

import subprocess
import sys
from pathlib import Path
import time
from providers import fetch_ollama_models

# --- Configuration ---
# Update this path to the file you want to test
INPUT_FILE = "input/https___leai.learnexperts.ca_share_8f4d898a-89b1-4def-85b6-61962db1e8f7.mhtml"
# ---------------------

def run_process_with_model(model_name, input_file):
    """Runs process.py with a specific model and input file."""
    print(f"\n--- Benchmarking Model: {model_name} ---")
    
    # We need to temporarily update the config in readme.md or pass it via env/args.
    # Since process.py loads from readme.md, and doesn't take --model arg,
    # we have a slight limitation in process.py.
    # However, process.py DOES save the config at the end of a run.
    # A cleaner way without modifying process.py heavily is to modify readme.md programmatically 
    # OR (better for a test script) just modify utils.py/process.py to accept --model.
    # BUT, to avoid modifying your stable codebase, let's just temporarily patch readme.md 
    # for this run, similar to how utils.save_config does it.
    
    update_config_model(model_name)
    
    input_path = Path(input_file)
    source_type = "docx" if input_path.suffix.lower() == ".docx" else "mhtml"
    
    cmd = [
        sys.executable, "process.py",
        "--source-type", source_type,
        "--input", str(input_path)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("  > Completed run.")
            
    except subprocess.CalledProcessError as e:
        print(f"  > Error running process.py for model {model_name}: {e}")

def update_config_model(model_name):
    """Updates the LLM Model in readme.md directly."""
    readme_path = Path(__file__).parent / 'readme.md'
    if not readme_path.exists():
        print("Error: readme.md not found.")
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    updated_lines = []
    in_scope_section = False
    for line in lines:
        if '## Configuration' in line: # Note: readme header changed in previous steps
             in_scope_section = True
        elif line.startswith('##') and 'Configuration' not in line:
            in_scope_section = False
        
        if in_scope_section and line.strip().startswith('LLM Model:'):
            updated_lines.append(f"LLM Model: {model_name}\n")
        else:
            updated_lines.append(line)

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

def main():
    workspace_dir = Path(__file__).parent
    
    # Verify input file
    input_path = workspace_dir / INPUT_FILE
    if not input_path.exists():
        print(f"Error: Input file not found at {input_path}")
        return

    # Get models
    models = fetch_ollama_models()
    if not models:
        print("No models to test.")
        return

    print(f"Found {len(models)} models: {', '.join(models)}")
    print(f"Target file: {input_path.name}")
    
    # Loop through all models
    for model in models:
        run_process_with_model(model, input_path)
        time.sleep(1) # Small pause

    print("\n--- Benchmarking Complete ---")

if __name__ == "__main__":
    main()
