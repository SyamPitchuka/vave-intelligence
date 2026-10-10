import { z } from "zod";

export const ideaDraftSchema = z.object({
  idea_code: z.string().trim().max(64).optional().or(z.literal("")),
  component: z.string().trim().max(200).optional().or(z.literal("")),
  idea_belonged_department: z.string().optional().or(z.literal("")),
  idea_generation_date: z.string().optional().or(z.literal("")),
  description: z.string().max(8000).optional().or(z.literal("")),
  current_design: z.string().max(4000).optional().or(z.literal("")),
  proposed_change: z.string().max(4000).optional().or(z.literal("")),
  engineering_rationale: z.string().max(4000).optional().or(z.literal("")),
  expected_benefit: z.string().max(4000).optional().or(z.literal("")),
  constraints: z.string().max(4000).optional().or(z.literal("")),
  idea_type: z.string().max(80).optional().or(z.literal("")),
  applicable_vehicle_details: z.string().max(2000).optional().or(z.literal("")),
  saving_per_vehicle: z.string().optional().or(z.literal("")),
});

export const ideaSubmitSchema = ideaDraftSchema.extend({
  component: z.string().trim().min(1, "Component or assembly is required."),
  idea_belonged_department: z.string().min(1, "Select the idea belonged department."),
  description: z
    .string()
    .trim()
    .min(20, "Enter at least 20 characters so duplicate analysis has a technical description."),
});

export const reviewSchema = z.object({
  decision: z.enum(["confirm_duplicate", "similar_but_distinct", "no_duplicate", "escalate"]),
  rationale: z.string().trim().min(10, "Enter a rationale of at least 10 characters."),
});

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter the password."),
});

export type IdeaFormValues = z.infer<typeof ideaDraftSchema>;
export type ReviewFormValues = z.infer<typeof reviewSchema>;

export function buildIdeaQuery(filters: Record<string, string>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}
