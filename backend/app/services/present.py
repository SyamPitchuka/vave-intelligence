"""JSON shapes returned by the API. Missing source fields stay null."""

from __future__ import annotations

from decimal import Decimal

from app.domain.constants import ROLE_PERMISSIONS
from app.models import Idea, User


def money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def permissions_for(user: User) -> list[str]:
    names = {role.name for role in user.roles}
    if "system_administrator" in names:
        return ["*"]
    found: set[str] = set()
    for name in names:
        found |= ROLE_PERMISSIONS.get(name, set())
    return sorted(found)


def user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "timezone": user.timezone,
        "department": user.department.name if user.department else None,
        "roles": [role.name for role in user.roles],
        "role_labels": [role.description for role in user.roles],
        "permissions": permissions_for(user),
    }


def idea_dict(idea: Idea, *, detail: bool = False) -> dict:
    payload = {
        "id": str(idea.id),
        "idea_code": idea.idea_code,
        "component": idea.component,
        "description": idea.description,
        "current_design": idea.current_design,
        "proposed_change": idea.proposed_change,
        "engineering_rationale": idea.engineering_rationale,
        "expected_benefit": idea.expected_benefit,
        "constraints": idea.constraints,
        "idea_generation_date": idea.idea_generation_date.isoformat() if idea.idea_generation_date else None,
        "rejection_date": idea.rejection_date.isoformat() if idea.rejection_date else None,
        "idea_belonged_department": idea.belonged_department.name if idea.belonged_department else None,
        "idea_belonged_department_id": str(idea.idea_belonged_department_id) if idea.idea_belonged_department_id else None,
        "rejected_department": idea.rejected_department.name if idea.rejected_department else None,
        "rejected_department_id": str(idea.rejected_department_id) if idea.rejected_department_id else None,
        "stage_status": idea.stage_status,
        "rejection_category": idea.rejection_category,
        "rejection_reason": idea.rejection_reason,
        "idea_type": idea.idea_type,
        "idea_disposition": idea.idea_disposition,
        "applicable_vehicle_details": idea.applicable_vehicle_details,
        "saving_per_vehicle": money(idea.saving_per_vehicle),
        "reported_total_saving": money(idea.reported_total_saving),
        "total_combined_annual_saving": money(idea.total_combined_annual_saving),
        "savings_mismatch": idea.savings_mismatch,
        "is_rejected": idea.is_rejected,
        "origin": idea.origin,
        "lifecycle_status": idea.lifecycle_status,
        "is_synthetic": idea.is_synthetic,
        "source_reference": idea.source_reference,
        "import_batch_id": str(idea.import_batch_id) if idea.import_batch_id else None,
        "vehicles": [
            {
                "family_code": row.vehicle_family.code if row.vehicle_family else None,
                "family_name": row.vehicle_family.name if row.vehicle_family else None,
                "annual_volume": money(row.annual_volume),
            }
            for row in idea.applicability
        ],
        "created_at": idea.created_at.isoformat() if idea.created_at else None,
        "updated_at": idea.updated_at.isoformat() if idea.updated_at else None,
    }
    if detail:
        batch = idea.import_batch
        payload["import_batch"] = None
        if batch is not None:
            payload["import_batch"] = {
                "id": str(batch.id),
                "filename": batch.filename,
                "sheet_name": batch.sheet_name,
                "status": batch.status,
                "is_synthetic": batch.is_synthetic,
                "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
            }
    return payload
