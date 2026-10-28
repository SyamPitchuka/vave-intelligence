"""Store and search embeddings in pgvector. Searches never mix model names."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import EmbeddingRecord
from app.services.text import comparison_blob


def idea_embedding_text(idea) -> str:
    department = idea.belonged_department.name if idea.belonged_department else ""
    vehicles = []
    for row in idea.applicability:
        if row.vehicle_family is not None:
            vehicles.append(f"{row.vehicle_family.name} {row.annual_volume}")
    return "\n".join(
        [
            f"Component: {idea.component or ''}",
            f"Description: {idea.description or ''}",
            f"Current design: {idea.current_design or ''}",
            f"Proposed change: {idea.proposed_change or ''}",
            f"Rationale: {idea.engineering_rationale or ''}",
            f"Benefit: {idea.expected_benefit or ''}",
            f"Constraints: {idea.constraints or ''}",
            f"Department: {department}",
            # Sorted: applicability rows come back in load order, which would make the vector depend on it.
            f"Vehicles: {', '.join(sorted(vehicles))}",
            f"Idea type: {idea.idea_type or ''}",
        ]
    )


def comparison_text(idea) -> str:
    return comparison_blob(
        component=idea.component,
        description=idea.description,
        proposed_change=idea.proposed_change,
        expected_benefit=idea.expected_benefit,
        current_design=idea.current_design,
    )


def upsert_embedding(db: Session, *, entity_type: str, entity_id: uuid.UUID, model_name: str, text: str, embedder) -> None:
    if not text.strip():
        return
    vector = embedder.embed(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(EmbeddingRecord).where(
            EmbeddingRecord.entity_type == entity_type,
            EmbeddingRecord.entity_id == entity_id,
            EmbeddingRecord.model_name == model_name,
        )
    )
    if existing and existing.content_hash == digest:
        return
    if existing:
        existing.embedding = vector
        existing.content_hash = digest
        existing.dimensions = len(vector)
        return
    db.add(
        EmbeddingRecord(
            entity_type=entity_type,
            entity_id=entity_id,
            model_name=model_name,
            dimensions=len(vector),
            content_hash=digest,
            embedding=vector,
        )
    )


def search_similar(
    db: Session,
    *,
    vector: list[float],
    model_name: str,
    entity_type: str,
    limit: int,
    entity_ids: Select | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Nearest vectors by cosine. ``entity_ids`` (a select of ids) restricts the search before the limit applies."""
    distance = EmbeddingRecord.embedding.cosine_distance(vector)
    similarity = (1 - distance).label("similarity")
    query = select(EmbeddingRecord.entity_id, similarity).where(
        EmbeddingRecord.entity_type == entity_type, EmbeddingRecord.model_name == model_name
    )
    if entity_ids is not None:
        query = query.where(EmbeddingRecord.entity_id.in_(entity_ids))
    rows = db.execute(query.order_by(distance).limit(limit)).all()
    return [(row[0], float(row[1])) for row in rows]
