"""Calls the configured LLM, parses JSON correction responses, and tracks token usage."""

import time
import json
import re
from datetime import datetime
from pathlib import Path
try:
    from toolkit.prompts import PROMPTS, DEFAULT_PROMPT_KEY
except ImportError:
    PROMPTS = {}
    DEFAULT_PROMPT_KEY = "default"


RAW_OUTPUT_TRACKER_PATH = Path(__file__).resolve().parent.parent / "output" / "llm_raw_output.log"
RAW_OUTPUT_TRACKER_MAX_LINES = 2000


def _append_raw_llm_output(model_name, prompt_key, content):
    """Append raw LLM response text to a tracker file capped to the last N lines."""
    RAW_OUTPUT_TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry_lines = [
        f"[{datetime.now().isoformat()}] model={model_name} prompt={prompt_key}",
        content if content is not None else "",
        "",
    ]

    with open(RAW_OUTPUT_TRACKER_PATH, "a", encoding="utf-8") as tracker_file:
        tracker_file.write("\n".join(entry_lines))

    with open(RAW_OUTPUT_TRACKER_PATH, "r", encoding="utf-8") as tracker_file:
        lines = tracker_file.readlines()

    if len(lines) > RAW_OUTPUT_TRACKER_MAX_LINES:
        with open(RAW_OUTPUT_TRACKER_PATH, "w", encoding="utf-8") as tracker_file:
            tracker_file.writelines(lines[-RAW_OUTPUT_TRACKER_MAX_LINES:])

def get_corrections_from_llm(text, config, client):
    """Sends text to the LLM and returns corrections, input/output tokens, and duration."""
    
    # Load prompt from prompts.py based on config, fallback to default if key missing
    prompt_key = config.get('active_prompt', DEFAULT_PROMPT_KEY)
    prompt_template = PROMPTS.get(prompt_key)
    if not prompt_template:
        prompt_template = PROMPTS.get(DEFAULT_PROMPT_KEY, "Copy edit this {language} text. Return JSON corrections. Text: {text}")
    
    prompt = prompt_template.format(language=config['language'], text=text)

    max_retries = 3
    for attempt in range(max_retries):
        llm_start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=config['llm_model'],
                messages=[{"role": "user", "content": prompt}],
                temperature=config['llm_temperature'],
                max_tokens=config['llm_max_tokens']
            )
            llm_time = time.time() - llm_start_time
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            content = response.choices[0].message.content.strip()
            _append_raw_llm_output(config.get('llm_model', ''), prompt_key, content)

            # More robustly find JSON, even if it's embedded in conversation
            json_str_to_decode = ""
            json_match = re.search(r'```(?:json)?\s*(\[.*\])\s*```', content, re.DOTALL)
            if json_match:
                json_str_to_decode = json_match.group(1)
            else:
                # Fallback to finding the raw array if no markdown block is found
                json_start_index = content.find('[')
                json_end_index = content.rfind(']')
                if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                    json_str_to_decode = content[json_start_index : json_end_index + 1]
                else:
                    # If we can't find a JSON block or array, the response is invalid.
                    raise ValueError("Could not find a valid JSON array in the LLM response.")
            
            # Attempt to fix common JSON syntax errors from LLMs
            json_str_to_decode = re.sub(r'}\s*{', '}, {', json_str_to_decode) # Fix missing comma between objects
            json_str_to_decode = re.sub(r',\s*]', ']', json_str_to_decode)    # Fix trailing comma in list

            result = json.loads(json_str_to_decode)
            if not isinstance(result, list):
                raise ValueError("LLM response is valid JSON but not a list.")
            return result, prompt_tokens, completion_tokens, llm_time

        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [!] JSON parsing failed (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                print(f"  -> Raw response preview: {content[:500]}...")
                return [], prompt_tokens if 'prompt_tokens' in locals() else 0, completion_tokens if 'completion_tokens' in locals() else 0, llm_time
        except Exception as e:
            llm_time = time.time() - llm_start_time
            print(f"  [!] Error calling LLM API (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return [], 0, 0, llm_time