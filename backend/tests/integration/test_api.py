"""API workflow against the disposable PostgreSQL database."""

from __future__ import annotations

import httpx
from app.services.imports.workbook import build_workbook_bytes
from tests.conftest import auth, login

PARAPHRASE = (
    "Use an aluminum alloy cab mounting bracket instead of the steel bracket, "
    "sized so stiffness stays equivalent and vehicle mass drops."
)
TOPOLOGY = (
    "Redesign the cab mounting bracket as a topology-optimised steel casting, "
    "removing material only from low-stress regions while retaining the steel grade."
)
BRAKE = "Chamfer the edge of the disc brake pad to cut noise and to use a cheaper friction material."


def test_health(client):
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["pgvector"] == "ok"
    assert body["ai_mode"] == "fallback"


def test_viewer_cannot_create_ideas(client):
    token = login(client, "viewer@vave.local", "VaveDemo!234")
    response = client.post("/api/v1/ideas", headers=auth(token), json={"description": "A long enough draft description.", "submit": False})
    assert response.status_code == 403


def test_dashboard_and_savings_match_the_formula(client):
    token = login(client, "engineer@vave.local", "VaveDemo!234")
    summary = client.get("/api/v1/dashboard/summary", headers=auth(token))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_ideas"] == 20
    assert body["rejected_ideas"] == 7
    assert body["active_ideas"] == 13
    assert body["total_projected_savings"] == 18064500.0
    ideas = client.get("/api/v1/ideas", headers=auth(token), params={"idea_code": "VAVE-SYN-001", "origin": "historical"})
    record = ideas.json()["items"][0]
    assert record["total_combined_annual_saving"] == 1170000.0
    assert record["is_rejected"] is False
    assert record["is_synthetic"] is True
    mismatch = client.get("/api/v1/ideas", headers=auth(token), params={"idea_code": "VAVE-SYN-018", "origin": "historical"})
    row = mismatch.json()["items"][0]
    assert row["total_combined_annual_saving"] == 45000.0
    assert row["reported_total_saving"] == 46000.0
    assert row["savings_mismatch"] is True


def test_exception_sheet_is_rejected_until_fixed(client):
    token = login(client, "admin@vave.local", "ChangeMeAdmin!23")
    preview = client.post(
        "/api/v1/ideas/import/preview",
        headers=auth(token),
        files={"file": ("synthetic.xlsx", build_workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"sheet_name": "Exceptions", "merge_strategy": "reject_conflicts", "is_synthetic": "true", "allow_partial": "false"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["error_count"] > 0
    assert body["status"] == "preview"
    messages = " ".join(item["message"] for item in body["errors"])
    assert "Duplicate" in messages or "Stage" in messages or "Idea ID" in messages
    commit = client.post("/api/v1/ideas/import/commit", headers=auth(token), json={"batch_id": body["id"], "confirm": True})
    assert commit.status_code == 400


def test_valid_import_commits_and_indexes(client):
    from app.db.session import get_session_factory
    from app.models import EmbeddingRecord, Idea, ImportChange
    from sqlalchemy import delete, func, select

    token = login(client, "admin@vave.local", "ChangeMeAdmin!23")
    csv = (
        "Idea_ID,Component,Idea belonged department,Idea_Description,Stage_Status\n"
        "VAVE-TEST-IMPORT-001,Fuel tank strap,Chassis,Replace the fuel tank strap rubber liner with a cheaper EPDM grade.,A\n"
    )
    preview = client.post(
        "/api/v1/ideas/import/preview",
        headers=auth(token),
        files={"file": ("one-row.csv", csv.encode(), "text/csv")},
        data={"merge_strategy": "reject_conflicts", "is_synthetic": "true", "allow_partial": "false"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["error_count"] == 0
    batch_id = preview.json()["id"]

    commit = client.post("/api/v1/ideas/import/commit", headers=auth(token), json={"batch_id": batch_id, "confirm": True})
    assert commit.status_code == 200, commit.text
    assert commit.json()["inserted_count"] == 1
    db = get_session_factory()()
    try:
        idea_id = db.scalar(select(Idea.id).where(Idea.idea_code == "VAVE-TEST-IMPORT-001"))
        assert idea_id is not None
        vectors = db.scalar(select(func.count()).select_from(EmbeddingRecord).where(EmbeddingRecord.entity_id == idea_id))
        assert vectors == 1
    finally:
        # Remove the row directly so later tests see only the seeded ideas. Rollback cannot do this yet:
        # import_changes.idea_id is NOT NULL with no ON DELETE rule, so deleting the idea is refused.
        db.execute(delete(ImportChange).where(ImportChange.batch_id == batch_id))
        db.execute(delete(EmbeddingRecord).where(EmbeddingRecord.entity_type == "idea", EmbeddingRecord.entity_id == idea_id))
        db.execute(delete(Idea).where(Idea.id == idea_id))
        db.commit()
        db.close()


def test_duplicate_analysis_and_review_leave_history_unchanged(client):
    token = login(client, "engineer@vave.local", "VaveDemo!234")
    analysis = client.post(
        "/api/v1/ideas/analyze-duplicates",
        headers=auth(token),
        json={
            "component": "Cab mounting bracket",
            "idea_belonged_department": "Cab",
            "description": PARAPHRASE,
            "proposed_change": "Use an aluminium alloy bracket sized for equivalent stiffness.",
            "expected_benefit": "Lower mass.",
            "constraints": "Stiffness and durability.",
            "is_synthetic": True,
            "submit": True,
        },
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["outcome_category"] == "potential_duplicate"
    assert body["provider"] == "deterministic"
    codes = [item["historical"]["idea_code"] for item in body["candidates"] if item["historical"]]
    assert "VAVE-SYN-001" in codes
    historical = next(item for item in body["candidates"] if item["historical"]["idea_code"] == "VAVE-SYN-001")
    assert historical["category"] == "potential_duplicate"
    before = client.get(f"/api/v1/ideas/{historical['historical']['id']}", headers=auth(token)).json()
    review = client.post(
        "/api/v1/reviews",
        headers=auth(token),
        json={
            "run_id": body["id"],
            "candidate_id": historical["id"],
            "decision": "similar_but_distinct",
            "rationale": "The wording differs enough that engineering should confirm the section size.",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["historical_records_changed"] is False
    after = client.get(f"/api/v1/ideas/{before['id']}", headers=auth(token)).json()
    assert after["rejection_category"] == before["rejection_category"]
    assert after["stage_status"] == before["stage_status"]
    assert after["description"] == before["description"]

    topology = client.post(
        "/api/v1/ideas/analyze-duplicates",
        headers=auth(token),
        json={
            "component": "Cab mounting bracket",
            "idea_belonged_department": "Cab",
            "description": TOPOLOGY,
            "proposed_change": "Topology-optimised steel casting.",
            "is_synthetic": True,
            "submit": True,
        },
    )
    assert topology.status_code == 200, topology.text
    top = topology.json()
    matched = next(item for item in top["candidates"] if item["historical"] and item["historical"]["idea_code"] == "VAVE-SYN-001")
    assert matched["category"] != "potential_duplicate"

    rejected = client.post(
        "/api/v1/ideas/analyze-duplicates",
        headers=auth(token),
        json={
            "component": "Disc brake pad",
            "idea_belonged_department": "Brake",
            "description": BRAKE,
            "is_synthetic": True,
            "submit": True,
        },
    )
    assert rejected.status_code == 200, rejected.text
    brake = next(item for item in rejected.json()["candidates"] if item["historical"] and item["historical"]["idea_code"] == "VAVE-SYN-002")
    assert brake["historical"]["rejection_category"] == "Durability"
    assert brake["historical"]["rejected_department"] == "Quality"
    assert brake["historical"]["rejection_reason"] == "Durability concern"


def test_copilot_cites_the_guideline(client):
    token = login(client, "engineer@vave.local", "VaveDemo!234")
    response = client.post(
        "/api/v1/copilot/chat",
        headers=auth(token),
        json={"message": "How is total combined annual saving calculated?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["abstained"] is False
    # Fallback mode has no language model, so the answer is a labelled quote from the top passage.
    assert body["answer_mode"] == "extractive"
    assert body["provider"] == "extractive"
    assert body["answer"].startswith("Extractive answer")
    [citation] = body["citations"]
    assert "saving per vehicle" in citation["excerpt"].lower()
    assert citation["section_heading"] == "Savings"
    assert citation["document_title"] == "Synthetic VAVE guideline"
    assert len(body["evidence"]) <= 5


def test_copilot_abstains_below_the_citation_threshold_and_says_why(client):
    admin = login(client, "admin@vave.local", "ChangeMeAdmin!23")
    engineer = login(client, "engineer@vave.local", "VaveDemo!234")
    try:
        assert client.put("/api/v1/ai/settings", headers=auth(admin), json={"copilot_citation_threshold": 1.0}).status_code == 200
        body = client.post("/api/v1/copilot/chat", headers=auth(engineer), json={"message": "How is total combined annual saving calculated?"}).json()
        assert body["abstained"] is True and body["answer_mode"] == "abstained"
        assert "below the citation-confidence threshold of 1.000" in body["abstention_reason"]
        assert body["citations"] == []
    finally:
        reset = client.put("/api/v1/ai/settings", headers=auth(admin), json={"copilot_citation_threshold": None})
        assert reset.json()["copilot_citation_threshold"] is None


def test_evaluation_reports_only_labelled_metrics(client):
    token = login(client, "engineer@vave.local", "VaveDemo!234")
    datasets = client.get("/api/v1/evaluation/datasets", headers=auth(token))
    assert datasets.status_code == 200
    duplicate = next(item for item in datasets.json()["items"] if item["dataset_type"] == "duplicate")
    run = client.post("/api/v1/evaluation/runs", headers=auth(token), json={"dataset_id": duplicate["id"]})
    assert run.status_code == 200, run.text
    metrics = run.json()["metrics"]
    assert metrics["available"] is True
    assert metrics["support"] >= 1
    assert "not a production accuracy claim" in run.json()["notes"]


def test_offline_mode_does_not_call_openai(client, monkeypatch):
    token = login(client, "admin@vave.local", "ChangeMeAdmin!23")
    calls: list[str] = []
    real = httpx.Client

    class Guard:
        def __init__(self, *args, **kwargs):
            self._inner = real(*args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self._inner.__exit__(exc_type, exc, tb)

        def request(self, method, url, *args, **kwargs):
            calls.append(str(url))
            if "api.openai.com" in str(url):
                raise AssertionError(f"OpenAI was called in offline mode: {url}")
            return self._inner.request(method, url, *args, **kwargs)

        def get(self, url, *args, **kwargs):
            return self.request("GET", url, *args, **kwargs)

        def post(self, url, *args, **kwargs):
            return self.request("POST", url, *args, **kwargs)

    monkeypatch.setattr(httpx, "Client", Guard)
    try:
        saved = client.put(
            "/api/v1/ai/settings",
            headers=auth(token),
            json={"mode": "offline", "embedding_provider": "deterministic", "embedding_model": "deterministic-hash-v1", "llm_required": False, "chat_model": "llama3.2"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["external_inference_blocked"] is True
        analysis = client.post(
            "/api/v1/ideas/analyze-duplicates",
            headers=auth(token),
            json={
                "component": "Cab mounting bracket",
                "idea_belonged_department": "Cab",
                "description": PARAPHRASE,
                "is_synthetic": True,
                "submit": True,
            },
        )
        assert analysis.status_code == 200, analysis.text
        assert analysis.json()["provider"] != "openai"
        assert not any("api.openai.com" in url for url in calls)
    finally:
        client.put(
            "/api/v1/ai/settings",
            headers=auth(token),
            json={"mode": "fallback", "embedding_provider": "deterministic", "embedding_model": "deterministic-hash-v1", "llm_required": False},
        )


def test_engineer_cannot_change_ai_settings(client):
    token = login(client, "engineer@vave.local", "VaveDemo!234")
    response = client.put("/api/v1/ai/settings", headers=auth(token), json={"mode": "online"})
    assert response.status_code == 403
