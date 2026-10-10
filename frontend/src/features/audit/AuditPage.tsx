import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorState, Input, LoadingBlock, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { formatWhen, text } from "@/lib/format";
import { errorMessage } from "@/lib/utils";

type Row = {
  id: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  actor: string | null;
  details: Record<string, unknown>;
  created_at: string | null;
};

export function AuditPage() {
  const [q, setQ] = useState("");
  const logs = useQuery({
    queryKey: ["audit", q],
    queryFn: () => api<{ items: Row[] }>(`/api/v1/audit-logs${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  });
  return (
    <div>
      <PageHeader title="Audit log" description="Actions are recorded without idea description bodies or prompts." />
      <Input aria-label="Filter audit actions" className="mb-4 max-w-sm" placeholder="Filter by action" value={q} onChange={(event) => setQ(event.target.value)} />
      {logs.isLoading ? <LoadingBlock /> : null}
      {logs.isError ? <ErrorState message={errorMessage(logs.error)} onRetry={() => logs.refetch()} /> : null}
      {logs.data ? (
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>When</th><th>Action</th><th>Actor</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody>
              {logs.data.items.map((row) => (
                <tr key={row.id}>
                  <td>{formatWhen(row.created_at)}</td>
                  <td>{row.action}</td>
                  <td>{text(row.actor)}</td>
                  <td>{text(row.entity_type)}</td>
                  <td className="max-w-md truncate">{JSON.stringify(row.details ?? {})}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
