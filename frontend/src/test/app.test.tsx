import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Shell } from "@/components/layout/Shell";
import { AiSettingsPage, AI_MODES } from "@/features/ai-settings/AiSettingsPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ImportPreview, canCommitImport } from "@/features/data-import/ImportPage";
import { CandidateCard } from "@/features/duplicate-detection/AnalysisPages";
import { AuthProvider } from "@/lib/auth";
import { can, visibleNav } from "@/lib/permissions";
import { buildIdeaQuery, ideaSubmitSchema, reviewSchema } from "@/lib/schemas";
import { writeSession } from "@/lib/session";
import type { AiStatus, AnalysisCandidate, ImportBatch } from "@/types";

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const viewer = {
  id: "1",
  email: "viewer@vave.local",
  full_name: "Management Viewer",
  timezone: "Asia/Kolkata",
  department: null,
  roles: ["readonly_management"],
  role_labels: ["Read-only Management / Inspection"],
  permissions: ["dashboard:read", "ideas:read", "analytics:read", "copilot:use", "documents:read_management", "evaluation:read", "exports:create"],
};

const status: AiStatus = {
  mode: "fallback",
  mode_label: "Deterministic fallback",
  provider: "deterministic",
  chat_model: null,
  embedding_provider: "deterministic",
  embedding_model: "deterministic-hash-v1",
  embedding_dimensions: 384,
  retrieval_top_k: 15,
  comparison_timeout_seconds: 60,
  fuzzy_strong_threshold: 86,
  cosine_retrieve_threshold: 0.22,
  copilot_lexical_threshold: 0.45,
  llm_required: false,
  dataset_label: "Synthetic",
  display_timezone: "Asia/Kolkata",
  external_inference_blocked: true,
  openai_configured: false,
  runtime_warnings: [],
  last_connection_check: null,
  last_connection_ok: null,
  last_connection_detail: null,
  threshold_note: "Thresholds are configuration values.",
};

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo) => {
    const url = String(input);
    if (url.includes("/auth/dev-accounts")) return json({ enabled: false, accounts: [] });
    if (url.includes("/auth/me")) return json(viewer);
    if (url.includes("/ai/status") || url.includes("/ai/settings")) return json(status);
    if (url.includes("/notifications")) return json({ items: [] });
    if (url.includes("/ideas/search")) return json({ items: [] });
    return json({});
  }));
});

test("read-only navigation hides submission and import", () => {
  expect(can(viewer.permissions, "ideas:write")).toBe(false);
  expect(can(["*"], "ideas:import")).toBe(true);
  const labels = visibleNav(viewer.permissions).map((item) => item.label);
  expect(labels).toContain("Dashboard");
  expect(labels).not.toContain("Submit idea");
  expect(labels).not.toContain("Import data");
  expect(labels).not.toContain("Administration");
});

test("shell shows the allowed destinations", async () => {
  writeSession({ token: "token", user: viewer });
  wrap(<Shell />);
  expect(await screen.findByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Submit idea" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Search ideas")).toBeInTheDocument();
});

test("login form exposes labelled fields", async () => {
  wrap(<LoginPage />);
  expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
});

test("submission schema requires a technical description", () => {
  const result = ideaSubmitSchema.safeParse({ component: "", idea_belonged_department: "", description: "too short" });
  expect(result.success).toBe(false);
});

test("idea filters become a query string", () => {
  expect(buildIdeaQuery({ idea_code: "VAVE-SYN-001", component: "", origin: "historical" })).toBe("?idea_code=VAVE-SYN-001&origin=historical");
});

test("import preview blocks commit while errors remain", () => {
  const batch = { status: "preview", error_count: 2, allow_partial: false } as ImportBatch;
  expect(canCommitImport(batch)).toBe(false);
  wrap(<ImportPreview batch={{ ...batch, filename: "sample.xlsx", is_synthetic: true, row_count: 2, warning_count: 0, merge_strategy: "reject_conflicts", preview_rows: [], errors: [{ row_number: 2, column_name: "Idea_ID", severity: "error", message: "Duplicate Idea ID", raw_value: "A" }] }} onCommit={() => undefined} />);
  expect(screen.getByRole("button", { name: "Confirm and commit" })).toBeDisabled();
  expect(screen.getByText(/Duplicate Idea ID/)).toBeInTheDocument();
});

test("offline mode copy is explicit", async () => {
  writeSession({ token: "token", user: { ...viewer, permissions: ["*"], roles: ["system_administrator"], role_labels: ["System Administrator"] } });
  wrap(<AiSettingsPage />);
  expect(await screen.findByLabelText("AI mode")).toBeInTheDocument();
  expect(AI_MODES.find((item) => item.value === "offline")?.note).toMatch(/External inference is blocked/);
  expect(screen.getByText(/External inference blocked/)).toBeInTheDocument();
});

test("review actions require a rationale before confirmation", async () => {
  const candidate = {
    id: "c1",
    rank: 1,
    category: "potential_duplicate",
    heuristic_category: "potential_duplicate",
    llm_category: null,
    disagreement: false,
    cosine_similarity: 0.4,
    fuzzy_score: 90,
    exact_match: false,
    explanation: "Same material substitution on the cab bracket.",
    similarities: ["Same component"],
    differences: [],
    evidence: {},
    historical: null,
  } satisfies AnalysisCandidate;
  wrap(<CandidateCard analysisId="run" candidate={candidate} canReview onDecided={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Confirm Duplicate" }));
  const confirm = await screen.findByRole("button", { name: "Record decision" });
  expect(confirm).toBeDisabled();
  expect(reviewSchema.safeParse({ decision: "confirm_duplicate", rationale: "short" }).success).toBe(false);
});
