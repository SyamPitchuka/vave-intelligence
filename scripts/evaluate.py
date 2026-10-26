"""Run the labelled evaluation datasets and print the stored metrics.

Usage (from the repository root, with the backend virtualenv):

    backend/.venv/bin/python scripts/evaluate.py                  # active embedding provider
    backend/.venv/bin/python scripts/evaluate.py --deterministic  # deterministic-hash-v1 baseline

The active provider is the one in AI settings. Its vectors must already be indexed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.seed import seed_demo_content  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import EvaluationDataset, User  # noqa: E402
from app.services.evaluation_service import run_evaluation  # noqa: E402
from app.services.llm_providers.factory import build_embedding_provider  # noqa: E402
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider  # noqa: E402
from app.services.settings_store import effective_ai  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Evaluate deterministic-hash-v1 instead of the active embedding provider.",
    )
    args = parser.parse_args()
    db = get_session_factory()()
    try:
        seed_demo_content(db)
        db.commit()
        config = effective_ai(db)
        if args.deterministic:
            embedder = DeterministicEmbeddingProvider()
        else:
            embedder = build_embedding_provider(
                get_settings(), config["mode"], config["embedding_provider"], config["embedding_model"]
            )
        print(f"Embedding model: {embedder.model}")
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
