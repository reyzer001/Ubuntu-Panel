import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthUser {
  username: string;
  role?: string;
}

interface ElevatedEntry {
  token: string;
  expiresAt: number;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  /** Step-up tokens (mis. "cctv"). Tidak dipersist — hilang saat reload. */
  elevated: Record<string, ElevatedEntry>;
  /** Password global CCTV terakhir (all-in-one) — persist agar bisa auto-masuk */
  cctvGlobalPassword: string | null;
  setAuth: (token: string, user: AuthUser) => void;
  setAuthUser: (user: AuthUser) => void;
  setElevated: (scope: string, token: string, ttlSeconds: number) => void;
  getElevated: (scope: string) => string | null;
  /** Epoch kedaluwarsa (ms) token step-up, atau null bila tidak ada. */
  getElevatedExpiry: (scope: string) => number | null;
  setCctvGlobalPassword: (pw: string | null) => void;
  clearElevated: (scope?: string) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      elevated: {},
      cctvGlobalPassword: null,
      setAuth: (token, user) => set({ token, user }),
      setAuthUser: (user) =>
        set((s) => ({ user: { ...s.user, ...user } })),
      setElevated: (scope, token, ttlSeconds) =>
        set((s) => ({
          elevated: {
            ...s.elevated,
            [scope]: { token, expiresAt: Date.now() + ttlSeconds * 1000 },
          },
        })),
      getElevated: (scope) => {
        const entry = get().elevated[scope];
        if (!entry) return null;
        if (entry.expiresAt <= Date.now()) return null;
        return entry.token;
      },
      getElevatedExpiry: (scope) => {
        const entry = get().elevated[scope];
        if (!entry) return null;
        return entry.expiresAt;
      },
      setCctvGlobalPassword: (pw) => set({ cctvGlobalPassword: pw }),
      clearElevated: (scope) =>
        set((s) => {
          if (!scope) return { elevated: {} };
          const next = { ...s.elevated };
          delete next[scope];
          return { elevated: next };
        }),
      logout: () => {
        set({ token: null, user: null, elevated: {} });
        if (typeof window !== "undefined") {
          window.localStorage.removeItem("ubuntu-panel-auth");
        }
      },
    }),
    {
      name: "ubuntu-panel-auth",
      partialize: (s) => ({
        token: s.token,
        user: s.user,
        cctvGlobalPassword: s.cctvGlobalPassword,
      }),
    }
  )
);
