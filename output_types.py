"""Output type registry and helper functions used by processing workflows."""

OUTPUT_TYPE_REGISTRY = {
    "inline": {
        "label": "Inline (with comments)",
        "suffix": "corrected_inline.docx",
    },
    "uncommented": {
        "label": "Inline (no comments)",
        "suffix": "corrected_uncommented.docx",
    },
    "track_changes": {
        "label": "Track Changes",
        "suffix": "corrected_track_changes.docx",
    },
    "hybrid": {
        "label": "Hybrid (inline + Word comments)",
        "suffix": "corrected_hybrid.docx",
    },
}

DEFAULT_OUTPUT_TYPES = ["inline", "track_changes", "hybrid"]


def normalize_output_types(output_types):
    """Return valid output types in registry order; fallback to defaults."""
    if isinstance(output_types, str):
        requested = [x.strip().lower() for x in output_types.split(',') if x.strip()]
    elif isinstance(output_types, (list, tuple, set)):
        requested = [str(x).strip().lower() for x in output_types if str(x).strip()]
    else:
        requested = []

    requested_set = set(requested)
    normalized = [key for key in OUTPUT_TYPE_REGISTRY if key in requested_set]
    if not normalized:
        return list(DEFAULT_OUTPUT_TYPES)
    return normalized


def serialize_output_types(output_types):
    """Serialize selected output types for config persistence."""
    return ", ".join(normalize_output_types(output_types))


def format_output_types(output_types):
    """Return a human-readable label list for selected output types."""
    selected = normalize_output_types(output_types)
    return ", ".join(OUTPUT_TYPE_REGISTRY[key]["label"] for key in selected)
