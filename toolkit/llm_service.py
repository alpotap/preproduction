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


def _append_terminal_period_once(value: str) -> str:
    stripped = (value or "").rstrip()
    if not stripped:
        return stripped
    if _last_non_space_char(stripped) in ".?!,:;":
        return stripped
    return stripped + "."


def _normalize_hidden_whitespace_for_comparison(text: str) -> str:
    """Normalize invisible Unicode whitespace for comparison purposes only.
    
    Returns text with invisible spaces converted to regular spaces and zero-width chars removed.
    Used to detect no-op corrections caused by hidden whitespace.
    """
    if not text:
        return text
    
    # Invisible space characters to replace with regular space
    invisible_spaces = {
        '\xa0': ' ',      # Non-breaking space (NBSP)
        '\u202f': ' ',    # Narrow no-break space
        '\u2000': ' ',    # En quad
        '\u2001': ' ',    # Em quad
        '\u2002': ' ',    # En space
        '\u2003': ' ',    # Em space
        '\u2004': ' ',    # Three-per-em space
        '\u2005': ' ',    # Four-per-em space
        '\u2006': ' ',    # Six-per-em space
        '\u2007': ' ',    # Figure space
        '\u2008': ' ',    # Punctuation space
        '\u2009': ' ',    # Thin space
        '\u200a': ' ',    # Hair space
    }
    
    for char, replacement in invisible_spaces.items():
        if char in text:
            text = text.replace(char, replacement)
    
    # Zero-width characters to remove
    zero_width_chars = {
        '\u200b',  # Zero-width space
        '\u200c',  # Zero-width non-joiner
        '\u200d',  # Zero-width joiner
        '\ufeff',  # Zero-width no-break space (BOM)
    }
    
    for char in zero_width_chars:
        if char in text:
            text = text.replace(char, '')
    
    return text


def _sanitize_and_augment_corrections(result: list, text: str) -> tuple[list, int, int, int]:
    sanitized: list[dict] = []
    dropped_terminal_downgrades = 0
    dropped_hidden_whitespace_noops = 0
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
        
        # Drop corrections where original and corrected are identical after hidden-whitespace normalization
        # (these are false positives from invisible Unicode spaces in input)
        if _normalize_hidden_whitespace_for_comparison(original) == _normalize_hidden_whitespace_for_comparison(corrected):
            dropped_hidden_whitespace_noops += 1
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
        existing_missing_period_fixes = {
            _normalize_space(item.get("original", ""))
            for item in sanitized
            if _is_missing_period_fix(item.get("original", ""), item.get("corrected", ""))
        }
        for line in text.splitlines():
            if not _looks_like_bullet_or_option_line(line):
                continue
            if not _missing_terminal_period(line):
                continue
            if line in existing_originals:
                continue
            normalized_line = _normalize_space(line)
            if normalized_line in existing_missing_period_fixes:
                continue
            corrected_line = _append_terminal_period_once(line)
            if corrected_line == line.rstrip():
                continue
            sanitized.append(
                {
                    "explanation": "Missing sentence-ending period in list item.",
                    "original": line,
                    "corrected": corrected_line,
                }
            )
            existing_originals.add(line)
            existing_missing_period_fixes.add(normalized_line)
            added_missing_period_entries += 1

    return sanitized, dropped_terminal_downgrades, added_missing_period_entries, dropped_hidden_whitespace_noops


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


def _extract_json_array_from_response(content: str) -> tuple[str, bool]:
    """Robustly extract JSON array from LLM response, handling markdown blocks and embedded JSON.
    
    Tries multiple strategies in order:
    1. Find JSON in markdown code block: ```json [...] ```
    2. Find raw JSON array by bracket-depth matching: look for [ and find matching ]
    3. Lenient fallback: find first [ and last ] if both exist
    4. If nothing works, raise ValueError
    
    Returns (json_string, used_partial_recovery).
    """
    if not content:
        raise ValueError("LLM response is empty.")
    
    # Strategy 1: Look for markdown code block with JSON (non-greedy to avoid capturing too much)
    json_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', content)
    if json_match:
        return json_match.group(1), False
    
    # Strategy 2: Look for raw JSON array - try from each [ found in content
    # Uses bracket-depth tracking to find actual end of JSON, handling nested structures
    bracket_positions = [i for i, c in enumerate(content) if c == '[']
    
    for start_pos in bracket_positions:
        # Try to find matching ] by tracking bracket depth and string state
        bracket_depth = 0
        in_string = False
        escape_next = False
        
        for end_pos in range(start_pos, len(content)):
            char = content[end_pos]
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            
            if not in_string:
                if char == '[':
                    bracket_depth += 1
                elif char == ']':
                    bracket_depth -= 1
                    if bracket_depth == 0:
                        # Found matching ], try to parse this as JSON
                        candidate = content[start_pos:end_pos+1]
                        try:
                            json.loads(candidate)  # Validate it's parseable JSON
                            return candidate, False
                        except json.JSONDecodeError:
                            break  # This [ didn't work, try next one
    
    # Strategy 3: Lenient fallback - find first [ and last ] (handles edge cases with malformed JSON)
    # This may capture extra text but is better than losing corrections entirely
    first_bracket = content.find('[')
    last_bracket = content.rfind(']')
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = content[first_bracket:last_bracket+1]
        try:
            json.loads(candidate)
            return candidate, False
        except json.JSONDecodeError:
            pass  # This fallback didn't work either, will raise below

    # Strategy 4: Partial recovery for truncated JSON arrays.
    # Some providers cut output mid-object when generation stops early.
    recovered_objects: list[str] = []
    start = content.find('[')
    if start != -1:
        i = start + 1
        n = len(content)
        while i < n:
            while i < n and content[i] in " \t\r\n,":
                i += 1
            if i >= n:
                break
            if content[i] == ']':
                break
            if content[i] != '{':
                i += 1
                continue

            obj_start = i
            brace_depth = 0
            in_string = False
            escape_next = False
            j = i
            while j < n:
                ch = content[j]
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == '{':
                        brace_depth += 1
                    elif ch == '}':
                        brace_depth -= 1
                        if brace_depth == 0:
                            candidate_obj = content[obj_start:j+1]
                            try:
                                json.loads(candidate_obj)
                                recovered_objects.append(candidate_obj)
                            except json.JSONDecodeError:
                                pass
                            i = j + 1
                            break
                j += 1

            if j >= n:
                # Truncated mid-object; stop and keep recovered complete objects.
                break

    if recovered_objects:
        return f"[{','.join(recovered_objects)}]", True
    
    # If we get here, no valid JSON array was found
    raise ValueError("Could not find a valid JSON array in the LLM response.")


def _response_looks_truncated_json(content: str) -> bool:
    """Heuristic: detect likely truncated JSON responses from the model."""
    if not content:
        return False
    stripped = content.strip()
    if stripped.startswith("```json") and "```" not in stripped[7:]:
        return True
    if stripped.startswith("[") and not stripped.endswith("]"):
        return True
    return False


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

            # Use robust JSON extraction that handles markdown blocks, embedded JSON, and nested structures
            json_str_to_decode, used_partial_recovery = _extract_json_array_from_response(content)
            
            # Attempt to fix common JSON syntax errors from LLMs
            json_str_to_decode = re.sub(r'}\s*{', '}, {', json_str_to_decode) # Fix missing comma between objects
            json_str_to_decode = re.sub(r',\s*]', ']', json_str_to_decode)    # Fix trailing comma in list

            result = json.loads(json_str_to_decode)
            if not isinstance(result, list):
                raise ValueError("LLM response is valid JSON but not a list.")
            if used_partial_recovery:
                print(f"  [i] Recovered {len(result)} correction(s) from a truncated LLM JSON response.")
            result, dropped_count, added_count, dropped_hidden_ws_count = _sanitize_and_augment_corrections(result, text)
            if dropped_count:
                print(f"  [i] Dropped {dropped_count} terminal punctuation downgrade correction(s) (.?! -> ,).")
            if added_count:
                print(f"  [i] Added {added_count} missing-period correction(s) for bullet/option list items.")
            if dropped_hidden_ws_count:
                print(f"  [i] Dropped {dropped_hidden_ws_count} false-positive correction(s) caused by hidden Unicode whitespace.")
            return result, prompt_tokens, completion_tokens, llm_time

        except (ValueError, json.JSONDecodeError) as e:
            if not content:
                # A ValueError can come from the API client before response content exists.
                print(f"  [!] Error calling LLM API (Attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return [], 0, 0, llm_time
                continue

            print(f"  [!] JSON parsing failed (Attempt {attempt+1}/{max_retries}): {e}")
            if _response_looks_truncated_json(content):
                print(f"  [i] Likely truncated model response (len={len(content)}).")
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