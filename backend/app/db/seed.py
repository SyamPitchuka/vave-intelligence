"""Reference data, demo accounts, synthetic workbook, guideline, and labelled cases."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.domain.constants import (
    IDEA_DEPARTMENTS,
    REJECTED_DEPARTMENTS,
    REJECTION_CATEGORIES,
    REJECTION_REASONS,
    ROLES,
    VEHICLE_FAMILIES,
)
from app.domain.synthetic import COPILOT_CASES, EVALUATION_CASES, GUIDELINE_TEXT
from app.models import (
    DataSourceConfig,
    Department,
    EvaluationCase,
    EvaluationDataset,
    RejectionCategory,
    RejectionReason,
    Role,
    User,
    VehicleFamily,
)
from app.services.embeddings.index import upsert_embedding
from app.services.ideas.service import load_idea
from app.services.imports.service import build_preview, commit_batch
from app.services.imports.workbook import write_workbook
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider

logger = logging.getLogger(__name__)


def seed_reference(db: Session) -> None:
    settings = get_settings()
    departments = {name: _get_or_create_department(db, name) for name in dict.fromkeys([*IDEA_DEPARTMENTS, *REJECTED_DEPARTMENTS])}
    roles = {}
    for name, description in ROLES:
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=description)
            db.add(role)
            db.flush()
        roles[name] = role
    for code, name, order in VEHICLE_FAMILIES:
        if db.scalar(select(VehicleFamily).where(VehicleFamily.code == code)) is None:
            db.add(VehicleFamily(code=code, name=name, sort_order=order))
    for name in REJECTION_CATEGORIES:
        if db.scalar(select(RejectionCategory).where(RejectionCategory.name == name)) is None:
            db.add(RejectionCategory(name=name, description="Catalogue value. Source imports may add other labels."))
    for name in REJECTION_REASONS:
        if db.scalar(select(RejectionReason).where(RejectionReason.name == name)) is None:
            db.add(RejectionReason(name=name, description="Catalogue value. Duplicate is a reason, not a stage status."))
    _user(db, settings.admin_email, "System Administrator", settings.admin_password, [roles["system_administrator"]], None)
    _user(db, "engineer@vave.local", "VAVE Engineer", settings.demo_user_password, [roles["vave_engineer"]], departments["Cab"])
    _user(db, "reviewer@vave.local", "Department Reviewer", settings.demo_user_password, [roles["department_reviewer"]], departments["Cab"])
    _user(db, "head@vave.local", "Department Head", settings.demo_user_password, [roles["department_head"]], None)
    _user(db, "viewer@vave.local", "Management Viewer", settings.demo_user_password, [roles["readonly_management"]], None)
    if db.scalar(select(DataSourceConfig).limit(1)) is None:
        db.add(
            DataSourceConfig(
                name="Corporate historical ideas",
                driver="postgresql",
                dsn_env_var="CORPORATE_DATABASE_URL",
                view_name=settings.corporate_ideas_view,
                is_active=False,
            )
        )
    db.flush()


def seed_demo_content(db: Session) -> None:
    from app.models import Document, Idea

    settings = get_settings()
    seed_reference(db)
    from app.services.settings_store import ensure_ai_settings

    ensure_ai_settings(db)
    if db.scalar(select(func.count()).select_from(Idea)) == 0:
        path = settings.resolved_data_dir() / "synthetic" / "vave_synthetic_ideas.xlsx"
        write_workbook(path)
        admin = db.scalar(select(User).where(User.email == settings.admin_email))
        batch = build_preview(
            db,
            content=path.read_bytes(),
            filename=path.name,
            sheet_name="Ideas",
            mapping_override=None,
            merge_strategy="insert_only",
            is_synthetic=True,
            allow_partial=False,
            user_id=admin.id if admin else None,
            storage_dir=settings.resolved_storage_dir(),
        )
        if batch.error_count:
            raise RuntimeError(f"Synthetic workbook preview has {batch.error_count} errors and was not imported.")
        commit_batch(db, batch.id, confirm=True, user_id=admin.id if admin else None)
    embedder = DeterministicEmbeddingProvider()
    for idea in db.scalars(select(Idea)).all():
        loaded = load_idea(db, idea.id)
        if loaded is None:
            continue
        from app.services.embeddings.index import idea_embedding_text

        upsert_embedding(
            db,
            entity_type="idea",
            entity_id=loaded.id,
            model_name=embedder.model,
            text=idea_embedding_text(loaded),
            embedder=embedder,
        )
    _seed_cases(db, "Synthetic duplicate labels v1", "duplicate", EVALUATION_CASES)
    _seed_cases(db, "Synthetic copilot citations v1", "copilot", COPILOT_CASES)
    if db.scalar(select(func.count()).select_from(Document)) == 0:
        from app.services.copilot.service import ingest_bytes

        admin = db.scalar(select(User).where(User.email == settings.admin_email))
        ingest_bytes(
            db,
            content=GUIDELINE_TEXT.encode("utf-8"),
            filename="vave_synthetic_guideline.txt",
            title="Synthetic VAVE guideline",
            visibility="all_authenticated",
            user_id=admin.id if admin else None,
            storage_dir=settings.resolved_storage_dir(),
            embedder=embedder,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            is_synthetic=True,
            max_bytes=settings.upload_max_mb * 1024 * 1024,
        )
    db.flush()


def _seed_cases(db: Session, name: str, dataset_type: str, cases: list[dict]) -> None:
    dataset = db.scalar(select(EvaluationDataset).where(EvaluationDataset.name == name))
    if dataset is None:
        dataset = EvaluationDataset(
            name=name,
            dataset_type=dataset_type,
            description="Labelled synthetic cases. Ground truth is independent of model output.",
        )
        db.add(dataset)
        db.flush()
        for case in cases:
            db.add(
                EvaluationCase(
                    dataset_id=dataset.id,
                    case_code=case["case_code"],
                    query_text=case["query_text"],
                    candidate_idea_code=case.get("candidate_idea_code"),
                    ground_truth=case["ground_truth"],
                    rationale=case["rationale"],
                    split=case.get("split", "validation"),
                    retrieval_targets=case.get("retrieval_targets", []),
                    expected_keyword=case.get("expected_keyword"),
                )
            )


def _get_or_create_department(db: Session, name: str) -> Department:
    found = db.scalar(select(Department).where(Department.name == name))
    if found:
        return found
    created = Department(name=name)
    db.add(created)
    db.flush()
    return created


def _user(db: Session, email: str, full_name: str, password: str, roles: list[Role], department: Department | None) -> None:
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        department_id=department.id if department else None,
        timezone=get_settings().display_timezone,
    )
    user.roles = roles
    db.add(user)
    db.flush()
