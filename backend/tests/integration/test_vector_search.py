from __future__ import annotations

from app.models import Idea
from app.services.duplicate_detection.service import rank_historical
from app.services.embeddings.index import idea_embedding_text, upsert_embedding
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider

QUERY = "Replace the steel cab mounting bracket with an aluminium bracket to reduce mass."


def test_stored_submissions_do_not_crowd_historical_ideas_out_of_vector_search(seeded_database):
    from app.db.session import get_session_factory

    db = get_session_factory()()
    embedder = DeterministicEmbeddingProvider()
    try:
        # More near-identical submissions than the search limit, so without the origin filter they fill every slot.
        for number in range(25):
            submission = Idea(
                idea_code=f"VAVE-TEST-CROWD-{number:03d}",
                component="Cab mounting bracket",
                description=QUERY,
                origin="submission",
                lifecycle_status="submitted",
                is_synthetic=True,
            )
            db.add(submission)
            db.flush()
            upsert_embedding(
                db,
                entity_type="idea",
                entity_id=submission.id,
                model_name=embedder.model,
                text=idea_embedding_text(submission),
                embedder=embedder,
            )
        db.flush()

        query = Idea(idea_code="VAVE-TEST-QUERY", component="Cab mounting bracket", description=QUERY)
        ranked = rank_historical(db, query, embedder=embedder, limit=15)

        assert len(ranked) == 20
        assert all(item["idea"].origin == "historical" for item in ranked)
        missing = [item["idea"].idea_code for item in ranked if item["cosine"] is None]
        assert missing == []
    finally:
        db.rollback()
        db.close()
