"""Controlled vocabularies. Source values outside these lists are preserved, not rewritten."""

from __future__ import annotations

STAGE_STATUSES = ("A", "B", "C", "D", "E", "F")

IDEA_DEPARTMENTS = (
    "Cab",
    "Brake",
    "Air intake system",
    "engine",
    "rear axle",
    "steeting",
    "propeller shaft",
    "exterior trims",
    "interior trims",
    "tyres",
    "frame",
    "lamps",
    "ECU",
    "Infotainment system",
    "wiring harness",
    "LV battery",
)

REJECTED_DEPARTMENTS = IDEA_DEPARTMENTS + (
    "vehicle integration",
    "sales",
    "Service",
    "Quality",
    "Purchase",
    "Marketing",
)

VEHICLE_FAMILIES = (
    ("HCV_RIGID", "HCV Rigid Truck", 1),
    ("HCV_TIPPER", "HCV Tipper", 2),
    ("TRACTOR_TRAILER", "Tractor-Trailer", 3),
    ("RMC", "RMC", 4),
    ("COWL", "COWL", 5),
)

REJECTION_CATEGORIES = (
    "Technical feasibility",
    "Durability",
    "Cost",
    "Packaging",
    "Safety / compliance",
    "Already implemented",
    "Duplicate",
    "Commercial",
)

REJECTION_REASONS = (
    "Insufficient strength",
    "Durability concern",
    "Negative business case",
    "Packaging constraint",
    "Regulatory constraint",
    "Already in production",
    "Duplicate",
    "Brand appearance",
)

ROLES = (
    ("system_administrator", "System Administrator"),
    ("vave_engineer", "VAVE Engineer"),
    ("department_reviewer", "Department Reviewer"),
    ("department_head", "Department Head"),
    ("readonly_management", "Read-only Management / Inspection"),
)

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "system_administrator": {"*"},
    "vave_engineer": {
        "dashboard:read",
        "ideas:read",
        "ideas:write",
        "ideas:import",
        "analysis:run",
        "reviews:read",
        "reviews:write",
        "analytics:read",
        "copilot:use",
        "documents:read",
        "documents:write",
        "evaluation:read",
        "evaluation:run",
        "exports:create",
    },
    "department_reviewer": {
        "dashboard:read",
        "ideas:read",
        "analysis:run",
        "reviews:read",
        "reviews:write",
        "analytics:read",
        "copilot:use",
        "documents:read",
        "evaluation:read",
        "exports:create",
    },
    "department_head": {
        "dashboard:read",
        "ideas:read",
        "reviews:read",
        "reviews:write",
        "analytics:read",
        "copilot:use",
        "documents:read",
        "evaluation:read",
        "audit:read",
        "exports:create",
    },
    "readonly_management": {
        "dashboard:read",
        "ideas:read",
        "analytics:read",
        "copilot:use",
        "documents:read_management",
        "evaluation:read",
        "exports:create",
    },
}

ANALYSIS_CATEGORIES = (
    "potential_duplicate",
    "similar_but_distinct",
    "no_strong_match",
    "insufficient_evidence",
)

REVIEW_DECISIONS = (
    "confirm_duplicate",
    "similar_but_distinct",
    "no_duplicate",
    "escalate",
)

MERGE_STRATEGIES = ("insert_only", "update_matching", "reject_conflicts")

EMBEDDING_DIM = 384
DETERMINISTIC_EMBEDDING_MODEL = "deterministic-hash-v1"
