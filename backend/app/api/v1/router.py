"""Versioned HTTP API. Routes stay thin and call services."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.api.deps import client_ip, enforce_rate_limit, get_current_user, require
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.domain.constants import REVIEW_DECISIONS, ROLES, STAGE_STATUSES
from app.models import (
    AuditLog,
    ChatFeedback,
    ChatMessage,
    ChatSession,
    DataSourceConfig,
    Department,
    Document,
    DuplicateAnalysisCandidate,
    DuplicateAnalysisRun,
    EvaluationDataset,
    EvaluationRun,
    Idea,
    ImportBatch,
    ImportRowError,
    ImportStagingRow,
    Job,
    ReviewDecision,
    Role,
    User,
    VehicleFamily,
)
from app.services.analytics_service import dashboard, rejections, savings
from app.services.audit import add_audit
from app.services.copilot.service import answer_question, can_read_document, ingest_bytes, reindex_documents
from app.services.duplicate_detection.service import analyze_submission, latest_decision
from app.services.evaluation_service import run_evaluation
from app.services.ideas.service import create_submission, list_ideas, load_idea, search_ideas, update_draft
from app.services.imports.service import build_preview, commit_batch, rollback_batch
from app.services.llm_providers.factory import build_chat_provider, build_embedding_provider
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider, FallbackChatProvider
from app.services.local_folder import list_local_files, read_local_file
from app.services.present import idea_dict, user_dict
from app.services.settings_store import effective_ai, record_connection_check, save_ai_settings
from app.services.sources.corporate import fetch_rows, test_connection

api = APIRouter(prefix="/api/v1")


class LoginBody(BaseModel):
    email: str
    password: str


class IdeaBody(BaseModel):
    idea_code: str | None = None
    component: str | None = None
    description: str | None = None
    current_design: str | None = None
    proposed_change: str | None = None
    engineering_rationale: str | None = None
    expected_benefit: str | None = None
    constraints: str | None = None
    idea_generation_date: date | None = None
    rejection_date: date | None = None
    idea_belonged_department: str | None = None
    rejected_department: str | None = None
    stage_status: str | None = None
    rejection_category: str | None = None
    rejection_reason: str | None = None
    idea_type: str | None = None
    idea_disposition: str | None = None
    applicable_vehicle_details: str | None = None
    saving_per_vehicle: float | None = None
    reported_total_saving: float | None = None
    is_synthetic: bool = True
    vehicles: list[dict[str, Any]] = Field(default_factory=list)
    submit: bool = False


class CommitBody(BaseModel):
    batch_id: uuid.UUID
    confirm: bool = False


class LocalImportBody(BaseModel):
    filename: str
    sheet_name: str | None = None
    merge_strategy: str = "reject_conflicts"
    is_synthetic: bool = True
    allow_partial: bool = False


class ReviewBody(BaseModel):
    run_id: uuid.UUID
    candidate_id: uuid.UUID | None = None
    decision: str
    rationale: str


class ChatBody(BaseModel):
    message: str
    session_id: uuid.UUID | None = None


class FeedbackBody(BaseModel):
    rating: str
    comment: str | None = None


class SettingsBody(BaseModel):
    mode: str | None = None
    llm_required: bool | None = None
    chat_model: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    retrieval_top_k: int | None = None
    comparison_timeout_seconds: int | None = None
    fuzzy_strong_threshold: float | None = None
    cosine_retrieve_threshold: float | None = None
    semantic_duplicate_threshold: float | None = None
    component_fuzzy_match: bool | None = None
    component_subset_guard: bool | None = None
    lexical_requires_component: bool | None = None
    negation_detection: bool | None = None
    direction_detection: bool | None = None
    scope_comparison: bool | None = None
    symmetric_lexical_fuzzy: bool | None = None
    copilot_top_k: int | None = None
    copilot_distinct_sections: bool | None = None
    copilot_citation_threshold: float | None = None
    dataset_label: str | None = None
    display_timezone: str | None = None


class EvaluationBody(BaseModel):
    dataset_id: uuid.UUID
    fuzzy_strong_threshold: float | None = None
    cosine_retrieve_threshold: float | None = None
    retrieval_k: int | None = None


class UserBody(BaseModel):
    email: str
    full_name: str
    password: str
    role: str
    department: str | None = None


class DataSourceBody(BaseModel):
    view_name: str
    dsn_env_var: str = "CORPORATE_DATABASE_URL"
    is_active: bool = False


def _filters(
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    rejected_department_id: uuid.UUID | None = None,
    stage_status: str | None = None,
    rejected: bool | None = None,
    vehicle_family_id: uuid.UUID | None = None,
    origin: str | None = None,
    q: str | None = None,
    idea_code: str | None = None,
    component: str | None = None,
    rejection_category: str | None = None,
    rejection_reason: str | None = None,
    idea_type: str | None = None,
    rejection_date_from: date | None = None,
    rejection_date_to: date | None = None,
    min_saving: float | None = None,
    max_saving: float | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
    lifecycle_status: str | None = None,
) -> dict[str, Any]:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "department_id": department_id,
        "rejected_department_id": rejected_department_id,
        "stage_status": stage_status,
        "rejected": rejected,
        "vehicle_family_id": vehicle_family_id,
        "origin": origin,
        "q": q,
        "idea_code": idea_code,
        "component": component,
        "rejection_category": rejection_category,
        "rejection_reason": rejection_reason,
        "idea_type": idea_type,
        "rejection_date_from": rejection_date_from,
        "rejection_date_to": rejection_date_to,
        "min_saving": min_saving,
        "max_saving": max_saving,
        "min_total": min_total,
        "max_total": max_total,
        "lifecycle_status": lifecycle_status,
    }


@api.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    database = "ok"
    pgvector = "missing"
    try:
        db.execute(text("SELECT 1"))
        pgvector = "ok" if db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() else "missing"
    except Exception:
        database = "error"
    status = "ok" if database == "ok" and pgvector == "ok" else "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "version": settings.app_version,
        "database": database,
        "pgvector": pgvector,
        "ai_mode": effective_ai(db)["mode"] if database == "ok" else settings.ai_mode,
        "environment": settings.app_env,
    }


@api.post("/auth/login", tags=["auth"])
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    enforce_rate_limit(f"login:{client_ip(request)}", 10)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        add_audit(db, user_id=None, action="auth.login_failed", entity_type="user", entity_id=None, details={"email": body.email.strip().lower()}, ip_address=client_ip(request))
        db.commit()
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Email or password is incorrect."})
    user.last_login_at = datetime.now(UTC)
    token, expires_in = create_access_token(str(user.id))
    add_audit(db, user_id=user.id, action="auth.login", entity_type="user", entity_id=str(user.id), details={}, ip_address=client_ip(request))
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user_dict(user)}


@api.get("/auth/me", tags=["auth"])
def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return user_dict(user)


@api.get("/auth/dev-accounts", tags=["auth"])
def dev_accounts() -> dict[str, Any]:
    settings = get_settings()
    if settings.app_env != "development":
        return {"enabled": False, "accounts": []}
    return {
        "enabled": True,
        "note": "Development accounts only. Disabled unless APP_ENV=development.",
        "accounts": [
            {"email": settings.admin_email, "password": settings.admin_password, "role": "system_administrator"},
            {"email": "engineer@vave.local", "password": settings.demo_user_password, "role": "vave_engineer"},
            {"email": "reviewer@vave.local", "password": settings.demo_user_password, "role": "department_reviewer"},
            {"email": "head@vave.local", "password": settings.demo_user_password, "role": "department_head"},
            {"email": "viewer@vave.local", "password": settings.demo_user_password, "role": "readonly_management"},
        ],
    }


@api.get("/meta/options", tags=["meta"])
def options(db: Session = Depends(get_db), _: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    departments = [
        {"id": str(row.id), "name": row.name}
        for row in db.scalars(select(Department).order_by(Department.name)).all()
    ]
    families = [
        {"id": str(row.id), "code": row.code, "name": row.name}
        for row in db.scalars(select(VehicleFamily).order_by(VehicleFamily.sort_order)).all()
    ]
    categories = sorted({value for value in db.scalars(select(Idea.rejection_category).where(Idea.rejection_category.is_not(None))).all() if value})
    reasons = sorted({row for row in db.scalars(select(Idea.rejection_reason).where(Idea.rejection_reason.is_not(None))).all() if row})
    types = sorted({row for row in db.scalars(select(Idea.idea_type).where(Idea.idea_type.is_not(None))).all() if row})
    return {
        "departments": departments,
        "vehicle_families": families,
        "stage_statuses": list(STAGE_STATUSES),
        "rejection_categories": categories,
        "rejection_reasons": reasons,
        "idea_types": types,
        "roles": [{"name": name, "label": label} for name, label in ROLES],
    }


@api.get("/dashboard/summary", tags=["dashboard"])
def dashboard_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require("dashboard:read")),
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    stage_status: str | None = None,
    rejected: bool | None = None,
    vehicle_family_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return dashboard(
        db,
        _filters(
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            stage_status=stage_status,
            rejected=rejected,
            vehicle_family_id=vehicle_family_id,
            origin="historical",
        ),
    )


@api.get("/ideas", tags=["ideas"])
def ideas(
    db: Session = Depends(get_db),
    _: User = Depends(require("ideas:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort: str = "idea_generation_date",
    order: str = "desc",
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    rejected_department_id: uuid.UUID | None = None,
    stage_status: str | None = None,
    rejected: bool | None = None,
    vehicle_family_id: uuid.UUID | None = None,
    origin: str | None = "historical",
    q: str | None = None,
    idea_code: str | None = None,
    component: str | None = None,
    rejection_category: str | None = None,
    rejection_reason: str | None = None,
    idea_type: str | None = None,
    rejection_date_from: date | None = None,
    rejection_date_to: date | None = None,
    min_saving: float | None = None,
    max_saving: float | None = None,
    min_total: float | None = None,
    max_total: float | None = None,
    lifecycle_status: str | None = None,
) -> dict[str, Any]:
    rows, total = list_ideas(
        db,
        _filters(
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            rejected_department_id=rejected_department_id,
            stage_status=stage_status,
            rejected=rejected,
            vehicle_family_id=vehicle_family_id,
            origin=origin,
            q=q,
            idea_code=idea_code,
            component=component,
            rejection_category=rejection_category,
            rejection_reason=rejection_reason,
            idea_type=idea_type,
            rejection_date_from=rejection_date_from,
            rejection_date_to=rejection_date_to,
            min_saving=min_saving,
            max_saving=max_saving,
            min_total=min_total,
            max_total=max_total,
            lifecycle_status=lifecycle_status,
        ),
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return {"items": [idea_dict(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@api.get("/ideas/search", tags=["ideas"])
def idea_search(q: str, db: Session = Depends(get_db), _: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    rows = search_ideas(db, q.strip(), 8) if q.strip() else []
    return {
        "items": [
            {"id": str(row.id), "idea_code": row.idea_code, "component": row.component, "stage_status": row.stage_status, "is_rejected": row.is_rejected}
            for row in rows
        ]
    }


@api.post("/ideas", tags=["ideas"])
def create_idea(body: IdeaBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("ideas:write"))) -> dict[str, Any]:
    idea = create_submission(db, body.model_dump(mode="json"), user.id, submit=body.submit)
    add_audit(db, user_id=user.id, action="idea.create", entity_type="idea", entity_id=str(idea.id), details={"idea_code": idea.idea_code, "submit": body.submit}, ip_address=client_ip(request))
    db.commit()
    return idea_dict(load_idea(db, idea.id), detail=True)


@api.get("/ideas/{idea_id}", tags=["ideas"])
def idea_detail(idea_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    idea = load_idea(db, idea_id)
    if idea is None:
        raise LookupError("Idea was not found.")
    payload = idea_dict(idea, detail=True)
    audits = db.scalars(select(AuditLog).where(AuditLog.entity_type == "idea", AuditLog.entity_id == str(idea.id)).order_by(AuditLog.created_at.desc()).limit(20)).all()
    payload["audit"] = [
        {"action": row.action, "created_at": row.created_at.isoformat() if row.created_at else None, "details": row.details}
        for row in audits
    ]
    reviews = db.execute(
        select(ReviewDecision, User.full_name)
        .join(DuplicateAnalysisRun, DuplicateAnalysisRun.id == ReviewDecision.run_id)
        .join(User, User.id == ReviewDecision.decided_by)
        .where(or_(DuplicateAnalysisRun.submission_id == idea.id, ReviewDecision.candidate_id.in_(select(DuplicateAnalysisCandidate.id).where(DuplicateAnalysisCandidate.historical_idea_id == idea.id))))
        .order_by(ReviewDecision.created_at.desc())
        .limit(20)
    ).all()
    payload["reviews"] = [
        {"id": str(row.id), "decision": row.decision, "rationale": row.rationale, "ai_recommendation": row.ai_recommendation, "actor": name, "created_at": row.created_at.isoformat()}
        for row, name in reviews
    ]
    return payload


@api.patch("/ideas/{idea_id}", tags=["ideas"])
def patch_idea(idea_id: uuid.UUID, body: IdeaBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("ideas:write"))) -> dict[str, Any]:
    idea = update_draft(db, idea_id, body.model_dump(mode="json"), submit=body.submit)
    add_audit(db, user_id=user.id, action="idea.update", entity_type="idea", entity_id=str(idea.id), details={"idea_code": idea.idea_code}, ip_address=client_ip(request))
    db.commit()
    return idea_dict(load_idea(db, idea.id), detail=True)


@api.post("/ideas/{idea_id}/analyze", tags=["duplicate-detection"])
def analyze(idea_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require("analysis:run"))) -> dict[str, Any]:
    enforce_rate_limit(f"analyze:{user.id}", 30)
    idea = load_idea(db, idea_id)
    if idea is None:
        raise LookupError("Idea was not found.")
    if not (idea.description or "").strip():
        raise ValueError("The idea needs a description before duplicate analysis can run.")
    config, chat, embedder, llm_status, warning = _runtime(db)
    run = analyze_submission(db, idea, user_id=user.id, ai_config=config, chat_provider=chat, embedder=embedder, llm_status=llm_status, warning=warning)
    add_audit(db, user_id=user.id, action="analysis.run", entity_type="duplicate_analysis_run", entity_id=str(run.id), details={"idea_code": idea.idea_code, "provider": run.provider, "outcome": run.outcome_category}, ip_address=client_ip(request))
    db.commit()
    return _analysis(db, run.id)


@api.post("/ideas/analyze-duplicates", tags=["duplicate-detection"])
def analyze_inline(body: IdeaBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("analysis:run"))) -> dict[str, Any]:
    created = create_submission(db, body.model_dump(mode="json"), user.id, submit=True)
    config, chat, embedder, llm_status, warning = _runtime(db)
    run = analyze_submission(db, created, user_id=user.id, ai_config=config, chat_provider=chat, embedder=embedder, llm_status=llm_status, warning=warning)
    add_audit(db, user_id=user.id, action="analysis.run", entity_type="duplicate_analysis_run", entity_id=str(run.id), details={"idea_code": created.idea_code, "provider": run.provider}, ip_address=client_ip(request))
    db.commit()
    return _analysis(db, run.id)


@api.get("/local-folder", tags=["import"])
def local_folder_list(_: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    return {"folder": "data/local", "items": list_local_files()}


@api.post("/ideas/import/from-folder", tags=["import"])
def import_from_folder(
    body: LocalImportBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require("ideas:import")),
) -> dict[str, Any]:
    filename, content = read_local_file(body.filename)
    if Path(filename).suffix.lower() not in {".xlsx", ".csv"}:
        raise ValueError("Load a CSV or XLSX file from the local folder. Other types belong in the knowledge copilot upload.")
    batch = build_preview(
        db,
        content=content,
        filename=filename,
        sheet_name=body.sheet_name,
        mapping_override=None,
        merge_strategy=body.merge_strategy,
        is_synthetic=body.is_synthetic,
        allow_partial=body.allow_partial,
        user_id=user.id,
        storage_dir=get_settings().resolved_storage_dir(),
    )
    add_audit(
        db,
        user_id=user.id,
        action="import.local_folder",
        entity_type="import_batch",
        entity_id=str(batch.id),
        details={"filename": filename},
        ip_address=client_ip(request),
    )
    db.commit()
    return _batch(db, batch.id)


@api.post("/ideas/import/preview", tags=["import"])
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    mapping_json: str | None = Form(None),
    merge_strategy: str = Form("reject_conflicts"),
    is_synthetic: bool = Form(True),
    allow_partial: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require("ideas:import")),
) -> dict[str, Any]:
    import json

    content = await file.read()
    settings = get_settings()
    if len(content) > settings.upload_max_mb * 1024 * 1024:
        raise ValueError(f"The file exceeds the {settings.upload_max_mb} MB limit.")
    mapping = json.loads(mapping_json) if mapping_json else None
    batch = build_preview(
        db,
        content=content,
        filename=file.filename or "upload.xlsx",
        sheet_name=sheet_name,
        mapping_override=mapping,
        merge_strategy=merge_strategy,
        is_synthetic=is_synthetic,
        allow_partial=allow_partial,
        user_id=user.id,
        storage_dir=settings.resolved_storage_dir(),
    )
    db.commit()
    return _batch(db, batch.id)


@api.post("/ideas/import/commit", tags=["import"])
def import_commit(body: CommitBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("ideas:import"))) -> dict[str, Any]:
    batch = commit_batch(db, body.batch_id, confirm=body.confirm, user_id=user.id)
    from app.models import ImportChange

    changed = list(db.scalars(select(ImportChange.idea_id).where(ImportChange.batch_id == batch.id)).all())
    _reindex_ids(db, changed)
    add_audit(db, user_id=user.id, action="import.commit.requested", entity_type="import_batch", entity_id=str(batch.id), details={"inserted": batch.inserted_count}, ip_address=client_ip(request))
    db.commit()
    return _batch(db, batch.id)


@api.get("/ideas/import/batches", tags=["import"])
def import_batches(db: Session = Depends(get_db), _: User = Depends(require("ideas:import"))) -> dict[str, Any]:
    rows = db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(50)).all()
    return {"items": [_batch_summary(row) for row in rows]}


@api.get("/ideas/import/batches/{batch_id}", tags=["import"])
def import_batch(batch_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("ideas:import"))) -> dict[str, Any]:
    return _batch(db, batch_id)


@api.post("/ideas/import/batches/{batch_id}/rollback", tags=["import"])
def import_rollback(batch_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require("ideas:import"))) -> dict[str, Any]:
    batch = rollback_batch(db, batch_id, user_id=user.id)
    db.commit()
    return _batch_summary(batch)


@api.get("/duplicate-analyses", tags=["duplicate-detection"])
def analyses(db: Session = Depends(get_db), _: User = Depends(require("ideas:read")), limit: int = Query(50, le=200)) -> dict[str, Any]:
    rows = db.scalars(select(DuplicateAnalysisRun).order_by(DuplicateAnalysisRun.created_at.desc()).limit(limit)).all()
    return {"items": [_analysis_summary(db, row) for row in rows]}


@api.get("/duplicate-analyses/{analysis_id}", tags=["duplicate-detection"])
def analysis_detail(analysis_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    return _analysis(db, analysis_id)


@api.post("/duplicate-analyses/{analysis_id}/rerun", tags=["duplicate-detection"])
def rerun(analysis_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require("analysis:run"))) -> dict[str, Any]:
    existing = db.get(DuplicateAnalysisRun, analysis_id)
    if existing is None:
        raise LookupError("Analysis was not found.")
    idea = load_idea(db, existing.submission_id)
    if idea is None:
        raise LookupError("The submitted idea was not found.")
    config, chat, embedder, llm_status, warning = _runtime(db)
    run = analyze_submission(db, idea, user_id=user.id, ai_config=config, chat_provider=chat, embedder=embedder, llm_status=llm_status, warning=warning)
    add_audit(db, user_id=user.id, action="analysis.rerun", entity_type="duplicate_analysis_run", entity_id=str(run.id), details={"previous": str(analysis_id)}, ip_address=client_ip(request))
    db.commit()
    return _analysis(db, run.id)


@api.get("/reviews", tags=["reviews"])
def reviews(queue: str | None = None, db: Session = Depends(get_db), _: User = Depends(require("reviews:read"))) -> dict[str, Any]:
    if queue == "pending":
        rows = db.scalars(
            select(DuplicateAnalysisRun)
            .where(~select(ReviewDecision.id).where(ReviewDecision.run_id == DuplicateAnalysisRun.id).exists())
            .order_by(DuplicateAnalysisRun.created_at.desc())
        ).all()
        return {"items": [_analysis_summary(db, row) for row in rows]}
    rows = db.execute(
        select(ReviewDecision, User.full_name).join(User, User.id == ReviewDecision.decided_by).order_by(ReviewDecision.created_at.desc()).limit(100)
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "run_id": str(row.run_id),
                "candidate_id": str(row.candidate_id) if row.candidate_id else None,
                "decision": row.decision,
                "rationale": row.rationale,
                "ai_recommendation": row.ai_recommendation,
                "actor": name,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row, name in rows
        ]
    }


@api.post("/reviews", tags=["reviews"])
def create_review(body: ReviewBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("reviews:write"))) -> dict[str, Any]:
    if body.decision not in REVIEW_DECISIONS:
        raise ValueError("Decision must be confirm_duplicate, similar_but_distinct, no_duplicate, or escalate.")
    if len(body.rationale.strip()) < 10:
        raise ValueError("Enter a rationale of at least 10 characters. The historical record will not be changed.")
    run = db.get(DuplicateAnalysisRun, body.run_id)
    if run is None:
        raise LookupError("Analysis was not found.")
    ai_recommendation = run.outcome_category
    if body.candidate_id:
        candidate = db.get(DuplicateAnalysisCandidate, body.candidate_id)
        if candidate is None or candidate.run_id != run.id:
            raise ValueError("That candidate is not part of this analysis.")
        ai_recommendation = candidate.category
    decision = ReviewDecision(
        run_id=run.id,
        candidate_id=body.candidate_id,
        decision=body.decision,
        rationale=body.rationale.strip(),
        ai_recommendation=ai_recommendation,
        decided_by=user.id,
    )
    db.add(decision)
    db.flush()
    add_audit(
        db,
        user_id=user.id,
        action="review.decide",
        entity_type="review_decision",
        entity_id=str(decision.id),
        details={"decision": body.decision, "ai_recommendation": ai_recommendation, "run_id": str(run.id)},
        ip_address=client_ip(request),
    )
    db.commit()
    return {"id": str(decision.id), "decision": decision.decision, "ai_recommendation": ai_recommendation, "historical_records_changed": False}


@api.get("/reviews/{review_id}", tags=["reviews"])
def review_detail(review_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("reviews:read"))) -> dict[str, Any]:
    row = db.get(ReviewDecision, review_id)
    if row is None:
        raise LookupError("Review was not found.")
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "candidate_id": str(row.candidate_id) if row.candidate_id else None,
        "decision": row.decision,
        "rationale": row.rationale,
        "ai_recommendation": row.ai_recommendation,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@api.get("/analytics/savings", tags=["analytics"])
def savings_view(db: Session = Depends(get_db), _: User = Depends(require("analytics:read")), date_from: date | None = None, date_to: date | None = None, department_id: uuid.UUID | None = None, stage_status: str | None = None, rejected: bool | None = None, vehicle_family_id: uuid.UUID | None = None) -> dict[str, Any]:
    return savings(db, _filters(date_from=date_from, date_to=date_to, department_id=department_id, stage_status=stage_status, rejected=rejected, vehicle_family_id=vehicle_family_id, origin="historical"))


@api.get("/analytics/rejections", tags=["analytics"])
def rejection_view(db: Session = Depends(get_db), _: User = Depends(require("analytics:read")), date_from: date | None = None, date_to: date | None = None, department_id: uuid.UUID | None = None, stage_status: str | None = None, vehicle_family_id: uuid.UUID | None = None) -> dict[str, Any]:
    return rejections(db, _filters(date_from=date_from, date_to=date_to, department_id=department_id, stage_status=stage_status, vehicle_family_id=vehicle_family_id, origin="historical"))


@api.get("/documents", tags=["documents"])
def documents(db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    rows = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    visible = [row for row in rows if can_read_document(user, row.visibility)]
    return {"items": [_document(row) for row in visible]}


@api.post("/documents", tags=["documents"])
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    visibility: str = Form("engineering"),
    is_synthetic: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require("documents:write")),
) -> dict[str, Any]:
    content = await file.read()
    settings = get_settings()
    config, _chat, embedder, _status, _warning = _runtime(db)
    document = ingest_bytes(
        db,
        content=content,
        filename=file.filename or "document.txt",
        title=title,
        visibility=visibility,
        user_id=user.id,
        storage_dir=settings.resolved_storage_dir(),
        embedder=embedder,
        is_synthetic=is_synthetic,
        max_bytes=settings.upload_max_mb * 1024 * 1024,
        max_tokens=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    add_audit(db, user_id=user.id, action="document.upload", entity_type="document", entity_id=str(document.id), details={"filename": document.filename, "visibility": visibility}, ip_address=client_ip(request))
    db.commit()
    return _document(document)


@api.get("/documents/{document_id}", tags=["documents"])
def document_detail(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    document = db.scalar(select(Document).options(selectinload(Document.chunks)).where(Document.id == document_id))
    if document is None or not can_read_document(user, document.visibility):
        raise LookupError("Document was not found.")
    payload = _document(document)
    payload["chunks"] = [
        {"id": str(chunk.id), "chunk_index": chunk.chunk_index, "page_number": chunk.page_number, "section": chunk.section, "section_number": chunk.section_number, "section_heading": chunk.section_heading, "section_path": chunk.section_path, "window": chunk.window, "token_count": chunk.token_count, "excerpt": chunk.content[:400]}
        for chunk in document.chunks
    ]
    return payload


@api.get("/documents/{document_id}/file", tags=["documents"])
def document_file(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))):
    document = db.get(Document, document_id)
    if document is None or not document.storage_path or not can_read_document(user, document.visibility):
        raise LookupError("Document was not found.")
    data = Path(document.storage_path).read_bytes()
    return Response(content=data, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{document.filename}"'})


@api.delete("/documents/{document_id}", tags=["documents"])
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require("documents:write"))) -> dict[str, Any]:
    document = db.get(Document, document_id)
    if document is None:
        raise LookupError("Document was not found.")
    db.delete(document)
    add_audit(db, user_id=user.id, action="document.delete", entity_type="document", entity_id=str(document_id), details={"title": document.title})
    db.commit()
    return {"deleted": True}


@api.post("/copilot/chat", tags=["copilot"])
def copilot_chat(body: ChatBody, request: Request, db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    enforce_rate_limit(f"copilot:{user.id}", 30)
    if not body.message.strip():
        raise ValueError("Enter a question.")
    config, chat, embedder, llm_status, _warning = _runtime(db)
    session, message = answer_question(db, user=user, session_id=body.session_id, message=body.message.strip(), embedder=embedder, chat_provider=chat, ai_config=config, llm_status=llm_status)
    add_audit(db, user_id=user.id, action="copilot.ask", entity_type="chat_message", entity_id=str(message.id), details={"abstained": message.abstained, "provider": message.provider}, ip_address=client_ip(request))
    db.commit()
    return _message(session, message)


@api.get("/copilot/sessions", tags=["copilot"])
def sessions(db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    rows = db.scalars(select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc())).all()
    return {"items": [{"id": str(row.id), "title": row.title, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]}


@api.get("/copilot/sessions/{session_id}", tags=["copilot"])
def session_detail(session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    session = db.scalar(select(ChatSession).options(selectinload(ChatSession.messages)).where(ChatSession.id == session_id, ChatSession.user_id == user.id))
    if session is None:
        raise LookupError("Conversation was not found.")
    return {
        "id": str(session.id),
        "title": session.title,
        "messages": [
            {"id": str(item.id), "role": item.role, "content": item.content, "citations": item.citations, "evidence": item.evidence, "abstained": item.abstained, "answer_mode": item.answer_mode, "abstention_reason": item.abstention_reason, "provider": item.provider, "model": item.model_name, "created_at": item.created_at.isoformat() if item.created_at else None}
            for item in session.messages
        ],
    }


@api.post("/copilot/messages/{message_id}/feedback", tags=["copilot"])
def feedback(message_id: uuid.UUID, body: FeedbackBody, db: Session = Depends(get_db), user: User = Depends(require("copilot:use"))) -> dict[str, Any]:
    if body.rating not in {"up", "down"}:
        raise ValueError("Rating must be up or down.")
    message = db.get(ChatMessage, message_id)
    if message is None:
        raise LookupError("Message was not found.")
    session = db.get(ChatSession, message.session_id)
    if session is None or session.user_id != user.id:
        raise LookupError("Message was not found.")
    row = ChatFeedback(message_id=message.id, user_id=user.id, rating=body.rating, comment=body.comment)
    db.add(row)
    db.commit()
    return {"id": str(row.id), "rating": row.rating}


@api.get("/ai/status", tags=["ai"])
def ai_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict[str, Any]:
    config = effective_ai(db)
    return _status_payload(config)


@api.get("/ai/settings", tags=["ai"])
def ai_settings(db: Session = Depends(get_db), _: User = Depends(require("ideas:read"))) -> dict[str, Any]:
    return _status_payload(effective_ai(db))


@api.put("/ai/settings", tags=["ai"])
def update_ai_settings(body: SettingsBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    if "*" not in set(user_dict(user)["permissions"]):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only a system administrator can change AI settings."})
    updates = {key: value for key, value in body.model_dump().items() if value is not None}
    # An explicit null turns a threshold off, so it is not dropped with the other unset fields.
    for key in ("semantic_duplicate_threshold", "copilot_citation_threshold"):
        if key in body.model_fields_set:
            updates[key] = getattr(body, key)
    config, reindex = save_ai_settings(db, updates, user.id)
    add_audit(db, user_id=user.id, action="ai.settings", entity_type="application_settings", entity_id="ai", details={"mode": config["mode"], "embedding_model": config["embedding_model"], "copilot_citation_threshold": config.get("copilot_citation_threshold"), "reindex_required": reindex}, ip_address=client_ip(request))
    db.commit()
    payload = _status_payload(config)
    payload["reindex_required"] = reindex
    return payload


@api.get("/ai/providers", tags=["ai"])
def providers(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict[str, Any]:
    config = effective_ai(db)
    return {"active": _status_payload(config), "modes": ["online", "offline", "fallback"]}


@api.post("/ai/providers/test", tags=["ai"])
def test_provider(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    if "*" not in set(user_dict(user)["permissions"]):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only a system administrator can test providers."})
    config = effective_ai(db)
    settings = get_settings()
    chat = build_chat_provider(settings, config["mode"], config.get("chat_model"))
    status = chat.status()
    record_connection_check(db, ok=status.available, detail=status.detail)
    db.commit()
    return {"provider": status.provider, "model": status.model, "available": status.available, "detail": status.detail, "external": status.external, "checked_at": effective_ai(db)["last_connection_check"]}


@api.post("/ai/reindex", tags=["ai"])
def reindex(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    if "*" not in set(user_dict(user)["permissions"]):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only a system administrator can re-index embeddings."})
    job = Job(job_type="reindex", status="running", created_by=user.id, message="Re-indexing the active embedding model.")
    db.add(job)
    db.flush()
    ids = list(db.scalars(select(Idea.id)).all())
    _reindex_ids(db, ids)
    config, _chat, embedder, _status, _warning = _runtime(db)
    chunk_count = reindex_documents(db, embedder)
    job.status = "completed"
    job.progress = 100
    job.finished_at = datetime.now(UTC)
    job.result = {"ideas": len(ids), "chunks": chunk_count, "model": embedder.model}
    db.commit()
    return {"id": str(job.id), "status": job.status, "result": job.result}


@api.get("/jobs/{job_id}", tags=["jobs"])
def job_detail(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict[str, Any]:
    job = db.get(Job, job_id)
    if job is None:
        raise LookupError("Job was not found.")
    return {"id": str(job.id), "job_type": job.job_type, "status": job.status, "progress": job.progress, "message": job.message, "result": job.result, "error": job.error}


@api.get("/evaluation/datasets", tags=["evaluation"])
def evaluation_datasets(db: Session = Depends(get_db), _: User = Depends(require("evaluation:read"))) -> dict[str, Any]:
    rows = db.scalars(select(EvaluationDataset).order_by(EvaluationDataset.name)).all()
    return {"items": [{"id": str(row.id), "name": row.name, "description": row.description, "dataset_type": row.dataset_type, "cases": len(row.cases)} for row in rows]}


@api.post("/evaluation/runs", tags=["evaluation"])
def evaluation_run(body: EvaluationBody, db: Session = Depends(get_db), user: User = Depends(require("evaluation:run"))) -> dict[str, Any]:
    config, _chat, embedder, _status, _warning = _runtime(db)
    run = run_evaluation(
        db,
        body.dataset_id,
        user_id=user.id,
        embedder=embedder,
        fuzzy_strong_threshold=body.fuzzy_strong_threshold or float(config["fuzzy_strong_threshold"]),
        cosine_retrieve_threshold=body.cosine_retrieve_threshold or float(config["cosine_retrieve_threshold"]),
        retrieval_k=body.retrieval_k or int(config["retrieval_top_k"]),
        provider=config["mode"],
        embedding_model=embedder.model,
    )
    db.commit()
    return _evaluation(run)


@api.get("/evaluation/runs", tags=["evaluation"])
def evaluation_runs(db: Session = Depends(get_db), _: User = Depends(require("evaluation:read"))) -> dict[str, Any]:
    rows = db.scalars(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(30)).all()
    return {"items": [_evaluation(row) for row in rows]}


@api.get("/evaluation/runs/{run_id}", tags=["evaluation"])
def evaluation_run_detail(run_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("evaluation:read"))) -> dict[str, Any]:
    run = db.scalar(select(EvaluationRun).options(selectinload(EvaluationRun.predictions)).where(EvaluationRun.id == run_id))
    if run is None:
        raise LookupError("Evaluation run was not found.")
    payload = _evaluation(run)
    payload["predictions"] = [
        {"case_id": str(item.case_id), "predicted": item.predicted, "rank": item.rank, "scores": item.scores} for item in run.predictions
    ]
    return payload


@api.get("/audit-logs", tags=["audit"])
def audit_logs(q: str | None = None, db: Session = Depends(get_db), _: User = Depends(require("audit:read"))) -> dict[str, Any]:
    stmt = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id).order_by(AuditLog.created_at.desc()).limit(200)
    if q:
        stmt = stmt.where(AuditLog.action.ilike(f"%{q}%"))
    rows = db.execute(stmt).all()
    return {
        "items": [
            {"id": str(row.id), "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "actor": name, "details": row.details, "ip_address": row.ip_address, "created_at": row.created_at.isoformat() if row.created_at else None}
            for row, name in rows
        ]
    }


@api.get("/notifications", tags=["audit"])
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(8)).all()
    return {"items": [{"id": str(row.id), "action": row.action, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]}


@api.get("/admin/users", tags=["admin"])
def users(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return _guard_admin(db, user)


@api.post("/admin/users", tags=["admin"])
def create_user(body: UserBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_admin(user)
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise ValueError("A user with that email already exists.")
    role = db.scalar(select(Role).where(Role.name == body.role))
    if role is None:
        raise ValueError("Unknown role.")
    from app.core.security import hash_password

    department = None
    if body.department:
        department = db.scalar(select(Department).where(func.lower(Department.name) == body.department.lower()))
        if department is None:
            raise ValueError("Unknown department.")
    created = User(email=body.email.strip().lower(), full_name=body.full_name.strip(), hashed_password=hash_password(body.password), department_id=department.id if department else None)
    created.roles = [role]
    db.add(created)
    db.flush()
    add_audit(db, user_id=user.id, action="user.create", entity_type="user", entity_id=str(created.id), details={"email": created.email, "role": body.role}, ip_address=client_ip(request))
    db.commit()
    return user_dict(created)


@api.get("/admin/data-sources", tags=["admin"])
def data_sources(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_admin(user)
    rows = db.scalars(select(DataSourceConfig)).all()
    return {
        "excel_mode_available": True,
        "items": [
            {"id": str(row.id), "name": row.name, "driver": row.driver, "dsn_env_var": row.dsn_env_var, "view_name": row.view_name, "is_active": row.is_active, "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None, "last_error": row.last_error, "secret_stored": False}
            for row in rows
        ],
    }


@api.put("/admin/data-sources", tags=["admin"])
def update_data_source(body: DataSourceBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_admin(user)
    row = db.scalar(select(DataSourceConfig).limit(1))
    if row is None:
        row = DataSourceConfig(name="Corporate historical ideas")
        db.add(row)
    row.view_name = body.view_name
    row.dsn_env_var = body.dsn_env_var
    row.is_active = body.is_active
    db.commit()
    return {"id": str(row.id), "view_name": row.view_name, "dsn_env_var": row.dsn_env_var, "is_active": row.is_active}


@api.post("/admin/data-sources/test", tags=["admin"])
def test_data_source(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_admin(user)
    row = db.scalar(select(DataSourceConfig).limit(1))
    if row is None:
        raise ValueError("No corporate source is configured. Excel mode remains available.")
    try:
        detail = test_connection(row.dsn_env_var, row.view_name)
        row.last_error = None
    except Exception as exc:  # noqa: BLE001 — the administrator needs the connection error
        detail = str(exc)
        row.last_error = detail[:500]
        row.last_checked_at = datetime.now(UTC)
        db.commit()
        raise ValueError(detail) from exc
    row.last_checked_at = datetime.now(UTC)
    db.commit()
    return {"ok": True, "detail": detail}


@api.post("/admin/data-sources/sync", tags=["admin"])
def sync_data_source(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_admin(user)
    row = db.scalar(select(DataSourceConfig).where(DataSourceConfig.is_active.is_(True)))
    if row is None:
        raise ValueError("No active corporate source is configured. The application remains usable from Excel imports.")
    rows = fetch_rows(row.dsn_env_var, row.view_name)
    return {"fetched": len(rows), "note": "Rows were read with the fixed column list. Review them through import preview before committing changes."}


@api.get("/exports/ideas", tags=["exports"])
def export_ideas(request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx", origin: str | None = "historical", rejected: bool | None = None, stage_status: str | None = None, department_id: uuid.UUID | None = None):
    rows, _total = list_ideas(db, _filters(origin=origin, rejected=rejected, stage_status=stage_status, department_id=department_id), page=1, page_size=5000, sort="idea_code", order="asc")
    add_audit(db, user_id=user.id, action="export.ideas", entity_type="idea", entity_id=None, details={"rows": len(rows), "format": format}, ip_address=client_ip(request))
    db.commit()
    table = [["Idea ID", "Component", "Department", "Stage", "Rejected", "Rejection category", "Rejection reason", "Saving per vehicle (INR)", "Projected annual saving (INR)", "Synthetic", "Generation date"]]
    for idea in rows:
        item = idea_dict(idea)
        table.append([item["idea_code"], item["component"], item["idea_belonged_department"], item["stage_status"], item["is_rejected"], item["rejection_category"], item["rejection_reason"], item["saving_per_vehicle"], item["total_combined_annual_saving"], item["is_synthetic"], item["idea_generation_date"]])
    return _file(table, "vave-ideas", format, "Historical ideas")


@api.get("/exports/import-errors/{batch_id}", tags=["exports"])
def export_errors(batch_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require("ideas:import")), format: str = "csv"):
    rows = db.scalars(select(ImportRowError).where(ImportRowError.batch_id == batch_id).order_by(ImportRowError.row_number)).all()
    table = [["Row", "Column", "Severity", "Message", "Raw value"]]
    for row in rows:
        table.append([row.row_number, row.column_name, row.severity, row.message, row.raw_value])
    return _file(table, "vave-import-errors", format, "Import validation errors")


@api.get("/exports/analyses", tags=["exports"])
def export_analyses(request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx"):
    rows = db.scalars(select(DuplicateAnalysisRun).order_by(DuplicateAnalysisRun.created_at.desc()).limit(500)).all()
    table = [["Analysis ID", "Idea ID", "Outcome", "Provider", "LLM status", "Human decision recorded", "Created at (UTC)"]]
    for run in rows:
        summary = _analysis_summary(db, run)
        table.append([summary["id"], summary["idea_code"], summary["outcome_category"], summary["provider"], summary["llm_status"], summary["has_human_decision"], summary["created_at"]])
    add_audit(db, user_id=user.id, action="export.analyses", entity_type="duplicate_analysis_run", entity_id=None, details={"rows": len(rows)}, ip_address=client_ip(request))
    db.commit()
    return _file(table, "vave-duplicate-analyses", format, "Duplicate analysis results")


@api.get("/exports/reviews", tags=["exports"])
def export_reviews(request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx"):
    rows = db.execute(
        select(ReviewDecision, User.full_name).join(User, User.id == ReviewDecision.decided_by).order_by(ReviewDecision.created_at.desc()).limit(1000)
    ).all()
    table = [["Review ID", "Analysis ID", "Human decision", "AI recommendation", "Rationale", "Reviewer", "Created at (UTC)"]]
    for row, name in rows:
        table.append([str(row.id), str(row.run_id), row.decision, row.ai_recommendation, row.rationale, name, row.created_at.isoformat() if row.created_at else None])
    add_audit(db, user_id=user.id, action="export.reviews", entity_type="review_decision", entity_id=None, details={"rows": len(rows)}, ip_address=client_ip(request))
    db.commit()
    return _file(table, "vave-review-decisions", format, "Review decisions")


@api.get("/exports/savings", tags=["exports"])
def export_savings(request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx"):
    payload = savings(db, _filters(origin="historical"))
    table = [["Department", "Idea count", "Projected annual saving (INR)"]]
    for row in payload["by_department"]:
        table.append([row["name"], row["count"], row["projected_saving"]])
    table.append([])
    table.append(["Vehicle family", "Code", "Projected annual saving (INR)"])
    for row in payload["by_vehicle_family"]:
        table.append([row["name"], row["code"], row["projected_saving"]])
    add_audit(db, user_id=user.id, action="export.savings", entity_type="idea", entity_id=None, details={"kind": "projected"}, ip_address=client_ip(request))
    db.commit()
    return _file(table, "vave-savings", format, "Projected savings analysis (INR)")


@api.get("/exports/rejections", tags=["exports"])
def export_rejections(request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx"):
    payload = rejections(db, _filters(origin="historical"))
    table = [["Rejection category", "Count"]]
    for row in payload["by_category"]:
        table.append([row["category"], row["count"]])
    table.append([])
    table.append(["Rejection reason", "Count"])
    for row in payload["by_reason"]:
        table.append([row["reason"], row["count"]])
    add_audit(db, user_id=user.id, action="export.rejections", entity_type="idea", entity_id=None, details={"count": payload["count"]}, ip_address=client_ip(request))
    db.commit()
    return _file(table, "vave-rejections", format, "Historical rejection analysis")


@api.get("/exports/evaluation/{run_id}", tags=["exports"])
def export_evaluation(run_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require("exports:create")), format: str = "xlsx"):
    run = db.scalar(select(EvaluationRun).options(selectinload(EvaluationRun.predictions)).where(EvaluationRun.id == run_id))
    if run is None:
        raise LookupError("Evaluation run was not found.")
    table = [["Metric group", "Key", "Value"]]
    for group, body in (run.metrics or {}).items():
        if isinstance(body, dict):
            for key, value in body.items():
                table.append([group, key, value])
        else:
            table.append(["metrics", group, body])
    table.append([])
    table.append(["Case ID", "Predicted", "Rank"])
    for item in run.predictions:
        table.append([str(item.case_id), item.predicted, item.rank])
    add_audit(db, user_id=user.id, action="export.evaluation", entity_type="evaluation_run", entity_id=str(run.id), details={}, ip_address=client_ip(request))
    db.commit()
    return _file(table, "vave-evaluation", format, "Evaluation results")


def _runtime(db: Session):
    config = effective_ai(db)
    settings = get_settings()
    mode = config["mode"]
    warning = " ".join(config.get("runtime_warnings") or []) or None
    llm_status = "not_run"
    if mode == "online":
        chat = build_chat_provider(settings, mode, config.get("chat_model"))
        llm_status = "pending"
    elif mode == "offline":
        chat = build_chat_provider(settings, mode, config.get("chat_model"))
        status = chat.status()
        if not status.available:
            if config.get("llm_required"):
                from app.services.llm_providers.base import ProviderUnavailable

                raise ProviderUnavailable(status.detail)
            warning = ((warning + " ") if warning else "") + status.detail + " Deterministic comparison was used. No external provider was contacted."
            chat = FallbackChatProvider()
            llm_status = "unavailable"
        else:
            llm_status = "pending"
    else:
        chat = FallbackChatProvider()
    try:
        embedder = build_embedding_provider(settings, mode if mode != "fallback" else "fallback", config["embedding_provider"], config["embedding_model"])
        status = embedder.status()
        if not getattr(status, "available", True):
            raise RuntimeError(status.detail)
    except Exception as exc:
        if mode == "online" and config["embedding_provider"] == "openai":
            raise
        warning = ((warning + " ") if warning else "") + f"{exc} Deterministic embeddings were used instead."
        embedder = DeterministicEmbeddingProvider()
    config["embedding_model"] = embedder.model
    config["embedding_provider"] = embedder.name
    return config, chat, embedder, llm_status, warning


def _reindex_ids(db: Session, idea_ids: list[uuid.UUID]) -> None:
    if not idea_ids:
        return
    _config, _chat, embedder, _status, _warning = _runtime(db)
    from app.services.embeddings.index import idea_embedding_text, upsert_embedding

    for idea_id in idea_ids:
        idea = load_idea(db, idea_id)
        if idea is None:
            continue
        upsert_embedding(db, entity_type="idea", entity_id=idea.id, model_name=embedder.model, text=idea_embedding_text(idea), embedder=embedder)


def _analysis(db: Session, analysis_id: uuid.UUID) -> dict[str, Any]:
    run = db.scalar(
        select(DuplicateAnalysisRun)
        .options(selectinload(DuplicateAnalysisRun.candidates))
        .where(DuplicateAnalysisRun.id == analysis_id)
    )
    if run is None:
        raise LookupError("Analysis was not found.")
    submission = load_idea(db, run.submission_id)
    decision = latest_decision(db, run.id)
    candidates = []
    for candidate in sorted(run.candidates, key=lambda item: item.rank):
        historical = load_idea(db, candidate.historical_idea_id)
        candidates.append(
            {
                "id": str(candidate.id),
                "rank": candidate.rank,
                "category": candidate.category,
                "heuristic_category": candidate.heuristic_category,
                "llm_category": candidate.llm_category,
                "disagreement": candidate.disagreement,
                "cosine_similarity": float(candidate.cosine_similarity) if candidate.cosine_similarity is not None else None,
                "fuzzy_score": float(candidate.fuzzy_score) if candidate.fuzzy_score is not None else None,
                "exact_match": candidate.exact_match,
                "explanation": candidate.explanation,
                "similarities": candidate.similarities,
                "differences": candidate.differences,
                "evidence": candidate.evidence,
                "historical": idea_dict(historical) if historical else None,
            }
        )
    return {
        "id": str(run.id),
        "status": run.status,
        "outcome_category": run.outcome_category,
        "provider": run.provider,
        "chat_model": run.chat_model,
        "embedding_model": run.embedding_model,
        "retrieval_k": run.retrieval_k,
        "llm_status": run.llm_status,
        "warning": run.warning,
        "config": run.config,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "submission": idea_dict(submission) if submission else None,
        "candidates": candidates,
        "human_decision": None
        if decision is None
        else {"id": str(decision.id), "decision": decision.decision, "rationale": decision.rationale, "ai_recommendation": decision.ai_recommendation, "created_at": decision.created_at.isoformat()},
        "score_note": "Cosine similarity and fuzzy score are retrieval signals, not calibrated probabilities.",
    }


def _analysis_summary(db: Session, run: DuplicateAnalysisRun) -> dict[str, Any]:
    submission = db.get(Idea, run.submission_id)
    decision = latest_decision(db, run.id)
    return {
        "id": str(run.id),
        "idea_code": submission.idea_code if submission else None,
        "submission_id": str(run.submission_id),
        "outcome_category": run.outcome_category,
        "provider": run.provider,
        "llm_status": run.llm_status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "has_human_decision": decision is not None,
    }


def _batch(db: Session, batch_id: uuid.UUID) -> dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise LookupError("Import batch was not found.")
    errors = db.scalars(select(ImportRowError).where(ImportRowError.batch_id == batch.id).order_by(ImportRowError.row_number).limit(200)).all()
    payload = _batch_summary(batch)
    payload["errors"] = [
        {"row_number": row.row_number, "column_name": row.column_name, "severity": row.severity, "message": row.message, "raw_value": row.raw_value}
        for row in errors
    ]
    payload["mapping"] = batch.mapping
    payload["summary"] = batch.summary
    staged = db.scalars(
        select(ImportStagingRow).where(ImportStagingRow.batch_id == batch.id).order_by(ImportStagingRow.row_number).limit(25)
    ).all()
    payload["preview_rows"] = [
        {
            "row_number": row.row_number,
            "action": row.action,
            "idea_code": (row.payload or {}).get("idea_code"),
            "component": (row.payload or {}).get("component"),
            "stage_status": (row.payload or {}).get("stage_status"),
            "rejection_category": (row.payload or {}).get("rejection_category"),
        }
        for row in staged
    ]
    return payload


def _batch_summary(batch: ImportBatch) -> dict[str, Any]:
    return {
        "id": str(batch.id),
        "filename": batch.filename,
        "sheet_name": batch.sheet_name,
        "status": batch.status,
        "merge_strategy": batch.merge_strategy,
        "is_synthetic": batch.is_synthetic,
        "allow_partial": batch.allow_partial,
        "row_count": batch.row_count,
        "inserted_count": batch.inserted_count,
        "updated_count": batch.updated_count,
        "skipped_count": batch.skipped_count,
        "error_count": batch.error_count,
        "warning_count": batch.warning_count,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
    }


def _document(row: Document) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "status": row.status,
        "visibility": row.visibility,
        "is_synthetic": row.is_synthetic,
        "page_count": row.page_count,
        "document_number": row.document_number,
        "document_type": row.document_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _message(session: ChatSession, message: ChatMessage) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "message_id": str(message.id),
        "answer": message.content,
        "citations": message.citations,
        "evidence": message.evidence,
        "abstained": message.abstained,
        "answer_mode": message.answer_mode,
        "abstention_reason": message.abstention_reason,
        "provider": message.provider,
        "model": message.model_name,
    }


def _status_payload(config: dict[str, Any]) -> dict[str, Any]:
    mode = config["mode"]
    labels = {"online": "Online API", "offline": "OFFLINE / LOCAL", "fallback": "Deterministic fallback"}
    return {
        "mode": mode,
        "mode_label": labels.get(mode, mode),
        "provider": "openai" if mode == "online" else "ollama" if mode == "offline" else "deterministic",
        "chat_model": config.get("chat_model"),
        "embedding_provider": config.get("embedding_provider"),
        "embedding_model": config.get("embedding_model"),
        "embedding_dimensions": config.get("embedding_dimensions"),
        "retrieval_top_k": config.get("retrieval_top_k"),
        "comparison_timeout_seconds": config.get("comparison_timeout_seconds"),
        "fuzzy_strong_threshold": config.get("fuzzy_strong_threshold"),
        "cosine_retrieve_threshold": config.get("cosine_retrieve_threshold"),
        "semantic_duplicate_threshold": config.get("semantic_duplicate_threshold"),
        "component_fuzzy_match": config.get("component_fuzzy_match"),
        "component_subset_guard": config.get("component_subset_guard"),
        "lexical_requires_component": config.get("lexical_requires_component"),
        "negation_detection": config.get("negation_detection"),
        "direction_detection": config.get("direction_detection"),
        "scope_comparison": config.get("scope_comparison"),
        "symmetric_lexical_fuzzy": config.get("symmetric_lexical_fuzzy"),
        "copilot_top_k": config.get("copilot_top_k"),
        "copilot_distinct_sections": config.get("copilot_distinct_sections"),
        "copilot_citation_threshold": config.get("copilot_citation_threshold"),
        "llm_required": config.get("llm_required"),
        "dataset_label": config.get("dataset_label"),
        "display_timezone": config.get("display_timezone"),
        "external_inference_blocked": config.get("external_inference_blocked"),
        "openai_configured": config.get("openai_configured"),
        "runtime_warnings": config.get("runtime_warnings") or [],
        "last_connection_check": config.get("last_connection_check"),
        "last_connection_ok": config.get("last_connection_ok"),
        "last_connection_detail": config.get("last_connection_detail"),
        "threshold_note": "Thresholds are configuration values. Calibrate them with the evaluation module. They are not a validated accuracy claim.",
    }


def _evaluation(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "dataset_id": str(run.dataset_id),
        "provider": run.provider,
        "embedding_model": run.embedding_model,
        "status": run.status,
        "metrics": run.metrics,
        "notes": run.notes,
        "config": run.config,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _ensure_admin(user: User) -> None:
    if "*" not in set(user_dict(user)["permissions"]):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Only a system administrator can do this."})


def _guard_admin(db: Session, user: User) -> dict[str, Any]:
    _ensure_admin(user)
    rows = db.scalars(select(User).options(selectinload(User.roles), selectinload(User.department)).order_by(User.email)).all()
    return {"items": [user_dict(row) for row in rows]}


def _file(table: list[list], stem: str, format: str, title: str):
    generated = datetime.now(UTC).isoformat()
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([title, "Generated at (UTC)", generated, "Unit", "INR where savings are shown"])
        writer.writerow([])
        writer.writerows(table)
        data = buffer.getvalue().encode("utf-8")
        media = "text/csv"
        filename = f"{stem}.csv"
    else:
        book = Workbook()
        sheet = book.active
        sheet.title = "Report"
        sheet.append([title])
        sheet.append(["Generated at (UTC)", generated])
        sheet.append(["Synthetic rows are marked in the Synthetic column when present."])
        sheet.append([])
        for row in table:
            sheet.append(row)
        output = io.BytesIO()
        book.save(output)
        data = output.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{stem}.xlsx"
    return StreamingResponse(iter([data]), media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
