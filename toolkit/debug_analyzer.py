"""Remote debug analyzer and CLI tool for diagnosing remote server issues."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

from toolkit.debug_collector import DebugCollector
from toolkit.providers import get_azure_ai_foundry_settings


class DebugAnalyzer:
    """Analyzes debug bundles to identify and diagnose issues."""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path(__file__).resolve().parent.parent / "output"
        self.collector = DebugCollector(self.output_dir)

    def load_bundle(self, bundle_path: Path) -> dict:
        """Load a debug bundle from disk."""
        try:
            with open(bundle_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load bundle: {e}")
            sys.exit(1)

    def analyze_bundle(self, bundle: dict) -> dict:
        """Analyze a debug bundle and extract diagnostics."""
        analysis = {
            "summary": {},
            "issues": [],
            "recommendations": [],
            "diagnostics": {},
        }

        # Basic info
        analysis["summary"] = {
            "timestamp": bundle.get("timestamp"),
            "job_id": bundle.get("job_id"),
            "task_type": bundle.get("task_type"),
            "status": bundle.get("status"),
        }

        # System analysis
        sys_snapshot = bundle.get("system_snapshot", {})
        self._analyze_system(sys_snapshot, analysis)

        # Configuration analysis
        runtime_config = bundle.get("runtime_config", {})
        self._analyze_config(runtime_config, analysis)

        # Error analysis
        error_details = bundle.get("error_details")
        if error_details:
            self._analyze_error(error_details, analysis)

        # Log analysis
        logs = bundle.get("logs", {})
        self._analyze_logs(logs, analysis)

        # Performance analysis
        perf_metrics = bundle.get("performance_metrics", {})
        if perf_metrics:
            analysis["diagnostics"]["performance"] = perf_metrics

        return analysis

    def _analyze_system(self, sys_snapshot: dict, analysis: dict) -> None:
        """Analyze system metrics for issues."""
        if not sys_snapshot:
            return

        analysis["diagnostics"]["system"] = {
            "hostname": sys_snapshot.get("hostname"),
            "platform": sys_snapshot.get("platform_info", {}).get("system"),
            "python_version": sys_snapshot.get("python_version", "").split("\n")[0],
            "cpu_usage_percent": sys_snapshot.get("cpu_usage"),
            "memory_usage_percent": sys_snapshot.get("memory_usage", {}).get("percent"),
            "disk_usage_percent": sys_snapshot.get("disk_usage", {}).get("percent"),
        }

        # Memory check
        mem = sys_snapshot.get("memory_usage", {})
        if mem.get("percent", 0) > 85:
            analysis["issues"].append(
                f"⚠️  HIGH MEMORY USAGE: {mem.get('percent', 0)}% used "
                f"({mem.get('available_mb', 0):.0f}MB available)"
            )
            analysis["recommendations"].append(
                "Increase available memory or reduce batch size for processing"
            )
        elif mem.get("percent", 0) > 70:
            analysis["issues"].append(
                f"⚠️  MODERATE MEMORY PRESSURE: {mem.get('percent', 0)}% used"
            )

        # Disk check
        disk = sys_snapshot.get("disk_usage", {})
        if disk.get("percent", 0) > 95:
            analysis["issues"].append(
                f"🔴 CRITICAL DISK SPACE: {disk.get('percent', 0)}% full "
                f"(only {disk.get('free_mb', 0):.0f}MB free)"
            )
            analysis["recommendations"].append("FREE UP DISK SPACE IMMEDIATELY")
        elif disk.get("percent", 0) > 90:
            analysis["issues"].append(
                f"🔴 DISK NEARLY FULL: {disk.get('percent', 0)}% used "
                f"({disk.get('free_mb', 0):.0f}MB free)"
            )
            analysis["recommendations"].append("Delete old output/cache files or expand disk")
        elif disk.get("percent", 0) > 80:
            analysis["issues"].append(
                f"⚠️  LOW DISK SPACE: {disk.get('percent', 0)}% used"
            )

        # CPU check
        cpu = sys_snapshot.get("cpu_usage", 0)
        if cpu > 95:
            analysis["issues"].append(f"⚠️  HIGH CPU USAGE: {cpu}%")
            analysis["recommendations"].append("Check for competing processes or reduce parallelism")

    def _analyze_config(self, runtime_config: dict, analysis: dict) -> None:
        """Analyze runtime configuration."""
        if not runtime_config:
            analysis["issues"].append("⚠️  NO RUNTIME CONFIGURATION LOADED")
            analysis["recommendations"].append("Check if configuration file is readable and properly formatted")
            return

        analysis["diagnostics"]["configuration"] = {
            "llm_provider": runtime_config.get("llm_provider", "NOT SET"),
            "llm_model": runtime_config.get("llm_model", "NOT SET"),
            "output_dir": runtime_config.get("output_dir"),
            "input_dir": runtime_config.get("input_dir"),
        }

        # Provider check
        if not runtime_config.get("llm_provider"):
            analysis["issues"].append("🔴 LLM PROVIDER NOT CONFIGURED")
            analysis["recommendations"].append(
                "Set LLM_PROVIDER in environment (ollama|lm_studio|azure_ai_foundry)"
            )
        else:
            analysis["issues"].append(f"✓ LLM Provider: {runtime_config.get('llm_provider')}")

        if not runtime_config.get("llm_model"):
            analysis["issues"].append("🔴 LLM MODEL NOT CONFIGURED")
            analysis["recommendations"].append("Set LLM_MODEL in environment or configuration")

        # Provider-specific checks
        provider = runtime_config.get("llm_provider", "").lower()

        if provider == "azure_ai_foundry":
            foundry_settings = get_azure_ai_foundry_settings(runtime_config)
            if not foundry_settings.get("api_key"):
                analysis["issues"].append("🔴 AZURE AI FOUNDRY: Missing API key")
                analysis["recommendations"].append(
                    "Set AZURE_AI_FOUNDRY_<PROFILE>_API_KEY and include the profile in AZURE_AI_FOUNDRY_PROFILE_IDS"
                )
            endpoint = foundry_settings.get("endpoint", "")
            if not endpoint:
                analysis["issues"].append("🔴 AZURE AI FOUNDRY: Missing endpoint")
                analysis["recommendations"].append(
                    "Set AZURE_AI_FOUNDRY_<PROFILE>_ENDPOINT and include the profile in AZURE_AI_FOUNDRY_PROFILE_IDS"
                )
            elif "services.ai.azure.com" not in endpoint and "cognitiveservices.azure.com" not in endpoint:
                analysis["issues"].append(
                    f"⚠️  AZURE AI FOUNDRY: Unrecognised endpoint domain in '{endpoint}'. "
                    "Expected cognitiveservices.azure.com or services.ai.azure.com."
                )
                analysis["recommendations"].append(
                    "Verify AZURE_AI_FOUNDRY_ENDPOINT matches the endpoint shown in Azure AI Foundry portal."
                )

        elif provider == "lm_studio":
            lm_url = runtime_config.get("lm_studio_base_url", "http://127.0.0.1:1234/v1")
            if not lm_url or "127.0.0.1" in lm_url or "localhost" in lm_url:
                analysis["issues"].append(
                    f"⚠️  LM_STUDIO URL: {lm_url} (may not work if server is remote)"
                )
                analysis["recommendations"].append(
                    "Update LM_STUDIO_BASE_URL to point to actual remote LM Studio server"
                )

    def _analyze_error(self, error_details: dict, analysis: dict) -> None:
        """Analyze error information."""
        error_type = error_details.get("error_type", "Unknown")
        error_msg = error_details.get("error_message", "No message")

        analysis["diagnostics"]["error"] = {
            "type": error_type,
            "message": error_msg,
            "traceback_available": bool(error_details.get("traceback")),
        }

        # Common error patterns
        error_msg_lower = error_msg.lower()
        error_type_lower = error_type.lower()

        if "connection" in error_msg_lower or "refused" in error_msg_lower:
            analysis["issues"].append(f"🔴 CONNECTION ERROR: {error_msg}")
            analysis["recommendations"].append(
                "Verify LLM provider is running and accessible at configured URL"
            )

        elif "timeout" in error_msg_lower:
            analysis["issues"].append(f"⏱️  TIMEOUT ERROR: {error_msg}")
            analysis["recommendations"].append(
                "Increase timeout, reduce input size, or check network connectivity"
            )

        elif "authentication" in error_msg_lower or "unauthorized" in error_msg_lower:
            analysis["issues"].append(f"🔐 AUTHENTICATION ERROR: {error_msg}")
            analysis["recommendations"].append(
                "Verify API credentials (keys, endpoints) are correct and not expired"
            )

        elif "outofmemory" in error_type_lower or "memory" in error_msg_lower:
            analysis["issues"].append(f"💾 MEMORY ERROR: {error_msg}")
            analysis["recommendations"].append(
                "Reduce batch size, limit input size, or increase available memory"
            )

        elif "filenotfound" in error_type_lower or "path" in error_msg_lower:
            analysis["issues"].append(f"📁 FILE/PATH ERROR: {error_msg}")
            analysis["recommendations"].append(
                "Verify input/output paths exist and have correct permissions"
            )

        else:
            analysis["issues"].append(f"❌ {error_type}: {error_msg}")

        # Show traceback
        traceback_text = error_details.get("traceback", "")
        if traceback_text:
            analysis["diagnostics"]["error"]["traceback"] = traceback_text

    def _analyze_logs(self, logs: dict, analysis: dict) -> None:
        """Analyze log content for issues."""
        if not logs:
            analysis["issues"].append("⚠️  NO LOGS CAPTURED")
            return

        for log_name, log_content in logs.items():
            if not log_content or log_content.startswith("[ERROR"):
                continue

            log_lower = log_content.lower()

            # Pattern matching
            if "error" in log_lower:
                lines_with_error = [
                    line for line in log_content.split("\n") if "error" in line.lower()
                ]
                analysis["issues"].extend(
                    [f"Log [{log_name}]: {line[:100]}" for line in lines_with_error[:3]]
                )

            if "exception" in log_lower:
                analysis["issues"].append(f"Exception found in {log_name}")

            if "failed" in log_lower:
                lines_with_failed = [
                    line for line in log_content.split("\n") if "failed" in line.lower()
                ]
                analysis["issues"].extend(
                    [f"Log [{log_name}]: {line[:100]}" for line in lines_with_failed[:3]]
                )

    def format_report(self, analysis: dict) -> str:
        """Format analysis as readable report."""
        lines = [
            "=" * 80,
            "REMOTE DEBUG ANALYSIS REPORT",
            "=" * 80,
            "",
        ]

        # Summary
        summary = analysis.get("summary", {})
        lines.extend([
            f"Job ID:       {summary.get('job_id', 'N/A')}",
            f"Task Type:    {summary.get('task_type', 'N/A')}",
            f"Status:       {summary.get('status', 'N/A')}",
            f"Timestamp:    {summary.get('timestamp', 'N/A')}",
            "",
        ])

        # Issues
        issues = analysis.get("issues", [])
        if issues:
            lines.append("ISSUES FOUND:")
            for issue in issues:
                lines.append(f"  {issue}")
            lines.append("")

        # Recommendations
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            lines.append("RECOMMENDATIONS:")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")

        # Diagnostics
        diagnostics = analysis.get("diagnostics", {})
        if diagnostics:
            lines.append("DETAILED DIAGNOSTICS:")
            lines.append(json.dumps(diagnostics, indent=2))

        lines.extend([
            "",
            "=" * 80,
        ])

        return "\n".join(lines)

    def save_report(self, bundle_path: Path, report_text: str) -> Path:
        """Save analysis report alongside bundle."""
        report_path = bundle_path.with_suffix(".analysis.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        return report_path


def main():
    """CLI entry point for debug analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze remote debug bundles to diagnose issues"
    )
    parser.add_argument(
        "bundle",
        nargs="?",
        help="Path to debug bundle JSON file (or 'latest' for most recent)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List recent debug bundles"
    )
    parser.add_argument(
        "--save", action="store_true", help="Save analysis report to file"
    )
    parser.add_argument(
        "-n", "--count", type=int, default=10, help="Number of bundles to list"
    )

    args = parser.parse_args()

    analyzer = DebugAnalyzer()

    # List bundles
    if args.list:
        print("\n📦 Recent Debug Bundles:\n")
        bundles = analyzer.collector.get_recent_bundles(limit=args.count)
        for bundle_path in bundles:
            try:
                with open(bundle_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(
                    f"  {bundle_path.name}"
                    f"\n    Job: {data.get('job_id')} | Status: {data.get('status')}"
                    f"\n    Task: {data.get('task_type')} | Time: {data.get('timestamp')}"
                    f"\n"
                )
            except Exception as e:
                print(f"  {bundle_path.name} [ERROR: {e}]\n")
        return

    # Analyze a specific bundle
    if not args.bundle:
        print("No bundle specified. Use --list to see available bundles.")
        sys.exit(1)

    # Find bundle
    if args.bundle.lower() == "latest":
        bundles = analyzer.collector.get_recent_bundles(limit=1)
        if not bundles:
            print("No debug bundles found.")
            sys.exit(1)
        bundle_path = bundles[0]
    else:
        bundle_path = Path(args.bundle)
        if not bundle_path.is_absolute():
            # Try finding in debug_bundles directory
            alt_path = analyzer.output_dir / "debug_bundles" / args.bundle
            if alt_path.exists():
                bundle_path = alt_path

    if not bundle_path.exists():
        print(f"Bundle not found: {bundle_path}")
        sys.exit(1)

    # Load and analyze
    print(f"\n📋 Analyzing: {bundle_path.name}\n")
    bundle = analyzer.load_bundle(bundle_path)
    analysis = analyzer.analyze_bundle(bundle)
    report = analyzer.format_report(analysis)

    # Display and optionally save
    print(report)

    if args.save:
        report_path = analyzer.save_report(bundle_path, report)
        print(f"\n✅ Report saved to: {report_path}")


if __name__ == "__main__":
    main()
