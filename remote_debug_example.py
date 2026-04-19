"""Example: Integrating remote debugging into your processing pipeline.

This example shows how to wrap your existing document processing with debug
collection, suitable for running on a remote server.

USAGE:
    On remote server:
    $ py remote_debug_example.py --dev-machine 192.168.1.100
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

# Import debug helper
from toolkit.remote_debug_helper import enable_debug, set_job_context, send_diagnostics, send_completion


def process_document_batch(
    input_dir: Path,
    output_dir: Path,
    job_id: str,
    dev_machine_url: Optional[str] = None,
) -> None:
    """Process a batch of documents with debug collection.

    Args:
        input_dir: Directory containing input documents
        output_dir: Where to save outputs
        job_id: Unique batch identifier
        dev_machine_url: Dev machine URL for sending diagnostics (optional)
    """

    # Step 1: Enable debug collection
    enable_debug(output_dir=output_dir, dev_machine_url=dev_machine_url)

    # Step 2: Set job context for all diagnostics
    set_job_context(
        job_id=job_id,
        task_type="process",
        batch_size=0,  # Will update after scanning
        server="production",
    )

    start_time = time.time()
    messages = [f"Processing batch {job_id}"]
    processed_count = 0

    try:
        # Step 3: Scan input files
        input_dir = Path(input_dir)
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(input_dir.glob("*.docx"))
        if not files:
            messages.append("No .docx files found")
            print(f"[INFO] {messages[-1]}")
            return

        messages.append(f"Found {len(files)} documents to process")
        print(f"[INFO] {messages[-1]}")

        # Update context with actual batch size
        set_job_context(
            job_id=job_id,
            task_type="process",
            batch_size=len(files),
            server="production",
        )

        # Step 4: Process each file
        for i, file_path in enumerate(files):
            try:
                print(f"\n[{i+1}/{len(files)}] Processing: {file_path.name}")
                messages.append(f"Processing: {file_path.name}")

                # REPLACE THIS with your actual processing logic
                # For example:
                # - Load document with python-docx
                # - Send to LLM for corrections
                # - Generate output formats
                # - Save to output_dir

                # Simulated processing
                time.sleep(0.5)  # Simulate work

                # For demo: just copy the file
                output_file = output_dir / f"{file_path.stem}_corrected.docx"
                # output_file.write_bytes(file_path.read_bytes())  # Uncomment to actually copy

                processed_count += 1
                messages.append(f"✓ Completed: {file_path.name}")

                # Optionally: check after each file if running low on resources
                # and send intermediate diagnostics
                if (i + 1) % 10 == 0:
                    print(f"[DEBUG] Processed {i+1}/{len(files)}, checking system...")

            except Exception as file_error:
                messages.append(f"✗ Failed: {file_path.name} - {str(file_error)}")
                print(f"[ERROR] {messages[-1]}")
                # Continue processing other files, but capture this error
                send_diagnostics(
                    messages=messages + [f"Error on file {file_path.name}"],
                    error=file_error,
                    error_context={"file": file_path.name, "processed_so_far": processed_count},
                )

        # Step 5: Send success diagnostics
        elapsed = time.time() - start_time
        messages.append(f"Batch complete: {processed_count}/{len(files)} files processed in {elapsed:.1f}s")
        print(f"\n[SUCCESS] {messages[-1]}")

        send_completion(
            messages=messages,
            performance_metrics={
                "elapsed_seconds": elapsed,
                "files_processed": processed_count,
                "files_total": len(files),
                "avg_time_per_file": elapsed / processed_count if processed_count > 0 else 0,
            },
        )

    except Exception as batch_error:
        elapsed = time.time() - start_time
        messages.append(f"Batch failed after {elapsed:.1f}s")
        print(f"\n[ERROR] {messages[-1]}")

        # Step 6: Send failure diagnostics
        send_diagnostics(
            status="failed",
            messages=messages,
            error=batch_error,
            error_context={
                "processed_count": processed_count,
                "elapsed_seconds": elapsed,
            },
            performance_metrics={
                "elapsed_seconds": elapsed,
                "files_processed": processed_count,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Process document batch with remote debugging"
    )
    parser.add_argument(
        "--input",
        default="input/batch_001",
        help="Input directory with .docx files",
    )
    parser.add_argument(
        "--output",
        default="output/batch_001",
        help="Output directory for results",
    )
    parser.add_argument(
        "--job-id",
        default="batch_001",
        help="Unique job identifier",
    )
    parser.add_argument(
        "--dev-machine",
        help="IP/hostname of dev machine (e.g., 192.168.1.100 or dev.local)",
    )

    args = parser.parse_args()

    # Build dev machine URL
    dev_url = None
    if args.dev_machine:
        # Handle cases like "192.168.1.100" or "dev.local"
        if "://" not in args.dev_machine:
            dev_url = f"http://{args.dev_machine}:8000"
        else:
            dev_url = args.dev_machine

    print(f"""
╔════════════════════════════════════════════════════════════╗
║       DOCUMENT PROCESSING WITH REMOTE DEBUGGING            ║
╚════════════════════════════════════════════════════════════╝

Job ID:              {args.job_id}
Input:               {args.input}
Output:              {args.output}
Dev Machine:         {dev_url or "(none - local diagnostics only)"}
""")

    try:
        process_document_batch(
            input_dir=args.input,
            output_dir=args.output,
            job_id=args.job_id,
            dev_machine_url=dev_url,
        )
        print("\n✅ All done!\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user\n")
        import sys

        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        import sys

        sys.exit(1)


# ============================================================================
# ALTERNATIVE: Query recent diagnostics from dev machine
# ============================================================================


def query_dev_machine_diagnostics(dev_machine_url: str) -> None:
    """Query and display recent diagnostics from dev machine.

    This lets you check "what did the remote server send?" from your local dev machine.
    """
    import requests

    print(f"\n📡 Querying {dev_machine_url}/api/debug/bundles...\n")

    try:
        response = requests.get(f"{dev_machine_url}/api/debug/bundles?limit=5", timeout=5)
        response.raise_for_status()

        data = response.json()
        bundles = data.get("bundles", [])

        if not bundles:
            print("No debug bundles found.")
            return

        print(f"Recent bundles:\n")
        for i, bundle in enumerate(bundles, 1):
            print(f"{i}. {bundle['filename']}")
            print(f"   Job: {bundle['job_id']} | Status: {bundle['status']}")
            print(f"   Task: {bundle['task_type']} | Time: {bundle['timestamp']}\n")

    except Exception as e:
        print(f"Failed to query dev machine: {e}")


if __name__ == "__main__":
    main()
