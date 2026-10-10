export type NavItem = {
  to: string;
  label: string;
  permission?: string;
  end?: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", permission: "dashboard:read", end: true },
  { to: "/ideas", label: "Idea Explorer", permission: "ideas:read" },
  { to: "/ideas/new", label: "Submit idea", permission: "ideas:write" },
  { to: "/analyses", label: "Duplicate detection", permission: "ideas:read" },
  { to: "/reviews", label: "Reviews", permission: "reviews:read" },
  { to: "/import", label: "Import data", permission: "ideas:import" },
  { to: "/analytics/savings", label: "Savings", permission: "analytics:read" },
  { to: "/analytics/rejections", label: "Rejections", permission: "analytics:read" },
  { to: "/copilot", label: "Knowledge Copilot", permission: "copilot:use" },
  { to: "/evaluation", label: "Evaluation", permission: "evaluation:read" },
  { to: "/settings/ai", label: "AI settings" },
  { to: "/audit", label: "Audit log", permission: "audit:read" },
  { to: "/admin", label: "Administration", permission: "*" },
];

export function can(permissions: string[] | undefined, permission?: string): boolean {
  if (!permission) return true;
  const granted = permissions ?? [];
  return granted.includes("*") || granted.includes(permission);
}

export function visibleNav(permissions: string[] | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => can(permissions, item.permission));
}
