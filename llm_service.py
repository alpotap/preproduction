import time
import json
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
            print(f"Error getting/parsing LLM response: Could not find a valid JSON array structure in the response.")
            return [], completion_tokens, llm_time

        # Extract the potential JSON string
        json_str_to_decode = content[json_start_index : json_end_index + 1]
        
        return json.loads(json_str_to_decode), completion_tokens, llm_time

    except Exception as e:
        llm_time = time.time() - llm_start_time
        print(f"Error getting/parsing LLM response: {e}")
        return [], 0, llm_time