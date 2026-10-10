import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingBlock, Metric, PageHeader } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { inr } from "@/lib/format";
import { errorMessage } from "@/lib/utils";

type Savings = {
  projected_total: number;
  active_projected_saving: number;
  rejected_projected_saving: number;
  duplicate_associated_projected_saving: number;
  by_department: { name: string; projected_saving: number; count: number }[];
  by_vehicle_family: { name: string; projected_saving: number }[];
  by_stage: { stage: string; projected_saving: number; count: number }[];
  currency: string;
  kind: string;
  assumptions: string[];
};

export function SavingsPage() {
  const data = useQuery({ queryKey: ["savings"], queryFn: () => api<Savings>("/api/v1/analytics/savings") });
  if (data.isLoading) return <LoadingBlock />;
  if (data.isError || !data.data) return <ErrorState message={errorMessage(data.error)} onRetry={() => data.refetch()} />;
  const savings = data.data;
  return (
    <div>
      <PageHeader
        title="Savings and value"
        description="Projected annual saving = saving per vehicle × the sum of unique vehicle-family annual volumes. Figures are INR and are not verified realised savings."
        actions={<Button variant="secondary" onClick={() => downloadFile("/api/v1/exports/savings?format=xlsx", "vave-savings.xlsx")}>Download report</Button>}
      />
      <div className="grid gap-3 md:grid-cols-4">
        <Metric label="Projected total" value={inr(savings.projected_total)} hint={savings.kind} />
        <Metric label="Active ideas" value={inr(savings.active_projected_saving)} />
        <Metric label="Rejected ideas" value={inr(savings.rejected_projected_saving)} />
        <Metric label="Duplicate-associated" value={inr(savings.duplicate_associated_projected_saving)} hint="Not subtracted from the gross total." />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Chart title="By department" data={savings.by_department} x="name" />
        <Chart title="By vehicle family" data={savings.by_vehicle_family} x="name" />
      </div>
      <section className="card mt-4 p-4">
        <h2 className="text-sm font-semibold">By stage</h2>
        <table className="data mt-3">
          <thead><tr><th>Stage</th><th>Ideas</th><th>Projected annual saving</th></tr></thead>
          <tbody>
            {savings.by_stage.map((row) => (
              <tr key={row.stage}><td>{row.stage}</td><td>{row.count}</td><td>{inr(row.projected_saving)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
      <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted">
        {savings.assumptions.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function Chart({ title, data, x }: { title: string; data: { projected_saving: number; name: string }[]; x: string }) {
  return (
    <section className="card p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-3 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid stroke="#e6ebf0" vertical={false} />
            <XAxis dataKey={x} tick={{ fontSize: 11 }} interval={0} angle={-25} height={70} textAnchor="end" />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="projected_saving" fill="#1f4e79" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
