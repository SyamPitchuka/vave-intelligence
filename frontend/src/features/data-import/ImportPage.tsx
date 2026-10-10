import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Badge, EmptyState, ErrorState, Hint, Label, LoadingBlock, PageHeader, Select } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { errorMessage } from "@/lib/utils";
import type { ImportBatch } from "@/types";

export function canCommitImport(batch: Pick<ImportBatch, "status" | "error_count" | "allow_partial"> | null): boolean {
  if (!batch || batch.status !== "preview") return false;
  return batch.error_count === 0 || batch.allow_partial;
}

export function ImportPage() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("");
  const [strategy, setStrategy] = useState("reject_conflicts");
  const [synthetic, setSynthetic] = useState(true);
  const [partial, setPartial] = useState(false);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [localFile, setLocalFile] = useState("");
  const batches = useQuery({ queryKey: ["import-batches"], queryFn: () => api<{ items: ImportBatch[] }>("/api/v1/ideas/import/batches") });
  const localFolder = useQuery({
    queryKey: ["local-folder"],
    queryFn: () => api<{ folder: string; items: { name: string; size_bytes: number; suffix: string }[] }>("/api/v1/local-folder"),
  });

  const preview = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a CSV or XLSX file.");
      const body = new FormData();
      body.set("file", file);
      if (sheet) body.set("sheet_name", sheet);
      body.set("merge_strategy", strategy);
      body.set("is_synthetic", String(synthetic));
      body.set("allow_partial", String(partial));
      return api<ImportBatch>("/api/v1/ideas/import/preview", { method: "POST", body });
    },
    onSuccess: (next) => {
      setBatch(next);
      queryClient.invalidateQueries({ queryKey: ["import-batches"] });
    },
  });
  const commit = useMutation({
    mutationFn: () => api<ImportBatch>("/api/v1/ideas/import/commit", { method: "POST", body: JSON.stringify({ batch_id: batch?.id, confirm: true }) }),
    onSuccess: (next) => {
      setBatch(next);
      setConfirm(false);
      queryClient.invalidateQueries({ queryKey: ["import-batches"] });
    },
  });
  const loadLocal = useMutation({
    mutationFn: async () => {
      if (!localFile) throw new Error("Choose a file from the local folder.");
      return api<ImportBatch>("/api/v1/ideas/import/from-folder", {
        method: "POST",
        body: JSON.stringify({
          filename: localFile,
          sheet_name: sheet || null,
          merge_strategy: strategy,
          is_synthetic: synthetic,
          allow_partial: partial,
        }),
      });
    },
    onSuccess: (next) => {
      setBatch(next);
      queryClient.invalidateQueries({ queryKey: ["import-batches"] });
    },
  });
  const rollback = useMutation({
    mutationFn: (id: string) => api<ImportBatch>(`/api/v1/ideas/import/batches/${id}/rollback`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["import-batches"] }),
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Import data"
        description="Map columns, review row errors, and confirm before anything is written. Historical rows are not overwritten silently. Files you place in data/local can be loaded by name."
      />
      <section className="card space-y-3 p-4" aria-label="Local folder">
        <h2 className="text-sm font-semibold">Load from local folder</h2>
        <p className="text-sm text-muted">Folder: {localFolder.data?.folder ?? "data/local"}. Put a CSV or XLSX file there, then load it. The server will not read a path outside this folder.</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <Label htmlFor="local-file">File in data/local</Label>
            <Select id="local-file" value={localFile} onChange={(event) => setLocalFile(event.target.value)}>
              <option value="">Select a file</option>
              {(localFolder.data?.items ?? []).filter((item) => item.suffix === ".xlsx" || item.suffix === ".csv").map((item) => (
                <option key={item.name} value={item.name}>{item.name}</option>
              ))}
            </Select>
          </div>
          <Button type="button" variant="secondary" onClick={() => loadLocal.mutate()} disabled={!localFile || loadLocal.isPending}>Load selected file</Button>
        </div>
        {localFolder.isError ? <ErrorState message={errorMessage(localFolder.error)} onRetry={() => localFolder.refetch()} /> : null}
        {loadLocal.isError ? <p className="text-sm text-rose-700">{errorMessage(loadLocal.error)}</p> : null}
      </section>
      <form
        className="card space-y-4 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          preview.mutate();
        }}
      >
        <div>
          <Label htmlFor="workbook">Workbook</Label>
          <input id="workbook" className="mt-1 block text-sm" type="file" accept=".xlsx,.csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <Hint>CSV and XLSX are accepted. Column order is not assumed. The first sheet named Ideas is preferred when present.</Hint>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <Label htmlFor="sheet">Sheet name</Label>
            <input id="sheet" className="w-full rounded-md border border-line px-3 py-2 text-sm" value={sheet} onChange={(event) => setSheet(event.target.value)} placeholder="Optional" />
          </div>
          <div>
            <Label htmlFor="strategy">Merge strategy</Label>
            <Select id="strategy" value={strategy} onChange={(event) => setStrategy(event.target.value)}>
              <option value="reject_conflicts">Reject conflicting Idea IDs</option>
              <option value="insert_only">Insert new records only</option>
              <option value="update_matching">Update matching records</option>
            </Select>
          </div>
          <div className="flex items-end gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={synthetic} onChange={(event) => setSynthetic(event.target.checked)} /> Mark synthetic</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={partial} onChange={(event) => setPartial(event.target.checked)} /> Allow valid rows only</label>
          </div>
        </div>
        {preview.isError ? <ErrorState message={errorMessage(preview.error)} /> : null}
        <Button type="submit" disabled={preview.isPending}>{preview.isPending ? "Validating…" : "Preview and validate"}</Button>
      </form>
      {batch ? <ImportPreview batch={batch} onCommit={() => setConfirm(true)} /> : null}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Commit this import"
        description="Confirmed rows will be written in a transaction and then re-indexed. Cancel leaves the preview uncommitted."
        confirmLabel="Commit import"
        pending={commit.isPending}
        onConfirm={() => commit.mutate()}
      >
        {commit.isError ? <p className="text-sm text-rose-700">{errorMessage(commit.error)}</p> : null}
      </ConfirmDialog>
      <section>
        <h2 className="mb-2 text-sm font-semibold">Recent batches</h2>
        {batches.isLoading ? <LoadingBlock /> : null}
        {batches.isError ? <ErrorState message={errorMessage(batches.error)} onRetry={() => batches.refetch()} /> : null}
        {(batches.data?.items.length ?? 0) === 0 ? <EmptyState title="No imports yet" body="A preview batch will be listed here with its status and timestamp." /> : null}
        {batches.data && batches.data.items.length > 0 ? (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>File</th><th>Status</th><th>Rows</th><th>Errors</th><th>Inserted</th><th>When</th><th></th></tr></thead>
              <tbody>
                {batches.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.filename}{item.is_synthetic ? " · Synthetic" : ""}</td>
                    <td>{item.status}</td>
                    <td>{item.row_count}</td>
                    <td>{item.error_count}</td>
                    <td>{item.inserted_count}</td>
                    <td>{formatWhen(item.created_at)}</td>
                    <td>
                      {item.status === "committed" ? (
                        <button type="button" className="text-sm text-accent-700" onClick={() => rollback.mutate(item.id)}>Roll back</button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {rollback.isError ? <p className="mt-2 text-sm text-rose-700">{errorMessage(rollback.error)}</p> : null}
      </section>
    </div>
  );
}

export function ImportPreview({ batch, onCommit }: { batch: ImportBatch; onCommit: () => void }) {
  const ready = canCommitImport(batch);
  return (
    <section className="card space-y-3 p-4" aria-label="Import preview">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Preview {batch.filename}</h2>
        <Badge tone={batch.is_synthetic ? "amber" : "slate"}>{batch.is_synthetic ? "Synthetic" : "Source file"}</Badge>
        <Badge>{batch.status}</Badge>
      </div>
      <p className="text-sm">
        {batch.row_count} rows · {batch.error_count} errors · {batch.warning_count} warnings · strategy {batch.merge_strategy}
      </p>
      {batch.summary?.unmapped && batch.summary.unmapped.length > 0 ? (
        <p className="text-sm text-muted">Unmapped columns: {batch.summary.unmapped.join(", ")}</p>
      ) : null}
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Row</th><th>Action</th><th>Idea ID</th><th>Component</th><th>Stage</th><th>Rejection category</th></tr></thead>
          <tbody>
            {(batch.preview_rows ?? []).map((row) => (
              <tr key={row.row_number}>
                <td>{row.row_number}</td>
                <td>{row.action}</td>
                <td>{row.idea_code ?? "—"}</td>
                <td>{row.component ?? "—"}</td>
                <td>{row.stage_status ?? "—"}</td>
                <td>{row.rejection_category ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(batch.errors ?? []).length > 0 ? (
        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Row issues</h3>
            <button type="button" className="text-sm text-accent-700" onClick={() => downloadFile(`/api/v1/exports/import-errors/${batch.id}?format=csv`, "vave-import-errors.csv")}>Download error report</button>
          </div>
          <ul className="max-h-48 space-y-1 overflow-auto text-sm">
            {batch.errors?.map((error, index) => (
              <li key={`${error.row_number}-${index}`}>Row {error.row_number} · {error.severity} · {error.column_name ?? "row"} · {error.message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <Button type="button" disabled={!ready} onClick={onCommit}>Confirm and commit</Button>
      {!ready ? <Hint>Commit stays disabled while error rows remain, unless you explicitly allow valid rows only.</Hint> : null}
    </section>
  );
}
