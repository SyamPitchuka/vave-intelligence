"""Ingest the Module 2 retrieval corpus (the PDFs in data/) into the knowledge copilot.

Usage (from the repository root, with the backend virtualenv):

    HF_HUB_OFFLINE=1 backend/.venv/bin/python scripts/ingest_corpus.py [--expect 14] [--replace] [PDF ...]

With no paths it ingests every data/*.pdf. Each document goes through the same ingest_bytes as the upload endpoint:
section-aware chunks, embedded by the active embedding provider (the one duplicate detection uses), stored in
document_chunk_embeddings. A document whose filename is already loaded is skipped, or replaced with --replace.
Each document is committed on its own, so a dropped connection loses at most one.

The script refuses to run if the runtime fell back to deterministic embeddings (for example because the
sentence-transformers model failed to load), so the corpus is never silently indexed with the wrong model.
Pass --allow-deterministic to index with the hashed vectors anyway.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.router import _runtime  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.constants import DETERMINISTIC_EMBEDDING_MODEL  # noqa: E402
from app.models import Document, DocumentChunk, User  # noqa: E402
from app.services.copilot.service import ingest_bytes  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--expect", type=int, default=None, help="stop unless exactly this many PDFs are found")
    parser.add_argument("--replace", action="store_true", help="re-ingest documents that are already loaded")
    parser.add_argument("--visibility", default="all_authenticated", choices=["all_authenticated", "engineering", "management"])
    parser.add_argument("--allow-deterministic", action="store_true")
    args = parser.parse_args()
    paths = sorted(args.paths or (ROOT / "data").glob("*.pdf"))
    print(f"found {len(paths)} PDF(s)")
    for path in paths:
        print(f"  {path.name}")
    if args.expect is not None and len(paths) != args.expect:
        raise SystemExit(f"Expected {args.expect} PDFs, found {len(paths)}. Nothing was ingested.")

    settings = get_settings()
    db = get_session_factory()()
    config, chat, embedder, llm_status, warning = _runtime(db)
    print(f"embedding: {embedder.name} {embedder.model}; max input tokens: {getattr(embedder, 'max_tokens', None)}")
    print(f"chat: {getattr(chat, 'name', None)} {getattr(chat, 'model', None)}; llm_status: {llm_status}")
    if warning:
        print(f"runtime warning: {warning}")
    if embedder.model == DETERMINISTIC_EMBEDDING_MODEL and not args.allow_deterministic:
        raise SystemExit("The runtime is using deterministic embeddings, not the configured model. Nothing was ingested.")
    admin = db.scalar(select(User).where(User.email == settings.admin_email))

    for path in paths:
        existing = db.scalars(select(Document).where(Document.filename == path.name)).all()
        if existing and not args.replace:
            print(f"skip {path.name}: already loaded")
            continue
        for document in existing:
            db.delete(document)
        document = ingest_bytes(
            db,
            content=path.read_bytes(),
            filename=path.name,
            title="",
            visibility=args.visibility,
            user_id=admin.id if admin else None,
            storage_dir=settings.resolved_storage_dir(),
            embedder=embedder,
            is_synthetic=True,
            max_bytes=settings.upload_max_mb * 1024 * 1024,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        db.commit()
        count = len(db.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)).all())
        print(f"ingested {path.name}: {document.document_number} | {document.document_type} | {document.page_count} pages | {count} chunks")

    names = [path.name for path in paths]
    rows = db.execute(
        select(DocumentChunk.token_count, DocumentChunk.window, Document.filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.filename.in_(names))
    ).all()
    db.close()
    tokens = sorted(row[0] for row in rows)
    if not tokens:
        return
    deciles = statistics.quantiles(tokens, n=10) if len(tokens) > 1 else tokens * 9
    print(f"\ncorpus: {len({row[2] for row in rows})} documents, {len(tokens)} chunks")
    print(
        f"tokens per chunk: min {tokens[0]}, p10 {deciles[0]:.0f}, p25 {statistics.quantiles(tokens, n=4)[0]:.0f}, "
        f"median {statistics.median(tokens):.0f}, p75 {statistics.quantiles(tokens, n=4)[2]:.0f}, p90 {deciles[8]:.0f}, "
        f"max {tokens[-1]}, mean {statistics.fmean(tokens):.1f}"
    )
    print(f"windowed chunks (sections split for length): {sum(row[1] > 0 for row in rows)}")


if __name__ == "__main__":
    main()
