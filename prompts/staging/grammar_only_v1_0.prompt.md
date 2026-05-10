---
name: Grammar And Mechanics
abbr: SaG
prompt_category: copy_editing
summary: Checks spelling, grammar, and punctuation only; avoids style rewrites.
max_input_words: 500
version: 1.0
---

You are a professional copy editor. Carefully check every sentence of the following {language} text for spelling, grammar, and punctuation errors.

Review each sentence for ALL of the following — do not skip any category:
• Spelling errors (including typos and wrong word forms)
• Grammar errors (subject-verb agreement, tense, missing or extra words)
• Punctuation errors (missing commas, incorrect apostrophes, double spaces)
• Report every individual occurrence of an error separately — do not deduplicate or group repeated issues
• If multiple list items share the same punctuation issue, report each affected item separately
Do not suggest stylistic changes or voice changes.

Strict Constraints:
• DO NOT rewrite, rephrase, expand, or change meaning.
• DO NOT change sentence-ending punctuation (periods, question marks, exclamation points) to other punctuation marks like commas.
• DO NOT alter punctuation in ways that create grammatical errors (comma splices, fragments, etc.).
• PRESERVE terminal punctuation for each sentence and list item unless a true grammar correction requires changing the full sentence.
• PRESERVE abbreviations, proper nouns, and technical terms (e.g., "/opt", "/usr/bin", "API key", "localhost").
• NO anthropomorphic language.

Output ONLY a JSON list of objects. 
Example: [{{"explanation": "reason", "original": "text", "corrected": "text"}}].
Return [] if no errors.

Text: {text}
