export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  timezone: string;
  department: string | null;
  roles: string[];
  role_labels: string[];
  permissions: string[];
};

export type VehicleRow = {
  family_code: string | null;
  family_name: string | null;
  annual_volume: number | null;
};

export type Idea = {
  id: string;
  idea_code: string;
  component: string | null;
  description: string | null;
  current_design: string | null;
  proposed_change: string | null;
  engineering_rationale: string | null;
  expected_benefit: string | null;
  constraints: string | null;
  idea_generation_date: string | null;
  rejection_date: string | null;
  idea_belonged_department: string | null;
  idea_belonged_department_id: string | null;
  rejected_department: string | null;
  rejected_department_id: string | null;
  stage_status: string | null;
  rejection_category: string | null;
  rejection_reason: string | null;
  idea_type: string | null;
  idea_disposition: string | null;
  applicable_vehicle_details: string | null;
  saving_per_vehicle: number | null;
  reported_total_saving: number | null;
  total_combined_annual_saving: number | null;
  savings_mismatch: boolean;
  is_rejected: boolean;
  origin: string;
  lifecycle_status: string;
  is_synthetic: boolean;
  source_reference: string | null;
  import_batch_id: string | null;
  vehicles: VehicleRow[];
  created_at: string | null;
  updated_at: string | null;
  import_batch?: {
    id: string;
    filename: string;
    sheet_name: string | null;
    status: string;
    is_synthetic: boolean;
    committed_at: string | null;
  } | null;
  audit?: { action: string; created_at: string | null; details: Record<string, unknown> }[];
  reviews?: {
    id: string;
    decision: string;
    rationale: string;
    ai_recommendation: string | null;
    actor: string | null;
    created_at: string;
  }[];
};

export type Paged<T> = { items: T[]; page: number; page_size: number; total: number };

export type CountRow = { count: number; name?: string; stage?: string; category?: string; reason?: string };

export type DashboardSummary = {
  total_ideas: number;
  active_ideas: number;
  rejected_ideas: number;
  potential_duplicates: number;
  identical_text_groups: number;
  awaiting_review: number;
  total_projected_savings: number;
  by_stage: { stage: string; count: number }[];
  by_department: { name: string; count: number }[];
  rejections_by_department: { name: string; count: number }[];
  rejections_by_category: { category: string; count: number }[];
  rejections_by_reason: { reason: string; count: number }[];
  submission_trend: { period: string; count: number }[];
  recent_activity: { id: string; action: string; actor: string | null; created_at: string | null }[];
  data_quality: {
    missing_description: number;
    missing_department: number;
    duplicate_idea_ids: number;
    savings_mismatch: number;
    invalid_dates: number;
    import_issues: number;
  };
  savings_by_department: { name: string; projected_saving: number; count: number }[];
  savings_by_vehicle_family: { name: string; code: string; projected_saving: number }[];
  assumptions: string[];
  dataset_note: string;
};

export type Options = {
  departments: { id: string; name: string }[];
  vehicle_families: { id: string; code: string; name: string }[];
  stage_statuses: string[];
  rejection_categories: string[];
  rejection_reasons: string[];
  idea_types: string[];
  roles: { name: string; label: string }[];
};

export type AiStatus = {
  mode: "online" | "offline" | "fallback" | string;
  mode_label: string;
  provider: string;
  chat_model: string | null;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimensions: number;
  retrieval_top_k: number;
  comparison_timeout_seconds: number;
  fuzzy_strong_threshold: number;
  cosine_retrieve_threshold: number;
  copilot_lexical_threshold: number;
  llm_required: boolean;
  dataset_label: string;
  display_timezone: string;
  external_inference_blocked: boolean;
  openai_configured: boolean;
  runtime_warnings: string[];
  last_connection_check: string | null;
  last_connection_ok: boolean | null;
  last_connection_detail: string | null;
  threshold_note: string;
  reindex_required?: boolean;
};

export type AnalysisCandidate = {
  id: string;
  rank: number;
  category: string;
  heuristic_category: string | null;
  llm_category: string | null;
  disagreement: boolean;
  cosine_similarity: number | null;
  fuzzy_score: number | null;
  exact_match: boolean;
  explanation: string | null;
  similarities: string[];
  differences: string[];
  evidence: Record<string, unknown> | null;
  historical: Idea | null;
};

export type Analysis = {
  id: string;
  status: string;
  outcome_category: string;
  provider: string;
  chat_model: string | null;
  embedding_model: string;
  retrieval_k: number;
  llm_status: string;
  warning: string | null;
  created_at: string | null;
  completed_at: string | null;
  submission: Idea | null;
  candidates: AnalysisCandidate[];
  human_decision: {
    id: string;
    decision: string;
    rationale: string;
    ai_recommendation: string | null;
    created_at: string;
  } | null;
  score_note: string;
};

export type ImportBatch = {
  id: string;
  filename: string;
  sheet_name: string | null;
  status: string;
  merge_strategy: string;
  is_synthetic: boolean;
  allow_partial: boolean;
  row_count: number;
  inserted_count: number;
  updated_count: number;
  skipped_count: number;
  error_count: number;
  warning_count: number;
  created_at: string | null;
  committed_at: string | null;
  errors?: { row_number: number; column_name: string | null; severity: string; message: string; raw_value: string | null }[];
  mapping?: Record<string, string>;
  summary?: { sheets?: string[]; unmapped?: string[]; headers?: string[]; ready?: boolean };
  preview_rows?: {
    row_number: number;
    action: string;
    idea_code: string | null;
    component: string | null;
    stage_status: string | null;
    rejection_category: string | null;
  }[];
};

export type Citation = {
  document_id: string;
  document_title: string;
  chunk_id: string;
  page_number: number | null;
  section: string | null;
  excerpt: string;
  lexical_score: number;
  cosine_similarity: number;
  is_synthetic: boolean;
};

export type ChatReply = {
  session_id: string;
  message_id: string;
  answer: string;
  citations: Citation[];
  evidence: Citation[];
  abstained: boolean;
  provider: string;
  model: string | null;
};
