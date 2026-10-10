import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingBlock, PageHeader } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { errorMessage } from "@/lib/utils";

type Rejections = {
  count: number;
  note: string;
  by_category: { category: string; count: number }[];
  by_reason: { reason: string; count: number }[];
  by_rejected_department: { name: string; count: number }[];
  by_belonged_department: { name: string; count: number }[];
  by_stage: { stage: string; count: number }[];
};

export function RejectionsPage() {
  const data = useQuery({ queryKey: ["rejections"], queryFn: () => api<Rejections>("/api/v1/analytics/rejections") });
  if (data.isLoading) return <LoadingBlock />;
  if (data.isError || !data.data) return <ErrorState message={errorMessage(data.error)} onRetry={() => data.refetch()} />;
  const body = data.data;
  return (
    <div>
      <PageHeader
        title="Historical rejection intelligence"
        description={body.note}
        actions={<Button variant="secondary" onClick={() => downloadFile("/api/v1/exports/rejections?format=xlsx", "vave-rejections.xlsx")}>Download report</Button>}
      />
      <p className="mb-4 text-sm">{body.count} rejected ideas in the current historical set. <Link className="text-accent-700" to="/ideas?rejected=true">Open the records</Link></p>
      <div className="grid gap-4 lg:grid-cols-2">
        <CountTable title="Rejection category" rows={body.by_category.map((row) => [row.category, row.count])} />
        <CountTable title="Rejection reason" rows={body.by_reason.map((row) => [row.reason, row.count])} />
        <CountTable title="Rejected department" rows={body.by_rejected_department.map((row) => [row.name, row.count])} />
        <CountTable title="Idea belonged department" rows={body.by_belonged_department.map((row) => [row.name, row.count])} />
        <CountTable title="Stage status of rejected ideas" rows={body.by_stage.map((row) => [row.stage, row.count])} />
      </div>
    </div>
  );
}

function CountTable({ title, rows }: { title: string; rows: [string, number][] }) {
  return (
    <section className="card p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      {rows.length === 0 ? <p className="mt-3 text-sm text-muted">No stored values.</p> : (
        <table className="data mt-3">
          <thead><tr><th>Value</th><th>Count</th></tr></thead>
          <tbody>{rows.map(([label, count]) => <tr key={label}><td>{label}</td><td>{count}</td></tr>)}</tbody>
        </table>
      )}
    </section>
  );
}
