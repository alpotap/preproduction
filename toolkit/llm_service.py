"""Calls the configured LLM, parses JSON correction responses, and tracks token usage."""

import time
import json
import re
from datetime import datetime
from pathlib import Path
from toolkit.prompts import PROMPTS, DEFAULT_PROMPT_KEY, PROMPT_DEFINITIONS
from toolkit.providers import resolve_model_for_request


RAW_OUTPUT_TRACKER_PATH = Path(__file__).resolve().parent.parent / "output" / "llm_raw_output.log"
RAW_OUTPUT_TRACKER_MAX_LINES = 2000


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _last_non_space_char(value: str) -> str:
    stripped = (value or "").rstrip()
    return stripped[-1] if stripped else ""


def _strip_terminal_punctuation(value: str) -> str:
    stripped = (value or "").rstrip()
    if stripped and stripped[-1] in ".?!,":
        stripped = stripped[:-1]
    return _normalize_space(stripped)


def _is_terminal_downgrade_to_comma(original: str, corrected: str) -> bool:
    original_end = _last_non_space_char(original)
    corrected_end = _last_non_space_char(corrected)
    if original_end not in ".?!" or corrected_end != ",":
        return False
    return _strip_terminal_punctuation(original) == _strip_terminal_punctuation(corrected)


def _looks_like_bullet_or_option_line(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*]\s+|[a-zA-Z][\.)]\s+|\d+[\.)]\s+)\S", line or ""))


def _missing_terminal_period(line: str) -> bool:
    stripped = (line or "").rstrip()
    if not stripped:
        return False
    if _last_non_space_char(stripped) in ".?!,:;":
        return False
    return bool(re.search(r"[A-Za-z0-9\)\]\"']$", stripped))


def _is_missing_period_fix(original: str, corrected: str) -> bool:
    return (original or "").rstrip() + "." == (corrected or "").rstrip()


def _sanitize_and_augment_corrections(result: list, text: str) -> tuple[list, int, int]:
    sanitized: list[dict] = []
    dropped_terminal_downgrades = 0
    for entry in result:
        if not isinstance(entry, dict):
            continue
        original = str(entry.get("original") or "")
        corrected = str(entry.get("corrected") or original)
        if not original:
            continue
        if _is_terminal_downgrade_to_comma(original, corrected):
            dropped_terminal_downgrades += 1
            continue
        sanitized.append(
            {
                "explanation": str(entry.get("explanation") or ""),
                "original": original,
                "corrected": corrected,
            }
        )

    detected_missing_period_issue = any(
        _is_missing_period_fix(item.get("original", ""), item.get("corrected", "")) for item in sanitized
    )

    added_missing_period_entries = 0
    if detected_missing_period_issue:
        existing_originals = {item.get("original", "") for item in sanitized}
        for line in text.splitlines():
            if not _looks_like_bullet_or_option_line(line):
                continue
            if not _missing_terminal_period(line):
                continue
            if line in existing_originals:
                continue
            sanitized.append(
                {
                    "explanation": "Missing sentence-ending period in list item.",
                    "original": line,
                    "corrected": line.rstrip() + ".",
                }
            )
            existing_originals.add(line)
            added_missing_period_entries += 1

    return sanitized, dropped_terminal_downgrades, added_missing_period_entries


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
    resolved_model = resolve_model_for_request(config.get('llm_provider', ''), config.get('llm_model', ''), config)
    for attempt in range(max_retries):
        prompt_tokens = 0
        completion_tokens = 0
        llm_time = 0
        content = ""
        llm_start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config['llm_temperature'],
                max_tokens=config['llm_max_tokens']
            )
            llm_time = time.time() - llm_start_time
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            content = response.choices[0].message.content.strip()
            _append_raw_llm_output(resolved_model, prompt_key, content)

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
            result, dropped_count, added_count = _sanitize_and_augment_corrections(result, text)
            if dropped_count:
                print(f"  [i] Dropped {dropped_count} terminal punctuation downgrade correction(s) (.?! -> ,).")
            if added_count:
                print(f"  [i] Added {added_count} missing-period correction(s) for bullet/option list items.")
            return result, prompt_tokens, completion_tokens, llm_time

        except (ValueError, json.JSONDecodeError) as e:
            if not content:
                # A ValueError can come from the API client before response content exists.
                print(f"  [!] Error calling LLM API (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return [], 0, 0, llm_time
                continue

            print(f"  [!] JSON parsing failed (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                print(f"  -> Raw response preview: {content[:500]}...")
                return [], prompt_tokens, completion_tokens, llm_time
        except Exception as e:
            llm_time = time.time() - llm_start_time
            print(f"  [!] Error calling LLM API (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return [], 0, 0, llm_time


def get_text_from_llm(text, config, client):
    """Sends text to the LLM and returns a plain-text response (not JSON), input/output tokens, and duration."""
    prompt_key = config.get('active_prompt', DEFAULT_PROMPT_KEY)
    prompt_template = PROMPTS.get(prompt_key)
    if not prompt_template:
        prompt_template = PROMPTS.get(DEFAULT_PROMPT_KEY, "Summarize this {language} text. Text: {text}")

    prompt = prompt_template.format(language=config['language'], text=text)

    # Allow prompts to override max_tokens (e.g. course_summary needs more output tokens)
    prompt_def = PROMPT_DEFINITIONS.get(prompt_key, {})
    max_tokens = prompt_def.get('max_tokens_override') or config['llm_max_tokens']

    llm_start_time = time.time()
    try:
        resolved_model = resolve_model_for_request(config.get('llm_provider', ''), config.get('llm_model', ''), config)
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config['llm_temperature'],
            max_tokens=max_tokens,
        )
        llm_time = time.time() - llm_start_time
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        content = response.choices[0].message.content.strip()
        _append_raw_llm_output(resolved_model, prompt_key, content)
        return content, input_tokens, output_tokens, llm_time
    except Exception as e:
        llm_time = time.time() - llm_start_time
        print(f"  [!] Error calling LLM API for text generation: {e}")
        return "", 0, 0, llm_time