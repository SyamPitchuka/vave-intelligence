import json

from app.services.copilot.chunking import FRONT_MATTER, chunk_segments, parse_pages, parse_text
from app.services.copilot.service import compose_answer
from app.services.llm_providers.fallback import DeterministicEmbeddingProvider, FallbackChatProvider

HEADER = ["ACME/VAVE/TD-BM/2024/001", "Sample teardown report", "SYNTHETIC - NOT A RECORD"]


def page(number: int, *lines: str) -> list[str]:
    return [*HEADER, f"Page {number}", *lines]


def corpus() -> list[list[str]]:
    return [
        page(
            1,
            "Sample Teardown Report",
            "Period covered",
            "1 April 2024 to 30 September 2024",
            "Contents",
            "1",
            "Scope and method",
            "2",
            "2",
            "Findings",
            "3",
        ),
        page(2, "1 Scope and method", "The study covers one vehicle.", "1.1 Costing basis", "Costs are fully absorbed."),
        page(3, "Costs continue here.", "2 Findings", "2.1 Alternator bracket", "Item", "3.1.5", "HSLA steel bracket saves 18 per cent."),
    ]


def test_running_header_and_page_lines_are_stripped_and_metadata_read():
    parsed = parse_pages(corpus())
    assert parsed.document_number == "ACME/VAVE/TD-BM/2024/001"
    assert parsed.title == "Sample teardown report"
    assert parsed.document_type == "Teardown benchmark"
    text = "\n".join(line for segment in parsed.segments for line in segment.lines)
    assert "SYNTHETIC" not in text and "Page 2" not in text


def test_contents_list_rejects_a_cover_line_that_looks_like_heading_one():
    parsed = parse_pages(corpus())
    front = parsed.segments[0]
    assert front.section_heading == FRONT_MATTER
    assert "1 April 2024 to 30 September 2024" in front.lines
    # The contents list itself is navigation, not content.
    assert "Contents" not in front.lines and "Findings" not in front.lines
    assert [s.section_number for s in parsed.segments[1:]] == ["1", "1.1", "1.1", "2.1"]


def test_sections_split_at_page_boundaries_and_keep_their_parent_headings():
    parsed = parse_pages(corpus())
    continued = parsed.segments[3]
    assert (continued.section_number, continued.page_number) == ("1.1", 3)
    assert continued.lines == ["Costs continue here."]
    finding = parsed.segments[4]
    assert finding.section_path == "2 Findings > 2.1 Alternator bracket"
    assert finding.page_number == 3
    # A table cell holding a number out of sequence is content, not a heading.
    assert "3.1.5" in finding.lines


def test_long_sections_become_overlapping_windows_within_the_limit():
    segment = parse_text("Heading\n" + "\n".join(f"w{i} x x x" for i in range(10))).segments[0]
    chunks = chunk_segments([segment], count_tokens=lambda text: len(text.split()), budget=lambda _: 12, overlap_tokens=4)
    assert len(chunks) > 1
    assert [chunk.window for chunk in chunks] == list(range(1, len(chunks) + 1))
    assert all(chunk.token_count <= 12 for chunk in chunks)
    # Each window repeats the last line of the one before it.
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.content.splitlines()[-1] == current.content.splitlines()[0]
    covered = {line for chunk in chunks for line in chunk.content.splitlines()}
    assert covered == set(segment.lines)


def test_a_short_section_is_one_unsplit_chunk():
    segment = parse_text("Savings\nSaving per vehicle times volume.").segments[0]
    chunks = chunk_segments([segment], count_tokens=lambda text: len(text.split()), budget=lambda _: 50, overlap_tokens=4)
    assert len(chunks) == 1 and chunks[0].window == 0 and chunks[0].section_heading == "Savings"


EVIDENCE = [
    {
        "rank": 1,
        "excerpt": "The alternator bracket is cast iron. Replacing it with HSLA steel saves 18 per cent of the mass.",
        "citation": "ACME/VAVE/TD-BM/2024/001, Sample teardown report, section 2.1 Alternator bracket, p. 3",
        "cosine_similarity": 0.61,
    },
    {"rank": 2, "excerpt": "Costs are fully absorbed.", "citation": "doc, section 1.1, p. 2", "cosine_similarity": 0.4},
]


class Model:
    name, model = "ollama", "test-model"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, messages, *, timeout):
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply)


def answer(evidence=EVIDENCE, threshold=None, chat=None, status="unavailable"):
    return compose_answer(
        "How much mass does the HSLA alternator bracket save?",
        evidence,
        threshold=threshold,
        chat_provider=chat or FallbackChatProvider(),
        llm_status=status,
        embedder=DeterministicEmbeddingProvider(),
        timeout=5,
    )


def test_without_a_language_model_the_answer_is_an_extractive_quote_from_the_top_passage():
    result = answer()
    assert result.mode == "extractive"
    assert result.text.startswith("Extractive answer: no language model was used.")
    assert "18 per cent" in result.text
    assert EVIDENCE[0]["citation"] in result.text
    assert result.citations == [EVIDENCE[0]]


def test_below_the_threshold_the_copilot_abstains_and_says_why():
    result = answer(threshold=0.7)
    assert result.mode == "abstained" and result.citations == []
    assert "0.610" in result.abstention_reason and "0.700" in result.abstention_reason


def test_without_a_threshold_a_low_score_is_still_answered():
    low = [{**EVIDENCE[0], "cosine_similarity": 0.05}]
    assert answer(evidence=low).mode == "extractive"


def test_with_nothing_retrieved_the_copilot_abstains():
    result = answer(evidence=[])
    assert result.mode == "abstained" and "No indexed passage" in result.abstention_reason


def test_generated_claims_keep_only_valid_citations():
    reply = {"claims": [{"text": "It saves 18 per cent.", "citations": [1]}, {"text": "Uncited.", "citations": [9]}]}
    result = answer(chat=Model(reply), status="pending")
    assert result.mode == "generated" and result.provider == "ollama"
    assert "It saves 18 per cent. [1]" in result.text
    assert "Uncited." not in result.text and "1 statement(s) without a valid citation were removed." in result.text
    assert result.citations == [EVIDENCE[0]]


def test_a_model_that_finds_the_passages_insufficient_abstains():
    result = answer(chat=Model({"claims": [], "insufficient": True}), status="pending")
    assert result.mode == "abstained" and "insufficient" in result.abstention_reason


def test_a_failed_model_call_falls_back_to_a_labelled_extractive_answer():
    result = answer(chat=Model(RuntimeError("connection refused")), status="pending")
    assert result.mode == "extractive"
    assert result.text.startswith("The language model did not return a usable answer")
