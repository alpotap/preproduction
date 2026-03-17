# Spell Check and Grammar Correction Agent

This project is a Python-based toolkit for automating spelling and grammar correction of technical documentation. It uses a local Large Language Model (LLM) via Ollama to process content from Microsoft Word (`.docx`) files and web pages, preserving structure and images.

## Features

- **Interactive Wizard**: A user-friendly, step-by-step guide for processing documents without needing command-line arguments.
- **Flexible Input Sources**: Process local `.docx` files, saved `.mhtml` web archives, or download live URLs directly.
- **Multi-Format Output**: Generate corrected documents as a `.docx` file with rich formatting (highlights, styles).
- **Structure & Image Preservation**: Extracts images from web pages and preserves paragraph styles (headings, lists) from source documents in the output.
- **Local AI Processing**: All text processing is done locally using an Ollama-hosted LLM, ensuring data privacy.
- **Configurable & Memorable**: Key settings are managed in this `readme.md` file, and the wizard remembers your last-used model and output format.
- **Performance Logging**: After each document, the tool logs key metrics, including processing time and token generation speed
## Configuration

This section acts as the live configuration file for the script. Edit the values below to change the tool's behavior.

Language: en-US
Input Directory: input
Output Directory: output
Highlight Corrections: true
Add Comments: true
Active Prompt: default
LLM Model: gpt-oss:20b-cloud
LLM Temperature: 0.1
LLM Max Tokens: 8000

## Usage Flow

1.  **Setup**:
    -   Clone the repository:
        ```shell
        git clone <repository_url>
        cd spell_check_grammar
        ```
    -   Ensure Python 3.9+ and all required libraries are installed (see `Requirements` section).
    -   Make sure your local Ollama instance is running and has the desired model pulled (e.g., `ollama pull gpt-oss:20b-cloud`).

2.  **Prepare Input Files**:
    -   Place `.docx` or previously downloaded `.mhtml` files into the `input/` directory.
    -   *Alternatively*, to download new web pages, add one URL per line to the `input/urls.txt` file.

3.  **Run the Interactive Wizard**:
    -   Open your terminal in the project directory and run the command:
    ```shell
    python process.py
    ```
4.  **Follow the Wizard Prompts**:
    -   **Download**: If `urls.txt` is found, you'll be asked if you want to download the web pages. They will be saved as `.mhtml` files in the `input/` directory.
    -   **Model Selection**: Choose which Ollama model to use for the corrections. Your last choice is the default.
    -   **File Selection**: Choose which documents from the `input/` directory you want to process.

5.  **Review Output**:
    -   The corrected files will be saved in the `output/` directory.
    -   Any images extracted from web pages will be in `output/images/`.
    -   A performance summary will be displayed in the terminal for eac
## AI Prompting Rules

The script uses the following rules when sending text to the AI model. These instructions are designed to ensure minimal, precise corrections suitable for technical documentation.

> You are a file-processing copy editor. For every text segment you receive, process it independently following Microsoft Writing Style Guide principles.
>
> **Your task is to make only minimal corrections:**
> - Fix spelling, grammar, and punctuation.
> - Fix incorrect words only when the intended meaning is clear.
> - Use plain language and active voice.
> - Keep text concise and direct.
>
> **STRICT RULES — DO NOT VIOLATE:**
> - Do NOT rewrite, rephrase, expand, shorten, or change the meaning or style.
> - Do NOT change abbreviations (e.g., "etc.", "e.g.", "i.e.", "ASAP", "API").
> - Do NOT replace technical terms, filenames, directory names, or paths. Examples: "Home directory", "/opt", "/usr/bin", "PATH", "API key", "SFTP", "localhost".
> - Do NOT replace proper nouns, usernames, project names, product names, or brand names.
> - Do NOT rewrite code, commands, arguments, flags, or configuration values.
> - Do NOT summarize or paraphrase.
> - Do NOT use anthropomorphic language.

### Command-Line Usage (for automation)

The script can also be run with arguments for non-interactive use.

-   **Download a single URL and process it:**
    ```shell
    python process.py --source-type url --input "https://example.com"
    ```
-   **Process an existing local file:**
    ```shell
    python process.py --source-type docx --input "input/my_doc.docx"
    ```

## Requirements

- Python 3.9+
- Libraries: `pip install python-docx openai requests beautifulsoup4 selenium`
- For SVG image support in DOCX files (optional): `pip install svglib reportlab`
- Microsoft Edge and the matching Edge WebDriver installed (add to PATH).
- Ollama running locally with a model loaded (e.g., on http://localhost:11434).
