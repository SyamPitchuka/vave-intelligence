import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Badge, EmptyState, ErrorState, FieldError, LoadingBlock, PageHeader, Textarea } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { decisionLabel, formatWhen, inr, outcomeLabel, text } from "@/lib/format";
import { reviewSchema } from "@/lib/schemas";
import { errorMessage } from "@/lib/utils";
import type { Analysis, AnalysisCandidate } from "@/types";

const DECISIONS = ["confirm_duplicate", "similar_but_distinct", "no_duplicate", "escalate"] as const;

export function AnalysesPage() {
  const rows = useQuery({
    queryKey: ["analyses"],
    queryFn: () =>
      api<{ items: { id: string; idea_code: string | null; outcome_category: string; provider: string; llm_status: string; created_at: string | null; has_human_decision: boolean }[] }>(
        "/api/v1/duplicate-analyses",
      ),
  });
  if (rows.isLoading) return <LoadingBlock />;
  if (rows.isError) return <ErrorState message={errorMessage(rows.error)} onRetry={() => rows.refetch()} />;
  return (
    <div>
      <PageHeader
        title="Duplicate detection"
        description="Analysis outcomes are recommendations. They are separate from Stage Status and from historical rejection fields."
        actions={<Button variant="secondary" onClick={() => downloadFile("/api/v1/exports/analyses?format=xlsx", "vave-duplicate-analyses.xlsx")}>Export</Button>}
      />
      {(rows.data?.items.length ?? 0) === 0 ? (
        <EmptyState title="No analyses yet" body="Submit an idea for duplicate analysis. The result will list historical candidates and the evidence used." />
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Idea</th><th>Outcome</th><th>Provider</th><th>LLM</th><th>Human decision</th><th>When</th>
              </tr>
            </thead>
            <tbody>
              {rows.data?.items.map((row) => (
                <tr key={row.id}>
                  <td><Link className="text-accent-700" to={`/analyses/${row.id}`}>{row.idea_code ?? row.id}</Link></td>
                  <td>{outcomeLabel(row.outcome_category)}</td>
                  <td>{row.provider}</td>
                  <td>{row.llm_status}</td>
                  <td>{row.has_human_decision ? "Recorded" : "Awaiting"}</td>
                  <td>{formatWhen(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function AnalysisDetailPage() {
  const { analysisId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { allowed } = useAuth();
  const analysis = useQuery({ queryKey: ["analysis", analysisId], queryFn: () => api<Analysis>(`/api/v1/duplicate-analyses/${analysisId}`) });
  const rerun = useMutation({
    mutationFn: () => api<Analysis>(`/api/v1/duplicate-analyses/${analysisId}/rerun`, { method: "POST" }),
    onSuccess: (next) => navigate(`/analyses/${next.id}`),
  });
  if (analysis.isLoading) return <LoadingBlock label="Loading analysis" />;
  if (analysis.isError) return <ErrorState message={errorMessage(analysis.error)} onRetry={() => analysis.refetch()} />;
  const data = analysis.data;
  if (!data) return null;
  return (
    <div className="space-y-4">
      <PageHeader
        title={outcomeLabel(data.outcome_category)}
        description={`${data.score_note} Provider ${data.provider}. Embedding ${data.embedding_model}. Retrieval count ${data.retrieval_k}.`}
        actions={
          allowed("analysis:run") ? (
            <Button variant="secondary" onClick={() => rerun.mutate()} disabled={rerun.isPending}>Re-run analysis</Button>
          ) : null
        }
      />
      {data.warning ? <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm">{data.warning}</p> : null}
      {rerun.isError ? <ErrorState message={errorMessage(rerun.error)} /> : null}
      <section className="card p-4 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge tone="blue">{data.provider}</Badge>
          <Badge>{data.llm_status}</Badge>
          <Badge tone="slate">{formatWhen(data.created_at)}</Badge>
          <Badge>Analysis {data.id.slice(0, 8)}</Badge>
        </div>
        <h2 className="mt-4 font-semibold">New idea</h2>
        {data.submission ? (
          <p className="mt-2 leading-6">
            <Link className="text-accent-700" to={`/ideas/${data.submission.id}`}>{data.submission.idea_code}</Link>
            {" · "}{text(data.submission.component)}
            <span className="mt-2 block">{text(data.submission.description)}</span>
          </p>
        ) : <p>The submitted idea is no longer available.</p>}
        {data.human_decision ? (
          <p className="mt-3 rounded bg-canvas px-3 py-2">
            Human decision: {decisionLabel(data.human_decision.decision)}. AI recommendation at the time: {outcomeLabel(data.human_decision.ai_recommendation)}. {data.human_decision.rationale}
          </p>
        ) : null}
      </section>
      {data.candidates.length === 0 ? (
        <EmptyState title="No strong historical candidate" body="The pipeline did not return a candidate above the configured retrieval floors. This is not a claim that no similar idea exists." />
      ) : (
        data.candidates.map((candidate) => (
          <CandidateCard
            key={candidate.id}
            analysisId={data.id}
            candidate={candidate}
            canReview={allowed("reviews:write") && !data.human_decision}
            onDecided={() => queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] })}
          />
        ))
      )}
    </div>
  );
}

export function CandidateCard({
  analysisId,
  candidate,
  canReview,
  onDecided,
}: {
  analysisId: string;
  candidate: AnalysisCandidate;
  canReview: boolean;
  onDecided: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("confirm_duplicate");
  const [rationale, setRationale] = useState("");
  const [formError, setFormError] = useState("");
  const historical = candidate.historical;
  const save = useMutation({
    mutationFn: () =>
      api("/api/v1/reviews", {
        method: "POST",
        body: JSON.stringify({ run_id: analysisId, candidate_id: candidate.id, decision, rationale }),
      }),
    onSuccess: () => {
      setOpen(false);
      onDecided();
    },
  });
  const parsed = reviewSchema.safeParse({ decision, rationale });

  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted">Rank {candidate.rank}</p>
          <h3 className="text-base font-semibold">
            {historical ? <Link className="text-accent-700" to={`/ideas/${historical.id}`}>{historical.idea_code}</Link> : "Historical record unavailable"}
          </h3>
          <p className="text-sm text-muted">{text(historical?.component)}</p>
        </div>
        <Badge tone={candidate.category === "potential_duplicate" ? "amber" : "blue"}>{outcomeLabel(candidate.category)}</Badge>
      </div>
      <dl className="mt-3 grid gap-2 text-sm md:grid-cols-4">
        <div><dt className="text-xs text-muted">Exact match</dt><dd>{candidate.exact_match ? "Yes" : "No"}</dd></div>
        <div><dt className="text-xs text-muted">Fuzzy score</dt><dd>{candidate.fuzzy_score ?? "Not recorded"}</dd></div>
        <div><dt className="text-xs text-muted">Cosine similarity</dt><dd>{candidate.cosine_similarity ?? "Not recorded"}</dd></div>
        <div><dt className="text-xs text-muted">Signals</dt><dd>Retrieval only</dd></div>
      </dl>
      <p className="mt-3 text-sm leading-6">{text(candidate.explanation)}</p>
      <div className="mt-3 grid gap-3 md:grid-cols-2 text-sm">
        <div>
          <h4 className="font-medium">Similarities</h4>
          <ul className="mt-1 list-disc pl-5">{(candidate.similarities ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div>
          <h4 className="font-medium">Differences</h4>
          <ul className="mt-1 list-disc pl-5">{(candidate.differences ?? []).length ? candidate.differences.map((item) => <li key={item}>{item}</li>) : <li>None recorded.</li>}</ul>
        </div>
      </div>
      <dl className="mt-4 grid gap-2 text-sm md:grid-cols-3">
        <div><dt className="text-xs text-muted">Stage</dt><dd>{text(historical?.stage_status)}</dd></div>
        <div><dt className="text-xs text-muted">Rejection category</dt><dd>{text(historical?.rejection_category)}</dd></div>
        <div><dt className="text-xs text-muted">Rejection reason</dt><dd>{text(historical?.rejection_reason)}</dd></div>
        <div><dt className="text-xs text-muted">Belonged department</dt><dd>{text(historical?.idea_belonged_department)}</dd></div>
        <div><dt className="text-xs text-muted">Rejected department</dt><dd>{text(historical?.rejected_department)}</dd></div>
        <div><dt className="text-xs text-muted">Projected annual saving</dt><dd>{inr(historical?.total_combined_annual_saving)}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-muted">A historical rejection does not make this new idea invalid.</p>
      {canReview ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {DECISIONS.map((item) => (
            <Button key={item} size="sm" variant="secondary" onClick={() => { setDecision(item); setOpen(true); }}>
              {decisionLabel(item)}
            </Button>
          ))}
        </div>
      ) : null}
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={decisionLabel(decision)}
        description="This records your decision beside the AI recommendation. Official historical rejection fields will not be changed."
        confirmLabel="Record decision"
        pending={save.isPending || !parsed.success}
        onConfirm={() => {
          if (!parsed.success) {
            setFormError(parsed.error.issues[0]?.message ?? "Check the rationale.");
            return;
          }
          setFormError("");
          save.mutate();
        }}
      >
        <label htmlFor="rationale" className="text-sm font-medium">Decision rationale</label>
        <Textarea id="rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
        <FieldError>{formError || (save.error ? errorMessage(save.error) : undefined)}</FieldError>
      </ConfirmDialog>
    </article>
  );
}
