"""Column mapping. Workbook headers are matched by alias, never by fixed position."""

from __future__ import annotations

import re

FIELD_ALIASES: dict[str, list[str]] = {
    "idea_code": ["idea_id", "idea id", "ideaid", "idea code", "id"],
    "component": ["component", "assembly", "component or assembly"],
    "idea_generation_date": ["idea generation date", "generation date", "idea_generation_date"],
    "idea_belonged_department": ["idea belonged department", "belonged department", "originating department"],
    "rejection_date": ["rejection date"],
    "rejected_department": ["rejected department"],
    "volume_hcv_rigid": ["hcv rigid truck", "hcv rigid"],
    "volume_hcv_tipper": ["hcv tipper"],
    "volume_tractor_trailer": ["tractor trailer", "tractor-trailer"],
    "volume_rmc": ["rmc"],
    "volume_cowl": ["cowl"],
    "description": ["idea_description", "idea description", "description", "technical description"],
    "current_design": ["current design or process", "current design", "current process"],
    "proposed_change": ["proposed technical change", "proposed change", "proposed design"],
    "engineering_rationale": ["engineering rationale", "rationale"],
    "expected_benefit": ["expected benefit", "benefit"],
    "constraints": ["constraints or validation requirements", "constraints", "validation requirements"],
    "stage_status": ["stage_status", "stage status"],
    "rejection_category": ["rejection_category", "rejection category"],
    "rejection_reason": ["rejection_reason", "rejection reason"],
    "idea_type": ["idea_type", "idea type"],
    "applicable_vehicle_details": [
        "applicable vehicle / tonnage details",
        "applicable vehicle tonnage details",
        "applicable vehicle",
        "tonnage details",
    ],
    "saving_per_vehicle": ["saving per vehicle", "saving per vehicle (inr)"],
    "reported_total_saving": [
        "total combined annual saving per idea",
        "total combined annual saving",
        "total saving",
    ],
    "idea_disposition": ["idea disposition", "disposition"],
}

VOLUME_FIELDS = {
    "volume_hcv_rigid": "HCV_RIGID",
    "volume_hcv_tipper": "HCV_TIPPER",
    "volume_tractor_trailer": "TRACTOR_TRAILER",
    "volume_rmc": "RMC",
    "volume_cowl": "COWL",
}


def normalize_header(header: str) -> str:
    text = header.strip().lower().replace("_", " ")
    text = text.replace("(inr)", " ").replace("(annual volume)", " ")
    text = text.replace("annual volume", " ")
    text = re.sub(r"[^a-z0-9/ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Map source header -> canonical field. First match wins; later duplicates stay unmapped."""
    lookup: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup.setdefault(normalize_header(alias), field)
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for header in headers:
        field = lookup.get(normalize_header(header))
        if field and field not in used:
            mapping[header] = field
            used.add(field)
    return mapping


def unmapped_headers(headers: list[str], mapping: dict[str, str]) -> list[str]:
    return [header for header in headers if header not in mapping]
