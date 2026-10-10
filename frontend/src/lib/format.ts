const FALLBACK_ZONE = "Asia/Kolkata";

export function inr(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "Not recorded";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not recorded";
  return new Intl.NumberFormat("en-IN").format(value);
}

export function formatWhen(value: string | null | undefined, timeZone = FALLBACK_ZONE): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(date);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  return value;
}

export function text(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  return String(value);
}

export const OUTCOME_LABELS: Record<string, string> = {
  potential_duplicate: "Potential Duplicate",
  similar_but_distinct: "Similar but Distinct",
  no_strong_match: "No Strong Match Found",
  insufficient_evidence: "Insufficient Evidence / Manual Review Required",
};

export const DECISION_LABELS: Record<string, string> = {
  confirm_duplicate: "Confirm Duplicate",
  similar_but_distinct: "Mark Similar but Distinct",
  no_duplicate: "Confirm No Duplicate",
  escalate: "Escalate for Engineering Review",
};

export function outcomeLabel(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  return OUTCOME_LABELS[value] ?? value;
}

export function decisionLabel(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  return DECISION_LABELS[value] ?? value;
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not calculated";
  return `${(value * 100).toFixed(1)}%`;
}
