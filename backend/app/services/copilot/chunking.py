"""Section-aware chunking for the knowledge copilot.

Answers are cited as document, section and page, so a chunk never crosses a section boundary or a page boundary.
A section's text on one page is one chunk, unless it is longer than the embedding model's input limit; only then
is it split into overlapping windows, still inside that section and page.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

# The type code is the third part of a document number such as CVOEM/VAVE/TD-BM/FY23/014.
DOCUMENT_TYPES = {
    "TD-BM": "Teardown benchmark",
    "CB-BM": "Competitor benchmark",
    "VE-CL": "Idea closure register",
    "MC-IX": "Commodity cost index",
    "WF-FA": "Field failure analysis",
    "ES-STD": "Engineering standard",
    "SC-TC": "Supplier and tooling cost study",
    "WR-RM": "Programme roadmap",
    "VE-WS": "Workshop minutes",
}
DOCUMENT_NUMBER = re.compile(r"^[A-Z][A-Z0-9]+(?:/[A-Z0-9-]+){3,}$")
# A numbered heading on its own line: "4.2 Alternator sub-system". Body text that happens to start with a number
# is ruled out by the sequence check in _follows, not by this pattern alone.
HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\s+([A-Z][^\n]*)$")
PAGE_LINE = re.compile(r"^Page \d+$")
MAX_HEADING_WORDS = 12
# Lines this far down a page can still belong to the running header.
HEADER_DEPTH = 6
FRONT_MATTER = "Front matter"


@dataclass
class Segment:
    """The text of one section on one page."""

    section_number: str | None
    section_heading: str
    page_number: int | None
    lines: list[str] = field(default_factory=list)
    # The headings from the top level down, e.g. "3 Powertrain cooling pack > 3.1 Benchmarked measure". A parent
    # heading with no text of its own makes no segment, so this is the only place it survives.
    section_path: str = ""


@dataclass
class ParsedDocument:
    document_number: str | None
    title: str | None
    document_type: str | None
    segments: list[Segment]


@dataclass
class Chunk:
    section_number: str | None
    section_heading: str
    section_path: str
    page_number: int | None
    content: str
    token_count: int
    window: int  # 0 for an unsplit segment; 1, 2, ... for the overlapping windows of a long one


def document_type(document_number: str | None) -> str | None:
    if not document_number:
        return None
    parts = document_number.split("/")
    return DOCUMENT_TYPES.get(parts[2]) if len(parts) > 2 else None


def _clean(line: str) -> str:
    # pypdf renders the bullet glyph as U+FFFD.
    return re.sub(r"\s+", " ", line.replace("�", "-")).strip()


def _running_header(pages: list[list[str]]) -> set[str]:
    """Lines that open most pages: document number, running title, watermark, disclaimer."""
    if len(pages) < 2:
        return set()
    counts = Counter(line for lines in pages for line in set(lines[:HEADER_DEPTH]))
    return {line for line, seen in counts.items() if seen >= 0.6 * len(pages) and not PAGE_LINE.match(line)}


def _number(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _follows(previous: tuple[int, ...] | None, candidate: tuple[int, ...]) -> bool:
    """A heading must continue the numbering: the next sibling at some level (one gap allowed) or a first child."""
    if previous is None:
        return len(candidate) == 1 and candidate[0] <= 2
    for level in range(1, min(len(previous) + 1, 4) + 1):
        if len(candidate) != level or candidate[: level - 1] != previous[: level - 1]:
            continue
        base = previous[level - 1] if level <= len(previous) else 0
        if base < candidate[level - 1] <= base + 2:
            return True
    return False


def parse_pdf(content: bytes) -> ParsedDocument:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages = [[_clean(line) for line in (page.extract_text() or "").splitlines()] for page in reader.pages]
    pages = [[line for line in lines if line] for lines in pages]
    return parse_pages(pages)


def _contents(lines: list[str]) -> dict[tuple[int, ...], str]:
    """Entries of a contents list extracted one cell per line: number, title, page."""
    if "Contents" not in lines:
        return {}
    rest = lines[lines.index("Contents") + 1 :]
    entries: dict[tuple[int, ...], str] = {}
    for index in range(len(rest) - 2):
        if re.fullmatch(r"\d{1,2}(?:\.\d{1,2}){0,3}", rest[index]) and re.fullmatch(r"\d{1,3}", rest[index + 2]):
            entries[_number(rest[index])] = rest[index + 1]
    return entries


def _agrees(contents: dict[tuple[int, ...], str], number: tuple[int, ...], heading: str) -> bool:
    """Where the contents list names this number, the heading must start the same way."""
    listed = contents.get(number)
    if listed is None:
        return True
    a, b = listed.lower().split(), heading.lower().split()
    width = min(3, len(a), len(b))
    return a[:width] == b[:width]


def parse_pages(pages: list[list[str]]) -> ParsedDocument:
    """Split page lines into sections. Pages are 1-based in the result."""
    header = _running_header(pages)
    contents = _contents(pages[0]) if pages else {}
    number = next((line for lines in pages[:1] for line in lines[:HEADER_DEPTH] if DOCUMENT_NUMBER.match(line)), None)
    title = next(
        (
            line
            for line in (pages[0][:HEADER_DEPTH] if pages else [])
            if line in header and line != number and "SYNTHETIC" not in line.upper()
        ),
        None,
    )
    segments: list[Segment] = []
    current: tuple[int, ...] | None = None
    section_number: str | None = None
    section_heading = FRONT_MATTER
    headings: dict[tuple[int, ...], str] = {}
    path = FRONT_MATTER
    in_contents = False
    for page_number, lines in enumerate(pages, start=1):
        body = [
            line
            for index, line in enumerate(lines)
            if not (index < HEADER_DEPTH and (line in header or PAGE_LINE.match(line)))
        ]
        segment = Segment(section_number, section_heading, page_number, section_path=path)
        for line in body:
            match = HEADING.match(line)
            if match and len(match.group(2).split()) <= MAX_HEADING_WORDS and not match.group(2).endswith("."):
                candidate = _number(match.group(1))
                if _follows(current, candidate) and _agrees(contents, candidate, match.group(2)):
                    in_contents = False
                    if segment.lines:
                        segments.append(segment)
                    current = candidate
                    section_number, section_heading = match.group(1), match.group(2)
                    headings[candidate] = line
                    path = " > ".join(
                        headings[candidate[:depth]] for depth in range(1, len(candidate) + 1) if candidate[:depth] in headings
                    )
                    segment = Segment(section_number, section_heading, page_number, section_path=path)
                    continue
            if current is None and line == "Contents":
                # The table of contents lists headings and page numbers; it is navigation, not content.
                in_contents = True
            if not in_contents:
                segment.lines.append(line)
        if segment.lines:
            segments.append(segment)
    return ParsedDocument(number, title, document_type(number), segments)


def parse_text(text: str) -> ParsedDocument:
    """Plain text and Markdown: a block's first line is its heading when it is short and is not a sentence."""
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [_clean(line) for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lstrip("#").strip()
        if len(lines) > 1 and len(first.split()) <= MAX_HEADING_WORDS and not first.endswith("."):
            match = HEADING.match(first)
            number, heading = (match.group(1), match.group(2)) if match else (None, first)
            segments.append(Segment(number, heading, None, lines[1:], section_path=first))
        else:
            previous = segments[-1] if segments else None
            segments.append(
                Segment(
                    previous.section_number if previous else None,
                    previous.section_heading if previous else FRONT_MATTER,
                    None,
                    lines,
                    section_path=previous.section_path if previous else FRONT_MATTER,
                )
            )
    return ParsedDocument(None, None, None, segments)


def chunk_segments(
    segments: list[Segment],
    *,
    count_tokens: Callable[[str], int],
    budget: Callable[[Segment], int],
    overlap_tokens: int,
) -> list[Chunk]:
    """One chunk per segment; a segment over its token budget becomes overlapping windows of whole lines."""
    chunks: list[Chunk] = []
    for segment in segments:
        limit = budget(segment)
        units: list[tuple[str, int]] = []
        for line in segment.lines:
            units.extend(_split_long(line, limit, count_tokens))
        total = sum(tokens for _, tokens in units)
        if total <= limit:
            chunks.append(_chunk(segment, units, 0))
            continue
        start, window = 0, 1
        while start < len(units):
            end, used = start, 0
            while end < len(units) and (end == start or used + units[end][1] <= limit):
                used += units[end][1]
                end += 1
            chunks.append(_chunk(segment, units[start:end], window))
            if end >= len(units):
                break
            # Step back over whole lines worth at most overlap_tokens, but always move forward.
            back, carried = end, 0
            while back - 1 > start and carried + units[back - 1][1] <= overlap_tokens:
                back -= 1
                carried += units[back][1]
            start, window = back, window + 1
    return chunks


def _split_long(line: str, limit: int, count_tokens: Callable[[str], int]) -> list[tuple[str, int]]:
    tokens = count_tokens(line)
    if tokens <= limit:
        return [(line, tokens)]
    words, pieces, current = line.split(), [], []
    for word in words:
        if current and count_tokens(" ".join([*current, word])) > limit:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return [(piece, count_tokens(piece)) for piece in pieces]


def _chunk(segment: Segment, units: list[tuple[str, int]], window: int) -> Chunk:
    return Chunk(
        section_number=segment.section_number,
        section_heading=segment.section_heading,
        section_path=segment.section_path,
        page_number=segment.page_number,
        content="\n".join(text for text, _ in units),
        token_count=sum(tokens for _, tokens in units),
        window=window,
    )


def embedding_text(document_title: str | None, section_path: str, content: str) -> str:
    """What is embedded: where the passage sits, then the passage. The stored content is the passage alone."""
    return f"{document_title or ''} - {section_path}\n{content}".strip()
