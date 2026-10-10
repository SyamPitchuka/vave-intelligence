"""Idea queries and submission workflow."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Department, Idea, IdeaVehicleApplicability, VehicleFamily
from app.services.rejection import is_rejected, normalize_stage
from app.services.savings import combined_annual_saving
from app.services.text import normalize_text

SORTS = {
    "idea_code": Idea.idea_code,
    "component": Idea.component,
    "idea_generation_date": Idea.idea_generation_date,
    "stage_status": Idea.stage_status,
    "saving_per_vehicle": Idea.saving_per_vehicle,
    "total_combined_annual_saving": Idea.total_combined_annual_saving,
    "created_at": Idea.created_at,
}


def load_idea(db: Session, idea_id: uuid.UUID) -> Idea | None:
    return db.scalar(
        select(Idea)
        .where(Idea.id == idea_id)
        .options(
            selectinload(Idea.applicability).selectinload(IdeaVehicleApplicability.vehicle_family),
            selectinload(Idea.belonged_department),
            selectinload(Idea.rejected_department),
            selectinload(Idea.import_batch),
        )
    )


def list_ideas(db: Session, filters: dict, *, page: int, page_size: int, sort: str, order: str) -> tuple[list[Idea], int]:
    total = db.scalar(_filter(select(func.count()).select_from(Idea), filters)) or 0
    stmt = select(Idea).options(
        selectinload(Idea.applicability).selectinload(IdeaVehicleApplicability.vehicle_family),
        selectinload(Idea.belonged_department),
        selectinload(Idea.rejected_department),
    )
    stmt = _filter(stmt, filters)
    column = SORTS.get(sort, Idea.idea_generation_date)
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc(), Idea.idea_code.asc())
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def search_ideas(db: Session, query: str, limit: int = 8) -> list[Idea]:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    stmt = (
        select(Idea)
        .where(
            or_(
                Idea.idea_code.ilike(pattern, escape="\\"),
                Idea.component.ilike(pattern, escape="\\"),
                Idea.normalized_text.ilike(pattern, escape="\\"),
                cast(Idea.description, String).ilike(pattern, escape="\\"),
            )
        )
        .order_by(Idea.idea_code)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def create_submission(db: Session, payload: dict, user_id: uuid.UUID, *, submit: bool) -> Idea:
    _validate_submission(payload, submit=submit)
    code = (payload.get("idea_code") or "").strip() or _next_code(db)
    if db.scalar(select(Idea.id).where(func.lower(Idea.idea_code) == code.lower())):
        raise ValueError(f"Idea ID '{code}' already exists.")
    idea = Idea(
        idea_code=code,
        origin="submission",
        lifecycle_status="submitted" if submit else "draft",
        is_synthetic=bool(payload.get("is_synthetic", True)),
        source_reference="manual-submission",
        created_by=user_id,
    )
    db.add(idea)
    _fill(db, idea, payload)
    db.flush()
    return load_idea(db, idea.id) or idea


def update_draft(db: Session, idea_id: uuid.UUID, payload: dict, *, submit: bool) -> Idea:
    idea = load_idea(db, idea_id)
    if idea is None:
        raise LookupError("Idea was not found.")
    if idea.origin != "submission" or idea.lifecycle_status not in {"draft", "submitted"}:
        raise ValueError("Historical records are not edited from the submission form. Use an audited import update.")
    _validate_submission(payload, submit=submit)
    idea.lifecycle_status = "submitted" if submit else idea.lifecycle_status
    _fill(db, idea, payload)
    db.flush()
    return load_idea(db, idea.id) or idea


def _validate_submission(payload: dict, *, submit: bool) -> None:
    if not submit:
        return
    description = (payload.get("description") or "").strip()
    if len(description) < 20:
        raise ValueError("A submission needs a technical description of at least 20 characters.")
    if not (payload.get("component") or "").strip():
        raise ValueError("Component or assembly is required to submit an idea.")
    if not (payload.get("idea_belonged_department") or "").strip():
        raise ValueError("Idea belonged department is required to submit an idea.")


def _fill(db: Session, idea: Idea, payload: dict) -> None:
    idea.component = _clean(payload.get("component"))
    idea.description = _clean(payload.get("description"))
    idea.current_design = _clean(payload.get("current_design"))
    idea.proposed_change = _clean(payload.get("proposed_change"))
    idea.engineering_rationale = _clean(payload.get("engineering_rationale"))
    idea.expected_benefit = _clean(payload.get("expected_benefit"))
    idea.constraints = _clean(payload.get("constraints"))
    idea.normalized_text = normalize_text(idea.description)
    idea.idea_generation_date = _date(payload.get("idea_generation_date"))
    idea.rejection_date = _date(payload.get("rejection_date"))
    idea.stage_status = normalize_stage(payload.get("stage_status"))
    idea.rejection_category = _clean(payload.get("rejection_category"))
    idea.rejection_reason = _clean(payload.get("rejection_reason"))
    idea.idea_type = _clean(payload.get("idea_type"))
    idea.idea_disposition = _clean(payload.get("idea_disposition"))
    idea.applicable_vehicle_details = _clean(payload.get("applicable_vehicle_details"))
    idea.is_rejected = is_rejected(idea.rejection_category)
    idea.is_synthetic = bool(payload.get("is_synthetic", idea.is_synthetic))
    belonged = _clean(payload.get("idea_belonged_department"))
    rejected = _clean(payload.get("rejected_department"))
    idea.idea_belonged_department_id = _department(db, belonged).id if belonged else None
    idea.rejected_department_id = _department(db, rejected).id if rejected else None
    saving = _decimal(payload.get("saving_per_vehicle"))
    idea.saving_per_vehicle = saving
    families = {item.code: item for item in db.scalars(select(VehicleFamily)).all()}
    pairs: list[tuple[str, Decimal]] = []
    idea.applicability.clear()
    db.flush()
    for entry in payload.get("vehicles") or []:
        code = entry.get("family_code")
        family = families.get(code)
        if family is None:
            raise ValueError(f"Unknown vehicle family '{code}'.")
        volume = _decimal(entry.get("annual_volume")) or Decimal("0")
        if volume < 0:
            raise ValueError("Annual volume cannot be negative.")
        pairs.append((code, volume))
        idea.applicability.append(
            IdeaVehicleApplicability(vehicle_family_id=family.id, vehicle_family=family, annual_volume=volume)
        )
    total, _warnings = combined_annual_saving(saving, pairs)
    idea.total_combined_annual_saving = total
    idea.reported_total_saving = _decimal(payload.get("reported_total_saving"))


def _department(db: Session, name: str) -> Department:
    found = db.scalar(select(Department).where(func.lower(Department.name) == name.lower()))
    if found:
        return found
    created = Department(name=name)
    db.add(created)
    db.flush()
    return created


def _next_code(db: Session) -> str:
    value = db.execute(text("SELECT nextval('submission_idea_seq')")).scalar()
    return f"VAVE-NEW-{int(value):05d}"


def _filter(stmt, filters: dict):
    if filters.get("origin") and filters["origin"] != "all":
        stmt = stmt.where(Idea.origin == filters["origin"])
    if filters.get("q"):
        escaped = str(filters["q"]).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                Idea.idea_code.ilike(pattern, escape="\\"),
                Idea.component.ilike(pattern, escape="\\"),
                Idea.normalized_text.ilike(pattern, escape="\\"),
            )
        )
    if filters.get("idea_code"):
        stmt = stmt.where(Idea.idea_code.ilike(f"%{filters['idea_code']}%"))
    if filters.get("component"):
        stmt = stmt.where(Idea.component.ilike(f"%{filters['component']}%"))
    if filters.get("department_id"):
        stmt = stmt.where(Idea.idea_belonged_department_id == filters["department_id"])
    if filters.get("rejected_department_id"):
        stmt = stmt.where(Idea.rejected_department_id == filters["rejected_department_id"])
    if filters.get("stage_status"):
        stmt = stmt.where(Idea.stage_status == filters["stage_status"])
    if filters.get("rejection_category"):
        stmt = stmt.where(Idea.rejection_category == filters["rejection_category"])
    if filters.get("rejection_reason"):
        stmt = stmt.where(Idea.rejection_reason == filters["rejection_reason"])
    if filters.get("idea_type"):
        stmt = stmt.where(Idea.idea_type == filters["idea_type"])
    if filters.get("rejected") is True:
        stmt = stmt.where(Idea.is_rejected.is_(True))
    if filters.get("rejected") is False:
        stmt = stmt.where(Idea.is_rejected.is_(False))
    if filters.get("date_from"):
        stmt = stmt.where(Idea.idea_generation_date >= filters["date_from"])
    if filters.get("date_to"):
        stmt = stmt.where(Idea.idea_generation_date <= filters["date_to"])
    if filters.get("rejection_date_from"):
        stmt = stmt.where(Idea.rejection_date >= filters["rejection_date_from"])
    if filters.get("rejection_date_to"):
        stmt = stmt.where(Idea.rejection_date <= filters["rejection_date_to"])
    if filters.get("min_saving") is not None:
        stmt = stmt.where(Idea.saving_per_vehicle >= filters["min_saving"])
    if filters.get("max_saving") is not None:
        stmt = stmt.where(Idea.saving_per_vehicle <= filters["max_saving"])
    if filters.get("min_total") is not None:
        stmt = stmt.where(Idea.total_combined_annual_saving >= filters["min_total"])
    if filters.get("max_total") is not None:
        stmt = stmt.where(Idea.total_combined_annual_saving <= filters["max_total"])
    if filters.get("vehicle_family_id"):
        stmt = stmt.where(
            Idea.id.in_(
                select(IdeaVehicleApplicability.idea_id).where(
                    IdeaVehicleApplicability.vehicle_family_id == filters["vehicle_family_id"]
                )
            )
        )
    if filters.get("lifecycle_status"):
        stmt = stmt.where(Idea.lifecycle_status == filters["lifecycle_status"])
    return stmt


def _clean(value):
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _decimal(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))
