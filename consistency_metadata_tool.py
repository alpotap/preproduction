"""Scans document sets and extracts normalized metadata for consistency analysis."""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document


SUPPORTED_EXTENSIONS = {".docx", ".mhtml", ".html", ".txt", ".md", ".pdf"}
STOP_WORDS = {
    "the", "and", "for", "that", "with", "this", "from", "are", "was", "were", "you", "your",
    "have", "has", "had", "not", "but", "can", "will", "all", "any", "into", "out", "about",
    "how", "when", "where", "what", "why", "who", "our", "their", "its", "they", "them", "then",
    "than", "also", "only", "more", "most", "such", "use", "using", "used", "each", "per", "new",
    "get", "set", "run", "runs", "let", "like", "very", "just", "over", "under", "through", "across",
    "after", "before", "while", "within", "without", "during", "between", "because", "should", "could",
    "would", "must", "may", "might", "been", "being", "here", "there", "these", "those", "some",
    "other", "same", "many", "much", "few", "another", "document", "documents", "page", "section"
}


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_text_docx(file_path: Path) -> tuple[str, list[str]]:
    doc = Document(str(file_path))
    lines = []
    headings = []
    for paragraph in doc.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        lines.append(text)
        style_name = ""
        if paragraph.style is not None:
            style_name = (paragraph.style.name or "").lower()
        if style_name.startswith("heading") or text.endswith(":"):
            headings.append(text)
    return "\n".join(lines), headings


def _extract_text_mhtml_or_html(file_path: Path) -> tuple[str, list[str]]:
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    headings = []
    for level in range(1, 7):
        for node in soup.find_all(f"h{level}"):
            text = node.get_text(" ", strip=True)
            if text:
                headings.append(text)

    text = soup.get_text("\n", strip=True)
    return text, headings


def _extract_text_txt_or_md(file_path: Path) -> tuple[str, list[str]]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    headings = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            headings.append(stripped.lstrip("#").strip())
        elif stripped.endswith(":") and len(stripped) < 120:
            headings.append(stripped)
    return text, headings


def _extract_text_by_extension(file_path: Path) -> tuple[str, list[str], str]:
    ext = file_path.suffix.lower()
    if ext == ".docx":
        text, headings = _extract_text_docx(file_path)
        return text, headings, "ok"
    if ext in {".mhtml", ".html"}:
        text, headings = _extract_text_mhtml_or_html(file_path)
        return text, headings, "ok"
    if ext in {".txt", ".md"}:
        text, headings = _extract_text_txt_or_md(file_path)
        return text, headings, "ok"
    if ext == ".pdf":
        return "", [], "text_extraction_not_supported"
    return "", [], "unsupported_extension"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z\-']{2,}", text.lower())


def _top_keywords(text: str, limit: int = 25) -> list[tuple[str, int]]:
    words = [w for w in _tokenize(text) if w not in STOP_WORDS]
    counter = Counter(words)
    return counter.most_common(limit)


def _product_name_candidates(text: str, limit: int = 40) -> list[str]:
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9]+(?:[\- ][A-Z][A-Za-z0-9]+){0,3}\b", text)
    filtered = []
    for item in candidates:
        if len(item) < 4:
            continue
        if item.lower() in STOP_WORDS:
            continue
        filtered.append(item.strip())

    counts = Counter(filtered)
    return [name for name, _ in counts.most_common(limit)]


def _first_paragraphs(text: str, max_items: int = 8) -> list[str]:
    chunks = [c.strip() for c in text.split("\n") if c.strip()]
    return chunks[:max_items]


def _relative_path(file_path: Path, root: Path) -> str:
    return str(file_path.relative_to(root)).replace("\\", "/")


def scan_input_folder(input_folder: Path) -> dict:
    files = sorted(
        [p for p in input_folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS],
        key=lambda p: str(p).lower(),
    )

    documents = []
    global_keywords = Counter()
    global_product_names = Counter()

    for file_path in files:
        text, headings, status = _extract_text_by_extension(file_path)
        normalized_text = _normalize_text(text)
        keywords = _top_keywords(normalized_text, limit=25)
        for keyword, count in keywords:
            global_keywords[keyword] += count

        product_candidates = _product_name_candidates(normalized_text, limit=40)
        for product_name in product_candidates:
            global_product_names[product_name] += 1

        doc_info = {
            "file_name": file_path.name,
            "relative_path": _relative_path(file_path, input_folder),
            "extension": file_path.suffix.lower(),
            "status": status,
            "size_bytes": file_path.stat().st_size,
            "word_count": len(normalized_text.split()) if normalized_text else 0,
            "char_count": len(normalized_text),
            "headings": headings[:40],
            "sample_paragraphs": _first_paragraphs(normalized_text, max_items=10),
            "top_keywords": [{"term": k, "count": c} for k, c in keywords],
            "product_name_candidates": product_candidates,
        }
        documents.append(doc_info)

    metadata = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input_folder": str(input_folder),
        "document_count": len(documents),
        "documents": documents,
        "global_top_keywords": [{"term": k, "count": c} for k, c in global_keywords.most_common(100)],
        "global_product_name_candidates": [
            {"value": k, "document_frequency": c} for k, c in global_product_names.most_common(200)
        ],
    }
    return metadata


def write_metadata_outputs(metadata: dict, output_folder: Path) -> dict:
    output_folder.mkdir(parents=True, exist_ok=True)

    json_path = output_folder / "consistency_metadata.json"
    docs_csv_path = output_folder / "consistency_documents.csv"
    keywords_csv_path = output_folder / "consistency_keywords.csv"
    product_names_csv_path = output_folder / "consistency_product_names.csv"

    json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    with docs_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "relative_path", "extension", "status", "size_bytes", "word_count", "char_count",
            "heading_count", "sample_paragraph_count", "top_keywords"
        ])
        for doc in metadata["documents"]:
            top_terms = ", ".join([entry["term"] for entry in doc["top_keywords"][:10]])
            writer.writerow([
                doc["relative_path"],
                doc["extension"],
                doc["status"],
                doc["size_bytes"],
                doc["word_count"],
                doc["char_count"],
                len(doc["headings"]),
                len(doc["sample_paragraphs"]),
                top_terms,
            ])

    with keywords_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["term", "count"])
        for row in metadata["global_top_keywords"]:
            writer.writerow([row["term"], row["count"]])

    with product_names_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate", "document_frequency"])
        for row in metadata["global_product_name_candidates"]:
            writer.writerow([row["value"], row["document_frequency"]])

    return {
        "json": str(json_path),
        "documents_csv": str(docs_csv_path),
        "keywords_csv": str(keywords_csv_path),
        "product_names_csv": str(product_names_csv_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan an input folder and produce metadata for cross-document consistency analysis."
    )
    parser.add_argument(
        "--input-folder",
        required=True,
        help="Folder to scan (for example: input/6360)",
    )
    parser.add_argument(
        "--output-folder",
        default="output/consistency",
        help="Where metadata files are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_folder = Path(args.input_folder).resolve()
    output_folder = Path(args.output_folder).resolve()

    if not input_folder.exists() or not input_folder.is_dir():
        raise SystemExit(f"Input folder not found or not a directory: {input_folder}")

    metadata = scan_input_folder(input_folder)
    outputs = write_metadata_outputs(metadata, output_folder)

    print("Metadata generation complete.")
    print(f"Documents scanned: {metadata['document_count']}")
    print(f"JSON metadata: {outputs['json']}")
    print(f"Documents CSV: {outputs['documents_csv']}")
    print(f"Keywords CSV: {outputs['keywords_csv']}")
    print(f"Product names CSV: {outputs['product_names_csv']}")


if __name__ == "__main__":
    main()
