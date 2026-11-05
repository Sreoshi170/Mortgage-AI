"""Non-mutating preparation of a reviewable future baseline row."""

from __future__ import annotations

from typing import Any, Mapping

from mortgage_precheck.data.ingest import NUMERIC_FIELDS, prepare_operational_features

from .spec import PROPOSED_FEATURES
from .target import construct_candidate_target


def prepare_baseline_row(row: Mapping[str, str]) -> dict[str, Any]:
    """Build a target plus safe candidate features without imputing values.

    This is a design helper, not a fitted preprocessing pipeline. It retains
    ``None`` for missing/special/invalid numeric values and adds status flags;
    it never replaces them with zero or a fabricated value. The source mapping
    is not modified, and only Phase 3's allowlisted operational fields are
    represented.
    """

    candidate = prepare_operational_features(row)
    features = {name: candidate["features"].get(name) for name in PROPOSED_FEATURES}
    statuses = {name: candidate["field_status"].get(name, "missing") for name in PROPOSED_FEATURES}
    safe_features: dict[str, Any] = {}
    for name in PROPOSED_FEATURES:
        safe_features[name] = features[name]
        status = statuses[name]
        safe_features[f"{name}__is_missing_or_special"] = int(status in {"missing", "special"})
        safe_features[f"{name}__is_invalid_or_out_of_range"] = int(status in {"invalid", "out_of_range"})
        if name in NUMERIC_FIELDS and status != "numeric":
            safe_features[name] = None
    return {
        "target": construct_candidate_target(row.get("action_taken")),
        "features": safe_features,
        "field_status": statuses,
        "source_values": {name: candidate["source_values"][name] for name in PROPOSED_FEATURES},
        "source_row_hash": candidate["source_row_hash"],
    }
