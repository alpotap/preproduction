import argparse
import json
from pathlib import Path

from consistency_analysis_tool import run_consistency_analysis, write_analysis_docx
from consistency_metadata_tool import scan_input_folder, write_metadata_outputs
from utils import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run metadata generation and AI consistency analysis in a single command."
    )
    parser.add_argument(
        "--input-folder",
        required=True,
        help="Folder containing the document set to analyze (for example: input/6360)",
    )
    parser.add_argument(
        "--output-folder",
        default="output/consistency",
        help="Folder where metadata and report files are written.",
    )
    parser.add_argument(
        "--output-docx",
        default="consistency_analysis.docx",
        help="Report filename or absolute path.",
    )
    return parser.parse_args()


def resolve_output_docx(output_folder: Path, output_docx_arg: str) -> Path:
    output_docx_path = Path(output_docx_arg)
    if output_docx_path.is_absolute():
        return output_docx_path
    return output_folder / output_docx_path


def run_full_consistency(input_folder: Path, output_folder: Path, output_docx_path: Path) -> dict:
    metadata = scan_input_folder(input_folder)
    metadata_outputs = write_metadata_outputs(metadata, output_folder)

    config = load_config()
    analysis = run_consistency_analysis(metadata, config)
    write_analysis_docx(analysis, metadata, output_docx_path)

    return {
        "metadata_json": metadata_outputs["json"],
        "documents_csv": metadata_outputs["documents_csv"],
        "keywords_csv": metadata_outputs["keywords_csv"],
        "product_names_csv": metadata_outputs["product_names_csv"],
        "analysis_docx": str(output_docx_path),
        "document_count": metadata.get("document_count", 0),
        "model_used": analysis.get("_model_used", ""),
        "provider_used": analysis.get("_provider_used", ""),
    }


def main() -> None:
    args = parse_args()
    input_folder = Path(args.input_folder).resolve()
    output_folder = Path(args.output_folder).resolve()
    output_docx = resolve_output_docx(output_folder, args.output_docx)

    if not input_folder.exists() or not input_folder.is_dir():
        raise SystemExit(f"Input folder not found or not a directory: {input_folder}")

    results = run_full_consistency(input_folder, output_folder, output_docx)

    print("Cross-document consistency run complete.")
    print(f"Documents scanned: {results['document_count']}")
    print(f"Metadata JSON: {results['metadata_json']}")
    print(f"Documents CSV: {results['documents_csv']}")
    print(f"Keywords CSV: {results['keywords_csv']}")
    print(f"Product names CSV: {results['product_names_csv']}")
    print(f"Analysis DOCX: {results['analysis_docx']}")
    print(f"Model used: {results['model_used']} ({results['provider_used']})")


if __name__ == "__main__":
    main()
