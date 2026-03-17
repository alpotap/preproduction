import time
import json
import re
try:
    from prompts import PROMPTS
except ImportError:
    PROMPTS = {}

def get_corrections_from_llm(text, config, client):
    """Sends text to the local LLM and returns a list of corrections, token count, and duration."""
    
    # Load prompt from prompts.py based on config, fallback to default if key missing
    prompt_key = config.get('active_prompt', 'default')
    prompt_template = PROMPTS.get(prompt_key)
    if not prompt_template:
        prompt_template = PROMPTS.get('default', "Copy edit this {language} text. Return JSON corrections. Text: {text}")
    
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
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            content = response.choices[0].message.content.strip()

            # Clean the response: extract content from markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:].strip()
            elif content.startswith("```"):
                content = content[3:].strip()
            if content.endswith("```"):
                content = content[:-3].strip()

            # Find the start and end of the JSON array.
            json_start_index = content.find('[')
            json_end_index = content.rfind(']')

            if json_start_index == -1 or json_end_index == -1 or json_end_index < json_start_index:
                raise ValueError("Could not find a valid JSON array structure in the response.")

            # Extract the potential JSON string
            json_str_to_decode = content[json_start_index : json_end_index + 1]
            
            # Attempt to fix common JSON syntax errors from LLMs
            json_str_to_decode = re.sub(r'}\s*{', '}, {', json_str_to_decode) # Fix missing comma between objects
            json_str_to_decode = re.sub(r',\s*]', ']', json_str_to_decode)    # Fix trailing comma in list

            result = json.loads(json_str_to_decode)
            if not isinstance(result, list):
                raise ValueError("LLM response is valid JSON but not a list.")
            return result, completion_tokens, llm_time

        except (ValueError, json.JSONDecodeError) as e:
            print(f"  [!] JSON parsing failed (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                print(f"  -> Raw response preview: {content[:500]}...")
                return [], completion_tokens if 'completion_tokens' in locals() else 0, llm_time
        except Exception as e:
            llm_time = time.time() - llm_start_time
            print(f"  [!] Error calling LLM API (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return [], 0, llm_time