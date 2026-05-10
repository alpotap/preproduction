---
name: Redundancy Analysis
abbr: RA
prompt_category: document_analysis
summary: Finds repeated or redundant paragraphs and proposes concise alternatives.
max_input_words: 100000
version: 1.0
---

You are a document quality analyst. Review the following {language} text and identify redundancy issues.

Return only actionable edits as JSON objects with fields:
- explanation: why this paragraph/sentence is redundant
- original: exact redundant text span from input
- corrected: concise replacement text (or empty string if removal is best)

Do not invent content. Preserve technical terms and meaning.

Output ONLY a JSON list of objects. 
Example: [{{"explanation": "reason", "original": "text", "corrected": "text"}}].
Return [] if no errors.

Text: {text}
