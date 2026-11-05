"""Deterministic institution-grouped split assignment for Phase 4."""

from __future__ import annotations

import hashlib
from typing import Literal, Mapping

SplitName = Literal["train", "validation", "test"]
MISSING_GROUP = "<missing_group>"


def _validate_ratios(ratios: Mapping[str, float]) -> None:
    expected = {"train", "validation", "test"}
    if set(ratios) != expected:
        raise ValueError("ratios must contain train, validation, and test")
    if any(value <= 0 for value in ratios.values()):
        raise ValueError("split ratios must be positive")
    if abs(sum(ratios.values()) - 1.0) > 1e-12:
        raise ValueError("split ratios must sum to 1")


def assign_group_split(
    group_value: object,
    *,
    seed: str,
    ratios: Mapping[str, float],
) -> SplitName:
    """Assign a group to one split; every row in the group gets the same split."""

    _validate_ratios(ratios)
    group = MISSING_GROUP if group_value is None or str(group_value).strip() == "" else str(group_value).strip()
    digest = hashlib.sha256(f"{seed}\x1f{group}".encode("utf-8")).digest()
    unit_interval = int.from_bytes(digest, "big") / (1 << 256)
    train_cutoff = ratios["train"]
    validation_cutoff = train_cutoff + ratios["validation"]
    if unit_interval < train_cutoff:
        return "train"
    if unit_interval < validation_cutoff:
        return "validation"
    return "test"


def assign_split_from_row(
    row: Mapping[str, object],
    *,
    group_column: str,
    seed: str,
    ratios: Mapping[str, float],
) -> SplitName:
    return assign_group_split(row.get(group_column), seed=seed, ratios=ratios)
