import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { decisionLabel, formatWhen, outcomeLabel } from "@/lib/format";
import { errorMessage } from "@/lib/utils";

export function ReviewsPage() {
  const [queue, setQueue] = useState<"pending" | "history">("pending");
  const pending = useQuery({
    queryKey: ["reviews", "pending"],
    queryFn: () =>
      api<{ items: { id: string; idea_code: string | null; outcome_category: string; created_at: string | null }[] }>(
        "/api/v1/reviews?queue=pending",
      ),
    enabled: queue === "pending",
  });
  const history = useQuery({
    queryKey: ["reviews", "history"],
    queryFn: () =>
      api<{ items: { id: string; run_id: string; decision: string; rationale: string; ai_recommendation: string | null; actor: string | null; created_at: string | null }[] }>(
        "/api/v1/reviews",
      ),
    enabled: queue === "history",
  });
  const active = queue === "pending" ? pending : history;
  return (
    <div>
      <PageHeader
        title="Review queue"
        description="The human decision is stored separately from the AI recommendation. Confirming a duplicate does not edit the historical idea."
        actions={
          <>
            <Button variant={queue === "pending" ? "primary" : "secondary"} onClick={() => setQueue("pending")}>Awaiting review</Button>
            <Button variant={queue === "history" ? "primary" : "secondary"} onClick={() => setQueue("history")}>Decision history</Button>
            <Button variant="secondary" onClick={() => downloadFile("/api/v1/exports/reviews?format=csv", "vave-review-decisions.csv")}>Export CSV</Button>
          </>
        }
      />
      {active.isLoading ? <LoadingBlock /> : null}
      {active.isError ? <ErrorState message={errorMessage(active.error)} onRetry={() => active.refetch()} /> : null}
      {queue === "pending" && pending.data?.items.length === 0 ? (
        <EmptyState title="Queue is clear" body="Analyses without a human decision will appear here." />
      ) : null}
      {queue === "pending" && pending.data && pending.data.items.length > 0 ? (
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Idea</th><th>AI outcome</th><th>Created</th></tr></thead>
            <tbody>
              {pending.data.items.map((row) => (
                <tr key={row.id}>
                  <td><Link className="text-accent-700" to={`/analyses/${row.id}`}>{row.idea_code ?? "Open analysis"}</Link></td>
                  <td>{outcomeLabel(row.outcome_category)}</td>
                  <td>{formatWhen(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {queue === "history" && history.data?.items.length === 0 ? (
        <EmptyState title="No decisions recorded" body="Review decisions will be listed with the reviewer, time, and rationale." />
      ) : null}
      {queue === "history" && history.data && history.data.items.length > 0 ? (
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Decision</th><th>AI recommendation</th><th>Reviewer</th><th>Rationale</th><th>When</th></tr></thead>
            <tbody>
              {history.data.items.map((row) => (
                <tr key={row.id}>
                  <td><Link className="text-accent-700" to={`/analyses/${row.run_id}`}>{decisionLabel(row.decision)}</Link></td>
                  <td>{outcomeLabel(row.ai_recommendation)}</td>
                  <td>{row.actor ?? "Not recorded"}</td>
                  <td>{row.rationale}</td>
                  <td>{formatWhen(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
