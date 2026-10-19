"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";

interface LoginResponse {
  access_token: string;
  user: { username: string; role?: string };
}

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuth((s) => s.setAuth);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setAuth(res.access_token, res.user);
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Cannot reach the server"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[radial-gradient(ellipse_at_top,#101a26,#080c11)] p-4">
      <div className="w-full max-w-sm rounded-card border border-line bg-panel p-7 shadow-[0_25px_60px_rgba(0,0,0,.4)]">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-[42px] w-[42px] place-items-center rounded-[11px] bg-accent font-black text-white">
            U
          </div>
          <div>
            <div className="text-lg font-bold">Server Manager</div>
            <div className="text-[11px] text-muted">
              Sign in to manage this server
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-widest text-muted2">
              Username
            </label>
            <input
              className="input w-full"
              value={username}
              onChange={(e) => { setUsername(e.target.value); setError(""); }}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-widest text-muted2">
              Password
            </label>
            <input
              className="input w-full"
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(""); }}
              autoComplete="current-password"
              required
            />
          </div>



          <button
            type="submit"
            className="btn btn-primary w-full py-2.5 text-xs"
            disabled={loading}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-5 text-center text-[10px] text-muted2">
          Default credentials are set via ADMIN_USERNAME / ADMIN_PASSWORD on the
          backend.
        </p>
      </div>
    </div>
  );
}
