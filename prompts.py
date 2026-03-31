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
You are a professional copy editor. Your task is to thoroughly review every sentence of the following {{language}} text and apply corrections based on Microsoft Style Guide principles.

Review each sentence for ALL of the following — do not skip any category:
• Spelling errors (including typos, wrong word forms)
• Grammar errors (subject-verb agreement, tense consistency, missing or extra words)
• Punctuation errors (missing commas, incorrect apostrophes, double spaces)
• Active voice where passive voice weakens clarity
• Awkward phrasing that can be made clearer without changing meaning
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    "grammar_only": f"""
You are a professional copy editor. Carefully check every sentence of the following {{language}} text for spelling, grammar, and punctuation errors.

Review each sentence for ALL of the following — do not skip any category:
• Spelling errors (including typos and wrong word forms)
• Grammar errors (subject-verb agreement, tense, missing or extra words)
• Punctuation errors (missing commas, incorrect apostrophes, double spaces)
Do not suggest stylistic changes or voice changes.
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
"""
}