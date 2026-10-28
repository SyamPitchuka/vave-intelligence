import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Badge, ErrorState, Hint, Label, PageHeader, Select, Textarea } from "@/components/ui/primitives";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/utils";
import type { AnswerMode, ChatReply, Citation } from "@/types";

type SessionItem = { id: string; title: string | null; created_at: string | null };
type Message = {
  id: string;
  role: string;
  content: string;
  citations: Citation[] | null;
  evidence: Citation[] | null;
  abstained: boolean;
  answer_mode?: AnswerMode | null;
  abstention_reason?: string | null;
  provider: string | null;
};

export function CopilotPage() {
  const { allowed } = useAuth();
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState("engineering");
  const [file, setFile] = useState<File | null>(null);
  const sessions = useQuery({ queryKey: ["copilot-sessions"], queryFn: () => api<{ items: SessionItem[] }>("/api/v1/copilot/sessions") });
  const thread = useQuery({
    queryKey: ["copilot-session", sessionId],
    queryFn: () => api<{ messages: Message[] }>(`/api/v1/copilot/sessions/${sessionId}`),
    enabled: Boolean(sessionId),
  });
  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => api<{ items: { id: string; title: string; filename: string; visibility: string; is_synthetic: boolean; status: string }[] }>("/api/v1/documents"),
  });
  const ask = useMutation({
    mutationFn: () =>
      api<ChatReply>("/api/v1/copilot/chat", {
        method: "POST",
        body: JSON.stringify({ message: question, session_id: sessionId }),
      }),
    onSuccess: (reply) => {
      setSessionId(reply.session_id);
      setQuestion("");
      queryClient.invalidateQueries({ queryKey: ["copilot-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["copilot-session", reply.session_id] });
    },
  });
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a PDF, DOCX, TXT, or Markdown file.");
      const body = new FormData();
      body.set("file", file);
      body.set("title", title || file.name);
      body.set("visibility", visibility);
      body.set("is_synthetic", "true");
      return api("/api/v1/documents", { method: "POST", body });
    },
    onSuccess: () => {
      setFile(null);
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
  const feedback = useMutation({
    mutationFn: ({ id, rating }: { id: string; rating: "up" | "down" }) =>
      api(`/api/v1/copilot/messages/${id}/feedback`, { method: "POST", body: JSON.stringify({ rating }) }),
  });

  return (
    <div className="grid gap-4 xl:grid-cols-[16rem_1fr_18rem]">
      <aside className="card p-3">
        <PageHeader title="Conversations" />
        <button type="button" className="mb-2 text-sm text-accent-700" onClick={() => setSessionId(null)}>New question</button>
        <ul className="space-y-1 text-sm">
          {(sessions.data?.items ?? []).map((item) => (
            <li key={item.id}>
              <button type="button" className="w-full rounded px-2 py-1 text-left hover:bg-canvas" onClick={() => setSessionId(item.id)}>
                {item.title || "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section>
        <PageHeader
          title="Knowledge Copilot"
          description="Answers are grounded in documents you are allowed to read. Unsupported statements are not presented as verified engineering facts."
        />
        <div className="card min-h-80 space-y-4 p-4">
          {(thread.data?.messages ?? []).map((message) => (
            <article key={message.id}>
              <p className="text-xs uppercase tracking-wide text-muted">{message.role}{message.provider ? ` · ${message.provider}` : ""}</p>
              <ModeBadge mode={message.answer_mode} abstained={message.abstained} />
              <div className="prose-sm mt-1 text-sm leading-6">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
              {message.role === "assistant" ? (
                <div className="mt-2 flex gap-2 text-xs">
                  <button type="button" onClick={() => feedback.mutate({ id: message.id, rating: "up" })}>Useful</button>
                  <button type="button" onClick={() => feedback.mutate({ id: message.id, rating: "down" })}>Not useful</button>
                </div>
              ) : null}
              <CitationList title="Citations" items={message.citations ?? []} />
              <CitationList title="Retrieved evidence" items={message.evidence ?? []} />
            </article>
          ))}
          {ask.data && sessionId === ask.data.session_id && !thread.data ? <Answer answer={ask.data} /> : null}
          {ask.data && thread.isFetching ? null : ask.data && !thread.data?.messages.some((item) => item.id === ask.data?.message_id) ? <Answer answer={ask.data} /> : null}
        </div>
        <form
          className="mt-3 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (question.trim()) ask.mutate();
          }}
        >
          <Label htmlFor="question">Question</Label>
          <Textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} />
          {ask.isError ? <ErrorState message={errorMessage(ask.error)} /> : null}
          <Button type="submit" disabled={ask.isPending}>Ask</Button>
        </form>
      </section>
      <aside className="space-y-3">
        <section className="card p-3">
          <h2 className="text-sm font-semibold">Approved documents</h2>
          <ul className="mt-2 space-y-2 text-sm">
            {(documents.data?.items ?? []).map((doc) => (
              <li key={doc.id}>
                <button type="button" className="text-left text-accent-700" onClick={() => downloadFile(`/api/v1/documents/${doc.id}/file`, doc.filename)}>{doc.title}</button>
                <span className="block text-xs text-muted">{doc.visibility}{doc.is_synthetic ? " · Synthetic" : ""} · {doc.status}</span>
              </li>
            ))}
          </ul>
        </section>
        {allowed("documents:write") ? (
          <form
            className="card space-y-2 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              upload.mutate();
            }}
          >
            <h2 className="text-sm font-semibold">Upload</h2>
            <input aria-label="Document file" type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <input aria-label="Document title" className="w-full rounded-md border border-line px-2 py-1 text-sm" placeholder="Title" value={title} onChange={(event) => setTitle(event.target.value)} />
            <Select aria-label="Visibility" value={visibility} onChange={(event) => setVisibility(event.target.value)}>
              <option value="engineering">Engineering</option>
              <option value="all_authenticated">All signed-in users</option>
              <option value="management">Management</option>
            </Select>
            <Hint>PDF, DOCX, TXT, and Markdown. Size limits are enforced on the server.</Hint>
            {upload.isError ? <p className="text-xs text-rose-700">{errorMessage(upload.error)}</p> : null}
            <Button type="submit" size="sm" disabled={upload.isPending}>Index document</Button>
          </form>
        ) : null}
      </aside>
    </div>
  );
}

function Answer({ answer }: { answer: ChatReply }) {
  return (
    <article>
      <ModeBadge mode={answer.answer_mode} abstained={answer.abstained} />
      <div className="text-sm leading-6"><ReactMarkdown>{answer.answer}</ReactMarkdown></div>
      <p className="mt-1 text-xs text-muted">{answer.provider} · {answer.model ?? "model not recorded"}</p>
      <CitationList title="Citations" items={answer.citations ?? []} />
      <CitationList title="Retrieved evidence" items={answer.evidence ?? []} />
    </article>
  );
}

function ModeBadge({ mode, abstained }: { mode?: AnswerMode | null; abstained: boolean }) {
  if (mode === "abstained" || (!mode && abstained)) return <Badge tone="amber">No answer: insufficient evidence</Badge>;
  if (mode === "extractive") return <Badge tone="blue">Extractive: quoted passage, no language model</Badge>;
  if (mode === "generated") return <Badge tone="blue">Generated from cited passages</Badge>;
  return null;
}

function sectionLabel(item: Citation): string {
  if (item.section_number) return `section ${item.section_number} ${item.section_heading ?? ""}`.trim();
  return item.section_heading || item.section || "Section not recorded";
}

function CitationList({ title, items }: { title: string; items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
      <ul className="mt-1 space-y-2">
        {items.map((item) => (
          <li key={item.chunk_id} className="rounded border border-line bg-canvas p-2 text-xs leading-5">
            {item.document_number ? <span className="text-muted">{item.document_number} · </span> : null}
            <a className="font-medium text-accent-700" href={`/api/v1/documents/${item.document_id}`}>{item.document_title}</a>
            {item.is_synthetic ? " · Synthetic" : ""} · {sectionLabel(item)} · page {item.page_number ?? "not recorded"} · cosine {item.cosine_similarity.toFixed(3)}
            <span className="mt-1 block">{item.excerpt}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
