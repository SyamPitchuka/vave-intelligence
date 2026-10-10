"""Run the labelled evaluation datasets and print the stored metrics.

Usage (from the repository root, with the backend virtualenv):

    backend/.venv/bin/python scripts/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.seed import seed_demo_content  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import EvaluationDataset, User  # noqa: E402
from app.services.evaluation_service import run_evaluation  # noqa: E402
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider  # noqa: E402
from app.services.settings_store import effective_ai  # noqa: E402


def main() -> None:
    db = get_session_factory()()
    try:
        seed_demo_content(db)
        db.commit()
        config = effective_ai(db)
        embedder = DeterministicEmbeddingProvider()
        admin = db.scalar(select(User).where(User.email == "admin@vave.local"))
        datasets = db.scalars(select(EvaluationDataset).order_by(EvaluationDataset.name)).all()
        if not datasets:
            raise SystemExit("No labelled datasets are available, so metrics were not calculated.")
        for dataset in datasets:
            run = run_evaluation(
                db,
                dataset.id,
                user_id=admin.id if admin else None,
                embedder=embedder,
                fuzzy_strong_threshold=float(config["fuzzy_strong_threshold"]),
                cosine_retrieve_threshold=float(config["cosine_retrieve_threshold"]),
                retrieval_k=int(config["retrieval_top_k"]),
                provider=config["mode"],
                embedding_model=embedder.model,
            )
            db.commit()
            print(dataset.name)
            print(json.dumps({"notes": run.notes, "metrics": run.metrics}, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
