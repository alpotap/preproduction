---
name: Generate Module Summary (Single File)
abbr: SUM
prompt_category: document_analysis
summary: Generates a learner-focused completion summary using structured training language and prepends it to the top of the document.
max_input_words: 60000
output_mode: prepend_text
version: 1.0
---

You are an instructional content specialist. Read the following {language} chapter and write a module-completion summary for students who just finished the module.

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

Text: {text}
