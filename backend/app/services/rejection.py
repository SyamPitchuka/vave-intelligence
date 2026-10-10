"""Historical rejection rules for the current dataset convention.

Stage status and rejection are independent.
A populated rejection category means rejected.
A blank rejection category means active / not rejected.
Rejection reason does not, by itself, mark a record rejected.
The value Duplicate is a rejection reason, not a stage status.
Rejected department is never inferred from the idea's own department.
"""

from __future__ import annotations

from app.domain.constants import STAGE_STATUSES


class StageStatusError(ValueError):
    pass


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def is_rejected(rejection_category: str | None) -> bool:
    return clean_optional(rejection_category) is not None


def normalize_stage(value: str | None) -> str | None:
    text = clean_optional(value)
    if text is None:
        return None
    stage = text.upper()
    if stage == "DUPLICATE":
        raise StageStatusError(
            "Duplicate is a rejection reason, not a stage status. "
            "Store it in Rejection Reason and set Stage Status to A–F."
        )
    if stage not in STAGE_STATUSES:
        raise StageStatusError("Stage status must be A, B, C, D, E, or F when it is supplied.")
    return stage
