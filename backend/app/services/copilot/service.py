"""Document ingestion and grounded answers. Idea vectors and document vectors stay separate."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.constants import ROLE_PERMISSIONS
from app.models import ChatMessage, ChatSession, Document, DocumentChunk, User
from app.services.embeddings.index import search_similar, upsert_embedding
from app.services.llm_providers.fallback import FallbackChatProvider
from app.services.text import query_coverage

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def can_read_document(user: User, visibility: str) -> bool:
    names = {role.name for role in user.roles}
    if "system_administrator" in names:
        return True
    permissions: set[str] = set()
    for name in names:
        permissions |= ROLE_PERMISSIONS.get(name, set())
    if visibility == "all_authenticated":
        return True
    if visibility == "engineering":
        return "documents:read" in permissions
    if visibility == "management":
        return "documents:read_management" in permissions or "audit:read" in permissions
    return False


def extract_pages(content: bytes, filename: str) -> list[dict]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported document types are PDF, DOCX, TXT, and MD.")
    if suffix == ".pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("The file extension is PDF but the content is not a PDF.")
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append({"page": index, "section": f"Page {index}", "text": page.extract_text() or ""})
        return pages
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            raise ValueError("The file extension is DOCX but the content is not a Word document.")
        from io import BytesIO

        import docx

        document = docx.Document(BytesIO(content))
        section = "Document"
        blocks: list[dict] = []
        buffer: list[str] = []
        for paragraph in document.paragraphs:
            style = paragraph.style.name if paragraph.style is not None else ""
            if style.startswith("Heading"):
                if buffer:
                    blocks.append({"page": None, "section": section, "text": "\n".join(buffer)})
                    buffer = []
                section = paragraph.text.strip() or section
            elif paragraph.text.strip():
                buffer.append(paragraph.text.strip())
        if buffer:
            blocks.append({"page": None, "section": section, "text": "\n".join(buffer)})
        return blocks or [{"page": None, "section": "Document", "text": ""}]
    text = content.decode("utf-8", errors="replace")
    return [{"page": None, "section": "Document", "text": text}]


def chunk_pages(pages: list[dict], size: int, overlap: int) -> list[dict]:
    chunks: list[dict] = []
    for page in pages:
        paragraphs = [part.strip() for part in (page.get("text") or "").splitlines() if part.strip()]
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 1 > size:
                chunks.append({"content": current, "page_number": page.get("page"), "section": page.get("section")})
                tail = current[-overlap:].strip() if overlap else ""
                space = tail.find(" ")
                current = tail[space + 1 :].strip() if space >= 0 else ""
            current = f"{current}\n{paragraph}".strip() if current else paragraph
        if current:
            chunks.append({"content": current, "page_number": page.get("page"), "section": page.get("section")})
    return chunks


def ingest_bytes(
    db: Session,
    *,
    content: bytes,
    filename: str,
    title: str,
    visibility: str,
    user_id: uuid.UUID | None,
    storage_dir: Path,
    embedder,
    chunk_size: int,
    chunk_overlap: int,
    is_synthetic: bool,
    max_bytes: int,
) -> Document:
    if len(content) > max_bytes:
        raise ValueError(f"The file exceeds the {max_bytes // (1024 * 1024)} MB upload limit.")
    if visibility not in {"all_authenticated", "engineering", "management"}:
        raise ValueError("Visibility must be all_authenticated, engineering, or management.")
    pages = extract_pages(content, filename)
    chunks = chunk_pages(pages, chunk_size, chunk_overlap)
    if not chunks:
        raise ValueError("No text could be extracted from this file.")
    document = Document(
        title=title or Path(filename).stem,
        filename=filename,
        content_type=Path(filename).suffix.lower().lstrip("."),
        size_bytes=len(content),
        status="indexed",
        visibility=visibility,
        is_synthetic=is_synthetic,
        page_count=max((page.get("page") or 0) for page in pages),
        uploaded_by=user_id,
    )
    db.add(document)
    db.flush()
    folder = storage_dir / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{document.id}{Path(filename).suffix.lower()}"
    path.write_bytes(content)
    document.storage_path = str(path)
    for index, chunk in enumerate(chunks):
        row = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=chunk["content"],
            page_number=chunk["page_number"],
            section=chunk["section"],
            token_count=len(chunk["content"].split()),
        )
        db.add(row)
        db.flush()
        upsert_embedding(
            db,
            entity_type="document_chunk",
            entity_id=row.id,
            model_name=embedder.model,
            text=chunk["content"],
            embedder=embedder,
        )
    db.flush()
    return document


def answer_question(
    db: Session,
    *,
    user: User,
    session_id: uuid.UUID | None,
    message: str,
    embedder,
    chat_provider,
    ai_config: dict,
    llm_status: str,
) -> tuple[ChatSession, ChatMessage]:
    if session_id:
        chat = db.scalar(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id))
        if chat is None:
            raise LookupError("Conversation was not found.")
    else:
        chat = ChatSession(user_id=user.id, title=message[:80])
        db.add(chat)
        db.flush()
    db.add(ChatMessage(session_id=chat.id, role="user", content=message))
    evidence, citations, best = _retrieve(db, user, message, embedder, ai_config)
    abstained = best < float(ai_config["copilot_lexical_threshold"]) and all(
        item["cosine"] < float(ai_config["cosine_retrieve_threshold"]) for item in evidence
    )
    if not evidence:
        abstained = True
    if abstained:
        answer = (
            "The approved documents available to your account do not contain enough evidence to answer this. "
            "No general model knowledge has been added."
        )
        provider_name = "abstention"
        model_name = None
    elif isinstance(chat_provider, FallbackChatProvider) or llm_status != "pending":
        lines = ["From the approved documents:"]
        for index, item in enumerate(citations, start=1):
            lines.append(f"[{index}] {item['excerpt']}")
        answer = "\n\n".join(lines)
        provider_name = "deterministic"
        model_name = embedder.model
    else:
        import json

        prompt = {
            "question": message,
            "excerpts": [
                {"index": index, "title": item["document_title"], "page": item["page_number"], "text": item["excerpt"]}
                for index, item in enumerate(citations)
            ],
        }
        try:
            raw = chat_provider.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Answer only from the excerpts. Return JSON with keys answer, citation_indexes, abstained. "
                            "If the excerpts do not support an answer, set abstained true and do not add outside facts. "
                            "Do not present general knowledge as a verified engineering fact."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                timeout=int(ai_config["comparison_timeout_seconds"]),
            )
            parsed = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
            if parsed.get("abstained"):
                abstained = True
                answer = (
                    "The retrieved excerpts are not sufficient to answer. "
                    "No general model knowledge has been added."
                )
            else:
                answer = str(parsed.get("answer") or "").strip() or "The model returned an empty answer."
            provider_name = chat_provider.name
            model_name = chat_provider.model
        except Exception as exc:  # noqa: BLE001 — show the failure instead of inventing an answer
            answer = (
                "The language model did not return a usable grounded answer "
                f"({exc}). Retrieved excerpts are listed separately. No external fallback was used."
            )
            provider_name = "deterministic"
            model_name = None
            abstained = False
    stored = ChatMessage(
        session_id=chat.id,
        role="assistant",
        content=answer,
        citations=citations,
        evidence=evidence,
        abstained=abstained,
        provider=provider_name,
        model_name=model_name,
    )
    db.add(stored)
    db.flush()
    return chat, stored


def _retrieve(db: Session, user: User, message: str, embedder, ai_config: dict) -> tuple[list[dict], list[dict], float]:
    allowed = {
        document.id
        for document in db.scalars(select(Document).where(Document.status == "indexed")).all()
        if can_read_document(user, document.visibility)
    }
    cosine: dict[uuid.UUID, float] = {}
    try:
        vector = embedder.embed(message)
        for entity_id, score in search_similar(
            db,
            vector=vector,
            model_name=embedder.model,
            entity_type="document_chunk",
            limit=int(ai_config["retrieval_top_k"]),
        ):
            cosine[entity_id] = score
    except Exception:
        cosine = {}
    chunks = db.scalars(select(DocumentChunk).options(selectinload(DocumentChunk.document))).all()
    scored = []
    for chunk in chunks:
        if chunk.document_id not in allowed:
            continue
        lexical = query_coverage(message, chunk.content)
        vector_score = cosine.get(chunk.id, 0.0)
        if lexical <= 0 and vector_score <= 0:
            continue
        scored.append((max(lexical, vector_score), lexical, vector_score, chunk))
    scored.sort(key=lambda item: (item[1], item[2]), reverse=True)
    evidence = []
    citations = []
    best = 0.0
    for combined, lexical, vector_score, chunk in scored[:5]:
        best = max(best, lexical, vector_score)
        document = chunk.document
        item = {
            "document_id": str(document.id),
            "document_title": document.title,
            "chunk_id": str(chunk.id),
            "page_number": chunk.page_number,
            "section": chunk.section,
            "excerpt": chunk.content[:700],
            "lexical_score": round(lexical, 4),
            "cosine_similarity": round(vector_score, 4),
            "is_synthetic": document.is_synthetic,
        }
        evidence.append(item)
        if lexical >= float(ai_config["copilot_lexical_threshold"]) or vector_score >= float(ai_config["cosine_retrieve_threshold"]):
            citations.append(item)
    if not citations and evidence and best >= 0.34:
        citations = evidence[:2]
    return evidence, citations, best
