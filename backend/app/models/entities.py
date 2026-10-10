"""SQLAlchemy models. One idea master row, with vehicle applicability stored separately."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.constants import EMBEDDING_DIM


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    aliases: Mapped[list[DepartmentAlias]] = relationship(back_populates="department")


class DepartmentAlias(Base):
    __tablename__ = "department_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    department_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("departments.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    department: Mapped[Department] = relationship(back_populates="aliases")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    department: Mapped[Department | None] = relationship()
    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class VehicleFamily(Base):
    __tablename__ = "vehicle_families"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RejectionCategory(Base):
    __tablename__ = "rejection_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class RejectionReason(Base):
    __tablename__ = "rejection_reasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="preview")
    merge_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="reject_conflicts")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    allow_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = (
        Index("ix_ideas_stage", "stage_status"),
        Index("ix_ideas_rejected", "is_rejected"),
        Index("ix_ideas_origin", "origin"),
        Index("ix_ideas_generation_date", "idea_generation_date"),
        Index("ix_ideas_belonged_dept", "idea_belonged_department_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    idea_code: Mapped[str] = mapped_column(String(64), nullable=False)
    component: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    current_design: Mapped[str | None] = mapped_column(Text)
    proposed_change: Mapped[str | None] = mapped_column(Text)
    engineering_rationale: Mapped[str | None] = mapped_column(Text)
    expected_benefit: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)
    idea_generation_date: Mapped[date | None] = mapped_column(Date)
    rejection_date: Mapped[date | None] = mapped_column(Date)
    idea_belonged_department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    rejected_department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    stage_status: Mapped[str | None] = mapped_column(String(1))
    rejection_category: Mapped[str | None] = mapped_column(String(255))
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    idea_type: Mapped[str | None] = mapped_column(String(255))
    idea_disposition: Mapped[str | None] = mapped_column(String(255))
    applicable_vehicle_details: Mapped[str | None] = mapped_column(Text)
    saving_per_vehicle: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    reported_total_saving: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    total_combined_annual_saving: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    savings_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    is_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="historical")
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="historical")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    source_reference: Mapped[str | None] = mapped_column(String(512))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batches.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    belonged_department: Mapped[Department | None] = relationship(foreign_keys=[idea_belonged_department_id])
    rejected_department: Mapped[Department | None] = relationship(foreign_keys=[rejected_department_id])
    applicability: Mapped[list[IdeaVehicleApplicability]] = relationship(
        back_populates="idea", cascade="all, delete-orphan"
    )
    import_batch: Mapped[ImportBatch | None] = relationship()


class IdeaVehicleApplicability(Base):
    __tablename__ = "idea_vehicle_applicability"
    __table_args__ = (UniqueConstraint("idea_id", "vehicle_family_id", name="uq_idea_vehicle_family"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False)
    vehicle_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicle_families.id"), nullable=False)
    annual_volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    tonnage_details: Mapped[str | None] = mapped_column(Text)

    idea: Mapped[Idea] = relationship(back_populates="applicability")
    vehicle_family: Mapped[VehicleFamily] = relationship()


class ImportStagingRow(Base):
    __tablename__ = "import_staging_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class ImportChange(Base):
    __tablename__ = "import_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id"), index=True)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSONB)
    after_json: Mapped[dict | None] = mapped_column(JSONB)


class ImportRowError(Base):
    __tablename__ = "import_row_errors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)


class EmbeddingRecord(Base):
    __tablename__ = "embedding_records"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "model_name", name="uq_embedding_entity_model"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=EMBEDDING_DIM)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DuplicateAnalysisRun(Base):
    __tablename__ = "duplicate_analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    outcome_category: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_model: Mapped[str | None] = mapped_column(String(120))
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    retrieval_k: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_run")
    warning: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Idea] = relationship(foreign_keys=[submission_id])
    candidates: Mapped[list[DuplicateAnalysisCandidate]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="DuplicateAnalysisCandidate.rank"
    )


class DuplicateAnalysisCandidate(Base):
    __tablename__ = "duplicate_analysis_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("duplicate_analysis_runs.id", ondelete="CASCADE"), index=True
    )
    historical_idea_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ideas.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cosine_similarity: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    fuzzy_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    exact_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    heuristic_category: Mapped[str] = mapped_column(String(64), nullable=False)
    llm_category: Mapped[str | None] = mapped_column(String(64))
    disagreement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    similarities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    differences: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    run: Mapped[DuplicateAnalysisRun] = relationship(back_populates="candidates")
    historical_idea: Mapped[Idea] = relationship()


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duplicate_analysis_runs.id"), index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("duplicate_analysis_candidates.id"))
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    ai_recommendation: Mapped[str | None] = mapped_column(String(64))
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[DuplicateAnalysisRun] = relationship()
    candidate: Mapped[DuplicateAnalysisCandidate | None] = relationship()
    author: Mapped[User] = relationship()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="engineering")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    page_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(String(512))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[ChatMessage]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    provider: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="duplicate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cases: Mapped[list[EvaluationCase]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), index=True)
    case_code: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_idea_code: Mapped[str | None] = mapped_column(String(64))
    ground_truth: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    split: Mapped[str] = mapped_column(String(32), nullable=False, default="validation")
    retrieval_targets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_keyword: Mapped[str | None] = mapped_column(String(200))

    dataset: Mapped[EvaluationDataset] = relationship(back_populates="cases")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_datasets.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_model: Mapped[str | None] = mapped_column(String(120))
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    predictions: Mapped[list[EvaluationPrediction]] = relationship(cascade="all, delete-orphan")


class EvaluationPrediction(Base):
    __tablename__ = "evaluation_predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_cases.id"))
    predicted: Mapped[str | None] = mapped_column(String(64))
    rank: Mapped[int | None] = mapped_column(Integer)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user: Mapped[User | None] = relationship()


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataSourceConfig(Base):
    __tablename__ = "data_source_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    driver: Mapped[str] = mapped_column(String(32), nullable=False, default="postgresql")
    dsn_env_var: Mapped[str] = mapped_column(String(80), nullable=False, default="CORPORATE_DATABASE_URL")
    view_name: Mapped[str] = mapped_column(String(120), nullable=False, default="vave_historical_ideas")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
