"""Defines prompt templates and metadata used by document processing workflows."""

# Shared components for prompts
CONSTRAINTS = """
Strict Constraints:
• DO NOT rewrite, rephrase, expand, or change meaning.
• DO NOT change sentence-ending punctuation (periods, question marks, exclamation points) to other punctuation marks like commas.
• DO NOT alter punctuation in ways that create grammatical errors (comma splices, fragments, etc.).
• PRESERVE terminal punctuation for each sentence and list item unless a true grammar correction requires changing the full sentence.
• PRESERVE abbreviations, proper nouns, and technical terms (e.g., "/opt", "/usr/bin", "API key", "localhost").
• NO anthropomorphic language."""

JSON_OUTPUT_INSTRUCTIONS = """
Output ONLY a JSON list of objects. 
Example: [{{"explanation": "reason", "original": "text", "corrected": "text"}}].
Return [] if no errors."""

DEFAULT_PROMPT_KEY = "default"

PROMPT_DEFINITIONS = {
    "default": {
        "name": "Full Copy Edit",
        "abbr": "FCE",
        "prompt_category": "copy_editing",
        "summary": "Checks spelling, grammar, punctuation, voice, and clarity while preserving meaning.",
        "max_input_words": 500,
        "template": f"""
You are a professional copy editor. Your task is to thoroughly review every sentence of the following {{language}} text and apply corrections based on Microsoft Style Guide principles.

Review each sentence for ALL of the following — do not skip any category:
• Spelling errors (including typos, wrong word forms)
• Grammar errors (subject-verb agreement, tense consistency, missing or extra words)
• Punctuation errors (missing commas, incorrect apostrophes, double spaces)
• Active voice where passive voice weakens clarity
• Awkward phrasing that can be made clearer without changing meaning
• Report every individual occurrence of an error separately — do not deduplicate or group repeated issues
• If multiple list items share the same punctuation issue, report each affected item separately
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    },
    "grammar_only": {
        "name": "Grammar And Mechanics",
        "abbr": "SaG",
        "prompt_category": "copy_editing",
        "summary": "Checks spelling, grammar, and punctuation only; avoids style rewrites.",
        "max_input_words": 500,
        "template": f"""
You are a professional copy editor. Carefully check every sentence of the following {{language}} text for spelling, grammar, and punctuation errors.

Review each sentence for ALL of the following — do not skip any category:
• Spelling errors (including typos and wrong word forms)
• Grammar errors (subject-verb agreement, tense, missing or extra words)
• Punctuation errors (missing commas, incorrect apostrophes, double spaces)
• Report every individual occurrence of an error separately — do not deduplicate or group repeated issues
• If multiple list items share the same punctuation issue, report each affected item separately
Do not suggest stylistic changes or voice changes.
{CONSTRAINTS}
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    },
    "paragraph_rewrite": {
        "name": "Paragraph Revision",
        "abbr": "PR",
        "prompt_category": "copy_editing",
        "summary": "Analyzes text and rewrites full paragraphs when broader changes are needed for clarity or correctness.",
        "max_input_words": 1200,
        "template": f"""
You are a professional copy editor. Review the following {{language}} text and improve it when sentence-level edits are not enough.

Tasks:
• Analyze the text for grammar, punctuation, clarity, structure, and paragraph-level flow issues.
• When needed, rewrite the full paragraph instead of proposing only small phrase edits.
• Prefer minimal corrections when they are sufficient, but allow full paragraph replacement when it produces a clearly better result.

Strict Constraints:
• PRESERVE technical meaning, product names, acronyms, and commands exactly unless they are clearly incorrect.
• DO NOT invent new facts.
• DO NOT expand content beyond what is needed to improve correctness or clarity.
• Return paragraph-level replacements only when justified.
• NO anthropomorphic language.

{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    },
    "redundancy_analysis": {
        "name": "Redundancy Analysis",
        "abbr": "RA",
        "prompt_category": "document_analysis",
        "summary": "Finds repeated or redundant paragraphs and proposes concise alternatives.",
        "max_input_words": 100000,
        "template": f"""
You are a document quality analyst. Review the following {{language}} text and identify redundancy issues.

Return only actionable edits as JSON objects with fields:
- explanation: why this paragraph/sentence is redundant
- original: exact redundant text span from input
- corrected: concise replacement text (or empty string if removal is best)

Do not invent content. Preserve technical terms and meaning.
{JSON_OUTPUT_INSTRUCTIONS}

Text: {{text}}
""",
    },
    "terminology_consistency": {
        "name": "Terminology Consistency Validation",
        "abbr": "TCV",
        "prompt_category": "multi_document_analysis",
        "summary": "Identifies inconsistent usage of defined terms, acronyms, and named entities across the document and aligns them to a single existing form.",
        "max_input_words": 15000,
        "template": """You are a terminology consistency reviewer. Analyze the following {language} text to identify inconsistent usage of terms, acronyms, product names, or technical entities that refer to the same concept.

Tasks:
• Detect multiple variants of the same term (e.g., acronym vs spelled-out form, capitalization differences).
• Determine whether one variant is used as the primary form in the document.
• Propose corrections that align inconsistent usages to an existing form already present in the text.
• Report every individual occurrence of an inconsistent term separately — do not deduplicate or group repeated instances.

Strict Constraints:
• DO NOT invent new terms or terminology.
• DO NOT rewrite sentences beyond the minimal change required for consistency.
• PRESERVE technical meaning, abbreviations, and proper nouns exactly.
• NO stylistic or grammatical rewrites unless required solely for consistency.
• NO anthropomorphic language.

Output ONLY a JSON list of objects.
Each object must include:
- explanation: why the usage is inconsistent
- original: the exact text span with inconsistent usage
- corrected: the aligned replacement using an existing variant

Return [] if no issues are found.

Text: {text}""",
    },
    "structural_integrity": {
        "name": "Structural Integrity Validation",
        "abbr": "SIV",
        "prompt_category": "document_analysis",
        "summary": "Validates heading hierarchy, section ordering, and overall document structure for logical and organizational correctness.",
        "max_input_words": 60000,
        "template": """You are a document structure validator. Examine the following {language} document for structural integrity issues.

Tasks:
• Verify correct heading hierarchy (e.g., no skipped levels such as jumping from H1 to H3).
• Identify orphaned or empty sections.
• Detect missing required sections or illogical section ordering.
• Ensure section titles accurately reflect their contents at a high level.

Strict Constraints:
• DO NOT rewrite or rephrase content.
• DO NOT propose new sections unless they are clearly missing based on existing structure.
• DO NOT change wording inside sections.
• NO anthropomorphic language.

Output ONLY a JSON list of objects.
Each object must include:
- explanation: description of the structural issue
- original: the exact heading or structural element involved
- corrected: a minimal structural correction suggestion (or empty string if manual author decision is required)

Return [] if no issues are found.

Text: {text}""",
    },
    "cross_reference_validation": {
        "name": "Cross-Reference and Citation Validation",
        "abbr": "CRV",
        "prompt_category": "multi_document_analysis",
        "summary": "Checks internal references, citations, and section links for existence, correctness, and consistency within the document.",
        "max_input_words": 80000,
        "template": """You are an internal cross-reference validator. Review the following {language} document and validate all internal references.

Tasks:
• Verify that all referenced sections, figures, tables, or appendices exist.
• Detect broken, missing, or mismatched references (e.g., incorrect numbering or naming).
• Identify references whose targets have been renamed or removed.

Strict Constraints:
• DO NOT invent new references or targets.
• DO NOT correct content beyond resolving reference mismatches.
• DO NOT rewrite prose.
• NO anthropomorphic language.

Output ONLY a JSON list of objects.
Each object must include:
- explanation: description of the reference issue
- original: the exact reference text as written
- corrected: the corrected reference text, or empty string if the target cannot be determined

Return [] if no issues are found.

Text: {text}""",
    },
    "audience_tone_alignment": {
        "name": "Audience and Tone Alignment Check",
        "abbr": "ATA",
        "prompt_category": "document_analysis",
        "summary": "Identifies sections whose tone, register, or terminology does not match the intended audience or document purpose.",
        "max_input_words": 8000,
        "template": """You are an audience and tone alignment reviewer. Evaluate the following {language} text to determine whether the tone and register are consistent with the intended audience and document purpose.

Tasks:
• Identify sections that are overly informal, overly technical, or mismatched to the target audience.
• Detect inconsistent tone shifts across sections.
• Highlight jargon usage that may be inappropriate for the stated audience.

Strict Constraints:
• DO NOT rewrite or rephrase text.
• DO NOT suggest stylistic improvements unless identifying a mismatch.
• Provide observations only; corrections may be indications rather than replacements.
• NO anthropomorphic language.

Output ONLY a JSON list of objects.
Each object must include:
- explanation: description of the tone or audience mismatch
- original: the exact text span exhibiting the issue
- corrected: empty string unless a minimal, audience-aligned alternative is explicitly implied by surrounding text

Return [] if no issues are found.

Text: {text}""",
    },
    "generate_summary": {
        "name": "Generate Module Summary (Single File)",
        "abbr": "SUM",
        "prompt_category": "document_analysis",
        "output_mode": "prepend_text",
        "summary": "Generates a learner-focused completion summary using structured training language and prepends it to the top of the document.",
        "max_input_words": 60000,
        "template": """You are an instructional content specialist. Read the following {language} chapter and write a module-completion summary for students who just finished the module.

Write the summary to match this structure, tone, and intent:
- Begin with "You have".
- Use one polished paragraph that describes what learners learned and what concepts were covered.
- Use coordinated clauses in this style where appropriate: "how...", "why...", "reviewed...", "explored...", "examined...", "learned...".
- Keep the tone professional, instructional, and learner-facing.
- Explicitly connect learning outcomes to day-to-day effectiveness.
- End the paragraph with a sentence in this style: "These concepts help ... in Service Request Management."
- Keep the paragraph concise (about 4-6 sentences).

After the paragraph, add this exact line on a new line:
Below is your module completion status and test score achieved in this module:

Output only the summary text and the required final line. Do not include JSON, code blocks, headings, labels, or additional commentary.

Text: {text}""",
    },
    "generate_course_summary": {
        "name": "Full Course Summary (multiple documents)",
        "abbr": "CSM",
        "prompt_category": "multi_document_analysis",
        "output_mode": "course_summary",
        "summary": "Analyzes all course documents in a folder and generates a full-page course overview including intended audience, course length estimate, description, and learning objectives.",
        "max_input_words": 150000,
        "max_tokens_override": 2000,
        "template": """You are a curriculum analyst writing a professional course description for a learning catalog.

Using the course structure data below, write a complete course overview in exactly this format. Output the four labeled sections below with their exact labels on their own line, followed by the content. Do not add any other text, headers, or formatting.

[COURSE DESCRIPTION]
Write 4-6 sentences describing the course. Name the product, platform, or domain. Describe what workflows and tasks are covered. Explain how the modules connect and build on each other. State what the learner will be able to do by the end.

[INTENDED AUDIENCE]
Write 2-3 sentences describing who this course is for. Include inferred job roles, assumed prior knowledge, and the operational context learners come from.

[COURSE LENGTH]
Write 1-2 sentences estimating the time commitment. Base this on the number of modules found and depth of the content. Example: "This course consists of 15 modules and is estimated to take approximately 6-8 hours to complete."

[LEARNING OBJECTIVES]
Write exactly 12 action-oriented learning objectives, one per line, each starting with a bullet •. Use active verbs: navigate, configure, create, manage, classify, resolve, analyze, identify, apply, distinguish, generate, link. Each objective is one complete sentence describing a practical skill.

Course Structure:
{text}""",
    },
}

PROMPTS = {
    key: definition["template"]
    for key, definition in PROMPT_DEFINITIONS.items()
}


def get_prompt_definition(prompt_key):
    """Returns prompt metadata for a key, falling back to default prompt."""
    if prompt_key in PROMPT_DEFINITIONS:
        return PROMPT_DEFINITIONS[prompt_key]
    return PROMPT_DEFINITIONS.get(DEFAULT_PROMPT_KEY, {})


def get_prompt_max_input_words(prompt_key, fallback=500):
    """Returns prompt-specific max input size in words used for batching."""
    definition = get_prompt_definition(prompt_key)
    value = definition.get("max_input_words", fallback)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = fallback
    return max(1, value)


def get_prompt_output_mode(prompt_key):
    """Returns the output_mode for a prompt key. Defaults to 'corrections' for standard JSON-diff prompts."""
    definition = get_prompt_definition(prompt_key)
    return definition.get("output_mode", "corrections")


def get_prompt_abbreviation(prompt_key, fallback="GEN"):
    """Returns prompt-specific abbreviation for output filenames."""
    definition = get_prompt_definition(prompt_key)
    value = str(definition.get("abbr", fallback)).strip()
    if not value:
        return fallback
    return "".join(ch for ch in value if ch.isalnum()) or fallback
    