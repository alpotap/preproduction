"""Calls the configured LLM, parses JSON correction responses, and tracks token usage."""

import time
import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from toolkit.prompts import PROMPTS, DEFAULT_PROMPT_KEY, PROMPT_DEFINITIONS
from toolkit.providers import resolve_model_for_request
from toolkit.utils import normalize_hidden_whitespace, normalize_space


RAW_OUTPUT_TRACKER_PATH = Path(__file__).resolve().parent.parent / "output" / "llm_raw_output.log"
_MID_SENTENCE_PERIOD_RE = re.compile(r"\.\s[a-z]")
_PERIOD_BEFORE_SEPARATOR_RE = re.compile(r"\.\s*[:,]")
RAW_OUTPUT_TRACKER_MAX_BYTES = 10 * 1024 * 1024
RAW_OUTPUT_ENTRY_MARKER = "=== LLM DEBUG ENTRY START ===\n"
DEFAULT_LLM_MAX_CONCURRENT_REQUESTS = 3
MIN_LLM_MAX_CONCURRENT_REQUESTS = 1
MAX_LLM_MAX_CONCURRENT_REQUESTS = 20


class _LlmRequestLimiter:
    """Global in-process limiter for concurrent outbound LLM requests."""

    def __init__(self, default_limit: int) -> None:
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._inflight = 0
        self._waiting = 0
        self._limit = default_limit
        self._grant_count = 0
        self._queued_grant_count = 0
        self._total_wait_ms = 0

    def set_limit(self, limit: int) -> int:
        with self._condition:
            self._limit = max(MIN_LLM_MAX_CONCURRENT_REQUESTS, min(MAX_LLM_MAX_CONCURRENT_REQUESTS, int(limit)))
            self._condition.notify_all()
            return self._limit

    @contextmanager
    def acquire(self, requested_limit: int):
        limit = self.set_limit(requested_limit)
        wait_started = time.time()
        with self._condition:
            self._waiting += 1
            while self._inflight >= self._limit:
                self._condition.wait()
            waited_ms = int((time.time() - wait_started) * 1000)
            self._waiting = max(0, self._waiting - 1)
            self._grant_count += 1
            self._total_wait_ms += waited_ms
            if waited_ms > 0:
                self._queued_grant_count += 1
            self._inflight += 1
            inflight_now = self._inflight

        try:
            yield {
                "limit": limit,
                "waited_ms": waited_ms,
                "inflight": inflight_now,
            }
        finally:
            with self._condition:
                self._inflight = max(0, self._inflight - 1)
                self._condition.notify()

    def get_metrics(self) -> dict:
        with self._condition:
            avg_wait_ms = (self._total_wait_ms / self._grant_count) if self._grant_count else 0.0
            return {
                "limit": int(self._limit),
                "inflight": int(self._inflight),
                "waiting": int(self._waiting),
                "totalRequests": int(self._grant_count),
                "queuedRequests": int(self._queued_grant_count),
                "averageWaitMs": round(avg_wait_ms, 2),
            }


_LLM_REQUEST_LIMITER = _LlmRequestLimiter(DEFAULT_LLM_MAX_CONCURRENT_REQUESTS)


def get_llm_request_runtime_telemetry() -> dict:
    """Return runtime telemetry for global LLM request limiting."""
    return _LLM_REQUEST_LIMITER.get_metrics()


def _as_bool(value, default: bool = False) -> bool:
    """Parse bool-like values from runtime config payloads."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _compact_preview(value: str, max_chars: int = 320) -> str:
    """Build a single-line preview suitable for log tails."""
    compact = normalize_space(value)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _last_non_space_char(value: str) -> str:
    stripped = (value or "").rstrip()
    return stripped[-1] if stripped else ""


def _strip_terminal_punctuation(value: str) -> str:
    stripped = (value or "").rstrip()
    if stripped and stripped[-1] in ".?!,":
        stripped = stripped[:-1]
    return normalize_space(stripped)


def _is_terminal_downgrade_to_comma(original: str, corrected: str) -> bool:
    original_end = _last_non_space_char(original)
    corrected_end = _last_non_space_char(corrected)
    if original_end not in ".?!" or corrected_end != ",":
        return False
    return _strip_terminal_punctuation(original) == _strip_terminal_punctuation(corrected)


def _is_invalid_terminal_period_append(original: str, corrected: str) -> bool:
    """Detect invalid terminal punctuation like '?.' or ':.' appended to an already terminal line."""
    original_stripped = (original or "").rstrip()
    corrected_stripped = (corrected or "").rstrip()
    if not original_stripped or not corrected_stripped:
        return False
    if original_stripped == corrected_stripped:
        return False
    original_end = _last_non_space_char(original_stripped)
    if original_end not in ".?!:;":
        return False
    return corrected_stripped == original_stripped + "."


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value, default: int = 0, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _resolve_llm_max_concurrent_requests(config) -> int:
    return _coerce_int(
        config.get("llm_max_concurrent_requests"),
        default=DEFAULT_LLM_MAX_CONCURRENT_REQUESTS,
        minimum=MIN_LLM_MAX_CONCURRENT_REQUESTS,
        maximum=MAX_LLM_MAX_CONCURRENT_REQUESTS,
    )


def _is_nontrivial_input_for_empty_retry(text: str) -> bool:
    """Retry only for substantial inputs where empty corrections are unlikely to be correct."""
    non_empty_lines = [line for line in (text or "").splitlines() if line.strip()]
    word_count = len((text or "").split())
    return word_count >= 80 and len(non_empty_lines) >= 8


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


def _introduces_mid_sentence_period(original: str, corrected: str) -> bool:
    """Detect corrections that insert a period followed by a lowercase letter.

    A period followed by a space and a lowercase letter is never valid — it indicates
    the model split a sentence at the wrong boundary.
    """
    orig_count = len(_MID_SENTENCE_PERIOD_RE.findall(original or ""))
    corr_count = len(_MID_SENTENCE_PERIOD_RE.findall(corrected or ""))
    return corr_count > orig_count


def _introduces_period_before_separator(original: str, corrected: str) -> bool:
    """Detect newly introduced patterns like 'word.:' or 'word.,'."""
    orig_count = len(_PERIOD_BEFORE_SEPARATOR_RE.findall(original or ""))
    corr_count = len(_PERIOD_BEFORE_SEPARATOR_RE.findall(corrected or ""))
    return corr_count > orig_count


def _append_terminal_period_once(value: str) -> str:
    stripped = (value or "").rstrip()
    if not stripped:
        return stripped
    if _last_non_space_char(stripped) in ".?!,:;":
        return stripped
    return stripped + "."


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
        if (
            _is_terminal_downgrade_to_comma(original, corrected)
            or _is_invalid_terminal_period_append(original, corrected)
            or _introduces_mid_sentence_period(original, corrected)
            or _introduces_period_before_separator(original, corrected)
        ):
            dropped_terminal_downgrades += 1
            continue
        
        # Drop corrections where original and corrected are identical after hidden-whitespace normalization
        # (these are false positives from invisible Unicode spaces in input)
        if normalize_hidden_whitespace(original) == normalize_hidden_whitespace(corrected):
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
            normalize_space(item.get("original", ""))
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
            normalized_line = normalize_space(line)
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


def _sanitize_corrections_ai_only(result: list) -> list[dict]:
    """Keep only model-provided corrections without local augmentation."""
    sanitized: list[dict] = []
    for entry in result:
        if not isinstance(entry, dict):
            continue
        original = str(entry.get("original") or "")
        corrected = str(entry.get("corrected") or original)
        if not original:
            continue
        if _is_terminal_downgrade_to_comma(original, corrected):
            continue
        if _is_invalid_terminal_period_append(original, corrected):
            continue
        if _introduces_mid_sentence_period(original, corrected):
            continue
        if _introduces_period_before_separator(original, corrected):
            continue
        sanitized.append(
            {
                "explanation": str(entry.get("explanation") or ""),
                "original": original,
                "corrected": corrected,
            }
        )
    return sanitized


def _append_raw_llm_output(model_name, prompt_key, input_content, output_content):
    """Append one structured LLM debug entry with input/output and cap file size to 10MB."""
    RAW_OUTPUT_TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)

    input_text = input_content if input_content is not None else ""
    output_text = output_content if output_content is not None else ""
    timestamp = datetime.now().isoformat()

    entry = (
        RAW_OUTPUT_ENTRY_MARKER
        + f"timestamp: {timestamp}\n"
        + f"model: {model_name}\n"
        + f"prompt_key: {prompt_key}\n"
        + f"input_char_count: {len(input_text)}\n"
        + f"input_word_count: {len(input_text.split())}\n"
        + f"output_char_count: {len(output_text)}\n"
        + "--- INPUT ---\n"
        + input_text
        + "\n--- OUTPUT ---\n"
        + output_text
        + "\n--- PREVIEW ---\n"
        + f"input_preview: {_compact_preview(input_text)}\n"
        + f"output_preview: {_compact_preview(output_text)}\n"
        + "=== LLM DEBUG ENTRY END ===\n"
    )

    with open(RAW_OUTPUT_TRACKER_PATH, "a", encoding="utf-8") as tracker_file:
        tracker_file.write(entry)

    try:
        current_size = RAW_OUTPUT_TRACKER_PATH.stat().st_size
    except FileNotFoundError:
        return

    if current_size <= RAW_OUTPUT_TRACKER_MAX_BYTES:
        return

    with open(RAW_OUTPUT_TRACKER_PATH, "rb") as tracker_file:
        data = tracker_file.read()

    keep_from = max(0, len(data) - RAW_OUTPUT_TRACKER_MAX_BYTES)
    trimmed = data[keep_from:]

    marker_bytes = RAW_OUTPUT_ENTRY_MARKER.encode("utf-8")
    marker_index = trimmed.find(marker_bytes)
    if marker_index > 0:
        trimmed = trimmed[marker_index:]

    with open(RAW_OUTPUT_TRACKER_PATH, "wb") as tracker_file:
        tracker_file.write(trimmed)


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


def _is_max_tokens_unsupported_error(exc: Exception) -> bool:
    """Return True when provider rejects max_tokens for current model family."""
    message = str(exc or "").lower()
    return (
        "unsupported parameter" in message
        and "max_tokens" in message
        and "max_completion_tokens" in message
    )


def _chat_completion_with_token_fallback(client, model, messages, temperature, token_budget):
    """Call chat completions with backward/forward token parameter compatibility."""
    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=token_budget,
        )
    except Exception as exc:
        if not _is_max_tokens_unsupported_error(exc):
            raise
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=token_budget,
        )


def get_corrections_from_llm(text, config, client, _allow_empty_retry=True, _remaining_passes=None):
    """Sends text to the LLM and returns corrections, input/output tokens, and duration."""
    
    # Load prompt from prompts.py based on config, fallback to default if key missing
    prompt_key = config.get('active_prompt', DEFAULT_PROMPT_KEY)
    prompt_template = PROMPTS.get(prompt_key)
    if not prompt_template:
        prompt_template = PROMPTS.get(DEFAULT_PROMPT_KEY, "Copy edit this {language} text. Return JSON corrections. Text: {text}")
    
    prompt = prompt_template.format(language=config['language'], text=text)

    configured_max_passes = _coerce_int(config.get("llm_max_passes"), default=2, minimum=1, maximum=5)
    max_retries = _coerce_int(_remaining_passes, default=configured_max_passes, minimum=1)
    resolved_model = resolve_model_for_request(config.get('llm_provider', ''), config.get('llm_model', ''), config)
    for attempt in range(max_retries):
        prompt_tokens = 0
        completion_tokens = 0
        llm_time = 0
        content = ""
        llm_start_time = time.time()
        try:
            with _LLM_REQUEST_LIMITER.acquire(_resolve_llm_max_concurrent_requests(config)) as slot_info:
                llm_start_time = time.time()
                response = _chat_completion_with_token_fallback(
                    client=client,
                    model=resolved_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=config['llm_temperature'],
                    token_budget=config['llm_max_tokens'],
                )
                llm_time = time.time() - llm_start_time
            if slot_info["waited_ms"] >= 200:
                print(
                    f"  [i] LLM queue waited {slot_info['waited_ms']} ms "
                    f"(limit={slot_info['limit']}, inflight_at_start={slot_info['inflight']})."
                )
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            content = response.choices[0].message.content.strip()
            _append_raw_llm_output(resolved_model, prompt_key, prompt, content)

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
            ai_only = _as_bool(config.get("ai_only_corrections"), default=True)
            if ai_only:
                result = _sanitize_corrections_ai_only(result)
            else:
                result, dropped_count, added_count, dropped_hidden_ws_count = _sanitize_and_augment_corrections(result, text)
                if dropped_count:
                    print(f"  [i] Dropped {dropped_count} terminal punctuation downgrade correction(s) (.?! -> ,).")
                if added_count:
                    print(f"  [i] Added {added_count} missing-period correction(s) for bullet/option list items.")
                if dropped_hidden_ws_count:
                    print(f"  [i] Dropped {dropped_hidden_ws_count} false-positive correction(s) caused by hidden Unicode whitespace.")

            retry_on_empty = _as_bool(config.get("retry_on_empty_corrections"), default=True)
            configured_temperature = _coerce_float(config.get("llm_temperature"), default=0.0)
            if (
                _allow_empty_retry
                and retry_on_empty
                and configured_temperature > 0.0
                and not result
                and _is_nontrivial_input_for_empty_retry(text)
            ):
                remaining_passes = max_retries - (attempt + 1)
                if remaining_passes <= 0:
                    return result, prompt_tokens, completion_tokens, llm_time
                print("  [i] Empty correction list on non-trivial input; retrying once at temperature 0.0.")
                retry_config = dict(config)
                retry_config["llm_temperature"] = 0.0
                retry_result, retry_prompt_tokens, retry_completion_tokens, retry_llm_time = get_corrections_from_llm(
                    text,
                    retry_config,
                    client,
                    _allow_empty_retry=False,
                    _remaining_passes=remaining_passes,
                )
                return (
                    retry_result,
                    prompt_tokens + retry_prompt_tokens,
                    completion_tokens + retry_completion_tokens,
                    llm_time + retry_llm_time,
                )

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
        with _LLM_REQUEST_LIMITER.acquire(_resolve_llm_max_concurrent_requests(config)) as slot_info:
            llm_start_time = time.time()
            response = _chat_completion_with_token_fallback(
                client=client,
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config['llm_temperature'],
                token_budget=max_tokens,
            )
            llm_time = time.time() - llm_start_time
        if slot_info["waited_ms"] >= 200:
            print(
                f"  [i] LLM queue waited {slot_info['waited_ms']} ms "
                f"(limit={slot_info['limit']}, inflight_at_start={slot_info['inflight']})."
            )
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        content = response.choices[0].message.content.strip()
        _append_raw_llm_output(resolved_model, prompt_key, prompt, content)
        return content, input_tokens, output_tokens, llm_time
    except Exception as e:
        llm_time = time.time() - llm_start_time
        print(f"  [!] Error calling LLM API for text generation: {e}")
        return "", 0, 0, llm_time