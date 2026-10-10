import {
  Bell,
  ChevronLeft,
  Cpu,
  LogOut,
  Menu,
  Search,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatWhen } from "@/lib/format";
import { visibleNav } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type { AiStatus } from "@/types";

const CRUMBS: { test: (path: string) => boolean; items: { label: string; to?: string }[] }[] = [
  { test: (path) => path === "/", items: [{ label: "Dashboard" }] },
  { test: (path) => path === "/ideas/new", items: [{ label: "Ideas", to: "/ideas" }, { label: "Submit idea" }] },
  { test: (path) => path.startsWith("/ideas/"), items: [{ label: "Ideas", to: "/ideas" }, { label: "Record" }] },
  { test: (path) => path === "/ideas", items: [{ label: "Idea Explorer" }] },
  { test: (path) => path.startsWith("/analyses/"), items: [{ label: "Duplicate detection", to: "/analyses" }, { label: "Analysis" }] },
  { test: (path) => path === "/analyses", items: [{ label: "Duplicate detection" }] },
  { test: (path) => path === "/reviews", items: [{ label: "Reviews" }] },
  { test: (path) => path === "/import", items: [{ label: "Import data" }] },
  { test: (path) => path === "/analytics/savings", items: [{ label: "Savings" }] },
  { test: (path) => path === "/analytics/rejections", items: [{ label: "Rejections" }] },
  { test: (path) => path === "/copilot", items: [{ label: "Knowledge Copilot" }] },
  { test: (path) => path === "/evaluation", items: [{ label: "Evaluation" }] },
  { test: (path) => path === "/settings/ai", items: [{ label: "AI settings" }] },
  { test: (path) => path === "/audit", items: [{ label: "Audit log" }] },
  { test: (path) => path === "/admin", items: [{ label: "Administration" }] },
];

export function Shell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [query, setQuery] = useState("");
  const items = visibleNav(user?.permissions);
  const crumbs = CRUMBS.find((entry) => entry.test(location.pathname))?.items ?? [{ label: "VAVE Intelligence" }];

  const status = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api<AiStatus>("/api/v1/ai/status"),
    refetchInterval: 60_000,
  });
  const notes = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: { id: string; action: string; created_at: string | null }[] }>("/api/v1/notifications"),
  });
  const search = useQuery({
    queryKey: ["global-search", query],
    queryFn: () =>
      api<{ items: { id: string; idea_code: string; component: string | null }[] }>(
        `/api/v1/ideas/search?q=${encodeURIComponent(query)}`,
      ),
    enabled: query.trim().length > 1,
  });

  useEffect(() => {
    setMobileOpen(false);
    setMenuOpen(false);
    setNotesOpen(false);
  }, [location.pathname]);

  const mode = status.data?.mode;
  const offline = mode === "offline";

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="flex min-h-screen">
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-30 flex flex-col bg-navy-950 text-slate-100 transition-all md:static",
            collapsed ? "md:w-16" : "md:w-64",
            mobileOpen ? "w-64" : "hidden md:flex",
          )}
        >
          <div className="flex items-center gap-3 border-b border-white/10 px-4 py-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded bg-accent-600 text-sm font-semibold">VI</div>
            {collapsed ? null : (
              <div>
                <p className="text-sm font-semibold leading-tight">VAVE Intelligence</p>
                <p className="text-[11px] text-slate-300">Engineering value</p>
              </div>
            )}
          </div>
          <nav aria-label="Primary" className="flex-1 space-y-1 overflow-auto px-2 py-3">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                title={item.label}
                className={({ isActive }) =>
                  cn(
                    "flex items-center rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-white/10",
                    isActive && "bg-white/15 font-medium text-white",
                  )
                }
              >
                {collapsed ? item.label.slice(0, 1) : item.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            className="m-2 hidden items-center gap-2 rounded-md px-3 py-2 text-xs text-slate-300 hover:bg-white/10 md:flex"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            <ChevronLeft className={cn("h-4 w-4", collapsed && "rotate-180")} />
            {collapsed ? null : "Collapse"}
          </button>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-line bg-white">
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <button type="button" className="md:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>
                <Menu className="h-5 w-5" />
              </button>
              <form
                className="relative min-w-[16rem] flex-1"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (query.trim()) navigate(`/ideas?q=${encodeURIComponent(query.trim())}`);
                }}
              >
                <label htmlFor="global-search" className="sr-only">
                  Search ideas
                </label>
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" />
                <input
                  id="global-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search idea ID, component, or description"
                  className="w-full rounded-md border border-line bg-canvas py-2 pl-9 pr-3 text-sm"
                />
                {search.data && query.trim().length > 1 ? (
                  <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-line bg-white shadow-card">
                    {search.data.items.length === 0 ? (
                      <li className="px-3 py-2 text-sm text-muted">No matching ideas.</li>
                    ) : (
                      search.data.items.map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left text-sm hover:bg-canvas"
                            onClick={() => navigate(`/ideas/${item.id}`)}
                          >
                            <span className="font-medium">{item.idea_code}</span>
                            <span className="ml-2 text-muted">{item.component ?? "Component not recorded"}</span>
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                ) : null}
              </form>
              <div
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
                  offline ? "border-amber-400 bg-amber-50 text-amber-950" : "border-line bg-canvas text-navy-800",
                )}
                title={status.data?.mode_label}
              >
                <Cpu className="h-3.5 w-3.5" />
                <span>{offline ? "OFFLINE / LOCAL" : status.data?.mode_label ?? "AI status"}</span>
                <span className="hidden text-muted lg:inline">
                  {status.data?.provider ?? ""} {status.data?.embedding_model ? `· ${status.data.embedding_model}` : ""}
                </span>
              </div>
              <span className="hidden rounded-full border border-line px-3 py-1 text-xs text-muted xl:inline">
                Dataset: {status.data?.dataset_label ?? "—"}
              </span>
              <div className="relative">
                <button type="button" aria-label="Notifications" className="rounded-md p-2 hover:bg-canvas" onClick={() => setNotesOpen((value) => !value)}>
                  <Bell className="h-4 w-4" />
                </button>
                {notesOpen ? (
                  <div className="absolute right-0 z-30 mt-1 w-72 rounded-md border border-line bg-white p-2 shadow-card">
                    <p className="px-2 py-1 text-xs font-medium text-muted">Recent actions</p>
                    {(notes.data?.items ?? []).length === 0 ? (
                      <p className="px-2 py-3 text-sm text-muted">No recent actions for this account.</p>
                    ) : (
                      notes.data?.items.map((item) => (
                        <p key={item.id} className="px-2 py-1.5 text-sm">
                          {item.action}
                          <span className="mt-0.5 block text-xs text-muted">{formatWhen(item.created_at, status.data?.display_timezone)}</span>
                        </p>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
              <div className="relative">
                <button type="button" className="rounded-md px-2 py-1 text-left text-sm hover:bg-canvas" onClick={() => setMenuOpen((value) => !value)}>
                  <span className="block font-medium">{user?.full_name}</span>
                  <span className="block text-xs text-muted">{user?.role_labels?.[0] ?? user?.roles?.[0]}</span>
                </button>
                {menuOpen ? (
                  <div className="absolute right-0 z-30 mt-1 w-52 rounded-md border border-line bg-white p-2 shadow-card">
                    <p className="px-2 py-1 text-xs text-muted">{user?.email}</p>
                    <button type="button" className="flex w-full items-center gap-2 rounded px-2 py-2 text-sm hover:bg-canvas" onClick={logout}>
                      <LogOut className="h-4 w-4" /> Sign out
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
            <nav aria-label="Breadcrumb" className="flex gap-2 px-4 pb-3 text-xs text-muted">
              {crumbs.map((crumb, index) => (
                <span key={crumb.label} className="flex items-center gap-2">
                  {index > 0 ? <span>/</span> : null}
                  {crumb.to ? (
                    <button type="button" className="hover:text-accent-700" onClick={() => navigate(crumb.to!)}>
                      {crumb.label}
                    </button>
                  ) : (
                    <span className="text-ink">{crumb.label}</span>
                  )}
                </span>
              ))}
            </nav>
          </header>
          <main id="content" className="flex-1 px-4 py-5 md:px-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
