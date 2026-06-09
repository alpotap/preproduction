# Security Policy

## Reporting a vulnerability

Please report security issues privately to project maintainers.
Do not open public issues for active vulnerabilities.

Include:

- Affected file/area
- Reproduction steps
- Potential impact
- Suggested mitigation (if known)

## Supported versions

Security fixes are applied to the default branch first.

## Release data-hygiene checklist

Before packaging or deploying, verify the release artifact excludes local operational data:

- Exclude `input/` and `output/` directories from deployment bundles.
- Exclude debug and run-history artifacts (for example `output/debug_bundles/`, `output/web_job_history.json`, `output/llm_raw_output.log`).
- Verify environment variables and host-level secrets are used for credentials; do not hardcode API keys or endpoints in source files.
