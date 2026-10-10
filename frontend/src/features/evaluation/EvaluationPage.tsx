import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatWhen, percent } from "@/lib/format";
import { errorMessage } from "@/lib/utils";

type Dataset = { id: string; name: string; description: string; dataset_type: string; cases: number };
type MetricBlock = { available?: boolean; reason?: string; [key: string]: unknown };
type Run = {
  id: string;
  provider: string;
  embedding_model: string;
  status: string;
  metrics: Record<string, MetricBlock | string>;
  notes: string | null;
  created_at: string | null;
};

export function EvaluationPage() {
  const { allowed } = useAuth();
  const queryClient = useQueryClient();
  const datasets = useQuery({ queryKey: ["eval-datasets"], queryFn: () => api<{ items: Dataset[] }>("/api/v1/evaluation/datasets") });
  const runs = useQuery({ queryKey: ["eval-runs"], queryFn: () => api<{ items: Run[] }>("/api/v1/evaluation/runs") });
  const run = useMutation({
    mutationFn: (datasetId: string) => api<Run>("/api/v1/evaluation/runs", { method: "POST", body: JSON.stringify({ dataset_id: datasetId }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["eval-runs"] }),
  });
  return (
    <div className="space-y-4">
      <PageHeader
        title="Evaluation"
        description="Metrics are calculated only from labelled cases. A small synthetic set is not a production accuracy claim."
      />
      {datasets.isLoading ? <LoadingBlock /> : null}
      {datasets.isError ? <ErrorState message={errorMessage(datasets.error)} onRetry={() => datasets.refetch()} /> : null}
      {(datasets.data?.items.length ?? 0) === 0 ? <EmptyState title="No labelled datasets" body="Precision and recall stay unavailable until labelled cases exist." /> : null}
      <div className="grid gap-3 md:grid-cols-2">
        {datasets.data?.items.map((dataset) => (
          <section key={dataset.id} className="card p-4">
            <h2 className="text-sm font-semibold">{dataset.name}</h2>
            <p className="mt-1 text-sm text-muted">{dataset.description}</p>
            <p className="mt-2 text-xs">{dataset.dataset_type} · {dataset.cases} cases</p>
            {allowed("evaluation:run") ? (
              <Button className="mt-3" size="sm" onClick={() => run.mutate(dataset.id)} disabled={run.isPending}>Run evaluation</Button>
            ) : null}
          </section>
        ))}
      </div>
      {run.isError ? <ErrorState message={errorMessage(run.error)} /> : null}
      <section>
        <h2 className="mb-2 text-sm font-semibold">Runs</h2>
        {(runs.data?.items.length ?? 0) === 0 ? <EmptyState title="No evaluation runs" body="Run a labelled dataset to record provider, embedding model, and metrics." /> : null}
        <div className="space-y-3">
          {runs.data?.items.map((item) => (
            <article key={item.id} className="card p-4 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p>{formatWhen(item.created_at)} · {item.provider} · {item.embedding_model}</p>
                <button type="button" className="text-accent-700" onClick={() => downloadFile(`/api/v1/exports/evaluation/${item.id}?format=xlsx`, "vave-evaluation.xlsx")}>Export</button>
              </div>
              <p className="mt-1 text-xs text-muted">{item.notes}</p>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {Object.entries(item.metrics || {}).map(([name, block]) => (
                  <MetricCard key={name} name={name} block={block} />
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function MetricCard({ name, block }: { name: string; block: MetricBlock | string }) {
  if (typeof block === "string") return <p>{name}: {block}</p>;
  if (block.available === false) {
    return (
      <div className="rounded border border-line p-3">
        <h3 className="font-medium">{name}</h3>
        <p className="mt-1 text-muted">{String(block.reason ?? "This metric was not calculated.")}</p>
      </div>
    );
  }
  return (
    <div className="rounded border border-line p-3">
      <h3 className="font-medium">{name}</h3>
      <ul className="mt-2 space-y-1">
        {Object.entries(block).filter(([key]) => !["available"].includes(key)).map(([key, value]) => (
          <li key={key}>{key}: {formatMetric(key, value)}</li>
        ))}
      </ul>
    </div>
  );
}

function formatMetric(key: string, value: unknown): string {
  if (typeof value === "number" && ["precision", "recall", "f1", "false_positive_rate", "false_negative_rate", "top_k_success", "mean_reciprocal_rank", "citation_hit_rate"].includes(key)) {
    return percent(value);
  }
  if (value === null || value === undefined) return "Not calculated";
  return String(value);
}
