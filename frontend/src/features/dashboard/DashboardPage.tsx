import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState, LoadingBlock, Metric, PageHeader, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { count, formatWhen, inr } from "@/lib/format";
import { errorMessage } from "@/lib/utils";
import type { DashboardSummary, Options } from "@/types";

export function DashboardPage() {
  const navigate = useNavigate();
  const options = useQuery({ queryKey: ["options"], queryFn: () => api<Options>("/api/v1/meta/options") });
  const [filters, setFilters] = useState({ department_id: "", stage_status: "", rejected: "", vehicle_family_id: "" });
  const summary = useQuery({
    queryKey: ["dashboard", filters],
    queryFn: () => {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      const query = params.toString();
      return api<DashboardSummary>(`/api/v1/dashboard/summary${query ? `?${query}` : ""}`);
    },
  });

  if (summary.isLoading) return <LoadingBlock label="Loading dashboard" />;
  if (summary.isError) return <ErrorState message={errorMessage(summary.error)} onRetry={() => summary.refetch()} />;
  const data = summary.data;
  if (!data) return null;

  return (
    <div>
      <PageHeader
        title="Executive dashboard"
        description="Live counts from stored historical ideas. Projected savings are INR and are not verified realised savings."
      />
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <Select aria-label="Department" value={filters.department_id} onChange={(event) => setFilters({ ...filters, department_id: event.target.value })}>
          <option value="">All belonged departments</option>
          {(options.data?.departments ?? []).map((item) => (
            <option key={item.id} value={item.id}>{item.name}</option>
          ))}
        </Select>
        <Select aria-label="Stage" value={filters.stage_status} onChange={(event) => setFilters({ ...filters, stage_status: event.target.value })}>
          <option value="">All stages</option>
          {(options.data?.stage_statuses ?? []).map((stage) => (
            <option key={stage} value={stage}>Stage {stage}</option>
          ))}
        </Select>
        <Select aria-label="Rejection" value={filters.rejected} onChange={(event) => setFilters({ ...filters, rejected: event.target.value })}>
          <option value="">Active and rejected</option>
          <option value="false">Active / not rejected</option>
          <option value="true">Rejected</option>
        </Select>
        <Select aria-label="Vehicle family" value={filters.vehicle_family_id} onChange={(event) => setFilters({ ...filters, vehicle_family_id: event.target.value })}>
          <option value="">All vehicle families</option>
          {(options.data?.vehicle_families ?? []).map((item) => (
            <option key={item.id} value={item.id}>{item.name}</option>
          ))}
        </Select>
      </div>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Historical ideas" value={count(data.total_ideas)} />
        <Metric label="Active" value={count(data.active_ideas)} hint="Blank rejection category" />
        <Metric label="Rejected" value={count(data.rejected_ideas)} hint="Populated rejection category" />
        <Metric label="Potential duplicates" value={count(data.potential_duplicates)} hint="Identical text or analysis flag. Not a probability." />
        <Metric label="Awaiting review" value={count(data.awaiting_review)} />
        <Metric label="Projected annual savings" value={inr(data.total_projected_savings)} hint="Calculated, INR" />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <ChartCard title="Ideas by stage" data={data.by_stage} xKey="stage" onPick={(stage) => navigate(`/ideas?stage_status=${stage}`)} />
        <ChartCard title="Ideas by belonged department" data={data.by_department} xKey="name" onPick={(name) => {
          const match = options.data?.departments.find((item) => item.name === name);
          navigate(match ? `/ideas?department_id=${match.id}` : "/ideas");
        }} />
        <ChartCard title="Rejections by department" data={data.rejections_by_department} xKey="name" onPick={() => navigate("/analytics/rejections")} />
        <ChartCard title="Rejections by category" data={data.rejections_by_category} xKey="category" onPick={(category) => navigate(`/ideas?rejected=true&rejection_category=${encodeURIComponent(category)}`)} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <section className="card p-4">
          <h2 className="text-sm font-semibold">Submission trend</h2>
          <div className="mt-3 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.submission_trend}>
                <CartesianGrid stroke="#e6ebf0" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#1f4e79" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="card p-4">
          <h2 className="text-sm font-semibold">Data quality</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li>Missing description: {data.data_quality.missing_description}</li>
            <li>Missing belonged department: {data.data_quality.missing_department}</li>
            <li>Savings mismatches: {data.data_quality.savings_mismatch}</li>
            <li>Import error rows: {data.data_quality.import_issues}</li>
            <li>Invalid dates held back at import: {data.data_quality.invalid_dates}</li>
          </ul>
          <p className="mt-3 text-xs leading-5 text-muted">{data.dataset_note}</p>
        </section>
      </div>
      <section className="card mt-4 p-4">
        <h2 className="text-sm font-semibold">Recent activity</h2>
        {data.recent_activity.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No audit events yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line text-sm">
            {data.recent_activity.map((item) => (
              <li key={item.id} className="flex justify-between gap-3 py-2">
                <span>{item.action}{item.actor ? ` · ${item.actor}` : ""}</span>
                <span className="text-muted">{formatWhen(item.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ChartCard({
  title,
  data,
  xKey,
  onPick,
}: {
  title: string;
  data: Record<string, string | number>[];
  xKey: string;
  onPick: (value: string) => void;
}) {
  return (
    <section className="card p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-3 h-56">
        {data.length === 0 ? (
          <p className="text-sm text-muted">No records for this filter.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              onClick={(state) => {
                const value = state?.activePayload?.[0]?.payload?.[xKey];
                if (value) onPick(String(value));
              }}
            >
              <CartesianGrid stroke="#e6ebf0" vertical={false} />
              <XAxis dataKey={xKey} tick={{ fontSize: 11 }} interval={0} angle={-25} height={60} textAnchor="end" />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#274864" cursor="pointer" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
