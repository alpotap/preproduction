"""CLI entrypoint that delegates interactive and command-line execution to the shared engine."""

import argparse
import sys
from pathlib import Path

from toolkit.utils import load_config
from toolkit.engine import hydrate_runtime_config, initialize_client_for_config, resolve_input_sources, process_files
from toolkit.wizard_ui import run_interactive_wizard


def build_parser():
    """Create the command-line parser for non-interactive execution."""
    parser = argparse.ArgumentParser(
        description="A unified tool to process documents for spelling and grammar correction. Run without arguments for an interactive wizard.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Examples:
  (Wizard Mode - Recommended)
    python process.py

  (Command-Line Mode)
  Process a single MHTML file:
    python process.py --source-type mhtml --input ./output/mhtml/some_page.mhtml

  Download and process a URL:
    python process.py --source-type url --input https://example.com
""",
    )
    parser.add_argument(
        "-track",
        action="store_true",
        help="Accepted for backward compatibility; processing now uses selected output types.",
    )
    parser.add_argument(
        "--source-type",
        choices=["docx", "mhtml", "pdf", "url"],
        required=True,
        help="The type of source to process.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a single input file or a URL (if --source-type is url).",
    )
    return parser


def run_cli_mode(args):
    """Execute one non-interactive processing run from parsed command-line args."""
    config = hydrate_runtime_config(load_config())
    workspace_dir = Path(__file__).parent

    try:
        client = initialize_client_for_config(config)
    except Exception as exc:
        provider = config.get("llm_provider", "")
        print(f"Error: Could not initialize {provider} client: {exc}")
        return

    try:
        files_to_process, source_type_for_processing = resolve_input_sources(args.input, args.source_type, workspace_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return

    if not files_to_process:
        print("No files to process.")
        return

    process_files(
        files_to_process,
        config,
        client,
        workspace_dir,
        source_type_for_processing,
    )


def main():
    """Run wizard mode by default or command-line mode when args are provided."""
    non_mode_args = [arg for arg in sys.argv[1:] if arg != "-track"]
    if not non_mode_args:
        run_interactive_wizard()
        return

    parser = build_parser()
    args = parser.parse_args()
    run_cli_mode(args)


if __name__ == "__main__":
    main()
