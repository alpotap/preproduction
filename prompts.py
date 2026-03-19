# Shared components for prompts
CONSTRAINTS = """
Strict Constraints:
• DO NOT rewrite, rephrase, expand, or change meaning.
• PRESERVE abbreviations, proper nouns, and technical terms (e.g., "/opt", "/usr/bin", "API key", "localhost").
• NO anthropomorphic language."""

JSON_OUTPUT_INSTRUCTIONS = """
Output ONLY a JSON list of objects. 
Example: [{{"explanation": "reason", "original": "text", "corrected": "text"}}].
Return [] if no errors."""

PROMPTS = {
    "default": f"""
Copy edit this {{language}} text segment (which may contain multiple paragraphs) using Microsoft Style Guide principles.

Tasks:
• Minimal corrections: spelling, grammar, punctuation, active voice.
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    "grammar_only": f"""
Check this {{language}} text for objective spelling, grammar, and punctuation errors only.
Do not offer stylistic improvements or voice changes.
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
"""
}