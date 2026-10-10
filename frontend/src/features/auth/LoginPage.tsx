import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { FieldError, Input, Label } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { loginSchema } from "@/lib/schemas";
import { errorMessage } from "@/lib/utils";

type FormValues = { email: string; password: string };

export function LoginPage() {
  const { user, login } = useAuth();
  const [formError, setFormError] = useState("");
  const accounts = useQuery({
    queryKey: ["dev-accounts"],
    queryFn: () =>
      api<{ enabled: boolean; note?: string; accounts: { email: string; password: string; role: string }[] }>(
        "/api/v1/auth/dev-accounts",
      ),
  });
  const form = useForm<FormValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  if (user) return <Navigate to="/" replace />;

  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-[22rem_1fr]">
      <aside className="hidden flex-col justify-between bg-navy-950 p-8 text-slate-100 lg:flex">
        <div>
          <p className="text-sm font-semibold">VAVE Intelligence</p>
          <h1 className="mt-8 text-2xl font-semibold leading-snug">Engineering value, with the historical record kept intact.</h1>
          <p className="mt-4 text-sm leading-6 text-slate-300">
            Search ideas by meaning, compare engineering changes, and record a human decision. AI recommendations never replace the official history.
          </p>
        </div>
        <p className="text-xs text-slate-400">Synthetic demonstration data is labelled as synthetic.</p>
      </aside>
      <main className="flex items-center justify-center px-4 py-10">
        <form
          className="card w-full max-w-md p-6"
          onSubmit={form.handleSubmit(async (values) => {
            setFormError("");
            try {
              await login(values.email, values.password);
            } catch (error) {
              setFormError(errorMessage(error));
            }
          })}
        >
          <h2 className="text-lg font-semibold text-navy-950">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use the account issued for your role.</p>
          <div className="mt-5 space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="username" {...form.register("email")} />
              <FieldError>{form.formState.errors.email?.message}</FieldError>
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete="current-password" {...form.register("password")} />
              <FieldError>{form.formState.errors.password?.message}</FieldError>
            </div>
          </div>
          {formError ? <p className="mt-3 text-sm text-rose-700">{formError}</p> : null}
          <Button className="mt-5 w-full" type="submit" disabled={form.formState.isSubmitting}>
            Sign in
          </Button>
          {accounts.data?.enabled ? (
            <div className="mt-6 border-t border-line pt-4">
              <p className="text-xs font-medium uppercase tracking-wide text-amber-800">Development accounts only</p>
              <p className="mt-1 text-xs leading-5 text-muted">{accounts.data.note}</p>
              <ul className="mt-3 space-y-2">
                {accounts.data.accounts.map((account) => (
                  <li key={account.email}>
                    <button
                      type="button"
                      className="text-left text-xs text-accent-700"
                      onClick={() => {
                        form.setValue("email", account.email);
                        form.setValue("password", account.password);
                      }}
                    >
                      {account.role}: {account.email}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </form>
      </main>
    </div>
  );
}
