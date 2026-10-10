import type { CurrentUser } from "@/types";

const KEY = "vave.session";
export const SESSION_EVENT = "vave-session";

export type Session = {
  token: string;
  user: CurrentUser;
};

export function readSession(): Session | null {
  const raw = localStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Session;
    if (!parsed.token || !parsed.user) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeSession(session: Session) {
  localStorage.setItem(KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession() {
  localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(SESSION_EVENT));
}
