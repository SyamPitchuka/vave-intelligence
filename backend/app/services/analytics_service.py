"""Dashboard, savings, and rejection aggregates. Totals come from stored calculations."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Department,
    DuplicateAnalysisCandidate,
    DuplicateAnalysisRun,
    Idea,
    IdeaVehicleApplicability,
    ImportRowError,
    ReviewDecision,
    User,
    VehicleFamily,
)


def _idea_ids(db: Session, filters: dict):
    stmt = select(Idea.id)
    origin = filters.get("origin") or "historical"
    if origin != "all":
        stmt = stmt.where(Idea.origin == origin)
    if filters.get("date_from"):
        stmt = stmt.where(Idea.idea_generation_date >= filters["date_from"])
    if filters.get("date_to"):
        stmt = stmt.where(Idea.idea_generation_date <= filters["date_to"])
    if filters.get("department_id"):
        stmt = stmt.where(Idea.idea_belonged_department_id == filters["department_id"])
    if filters.get("stage_status"):
        stmt = stmt.where(Idea.stage_status == filters["stage_status"])
    if filters.get("rejected") is True:
        stmt = stmt.where(Idea.is_rejected.is_(True))
    if filters.get("rejected") is False:
        stmt = stmt.where(Idea.is_rejected.is_(False))
    if filters.get("vehicle_family_id"):
        stmt = stmt.where(
            Idea.id.in_(
                select(IdeaVehicleApplicability.idea_id).where(
                    IdeaVehicleApplicability.vehicle_family_id == filters["vehicle_family_id"]
                )
            )
        )
    return stmt


def dashboard(db: Session, filters: dict) -> dict:
    ids = _idea_ids(db, filters).scalar_subquery()
    total = db.scalar(select(func.count()).select_from(Idea).where(Idea.id.in_(ids))) or 0
    rejected = db.scalar(select(func.count()).select_from(Idea).where(Idea.id.in_(ids), Idea.is_rejected.is_(True))) or 0
    active = db.scalar(select(func.count()).select_from(Idea).where(Idea.id.in_(ids), Idea.is_rejected.is_(False))) or 0
    gross = db.scalar(select(func.coalesce(func.sum(Idea.total_combined_annual_saving), 0)).where(Idea.id.in_(ids)))
    stages = _counts(db, ids, Idea.stage_status, "stage")
    departments = _named_counts(
        db, ids, Idea.idea_belonged_department_id, "ideas"
    )
    rejected_departments = _named_counts(
        db,
        select(Idea.id).where(Idea.id.in_(ids), Idea.is_rejected.is_(True)).scalar_subquery(),
        Idea.rejected_department_id,
        "rejections",
    )
    categories = _counts(
        db,
        select(Idea.id).where(Idea.id.in_(ids), Idea.is_rejected.is_(True)).scalar_subquery(),
        Idea.rejection_category,
        "category",
    )
    reasons = _counts(
        db,
        select(Idea.id).where(Idea.id.in_(ids), Idea.is_rejected.is_(True)).scalar_subquery(),
        Idea.rejection_reason,
        "reason",
    )
    period = func.to_char(Idea.idea_generation_date, "YYYY-MM").label("period")
    trend_rows = db.execute(
        select(period, func.count())
        .where(Idea.id.in_(ids), Idea.idea_generation_date.is_not(None))
        .group_by(period)
        .order_by(period)
    ).all()
    identical = _identical_duplicate_ids(db, ids)
    flagged = set(
        db.scalars(
            select(DuplicateAnalysisCandidate.historical_idea_id).where(
                DuplicateAnalysisCandidate.category == "potential_duplicate",
                DuplicateAnalysisCandidate.historical_idea_id.in_(ids),
            )
        ).all()
    )
    potential = identical | flagged
    awaiting = db.scalar(
        select(func.count())
        .select_from(DuplicateAnalysisRun)
        .where(~select(ReviewDecision.id).where(ReviewDecision.run_id == DuplicateAnalysisRun.id).exists())
    ) or 0
    activity = []
    logs = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    ).all()
    for log, name in logs:
        activity.append(
            {
                "id": str(log.id),
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "actor": name,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
        )
    return {
        "total_ideas": total,
        "active_ideas": active,
        "rejected_ideas": rejected,
        "potential_duplicates": len(potential),
        "identical_text_groups": _identical_group_count(db, ids),
        "awaiting_review": awaiting,
        "total_projected_savings": _float(gross),
        "by_stage": stages,
        "by_department": departments,
        "rejections_by_department": rejected_departments,
        "rejections_by_category": categories,
        "rejections_by_reason": reasons,
        "submission_trend": [{"period": period, "count": count} for period, count in trend_rows],
        "recent_activity": activity,
        "data_quality": _quality(db, ids),
        "savings_by_department": savings(db, filters)["by_department"],
        "savings_by_vehicle_family": savings(db, filters)["by_vehicle_family"],
        "assumptions": _assumptions(filters),
        "dataset_note": "Figures are calculated from stored records. Synthetic imports remain labelled synthetic.",
    }


def savings(db: Session, filters: dict) -> dict:
    ids = _idea_ids(db, filters).scalar_subquery()
    family_id = filters.get("vehicle_family_id")
    gross = db.scalar(select(func.coalesce(func.sum(Idea.total_combined_annual_saving), 0)).where(Idea.id.in_(ids)))
    active_sum = db.scalar(
        select(func.coalesce(func.sum(Idea.total_combined_annual_saving), 0)).where(
            Idea.id.in_(ids), Idea.is_rejected.is_(False)
        )
    )
    rejected_sum = db.scalar(
        select(func.coalesce(func.sum(Idea.total_combined_annual_saving), 0)).where(
            Idea.id.in_(ids), Idea.is_rejected.is_(True)
        )
    )
    by_department = _sum_by_department(db, ids)
    by_stage = _sum_by_column(db, ids, Idea.stage_status, "stage")
    family_stmt = (
        select(
            VehicleFamily.name,
            VehicleFamily.code,
            func.coalesce(func.sum(Idea.saving_per_vehicle * IdeaVehicleApplicability.annual_volume), 0),
        )
        .join(IdeaVehicleApplicability, IdeaVehicleApplicability.vehicle_family_id == VehicleFamily.id)
        .join(Idea, Idea.id == IdeaVehicleApplicability.idea_id)
        .where(Idea.id.in_(ids))
        .group_by(VehicleFamily.name, VehicleFamily.code, VehicleFamily.sort_order)
        .order_by(VehicleFamily.sort_order)
    )
    if family_id:
        family_stmt = family_stmt.where(VehicleFamily.id == family_id)
    by_family = [
        {"name": name, "code": code, "projected_saving": _float(total)}
        for name, code, total in db.execute(family_stmt).all()
    ]
    duplicate_ids = _identical_duplicate_ids(db, ids)
    duplicate_sum = None
    if duplicate_ids:
        duplicate_sum = db.scalar(
            select(func.coalesce(func.sum(Idea.total_combined_annual_saving), 0)).where(Idea.id.in_(duplicate_ids))
        )
    selected_family_total = sum(item["projected_saving"] for item in by_family) if family_id else None
    return {
        "projected_total": _float(selected_family_total if family_id else gross),
        "gross_idea_total": _float(gross),
        "active_projected_saving": _float(active_sum),
        "rejected_projected_saving": _float(rejected_sum),
        "duplicate_associated_projected_saving": _float(duplicate_sum) if duplicate_sum is not None else 0.0,
        "by_department": by_department,
        "by_vehicle_family": by_family,
        "by_stage": by_stage,
        "currency": "INR",
        "kind": "projected",
        "assumptions": _assumptions(filters),
    }


def rejections(db: Session, filters: dict) -> dict:
    filters = {**filters, "rejected": True}
    ids = _idea_ids(db, filters).scalar_subquery()
    rows = db.scalars(select(Idea).where(Idea.id.in_(ids)).order_by(Idea.idea_code)).all()
    return {
        "count": len(rows),
        "by_category": _counts(db, ids, Idea.rejection_category, "category"),
        "by_reason": _counts(db, ids, Idea.rejection_reason, "reason"),
        "by_rejected_department": _named_counts(db, ids, Idea.rejected_department_id, "rejections"),
        "by_belonged_department": _named_counts(db, ids, Idea.idea_belonged_department_id, "ideas"),
        "by_stage": _counts(db, ids, Idea.stage_status, "stage"),
        "note": (
            "A populated rejection category is the dataset rule for rejected. "
            "A blank category is active / not rejected. "
            "These historical outcomes do not automatically invalidate a new idea."
        ),
    }


def _counts(db: Session, ids, column, key: str) -> list[dict]:
    rows = db.execute(
        select(column, func.count()).where(Idea.id.in_(ids), column.is_not(None)).group_by(column).order_by(column)
    ).all()
    return [{key: value, "count": count} for value, count in rows]


def _named_counts(db: Session, ids, column, label: str) -> list[dict]:
    rows = db.execute(
        select(Department.name, func.count())
        .join(Idea, column == Department.id)
        .where(Idea.id.in_(ids))
        .group_by(Department.name)
        .order_by(func.count().desc())
    ).all()
    return [{"name": name, "count": count} for name, count in rows]


def _sum_by_department(db: Session, ids) -> list[dict]:
    rows = db.execute(
        select(Department.name, func.coalesce(func.sum(Idea.total_combined_annual_saving), 0), func.count())
        .join(Idea, Idea.idea_belonged_department_id == Department.id)
        .where(Idea.id.in_(ids))
        .group_by(Department.name)
        .order_by(Department.name)
    ).all()
    return [{"name": name, "projected_saving": _float(total), "count": count} for name, total, count in rows]


def _sum_by_column(db: Session, ids, column, key: str) -> list[dict]:
    rows = db.execute(
        select(column, func.coalesce(func.sum(Idea.total_combined_annual_saving), 0), func.count())
        .where(Idea.id.in_(ids), column.is_not(None))
        .group_by(column)
        .order_by(column)
    ).all()
    return [{key: value, "projected_saving": _float(total), "count": count} for value, total, count in rows]


def _identical_duplicate_ids(db: Session, ids) -> set[uuid.UUID]:
    grouped = (
        select(Idea.normalized_text)
        .where(Idea.id.in_(ids), func.length(Idea.normalized_text) >= 20)
        .group_by(Idea.normalized_text)
        .having(func.count() > 1)
        .scalar_subquery()
    )
    return set(db.scalars(select(Idea.id).where(Idea.id.in_(ids), Idea.normalized_text.in_(grouped))).all())


def _identical_group_count(db: Session, ids) -> int:
    grouped = (
        select(Idea.normalized_text)
        .where(Idea.id.in_(ids), func.length(Idea.normalized_text) >= 20)
        .group_by(Idea.normalized_text)
        .having(func.count() > 1)
    )
    return db.scalar(select(func.count()).select_from(grouped.subquery())) or 0


def _quality(db: Session, ids) -> dict:
    missing_description = db.scalar(
        select(func.count()).select_from(Idea).where(Idea.id.in_(ids), func.coalesce(Idea.description, "") == "")
    ) or 0
    missing_department = db.scalar(
        select(func.count()).select_from(Idea).where(Idea.id.in_(ids), Idea.idea_belonged_department_id.is_(None))
    ) or 0
    mismatch = db.scalar(
        select(func.count()).select_from(Idea).where(Idea.id.in_(ids), Idea.savings_mismatch.is_(True))
    ) or 0
    import_issues = db.scalar(
        select(func.count()).select_from(ImportRowError).where(ImportRowError.severity == "error")
    ) or 0
    return {
        "missing_description": missing_description,
        "missing_department": missing_department,
        "duplicate_idea_ids": 0,
        "savings_mismatch": mismatch,
        "invalid_dates": 0,
        "import_issues": import_issues,
    }


def _assumptions(filters: dict) -> list[str]:
    notes = [
        "Currency is INR.",
        "Figures are projected savings, not verified realised savings.",
        "Total combined annual saving = saving per vehicle × the sum of annual volumes across unique vehicle families.",
        "A repeated vehicle family on the same idea is counted once.",
        "Idea IDs are stored once even when several vehicle families apply.",
        "Duplicate-associated savings are not subtracted from the gross total.",
        "A historical rejection does not by itself invalidate a new idea.",
    ]
    if filters.get("vehicle_family_id"):
        notes.append(
            "With a vehicle family selected, the family chart and the filtered projected total use that family's volume × saving per vehicle."
        )
    return notes


def _float(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(value))
