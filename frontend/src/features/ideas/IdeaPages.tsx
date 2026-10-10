import { zodResolver } from "@hookform/resolvers/zod";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type VisibilityState,
} from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorState, FieldError, Hint, Input, Label, LoadingBlock, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, inr, outcomeLabel, text } from "@/lib/format";
import { buildIdeaQuery, ideaDraftSchema, ideaSubmitSchema, type IdeaFormValues } from "@/lib/schemas";
import { errorMessage } from "@/lib/utils";
import type { Idea, Options, Paged } from "@/types";

const helper = createColumnHelper<Idea>();

const columns = [
  helper.accessor("idea_code", { header: "Idea ID" }),
  helper.accessor("component", { header: "Component", cell: (info) => text(info.getValue()) }),
  helper.accessor("idea_belonged_department", { header: "Belonged department", cell: (info) => text(info.getValue()) }),
  helper.accessor("rejected_department", { header: "Rejected department", cell: (info) => text(info.getValue()) }),
  helper.accessor("stage_status", { header: "Stage", cell: (info) => text(info.getValue()) }),
  helper.accessor("rejection_category", { header: "Rejection category", cell: (info) => text(info.getValue()) }),
  helper.accessor("rejection_reason", { header: "Rejection reason", cell: (info) => text(info.getValue()) }),
  helper.accessor("idea_type", { header: "Type", cell: (info) => text(info.getValue()) }),
  helper.accessor("saving_per_vehicle", { header: "Saving / vehicle (INR)", cell: (info) => inr(info.getValue()) }),
  helper.accessor("total_combined_annual_saving", { header: "Projected annual (INR)", cell: (info) => inr(info.getValue()) }),
  helper.accessor("idea_generation_date", { header: "Generation date", cell: (info) => formatDate(info.getValue()) }),
  helper.accessor("is_synthetic", {
    header: "Source",
    cell: (info) => (info.getValue() ? <Badge tone="amber">Synthetic</Badge> : <Badge>Recorded</Badge>),
  }),
];

export function IdeasPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const options = useQuery({ queryKey: ["options"], queryFn: () => api<Options>("/api/v1/meta/options") });
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const filters = {
    q: params.get("q") ?? "",
    idea_code: params.get("idea_code") ?? "",
    component: params.get("component") ?? "",
    department_id: params.get("department_id") ?? "",
    rejected_department_id: params.get("rejected_department_id") ?? "",
    stage_status: params.get("stage_status") ?? "",
    rejection_category: params.get("rejection_category") ?? "",
    rejection_reason: params.get("rejection_reason") ?? "",
    idea_type: params.get("idea_type") ?? "",
    rejected: params.get("rejected") ?? "",
    vehicle_family_id: params.get("vehicle_family_id") ?? "",
    origin: params.get("origin") ?? "historical",
    page: params.get("page") ?? "1",
    sort: params.get("sort") ?? "idea_generation_date",
    order: params.get("order") ?? "desc",
  };
  const ideas = useQuery({
    queryKey: ["ideas", filters],
    queryFn: () => api<Paged<Idea>>(`/api/v1/ideas${buildIdeaQuery({ ...filters, page_size: "25" })}`),
  });
  const table = useReactTable({
    data: ideas.data?.items ?? [],
    columns,
    state: { columnVisibility: visibility },
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
  });

  function update(next: Partial<typeof filters>) {
    const merged = { ...filters, ...next, page: next.page ?? "1" };
    const search = new URLSearchParams();
    Object.entries(merged).forEach(([key, value]) => {
      if (value) search.set(key, value);
    });
    setParams(search);
  }

  return (
    <div>
      <PageHeader
        title="Idea Explorer"
        description="Historical records as stored. Blank fields stay blank. A populated rejection category means rejected."
        actions={
          <Button variant="secondary" onClick={() => downloadFile(`/api/v1/exports/ideas.xlsx`.replace(".xlsx", "") + buildIdeaQuery({ origin: filters.origin, rejected: filters.rejected, stage_status: filters.stage_status, department_id: filters.department_id, format: "xlsx" }), "vave-ideas.xlsx")}>
            Export Excel
          </Button>
        }
      />
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <Input aria-label="Idea ID" placeholder="Idea ID" value={filters.idea_code} onChange={(event) => update({ idea_code: event.target.value })} />
        <Input aria-label="Component" placeholder="Component" value={filters.component} onChange={(event) => update({ component: event.target.value })} />
        <Input aria-label="Search" placeholder="Search text" value={filters.q} onChange={(event) => update({ q: event.target.value })} />
        <Select aria-label="Origin" value={filters.origin} onChange={(event) => update({ origin: event.target.value })}>
          <option value="historical">Historical</option>
          <option value="submission">Submissions</option>
          <option value="all">All origins</option>
        </Select>
        <Select aria-label="Belonged department" value={filters.department_id} onChange={(event) => update({ department_id: event.target.value })}>
          <option value="">Belonged department</option>
          {(options.data?.departments ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
        <Select aria-label="Rejected department" value={filters.rejected_department_id} onChange={(event) => update({ rejected_department_id: event.target.value })}>
          <option value="">Rejected department</option>
          {(options.data?.departments ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
        <Select aria-label="Stage status" value={filters.stage_status} onChange={(event) => update({ stage_status: event.target.value })}>
          <option value="">Stage status</option>
          {(options.data?.stage_statuses ?? []).map((stage) => <option key={stage} value={stage}>{stage}</option>)}
        </Select>
        <Select aria-label="Rejection category" value={filters.rejection_category} onChange={(event) => update({ rejection_category: event.target.value })}>
          <option value="">Rejection category</option>
          {(options.data?.rejection_categories ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
        </Select>
        <Select aria-label="Rejection reason" value={filters.rejection_reason} onChange={(event) => update({ rejection_reason: event.target.value })}>
          <option value="">Rejection reason</option>
          {(options.data?.rejection_reasons ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
        </Select>
        <Select aria-label="Idea type" value={filters.idea_type} onChange={(event) => update({ idea_type: event.target.value })}>
          <option value="">Idea type</option>
          {(options.data?.idea_types ?? []).map((item) => <option key={item} value={item}>{item}</option>)}
        </Select>
        <Select aria-label="Rejected filter" value={filters.rejected} onChange={(event) => update({ rejected: event.target.value })}>
          <option value="">Rejection state</option>
          <option value="false">Active</option>
          <option value="true">Rejected</option>
        </Select>
        <Select aria-label="Sort" value={`${filters.sort}:${filters.order}`} onChange={(event) => {
          const [sort, order] = event.target.value.split(":");
          update({ sort, order, page: filters.page });
        }}>
          <option value="idea_generation_date:desc">Newest generation date</option>
          <option value="idea_code:asc">Idea ID</option>
          <option value="total_combined_annual_saving:desc">Highest projected saving</option>
          <option value="saving_per_vehicle:desc">Highest saving per vehicle</option>
        </Select>
      </div>
      <details className="mb-3 text-sm">
        <summary className="cursor-pointer text-accent-700">Visible columns</summary>
        <div className="mt-2 flex flex-wrap gap-3">
          {table.getAllLeafColumns().map((column) => (
            <label key={column.id} className="flex items-center gap-2">
              <input type="checkbox" checked={column.getIsVisible()} onChange={column.getToggleVisibilityHandler()} />
              {typeof column.columnDef.header === "string" ? column.columnDef.header : column.id}
            </label>
          ))}
        </div>
      </details>
      {ideas.isLoading ? <LoadingBlock /> : null}
      {ideas.isError ? <ErrorState message={errorMessage(ideas.error)} onRetry={() => ideas.refetch()} /> : null}
      {ideas.data && ideas.data.items.length === 0 ? (
        <EmptyState title="No ideas match" body="Adjust the filters. Missing historical fields are not filled in by the application." />
      ) : null}
      {ideas.data && ideas.data.items.length > 0 ? (
        <div className="table-wrap">
          <table className="data">
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="cursor-pointer" onClick={() => navigate(`/ideas/${row.original.id}`)}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {ideas.data ? (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span>{ideas.data.total} records</span>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" disabled={Number(filters.page) <= 1} onClick={() => update({ page: String(Number(filters.page) - 1) })}>Previous</Button>
            <span className="px-2 py-1">Page {filters.page}</span>
            <Button variant="secondary" size="sm" disabled={Number(filters.page) * 25 >= ideas.data.total} onClick={() => update({ page: String(Number(filters.page) + 1) })}>Next</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function IdeaDetailPage() {
  const { ideaId = "" } = useParams();
  const idea = useQuery({ queryKey: ["idea", ideaId], queryFn: () => api<Idea>(`/api/v1/ideas/${ideaId}`) });
  if (idea.isLoading) return <LoadingBlock />;
  if (idea.isError) return <ErrorState message={errorMessage(idea.error)} onRetry={() => idea.refetch()} />;
  const record = idea.data;
  if (!record) return null;
  const fields: [string, string][] = [
    ["Component", text(record.component)],
    ["Belonged department", text(record.idea_belonged_department)],
    ["Rejected department", text(record.rejected_department)],
    ["Generation date", formatDate(record.idea_generation_date)],
    ["Rejection date", formatDate(record.rejection_date)],
    ["Stage status", text(record.stage_status)],
    ["Rejection category", text(record.rejection_category)],
    ["Rejection reason", text(record.rejection_reason)],
    ["Idea type", text(record.idea_type)],
    ["Disposition", text(record.idea_disposition)],
    ["Saving per vehicle", inr(record.saving_per_vehicle)],
    ["Reported workbook total", inr(record.reported_total_saving)],
    ["Calculated annual saving", inr(record.total_combined_annual_saving)],
    ["Origin", text(record.origin)],
    ["Lifecycle", text(record.lifecycle_status)],
    ["Source reference", text(record.source_reference)],
  ];
  return (
    <div className="space-y-4">
      <PageHeader
        title={record.idea_code}
        description="Stored historical or submitted record. Nothing here is inferred by the model."
        actions={
          <>
            {record.is_synthetic ? <Badge tone="amber">Synthetic</Badge> : null}
            <Badge tone={record.is_rejected ? "red" : "green"}>{record.is_rejected ? "Rejected" : "Active"}</Badge>
            {record.origin === "submission" ? (
              <Link to={`/analyses?submission=${record.id}`} className="text-sm text-accent-700">Analyses</Link>
            ) : null}
          </>
        }
      />
      {record.savings_mismatch ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          The workbook total differs from the calculated total. The calculated figure is authoritative.
        </p>
      ) : null}
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Description</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{text(record.description)}</p>
        <dl className="mt-4 grid gap-3 md:grid-cols-2">
          {(["current_design", "proposed_change", "engineering_rationale", "expected_benefit", "constraints"] as const).map((key) => (
            <div key={key}>
              <dt className="text-xs uppercase tracking-wide text-muted">{key.replaceAll("_", " ")}</dt>
              <dd className="mt-1 text-sm leading-6">{text(record[key])}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Recorded fields</h2>
        <dl className="mt-3 grid gap-3 md:grid-cols-3">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted">{label}</dt>
              <dd className="text-sm">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-sm"><span className="text-muted">Applicability: </span>{text(record.applicable_vehicle_details)}</p>
      </section>
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Vehicle applicability</h2>
        <p className="mt-1 text-xs text-muted">Annual volumes are counted once per vehicle family. Currency is INR. Totals are projected.</p>
        {record.vehicles.length === 0 ? <p className="mt-3 text-sm">No vehicle volumes were recorded.</p> : (
          <table className="data mt-3">
            <thead><tr><th>Family</th><th>Annual volume</th></tr></thead>
            <tbody>
              {record.vehicles.map((row) => (
                <tr key={row.family_code ?? row.family_name}>
                  <td>{text(row.family_name)}</td>
                  <td>{row.annual_volume === null ? "Not recorded" : row.annual_volume}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Import and audit</h2>
        <p className="mt-2 text-sm">Workbook: {text(record.import_batch?.filename)} · Batch status: {text(record.import_batch?.status)}</p>
        <ul className="mt-3 space-y-2 text-sm">
          {(record.audit ?? []).length === 0 ? <li className="text-muted">No audit events for this record.</li> : record.audit?.map((row, index) => (
            <li key={`${row.action}-${index}`}>{row.action} · {formatDate(row.created_at)}</li>
          ))}
        </ul>
        <h3 className="mt-4 text-sm font-semibold">Review history</h3>
        <ul className="mt-2 space-y-2 text-sm">
          {(record.reviews ?? []).length === 0 ? <li className="text-muted">No human review is linked to this record.</li> : record.reviews?.map((row) => (
            <li key={row.id}>{row.decision} by {text(row.actor)}. AI recommendation was {outcomeLabel(row.ai_recommendation)}. {row.rationale}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

const emptyForm: IdeaFormValues = {
  idea_code: "",
  component: "",
  idea_belonged_department: "",
  idea_generation_date: "",
  description: "",
  current_design: "",
  proposed_change: "",
  engineering_rationale: "",
  expected_benefit: "",
  constraints: "",
  idea_type: "",
  applicable_vehicle_details: "",
  saving_per_vehicle: "",
};

export function SubmitPage() {
  const navigate = useNavigate();
  const { allowed } = useAuth();
  const options = useQuery({ queryKey: ["options"], queryFn: () => api<Options>("/api/v1/meta/options") });
  const [serverError, setServerError] = useState("");
  const [volumes, setVolumes] = useState<Record<string, string>>({});
  const form = useForm<IdeaFormValues>({ resolver: zodResolver(ideaDraftSchema), defaultValues: emptyForm });

  const departments = useMemo(
    () => ["Cab", "Brake", "Air intake system", "engine", "rear axle", "steeting", "propeller shaft", "exterior trims", "interior trims", "tyres", "frame", "lamps", "ECU", "Infotainment system", "wiring harness", "LV battery"],
    [],
  );

  async function send(submit: boolean) {
    setServerError("");
    const values = form.getValues();
    const parsed = (submit ? ideaSubmitSchema : ideaDraftSchema).safeParse(values);
    if (!parsed.success) {
      parsed.error.issues.forEach((issue) => {
        const key = issue.path[0];
        if (typeof key === "string") form.setError(key as keyof IdeaFormValues, { message: issue.message });
      });
      return;
    }
    const vehicles = (options.data?.vehicle_families ?? [])
      .filter((family) => volumes[family.code])
      .map((family) => ({ family_code: family.code, annual_volume: Number(volumes[family.code]) }));
    const body = {
      ...values,
      idea_code: values.idea_code || null,
      idea_generation_date: values.idea_generation_date || null,
      saving_per_vehicle: values.saving_per_vehicle ? Number(values.saving_per_vehicle) : null,
      vehicles,
      is_synthetic: true,
      submit,
    };
    try {
      if (submit && allowed("analysis:run")) {
        const analysis = await api<{ id: string }>("/api/v1/ideas/analyze-duplicates", { method: "POST", body: JSON.stringify(body) });
        navigate(`/analyses/${analysis.id}`);
        return;
      }
      const created = await api<Idea>("/api/v1/ideas", { method: "POST", body: JSON.stringify(body) });
      navigate(`/ideas/${created.id}`);
    } catch (error) {
      setServerError(errorMessage(error));
    }
  }

  return (
    <div>
      <PageHeader
        title="Submit an idea"
        description="Save a draft or submit it for duplicate analysis. The Idea ID is generated when you leave it blank. Batch files are validated on the import page."
        actions={<Link className="text-sm text-accent-700" to="/import">Batch CSV / XLSX</Link>}
      />
      <form className="card space-y-4 p-4" onSubmit={(event) => event.preventDefault()}>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <Label htmlFor="idea_code">Proposed Idea ID</Label>
            <Input id="idea_code" {...form.register("idea_code")} />
            <Hint>Leave blank to receive a VAVE-NEW identifier from the server.</Hint>
          </div>
          <div>
            <Label htmlFor="component">Component or assembly</Label>
            <Input id="component" {...form.register("component")} />
            <FieldError>{form.formState.errors.component?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="department">Idea belonged department</Label>
            <Select id="department" {...form.register("idea_belonged_department")}>
              <option value="">Select</option>
              {departments.map((name) => <option key={name} value={name}>{name}</option>)}
            </Select>
            <FieldError>{form.formState.errors.idea_belonged_department?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="generated">Idea generation date</Label>
            <Input id="generated" type="date" {...form.register("idea_generation_date")} />
          </div>
          <div>
            <Label htmlFor="idea_type">Idea type</Label>
            <Input id="idea_type" {...form.register("idea_type")} />
          </div>
          <div>
            <Label htmlFor="saving">Saving per vehicle (INR)</Label>
            <Input id="saving" inputMode="decimal" {...form.register("saving_per_vehicle")} />
            <Hint>Projected, not realised. Annual total is calculated on the server.</Hint>
          </div>
        </div>
        <div>
          <Label htmlFor="description">Technical description</Label>
          <Textarea id="description" {...form.register("description")} />
          <Hint>Describe the engineering change, not only the component or the benefit.</Hint>
          <FieldError>{form.formState.errors.description?.message}</FieldError>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div><Label htmlFor="current">Current design or process</Label><Textarea id="current" {...form.register("current_design")} /></div>
          <div><Label htmlFor="change">Proposed technical change</Label><Textarea id="change" {...form.register("proposed_change")} /></div>
          <div><Label htmlFor="rationale">Engineering rationale</Label><Textarea id="rationale" {...form.register("engineering_rationale")} /></div>
          <div><Label htmlFor="benefit">Expected benefit</Label><Textarea id="benefit" {...form.register("expected_benefit")} /></div>
        </div>
        <div>
          <Label htmlFor="constraints">Constraints or validation requirements</Label>
          <Textarea id="constraints" {...form.register("constraints")} />
        </div>
        <div>
          <Label htmlFor="vehicles">Applicable vehicle families and tonnage notes</Label>
          <Textarea id="vehicles" {...form.register("applicable_vehicle_details")} />
        </div>
        <fieldset>
          <legend className="text-sm font-medium">Annual volume assumptions</legend>
          <div className="mt-2 grid gap-3 md:grid-cols-3">
            {(options.data?.vehicle_families ?? []).map((family) => (
              <div key={family.code}>
                <Label htmlFor={family.code}>{family.name}</Label>
                <Input id={family.code} inputMode="decimal" value={volumes[family.code] ?? ""} onChange={(event) => setVolumes({ ...volumes, [family.code]: event.target.value })} />
              </div>
            ))}
          </div>
        </fieldset>
        {serverError ? <p className="text-sm text-rose-700">{serverError}</p> : null}
        <div className="flex gap-2">
          <Button type="button" variant="secondary" onClick={() => send(false)}>Save draft</Button>
          <Button type="button" onClick={() => send(true)}>Submit for duplicate analysis</Button>
        </div>
      </form>
    </div>
  );
}
