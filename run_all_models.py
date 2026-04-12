"""Benchmark helper for running the processor against multiple local models."""

import subprocess
import sys
from pathlib import Path
from openai import OpenAI
import time

# --- Configuration ---
# Update this path to the file you want to test
INPUT_FILE = "input/https___leai.learnexperts.ca_share_8f4d898a-89b1-4def-85b6-61962db1e8f7.mhtml"
OUTPUT_FORMAT = "docx" # or "docx"
# ---------------------

def get_ollama_models():
    """Fetches the list of available models from Ollama."""
    try:
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        models_response = client.models.list()
        if not models_response.data:
            print("No models found in Ollama.")
            return []
        return [m.id for m in models_response.data]
    except Exception as e:
        print(f"Error fetching models from Ollama: {e}")
        return []

def run_process_with_model(model_name, input_file, output_format):
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
    
    # Construct the command
    # We use source-type docx or mhtml based on extension
    input_path = Path(input_file)
    source_type = 'docx' if input_path.suffix == '.docx' else 'mhtml'
    
    cmd = [
        sys.executable, "process.py",
        "--source-type", source_type,
        "--input", str(input_path)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        
        # Rename the output file to include the model name
        # process.py saves to output/{stem}_corrected.{format}
        workspace_dir = Path(__file__).parent
        output_dir = workspace_dir / "output"
        default_output_name = f"{input_path.stem}_corrected.{output_format}"
        default_output_path = output_dir / default_output_name
        
        if default_output_path.exists():
            # Sanitize model name for filename
            safe_model_name = model_name.replace(":", "-").replace("/", "-")
            new_output_name = f"{input_path.stem}_{safe_model_name}.{output_format}"
            new_output_path = output_dir / new_output_name
            
            # Remove if exists from previous run
            if new_output_path.exists():
                new_output_path.unlink()
                
            default_output_path.rename(new_output_path)
            print(f"  > Saved output to: {new_output_name}")
        else:
            print(f"  > Warning: Expected output file not found: {default_output_name}")
            
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
    models = get_ollama_models()
    if not models:
        print("No models to test.")
        return

    print(f"Found {len(models)} models: {', '.join(models)}")
    print(f"Target file: {input_path.name}")
    
    # Loop through all models
    for model in models:
        run_process_with_model(model, input_path, OUTPUT_FORMAT)
        time.sleep(1) # Small pause

    print("\n--- Benchmarking Complete ---")

if __name__ == "__main__":
    main()
