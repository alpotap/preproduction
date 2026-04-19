# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Generate Course Summary Prompt** — New multi-document analysis prompt for course-level summarization
  - Analyzes all documents in a source folder to generate comprehensive course overview
  - Output structure: Half-page summary with two sections:
    - **Verbal Overview**: Course product description and learning intent (2-3 sentences)
    - **Main Topics**: Bulleted list of key concepts (6-12 bullets, typically module names or main descriptions)
  - Saves as standalone `Course_Summary.docx` in the folder's output directory
  - Prompt category: Multi-Document Analysis
  - Integrated into CLI wizard and web app prompt selection
  - Special workflow: runs once per folder instead of per-document
  - Output mode: `course_summary` — separate from standard correction and prepend modes
  - Processes all valid `.docx` files in the selected input folder

- **Generate Summary Prompt** — New content generation prompt that creates a module completion summary prepended to the top of the document
  - Integrated into CLI wizard and web app prompt selection
  - Supports plain-text generation workflow (distinct from correction-based prompts)
  - Refined template to match user-provided example voice and structure

- **Prompt Category System** — Organizational UI for grouping prompts by type
  - Four categories: Copy Editing, Document Analysis, Multi-Document Analysis, Content Generation
  - Web UI: Dropdown #1 for category selection filters dropdown #2 for prompts in that category
  - API returns `promptCategories` list and `category` field per prompt

- **gpt-4o-mini Model Support** — Azure AI Foundry model alongside existing oss-120b
  - Selectable as separate option in provider configuration
  - Supports comma-separated model list in `Azure AI Foundry Model Name` config
  - Verified working with Azure AI Foundry endpoint and API version `2025-01-01-preview`

- **Azure AI Foundry Registry Loading** — Environment variable initialization in batch script
  - `run_web.bat` now loads `AZURE_AI_FOUNDRY_API_KEY`, `AZURE_AI_FOUNDRY_ENDPOINT`, and `AZURE_AI_FOUNDRY_API_VERSION` from Windows user registry
  - Eliminates need to manually set variables before running web server

### Changed

- **Generate Course Summary Workflow** — Improved extraction and synthesis strategy for better course overview quality
  - **Problem Solved**: Previously sent raw concatenated text, causing LLM to focus on early documents and miss course-wide patterns
  - **New Approach**: Two-phase workflow with structured extraction followed by cross-module synthesis
  - **Phase 1 - Structure Extraction**: `_extract_document_structure()` method extracts per-document components:
    - Document titles and module names
    - Heading hierarchy (up to 2 levels)
    - Key content snippets (introductions, learning objectives, list items)
  - **Phase 2 - Synthesis**: LLM receives structured course outline instead of raw text, enabling:
    - Identification of overarching themes and learning progression
    - Coherent synthesis across all modules
    - Proper weighting of all documents equally
  - **Prompt Enhancement**: Template updated to guide synthesis of structured data with explicit instructions on identifying patterns, progression, and learning outcomes
  - **Result**: Course summaries now reflect the entire course scope and coherent learning trajectory

- **Generate Summary Prompt Template** — Refined structure to enforce:
  - Starts with "You have…" opening
  - Coordinated instructional clauses
  - Impact sentence ending pattern
  - Exact closing line: "Below is your module completion status and test score achieved in this module:"

- **Correction Occurrence Detection** — Fixed to report all instances instead of deduplicating
  - `_filter_corrections_for_block` now emits one correction entry per actual occurrence using `count()`
  - Added LLM instruction to `default`, `grammar_only`, and `terminology_consistency` prompts: "Report every individual occurrence of an error separately"

- **Prompt Categories in API Response** — Exposed `promptCategories` list and `category` field per prompt
  - `/api/capabilities` returns category metadata for UI filtering
  - All 9 prompts assigned to appropriate categories:
    - Copy Editing: default, grammar_only, paragraph_rewrite
    - Document Analysis: redundancy_analysis, structural_integrity, audience_tone_alignment
    - Multi-Document Analysis: terminology_consistency, cross_reference_validation
    - Content Generation: generate_summary

- **MHTML File Cleanup** — Enabled in web job processing
  - `web_jobs.py` now passes `cleanup_source_mhtml=True`
  - MHTML converts to `.docx` (not `.from_mhtml.docx`) after cleanup

- **Azure AI Foundry Integration** — Refactored client initialization
  - Switched from `OpenAI(base_url=...)` to `AzureOpenAI(azure_endpoint, api_version)`
  - Added endpoint normalization (strips `/openai/v1` suffix if present)
  - All model lists support comma-separated names parsed into array

- **Azure AI Foundry API Version** — Updated to `2025-01-01-preview`
  - Updated in `readme.md`, `toolkit/utils.py`, `toolkit/providers.py`
  - Updated in all troubleshooting documentation
  - Verified compatibility with `gpt-4o-mini` deployment on Azure AI Foundry

- **Frontend Category Filtering** — Implemented in `app.js`
  - Added `promptCategorySelect` to elements registry
  - `renderCapabilities()` now populates category dropdown and filters prompts
  - New `filterPromptsByCategory()` function handles dynamic filtering on category change
  - Event listener added to category select for real-time prompt list updates

### Fixed

- **File Selector Empty List** — Added explanatory message for non-"Process Existing Files" task types
  - Confirmed API returns correct file counts for valid folders

- **MHTML Conversion Cleanup** — Files now properly removed after DOCX conversion
  - Output files are clean `.docx` without intermediate `.from_mhtml.docx` artifacts

- **Repeated Error Instances** — All occurrences now detected and marked
  - Previously only one per unique string was caught
  - Now uses occurrence count to expand corrections properly

### Docs

- **Updated Configuration Documentation** — Added Azure AI Foundry section
  - Endpoint format: `https://<resource>.cognitiveservices.azure.com/` (without `/openai/v1`)
  - API version setup and examples for both PowerShell and `setx`
  - Troubleshooting section for deployment errors

- **Updated Wizard Documentation** — Added gpt-4o-mini setup guidance
  - Endpoint normalization notes
  - API version selection

- **Updated Webapp Documentation** — Azure AI Foundry troubleshooting
  - Common error scenarios and resolution steps

---

## Notes for Future Releases

- **Prompt Category UI**: Hard refresh browser (Ctrl+Shift+R) after updates to ensure latest `app.js` is loaded
- **Azure Configuration**: `run_web.bat` now handles environment variable loading — no manual setup needed after initial `setx`
- **Occurrence Reporting**: LLM instructions for marking every instance should be reviewed periodically as model behavior may vary
