import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState, Hint, Input, Label, LoadingBlock, PageHeader, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatWhen } from "@/lib/format";
import { errorMessage } from "@/lib/utils";
import type { AiStatus } from "@/types";

export const AI_MODES = [
  { value: "online", label: "Online API", note: "OpenAI is called only from the server. The API key is never sent to the browser." },
  { value: "offline", label: "OFFLINE / LOCAL", note: "Ollama on the configured local endpoint. External inference is blocked and there is no silent online fallback." },
  { value: "fallback", label: "Deterministic fallback", note: "Exact and fuzzy matching with hashed embeddings. No language model is called." },
] as const;

export function AiSettingsPage() {
  const { allowed } = useAuth();
  const admin = allowed("*");
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["ai-settings"], queryFn: () => api<AiStatus>("/api/v1/ai/settings") });
  const [form, setForm] = useState<Partial<AiStatus>>({});
  useEffect(() => {
    if (status.data) setForm(status.data);
  }, [status.data]);
  const save = useMutation({
    mutationFn: () =>
      api<AiStatus>("/api/v1/ai/settings", {
        method: "PUT",
        body: JSON.stringify({
          mode: form.mode,
          llm_required: form.llm_required,
          chat_model: form.chat_model,
          embedding_provider: form.embedding_provider,
          embedding_model: form.embedding_model,
          retrieval_top_k: Number(form.retrieval_top_k),
          comparison_timeout_seconds: Number(form.comparison_timeout_seconds),
          fuzzy_strong_threshold: Number(form.fuzzy_strong_threshold),
          cosine_retrieve_threshold: Number(form.cosine_retrieve_threshold),
          copilot_top_k: Number(form.copilot_top_k),
          dataset_label: form.dataset_label,
          display_timezone: form.display_timezone,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      queryClient.invalidateQueries({ queryKey: ["ai-status"] });
    },
  });
  const test = useMutation({
    mutationFn: () => api<{ available: boolean; detail: string }>("/api/v1/ai/providers/test", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-settings"] }),
  });
  const reindex = useMutation({
    mutationFn: () => api<{ status: string; result: { ideas: number; chunks: number; model: string } }>("/api/v1/ai/reindex", { method: "POST" }),
  });
  if (status.isLoading) return <LoadingBlock />;
  if (status.isError || !status.data) return <ErrorState message={errorMessage(status.error)} onRetry={() => status.refetch()} />;
  const current = status.data;
  const selected = AI_MODES.find((item) => item.value === form.mode);
  return (
    <div className="space-y-4">
      <PageHeader
        title="AI provider and mode"
        description="Switching mode does not delete existing vectors. An embedding-model change needs an explicit re-index because every vector must come from the same model."
      />
      <section className="card grid gap-3 p-4 text-sm md:grid-cols-2" aria-label="Provider status">
        <p>Active mode: <strong>{current.mode === "offline" ? "OFFLINE / LOCAL" : current.mode_label}</strong></p>
        <p>Provider: {current.provider}</p>
        <p>Chat model: {current.chat_model || "Not used in this mode"}</p>
        <p>Embedding: {current.embedding_provider} / {current.embedding_model} ({current.embedding_dimensions} dimensions)</p>
        <p>Retrieval count: {current.retrieval_top_k}</p>
        <p>Comparison timeout: {current.comparison_timeout_seconds}s</p>
        <p>Fuzzy threshold: {current.fuzzy_strong_threshold}</p>
        <p>Cosine floor: {current.cosine_retrieve_threshold}</p>
        <p>Copilot passages per question: {current.copilot_top_k}</p>
        <p>Copilot citation-confidence threshold: {current.copilot_citation_threshold ?? "Not set (not calibrated; the copilot does not abstain on confidence)"}</p>
        <p>OpenAI configured on server: {current.openai_configured ? "Yes" : "No"}</p>
        <p>External inference blocked: {current.external_inference_blocked ? "Yes" : "No"}</p>
        <p>Last connection check: {formatWhen(current.last_connection_check, current.display_timezone)} · {current.last_connection_ok === null ? "Not checked" : current.last_connection_ok ? "Succeeded" : "Failed"}</p>
        <p>{current.last_connection_detail || "No connection detail yet."}</p>
        {(current.runtime_warnings ?? []).map((warning) => <p key={warning} className="text-amber-900">{warning}</p>)}
        <p className="md:col-span-2 text-xs text-muted">{current.threshold_note}</p>
      </section>
      <form
        className="card space-y-4 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (admin) save.mutate();
        }}
      >
        <div>
          <Label htmlFor="mode">Mode</Label>
          <Select id="mode" aria-label="AI mode" disabled={!admin} value={form.mode ?? "fallback"} onChange={(event) => setForm({ ...form, mode: event.target.value })}>
            {AI_MODES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </Select>
          <Hint>{selected?.note}</Hint>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <Label htmlFor="chat_model">Chat model</Label>
            <Input id="chat_model" disabled={!admin} value={form.chat_model ?? ""} onChange={(event) => setForm({ ...form, chat_model: event.target.value })} />
            <Hint>Choose a model already configured or installed. Offline mode does not download models.</Hint>
          </div>
          <div>
            <Label htmlFor="embedding_provider">Embedding provider</Label>
            <Select id="embedding_provider" disabled={!admin} value={form.embedding_provider ?? "deterministic"} onChange={(event) => setForm({ ...form, embedding_provider: event.target.value })}>
              <option value="deterministic">deterministic</option>
              <option value="openai">openai</option>
              <option value="ollama">ollama</option>
              <option value="sentence_transformers">sentence_transformers</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="embedding_model">Embedding model</Label>
            <Input id="embedding_model" disabled={!admin} value={form.embedding_model ?? ""} onChange={(event) => setForm({ ...form, embedding_model: event.target.value })} />
          </div>
          <div>
            <Label htmlFor="topk">Retrieval count</Label>
            <Input id="topk" disabled={!admin} value={form.retrieval_top_k ?? 15} onChange={(event) => setForm({ ...form, retrieval_top_k: Number(event.target.value) })} />
          </div>
          <div>
            <Label htmlFor="timeout">Comparison timeout (seconds)</Label>
            <Input id="timeout" disabled={!admin} value={form.comparison_timeout_seconds ?? 60} onChange={(event) => setForm({ ...form, comparison_timeout_seconds: Number(event.target.value) })} />
          </div>
          <div>
            <Label htmlFor="fuzzy">Fuzzy threshold</Label>
            <Input id="fuzzy" disabled={!admin} value={form.fuzzy_strong_threshold ?? 86} onChange={(event) => setForm({ ...form, fuzzy_strong_threshold: Number(event.target.value) })} />
          </div>
          <div>
            <Label htmlFor="cosine">Cosine retrieval floor</Label>
            <Input id="cosine" disabled={!admin} value={form.cosine_retrieve_threshold ?? 0.22} onChange={(event) => setForm({ ...form, cosine_retrieve_threshold: Number(event.target.value) })} />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" disabled={!admin} checked={Boolean(form.llm_required)} onChange={(event) => setForm({ ...form, llm_required: event.target.checked })} />
          Require the language model. If it is unavailable, analysis fails instead of using deterministic comparison.
        </label>
        {save.isError ? <ErrorState message={errorMessage(save.error)} /> : null}
        {save.data?.reindex_required ? <p className="text-sm text-amber-900">The embedding model changed. Re-index before comparing new vectors with old ones.</p> : null}
        {test.data ? <p className="text-sm">{test.data.available ? "Connection succeeded. " : "Connection failed. "}{test.data.detail}</p> : null}
        {test.isError ? <p className="text-sm text-rose-700">{errorMessage(test.error)}</p> : null}
        {reindex.data ? <p className="text-sm">Re-index {reindex.data.status}: {reindex.data.result.ideas} ideas, {reindex.data.result.chunks} chunks, model {reindex.data.result.model}.</p> : null}
        {admin ? (
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending}>Save settings</Button>
            <Button type="button" variant="secondary" onClick={() => test.mutate()}>Test connection</Button>
            <Button type="button" variant="secondary" onClick={() => reindex.mutate()}>Re-index embeddings</Button>
          </div>
        ) : <Hint>Only a system administrator can change the provider, test the connection, or re-index.</Hint>}
      </form>
    </div>
  );
}
