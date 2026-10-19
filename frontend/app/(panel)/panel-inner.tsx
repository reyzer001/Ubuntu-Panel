"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { Sidebar } from "@/components/sidebar";

export function PanelInner({ children }: { children: ReactNode }) {
  const router = useRouter();
  const token = useAuth((s) => s.token);
  const setAuthUser = useAuth((s) => s.setAuthUser);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  // sinkronkan role/profil dari server — token lama (sebelum ada role)
  // tetap ikut terbarui tanpa harus login ulang
  const meQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: () => api<{ username: string; role?: string }>("/auth/me"),
    enabled: !!token,
    staleTime: 5 * 60_000,
    retry: false,
  });

  useEffect(() => {
    if (meQuery.data && token) {
      setAuthUser({ username: meQuery.data.username, role: meQuery.data.role });
    }
  }, [meQuery.data, token, setAuthUser]);

  useEffect(() => {
    if (hydrated && !token) router.replace("/login");
  }, [hydrated, token, router]);

  if (!hydrated || !token) {
    return (
      <div className="grid min-h-screen place-items-center text-xs text-muted">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="ml-[70px] min-h-screen p-4 lg:ml-[250px] lg:p-[26px]">
        {children}
      </main>
    </div>
  );
}
