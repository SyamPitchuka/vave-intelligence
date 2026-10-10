import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { can } from "@/lib/permissions";
import { SESSION_EVENT, clearSession, readSession, writeSession, type Session } from "@/lib/session";
import type { CurrentUser } from "@/types";

type AuthValue = {
  user: CurrentUser | null;
  token: string | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  allowed: (permission?: string) => boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => readSession());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setSession(readSession());
    window.addEventListener(SESSION_EVENT, sync);
    window.addEventListener("storage", sync);
    const existing = readSession();
    if (!existing) {
      setReady(true);
      return () => {
        window.removeEventListener(SESSION_EVENT, sync);
        window.removeEventListener("storage", sync);
      };
    }
    api<CurrentUser>("/api/v1/auth/me")
      .then((user) => {
        writeSession({ token: existing.token, user });
        setSession({ token: existing.token, user });
      })
      .catch(() => {
        clearSession();
        setSession(null);
      })
      .finally(() => setReady(true));
    return () => {
      window.removeEventListener(SESSION_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      ready,
      async login(email: string, password: string) {
        const result = await api<{ access_token: string; user: CurrentUser }>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        const next = { token: result.access_token, user: result.user };
        writeSession(next);
        setSession(next);
      },
      logout() {
        clearSession();
        setSession(null);
      },
      allowed(permission?: string) {
        return can(session?.user.permissions, permission);
      },
    }),
    [ready, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing.");
  return value;
}
