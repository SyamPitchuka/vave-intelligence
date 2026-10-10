import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorState, Hint, Input, Label, LoadingBlock, PageHeader, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/utils";
import type { CurrentUser, Options } from "@/types";

const DEPARTMENTS = [
  "Cab", "Brake", "Air intake system", "engine", "rear axle", "steeting", "propeller shaft",
  "exterior trims", "interior trims", "tyres", "frame", "lamps", "ECU", "Infotainment system",
  "wiring harness", "LV battery",
];

export function AdminPage() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: CurrentUser[] }>("/api/v1/admin/users") });
  const options = useQuery({ queryKey: ["options"], queryFn: () => api<Options>("/api/v1/meta/options") });
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<{ excel_mode_available: boolean; items: { id: string; name: string; view_name: string; dsn_env_var: string; is_active: boolean; last_error: string | null; secret_stored: boolean }[] }>("/api/v1/admin/data-sources"),
  });
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("vave_engineer");
  const [department, setDepartment] = useState("");
  const [viewName, setViewName] = useState("vave_historical_ideas");
  const [dsnEnv, setDsnEnv] = useState("CORPORATE_DATABASE_URL");
  const [active, setActive] = useState(false);
  const create = useMutation({
    mutationFn: () => api("/api/v1/admin/users", { method: "POST", body: JSON.stringify({ email, full_name: fullName, password, role, department: department || null }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
  const saveSource = useMutation({
    mutationFn: () => api("/api/v1/admin/data-sources", { method: "PUT", body: JSON.stringify({ view_name: viewName, dsn_env_var: dsnEnv, is_active: active }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
  const testSource = useMutation({ mutationFn: () => api<{ detail: string }>("/api/v1/admin/data-sources/test", { method: "POST" }) });
  return (
    <div className="space-y-4">
      <PageHeader title="Administration" description="Roles are enforced by the API. Excel import remains available when no corporate database is connected." />
      {users.isLoading ? <LoadingBlock /> : null}
      {users.isError ? <ErrorState message={errorMessage(users.error)} onRetry={() => users.refetch()} /> : null}
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Users</h2>
        <table className="data mt-3">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th></tr></thead>
          <tbody>
            {(users.data?.items ?? []).map((user) => (
              <tr key={user.id}><td>{user.full_name}</td><td>{user.email}</td><td>{user.role_labels.join(", ")}</td><td>{user.department ?? "Not recorded"}</td></tr>
            ))}
          </tbody>
        </table>
        <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
          <div><Label htmlFor="full_name">Name</Label><Input id="full_name" value={fullName} onChange={(event) => setFullName(event.target.value)} /></div>
          <div><Label htmlFor="user_email">Email</Label><Input id="user_email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
          <div><Label htmlFor="user_password">Password</Label><Input id="user_password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
          <div>
            <Label htmlFor="role">Role</Label>
            <Select id="role" value={role} onChange={(event) => setRole(event.target.value)}>
              {(options.data?.roles ?? []).map((item) => <option key={item.name} value={item.name}>{item.label}</option>)}
            </Select>
          </div>
          <div>
            <Label htmlFor="user_department">Department</Label>
            <Select id="user_department" value={department} onChange={(event) => setDepartment(event.target.value)}>
              <option value="">None</option>
              {DEPARTMENTS.map((name) => <option key={name} value={name}>{name}</option>)}
            </Select>
          </div>
          <div className="flex items-end"><Button type="submit">Create user</Button></div>
          {create.isError ? <p className="text-sm text-rose-700">{errorMessage(create.error)}</p> : null}
        </form>
      </section>
      <section className="card p-4">
        <h2 className="text-sm font-semibold">Corporate historical source</h2>
        <p className="mt-1 text-sm text-muted">Excel mode available: {sources.data?.excel_mode_available ? "Yes" : "No"}. The connection string is an environment variable name. The secret is not stored here.</p>
        <form className="mt-3 grid gap-3 md:grid-cols-2" onSubmit={(event) => { event.preventDefault(); saveSource.mutate(); }}>
          <div><Label htmlFor="view">View name</Label><Input id="view" value={viewName} onChange={(event) => setViewName(event.target.value)} /></div>
          <div><Label htmlFor="dsn">DSN environment variable</Label><Input id="dsn" value={dsnEnv} onChange={(event) => setDsnEnv(event.target.value)} /></div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active</label>
          <div className="flex gap-2">
            <Button type="submit">Save source</Button>
            <Button type="button" variant="secondary" onClick={() => testSource.mutate()}>Test connection</Button>
          </div>
        </form>
        <Hint>A test uses parameterised SQL against the named view. The language model cannot generate SQL.</Hint>
        {testSource.isError ? <p className="mt-2 text-sm text-rose-700">{errorMessage(testSource.error)}</p> : null}
        {testSource.data ? <p className="mt-2 text-sm">{testSource.data.detail}</p> : null}
        {(sources.data?.items ?? []).map((source) => (
          <p key={source.id} className="mt-2 text-sm">{source.name}: {source.is_active ? "active" : "inactive"} · secret stored: {source.secret_stored ? "yes" : "no"} · {source.last_error ?? "no last error"}</p>
        ))}
      </section>
    </div>
  );
}
