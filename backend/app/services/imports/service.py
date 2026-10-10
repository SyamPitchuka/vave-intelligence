"""Preview, commit, and roll back workbook imports inside database transactions."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Department,
    Idea,
    IdeaVehicleApplicability,
    ImportBatch,
    ImportChange,
    ImportRowError,
    ImportStagingRow,
    VehicleFamily,
)
from app.services.audit import add_audit
from app.services.imports.mapping import suggest_mapping, unmapped_headers
from app.services.imports.reader import read_tabular
from app.services.imports.validate import validate_mapped_row
from app.services.rejection import is_rejected
from app.services.text import normalize_text

COMPARE_FIELDS = (
    "component",
    "description",
    "stage_status",
    "rejection_category",
    "rejection_reason",
    "idea_type",
    "saving_per_vehicle",
    "idea_belonged_department",
    "rejected_department",
)


def build_preview(
    db: Session,
    *,
    content: bytes,
    filename: str,
    sheet_name: str | None,
    mapping_override: dict[str, str] | None,
    merge_strategy: str,
    is_synthetic: bool,
    allow_partial: bool,
    user_id: uuid.UUID | None,
    storage_dir: Path,
) -> ImportBatch:
    if merge_strategy not in {"insert_only", "update_matching", "reject_conflicts"}:
        raise ValueError("Merge strategy must be insert_only, update_matching, or reject_conflicts.")
    selected, sheets, headers, rows = read_tabular(content, filename, sheet_name)
    suggested = suggest_mapping(headers)
    mapping = dict(suggested)
    if mapping_override:
        unknown = [field for field in mapping_override.values() if field not in suggested.values() and field not in _known_fields()]
        if unknown:
            raise ValueError(f"Unknown target fields: {', '.join(unknown)}.")
        mapping = {header: field for header, field in mapping_override.items() if header in headers and field}
    if "idea_code" not in mapping.values():
        raise ValueError("Map a column to Idea ID before preview can continue.")

    batch = ImportBatch(
        filename=filename,
        sheet_name=selected,
        status="preview",
        merge_strategy=merge_strategy,
        is_synthetic=is_synthetic,
        allow_partial=allow_partial,
        mapping=mapping,
        created_by=user_id,
        summary={"sheets": sheets, "unmapped": unmapped_headers(headers, mapping), "headers": headers},
    )
    db.add(batch)
    db.flush()

    destination = storage_dir / "imports"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"{batch.id}{Path(filename).suffix.lower()}").write_bytes(content)

    seen: set[str] = set()
    errors = 0
    warnings = 0
    for index, raw in enumerate(rows, start=2):
        mapped = {field: raw.get(header) for header, field in mapping.items()}
        payload, issues = validate_mapped_row(mapped, row_number=index, seen_codes=seen)
        for issue in issues:
            if issue["severity"] == "error":
                errors += 1
            else:
                warnings += 1
            db.add(ImportRowError(batch_id=batch.id, **{k: issue[k] for k in ("row_number", "column_name", "severity", "message", "raw_value")}))
        if payload is None:
            db.add(ImportStagingRow(batch_id=batch.id, row_number=index, payload={}, action="error", errors=issues))
            continue
        action, conflict_issues = _plan_action(db, payload, merge_strategy)
        for issue in conflict_issues:
            if issue["severity"] == "error":
                errors += 1
            else:
                warnings += 1
            db.add(
                ImportRowError(
                    batch_id=batch.id,
                    row_number=index,
                    column_name=issue.get("column_name"),
                    severity=issue["severity"],
                    message=issue["message"],
                    raw_value=issue.get("raw_value"),
                )
            )
        issues.extend(conflict_issues)
        if action == "error":
            payload = {}
        db.add(ImportStagingRow(batch_id=batch.id, row_number=index, payload=payload or {}, action=action, errors=issues))

    batch.row_count = len(rows)
    batch.error_count = errors
    batch.warning_count = warnings
    batch.summary = {
        **batch.summary,
        "suggested_mapping": suggested,
        "ready": errors == 0 or allow_partial,
    }
    add_audit(
        db,
        user_id=user_id,
        action="import.preview",
        entity_type="import_batch",
        entity_id=str(batch.id),
        details={"filename": filename, "sheet": selected, "rows": len(rows), "errors": errors, "synthetic": is_synthetic},
    )
    db.flush()
    return batch


def commit_batch(db: Session, batch_id: uuid.UUID, *, confirm: bool, user_id: uuid.UUID | None) -> ImportBatch:
    if not confirm:
        raise ValueError("Commit requires explicit confirmation.")
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise LookupError("Import batch was not found.")
    if batch.status != "preview":
        raise ValueError(f"Batch status is {batch.status}. Only a preview can be committed.")
    if batch.error_count and not batch.allow_partial:
        raise ValueError(
            "This preview has error rows. No records were written. "
            "Fix the workbook or explicitly allow valid rows only."
        )

    families = {item.code: item for item in db.scalars(select(VehicleFamily)).all()}
    inserted = updated = skipped = 0
    staged = db.scalars(select(ImportStagingRow).where(ImportStagingRow.batch_id == batch.id).order_by(ImportStagingRow.row_number)).all()
    for row in staged:
        if row.action in {"error", "skip"} or not row.payload:
            skipped += 1
            continue
        if row.action == "insert":
            idea = _insert_idea(db, row.payload, batch, families, user_id)
            db.add(ImportChange(batch_id=batch.id, idea_id=idea.id, change_type="insert", before_json=None, after_json=_snapshot(idea)))
            inserted += 1
        elif row.action == "update":
            idea = _find_idea(db, row.payload["idea_code"])
            if idea is None:
                skipped += 1
                continue
            before = _snapshot(idea)
            _apply_payload(db, idea, row.payload, families)
            idea.import_batch_id = batch.id
            db.add(ImportChange(batch_id=batch.id, idea_id=idea.id, change_type="update", before_json=before, after_json=_snapshot(idea)))
            updated += 1
        else:
            skipped += 1
    batch.status = "committed"
    batch.inserted_count = inserted
    batch.updated_count = updated
    batch.skipped_count = skipped
    batch.committed_at = datetime.now(UTC)
    add_audit(
        db,
        user_id=user_id,
        action="import.commit",
        entity_type="import_batch",
        entity_id=str(batch.id),
        details={"inserted": inserted, "updated": updated, "skipped": skipped, "strategy": batch.merge_strategy},
    )
    db.flush()
    return batch


def rollback_batch(db: Session, batch_id: uuid.UUID, *, user_id: uuid.UUID | None) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise LookupError("Import batch was not found.")
    if batch.status != "committed":
        raise ValueError("Only a committed batch can be rolled back.")
    changes = db.scalars(select(ImportChange).where(ImportChange.batch_id == batch.id)).all()
    from app.models import DuplicateAnalysisCandidate, DuplicateAnalysisRun

    for change in changes:
        if change.change_type != "insert":
            continue
        used = db.scalar(
            select(func.count()).select_from(DuplicateAnalysisCandidate).where(
                DuplicateAnalysisCandidate.historical_idea_id == change.idea_id
            )
        )
        used_run = db.scalar(
            select(func.count()).select_from(DuplicateAnalysisRun).where(DuplicateAnalysisRun.submission_id == change.idea_id)
        )
        if used or used_run:
            raise ValueError(
                "Rollback stopped because an imported idea is already used in an analysis. "
                "No records were changed."
            )
    families = {item.code: item for item in db.scalars(select(VehicleFamily)).all()}
    for change in changes:
        idea = db.get(Idea, change.idea_id)
        if idea is None:
            continue
        if change.change_type == "insert":
            db.delete(idea)
        elif change.change_type == "update" and change.before_json:
            _apply_payload(db, idea, change.before_json, families)
    batch.status = "rolled_back"
    batch.rolled_back_at = datetime.now(UTC)
    add_audit(
        db,
        user_id=user_id,
        action="import.rollback",
        entity_type="import_batch",
        entity_id=str(batch.id),
        details={"changes": len(changes)},
    )
    db.flush()
    return batch


def _plan_action(db: Session, payload: dict[str, Any], strategy: str) -> tuple[str, list[dict[str, Any]]]:
    existing = _find_idea(db, payload["idea_code"])
    if existing is None:
        return "insert", []
    if strategy == "insert_only":
        return "error", [
            {
                "severity": "error",
                "message": f"Idea ID '{payload['idea_code']}' already exists. Insert-only mode will not change it.",
                "column_name": "idea_code",
                "raw_value": payload["idea_code"],
            }
        ]
    if strategy == "update_matching":
        return "update", [
            {
                "severity": "warning",
                "message": f"Idea ID '{payload['idea_code']}' exists and will be updated. Historical values are snapshotted.",
                "column_name": "idea_code",
                "raw_value": payload["idea_code"],
            }
        ]
    if _conflicts(existing, payload):
        return "error", [
            {
                "severity": "error",
                "message": f"Idea ID '{payload['idea_code']}' conflicts with the stored record. It was not overwritten.",
                "column_name": "idea_code",
                "raw_value": payload["idea_code"],
            }
        ]
    return "skip", [
        {
            "severity": "warning",
            "message": f"Idea ID '{payload['idea_code']}' already matches the stored record and will be skipped.",
            "column_name": "idea_code",
            "raw_value": payload["idea_code"],
        }
    ]


def _conflicts(idea: Idea, payload: dict[str, Any]) -> bool:
    snap = _snapshot(idea)
    for field in COMPARE_FIELDS:
        if str(snap.get(field) or "") != str(payload.get(field) or ""):
            return True
    snap_volumes = sorted(tuple(item) for item in snap.get("volumes") or [])
    new_volumes = sorted((item[0], str(item[1])) for item in payload.get("volumes") or [])
    return snap_volumes != new_volumes


def _find_idea(db: Session, code: str) -> Idea | None:
    return db.scalar(
        select(Idea)
        .options(
            selectinload(Idea.applicability).selectinload(IdeaVehicleApplicability.vehicle_family),
            selectinload(Idea.belonged_department),
            selectinload(Idea.rejected_department),
        )
        .where(func.lower(Idea.idea_code) == code.strip().lower())
    )


def _insert_idea(db: Session, payload: dict[str, Any], batch: ImportBatch, families: dict[str, VehicleFamily], user_id) -> Idea:
    idea = Idea(
        idea_code=payload["idea_code"],
        origin="historical",
        lifecycle_status="historical",
        is_synthetic=batch.is_synthetic,
        source_reference=f"import:{batch.id}:{batch.filename}",
        import_batch_id=batch.id,
        created_by=user_id,
    )
    db.add(idea)
    _apply_payload(db, idea, payload, families)
    db.flush()
    return idea


def _apply_payload(db: Session, idea: Idea, payload: dict[str, Any], families: dict[str, VehicleFamily]) -> None:
    idea.component = payload.get("component")
    idea.description = payload.get("description")
    idea.current_design = payload.get("current_design")
    idea.proposed_change = payload.get("proposed_change")
    idea.engineering_rationale = payload.get("engineering_rationale")
    idea.expected_benefit = payload.get("expected_benefit")
    idea.constraints = payload.get("constraints")
    idea.normalized_text = normalize_text(idea.description)
    idea.idea_generation_date = _date(payload.get("idea_generation_date"))
    idea.rejection_date = _date(payload.get("rejection_date"))
    idea.stage_status = payload.get("stage_status")
    idea.rejection_category = payload.get("rejection_category")
    idea.rejection_reason = payload.get("rejection_reason")
    idea.idea_type = payload.get("idea_type")
    idea.idea_disposition = payload.get("idea_disposition")
    idea.applicable_vehicle_details = payload.get("applicable_vehicle_details")
    idea.saving_per_vehicle = _decimal(payload.get("saving_per_vehicle"))
    idea.reported_total_saving = _decimal(payload.get("reported_total_saving"))
    idea.total_combined_annual_saving = _decimal(payload.get("computed_total"))
    idea.savings_mismatch = bool(payload.get("savings_mismatch"))
    idea.is_rejected = is_rejected(idea.rejection_category)
    belonged = payload.get("idea_belonged_department")
    rejected = payload.get("rejected_department")
    if belonged:
        department = _department(db, belonged)
        idea.idea_belonged_department_id = department.id
        idea.belonged_department = department
    else:
        idea.idea_belonged_department_id = None
        idea.belonged_department = None
    if rejected:
        department = _department(db, rejected)
        idea.rejected_department_id = department.id
        idea.rejected_department = department
    else:
        idea.rejected_department_id = None
        idea.rejected_department = None
    idea.applicability.clear()
    db.flush()
    for family_code, amount in payload.get("volumes") or []:
        family = families.get(family_code)
        if family is None:
            continue
        idea.applicability.append(
            IdeaVehicleApplicability(
                vehicle_family_id=family.id,
                vehicle_family=family,
                annual_volume=Decimal(amount),
            )
        )


def _department(db: Session, name: str) -> Department:
    found = db.scalar(select(Department).where(func.lower(Department.name) == name.strip().lower()))
    if found:
        return found
    created = Department(name=name.strip())
    db.add(created)
    db.flush()
    return created


def _snapshot(idea: Idea) -> dict[str, Any]:
    volumes = []
    for row in idea.applicability:
        code = row.vehicle_family.code if row.vehicle_family is not None else ""
        volumes.append([code, str(row.annual_volume)])
    return {
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
        "rejected_department": idea.rejected_department.name if idea.rejected_department else None,
        "stage_status": idea.stage_status,
        "rejection_category": idea.rejection_category,
        "rejection_reason": idea.rejection_reason,
        "idea_type": idea.idea_type,
        "idea_disposition": idea.idea_disposition,
        "applicable_vehicle_details": idea.applicable_vehicle_details,
        "saving_per_vehicle": str(idea.saving_per_vehicle) if idea.saving_per_vehicle is not None else None,
        "reported_total_saving": str(idea.reported_total_saving) if idea.reported_total_saving is not None else None,
        "computed_total": str(idea.total_combined_annual_saving) if idea.total_combined_annual_saving is not None else None,
        "savings_mismatch": idea.savings_mismatch,
        "is_rejected": idea.is_rejected,
        "volumes": volumes,
    }


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _known_fields() -> set[str]:
    from app.services.imports.mapping import FIELD_ALIASES

    return set(FIELD_ALIASES)
