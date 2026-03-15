PROMPTS = {
    "default": """
Copy edit this {language} text segment (which may contain multiple paragraphs) using Microsoft Style Guide principles.

Tasks:
• Minimal corrections: spelling, grammar, punctuation, active voice.

Strict Constraints:
• DO NOT rewrite, rephrase, expand, or change meaning.
• PRESERVE abbreviations, proper nouns, and technical terms (e.g., "/opt", "/usr/bin", "API key", "localhost").
• NO anthropomorphic language.
• ENSURE the output is a single, complete, and valid JSON list with no truncation.

Output ONLY a JSON list: [{{"original": "exact text match from input", "corrected": "new text", "explanation": "Brief description of the specific change (e.g., 'Added comma', 'Fixed spelling')"}}].
Return [] if no errors.

Text: {text}
""",
    "grammar_only": """
Check this {language} text for objective spelling, grammar, and punctuation errors only.
Do not offer stylistic improvements or voice changes.

Strict Constraints:
• DO NOT rewrite, rephrase, expand, or change meaning.
• PRESERVE abbreviations, proper nouns, and technical terms.

Output ONLY a JSON list: [{{"original": "exact text match", "corrected": "new text", "explanation": "Grammar/Spelling error"}}].
Return [] if no errors.

Text: {text}
"""
}