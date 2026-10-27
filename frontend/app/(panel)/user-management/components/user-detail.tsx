"use client";

import { useEffect, useMemo, useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/providers";
import type { ManagedComputer } from "@/lib/types";
import { RoleBadge } from "./role-badge";
import { isValidEmail, isValidPhone } from "./validations";

type PanelUserDetail = {
  id: number;
  username: string;
  role: string;
  full_name: string;
  email: string;
  phone: string;
  created_at: string;
  last_login_at: string | null;
  last_seen_at: string | null;
  logout_at: string | null;
  online: boolean;
  computer_access: number[];
  page_access: string[];
};

type ActivityLog = {
  id: number;
  timestamp: string;
  action: string;
  target: string;
  result: string;
};

type ComputerLite = Pick<ManagedComputer, "id" | "name" | "hostname">;

type Tab = "profil" | "log" | "akses" | "akses-hal";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "profil", label: "Profil" },
  { id: "log", label: "Log Aktivitas" },
  { id: "akses", label: "Akses Komputer" },
  { id: "akses-hal", label: "Akses Halaman" },
];

export function UserDetail({
  userId,
  computers,
  isSuperadmin,
  onUpdated,
}: {
  userId: number | null;
  computers: ComputerLite[];
  isSuperadmin: boolean;
  onUpdated: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("profil");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({ full_name: "", email: "", phone: "" });
  const [profileError, setProfileError] = useState("");
  const [computerSearch, setComputerSearch] = useState("");

  const detailQuery = useQuery({
    queryKey: ["panel-user-detail", userId],
    queryFn: () =>
      userId === null
        ? Promise.resolve(null)
        : api<PanelUserDetail>(`/panel-users/${userId}/detail`),
    enabled: userId !== null,
  });

  const activityQuery = useInfiniteQuery({
    queryKey: ["panel-user-activity", userId],
    queryFn: ({ pageParam = 0 }) =>
      api<{ total: number; offset: number; limit: number; logs: ActivityLog[] }>(
        `/panel-users/${userId}/activity?limit=50&offset=${pageParam}`
      ),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((sum, p) => sum + p.logs.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
    enabled: userId !== null,
  });

  const user = detailQuery.data;
  const allLogs = useMemo(
    () => activityQuery.data?.pages.flatMap((p) => p.logs) ?? [],
    [activityQuery.data]
  );
  const activityTotal = activityQuery.data?.pages[0]?.total ?? 0;

  const updateProfile = useMutation({
    mutationFn: (profile: { full_name: string; email: string; phone: string }) =>
      api(`/panel-users/${userId}`, { method: "PATCH", body: JSON.stringify(profile) }),
    onSuccess: () => {
      toast.success("Profil diperbarui");
      setEditingProfile(false);
      setProfileError("");
      if (userId)
        queryClient.invalidateQueries({ queryKey: ["panel-user-detail", userId] });
      queryClient.invalidateQueries({ queryKey: ["panel-users"] });
      onUpdated();
    },
    onError: (err) =>
      setProfileError(err instanceof ApiError ? err.message : "Gagal memperbarui profil"),
  });

  const saveComputerAccess = useMutation({
    mutationFn: (computerIds: number[]) =>
      api(`/panel-users/${userId}/computer-access`, {
        method: "PUT",
        body: JSON.stringify({ computer_ids: computerIds }),
      }),
    onSuccess: () => {
      toast.success(`Hak akses komputer diperbarui untuk ${user?.username ?? "user"}`);
      if (userId)
        queryClient.invalidateQueries({ queryKey: ["panel-user-detail", userId] });
      onUpdated();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan hak akses komputer"),
  });

  const savePageAccess = useMutation({
    mutationFn: (pages: string[]) =>
      api(`/panel-users/${userId}/page-access`, {
        method: "PUT",
        body: JSON.stringify({ pages }),
      }),
    onSuccess: () => {
      toast.success(`Izin halaman diperbarui untuk ${user?.username ?? "user"}`);
      if (userId)
        queryClient.invalidateQueries({ queryKey: ["panel-user-detail", userId] });
      onUpdated();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan izin halaman"),
  });

  const selectedIds = useMemo(() => user?.computer_access ?? [], [user]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const filteredComputers = useMemo(() => {
    const q = computerSearch.toLowerCase().trim();
    if (!q) return computers;
    return computers.filter(
      (c) =>
        (c.name ?? "").toLowerCase().includes(q) ||
        (c.hostname ?? "").toLowerCase().includes(q)
    );
  }, [computers, computerSearch]);

  const setAccess = (ids: number[]) => {
    if (!user || userId === null) return;
    queryClient.setQueryData(["panel-user-detail", userId], {
      ...user,
      computer_access: [...ids].sort((a, b) => a - b),
    });
  };

  const toggleComputer = (id: number) => {
    const next = new Set(selectedSet);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setAccess(Array.from(next));
  };

  if (userId === null) {
    return (
      <div className="card flex min-h-48 items-center justify-center text-center text-[11px] text-muted2">
        Pilih salah satu user untuk melihat detail
      </div>
    );
  }

  if (detailQuery.isLoading) {
    return (
      <div className="card flex min-h-48 items-center justify-center text-[11px] text-muted2">
        Memuat…
      </div>
    );
  }

  if (!user) {
    return (
      <div className="card flex min-h-48 items-center justify-center text-center text-[11px] text-muted2">
        User tidak ditemukan
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">{user.username}</div>
          <div className="card-subtitle">detail akun & izin</div>
        </div>
        <div className="flex items-center gap-2">
          <RoleBadge role={user.role} />
          {isSuperadmin && tab === "profil" ? (
            <button
              type="button"
              className="btn py-1.5 text-[10px]"
              onClick={() => {
                if (editingProfile) {
                  setEditingProfile(false);
                  setProfileError("");
                } else {
                  setProfileForm({
                    full_name: user.full_name || "",
                    email: user.email || "",
                    phone: user.phone || "",
                  });
                  setProfileError("");
                  setEditingProfile(true);
                }
              }}
            >
              {editingProfile ? "Batal Edit" : "Edit Profil"}
            </button>
          ) : null}
        </div>
      </div>

        <div className="mb-3 flex flex-wrap gap-1 border-b border-line">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`px-3 py-2 text-[11px] font-semibold ${
                tab === t.id
                  ? "border-b-2 border-[#5ea5ff] text-muted"
                  : "text-muted2 hover:text-muted"
              }`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === "log" && activityTotal > 0 ? ` (${activityTotal})` : ""}
            </button>
          ))}
        </div>

      {tab === "profil" ? (
        editingProfile ? (
          <div className="space-y-2">
            <label className="block text-[11px] text-muted">
              Nama lengkap
              <input
                className="input mt-1 w-full"
                value={profileForm.full_name}
                onChange={(e) =>
                  setProfileForm((p) => ({ ...p, full_name: e.target.value }))
                }
              />
            </label>
            <label className="block text-[11px] text-muted">
              Email
              <input
                type="email"
                className="input mt-1 w-full"
                value={profileForm.email}
                onChange={(e) =>
                  setProfileForm((p) => ({ ...p, email: e.target.value }))
                }
              />
            </label>
            <label className="block text-[11px] text-muted">
              Nomor telepon
              <input
                className="input mt-1 w-full"
                value={profileForm.phone}
                onChange={(e) =>
                  setProfileForm((p) => ({ ...p, phone: e.target.value }))
                }
              />
            </label>
            {profileError ? (
              <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-bad">
                {profileError}
              </div>
            ) : null}
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setEditingProfile(false);
                  setProfileError("");
                }}
              >
                Batal
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={updateProfile.isPending}
                onClick={() => {
                  const email = profileForm.email.trim();
                  if (email && !isValidEmail(email))
                    return setProfileError("Format email tidak valid");
                  const phone = profileForm.phone.trim();
                  if (phone && !isValidPhone(phone))
                    return setProfileError("Nomor telepon tidak valid");
                  updateProfile.mutate({
                    full_name: profileForm.full_name.trim(),
                    email,
                    phone,
                  });
                }}
              >
                {updateProfile.isPending ? "Menyimpan…" : "Simpan Profil"}
              </button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
              <div className="text-muted2">Nama lengkap</div>
              <div className="mt-1 font-semibold text-muted">
                {user.full_name || "—"}
              </div>
            </div>
            <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
              <div className="text-muted2">Kontak</div>
              <div className="mt-1 font-semibold text-muted">
                {user.email || user.phone || "—"}
              </div>
            </div>
            <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
              <div className="text-muted2">Akun dibuat</div>
              <div className="mt-1 font-semibold text-muted">
                {user.created_at || "—"}
              </div>
            </div>
            <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
              <div className="text-muted2">Last login</div>
              <div className="mt-1 font-semibold text-muted">
                {user.last_login_at ?? "—"}
              </div>
            </div>
            <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
              <div className="text-muted2">Log off (terakhir)</div>
              <div className="mt-1 font-semibold text-muted">
                {user.logout_at ?? "—"}
              </div>
            </div>
            <div
              className={`rounded-lg border px-3 py-2 text-[11px] ${
                user.online
                  ? "border-[#1d5a2e] bg-[#0d2a18] text-ok"
                  : "border-line bg-panel2 text-muted2"
              }`}
            >
              <div className="text-muted2">Status</div>
              <div className="mt-1 font-semibold">
                {user.online ? "Online" : "Offline"}
                <span className="ml-2 font-normal text-muted2">
                  {user.online
                    ? user.last_seen_at ?? ""
                    : user.logout_at ?? user.last_seen_at ?? ""}
                </span>
              </div>
            </div>
          </div>
        )
      ) : null}

      {tab === "log" ? (
        <div>
          <div className="max-h-64 space-y-2 overflow-auto">
            {activityQuery.isLoading ? (
              <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-muted2">
                Memuat…
              </div>
            ) : allLogs.length === 0 ? (
              <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-muted2">
                Belum ada aktivitas
              </div>
            ) : (
              allLogs.map((log) => (
                <div
                  key={log.id}
                  className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted"
                >
                  <div className="flex items-center justify-between gap-3">
                    <strong>{log.action}</strong>
                    <span className="text-[9px] uppercase text-muted2">
                      {log.result}
                    </span>
                  </div>
                  <div className="mt-1 text-muted2">{log.target || "—"}</div>
                  <div className="mt-1 font-mono text-[10px] text-muted">
                    {log.timestamp}
                  </div>
                </div>
              ))
            )}
          </div>
          {activityQuery.hasNextPage ? (
            <div className="mt-2 text-center">
              <button
                type="button"
                className="btn py-1.5 text-[10px]"
                disabled={activityQuery.isFetchingNextPage}
                onClick={() => activityQuery.fetchNextPage()}
              >
                {activityQuery.isFetchingNextPage
                  ? "Memuat…"
                  : `Muat lebih banyak (${allLogs.length}/${activityTotal})`}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === "akses" ? (
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <input
              className="input min-w-[180px] flex-1"
              placeholder="Cari komputer…"
              value={computerSearch}
              onChange={(e) => setComputerSearch(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] text-muted2">
                {selectedSet.size} dari {computers.length} dipilih
              </span>
              <button
                type="button"
                className="btn py-1.5 text-[10px]"
                onClick={() => setAccess(computers.map((c) => c.id))}
              >
                Pilih Semua
              </button>
              <button
                type="button"
                className="btn py-1.5 text-[10px]"
                onClick={() => setAccess([])}
              >
                Bersihkan
              </button>
              <button
                type="button"
                className="btn btn-primary py-1.5 text-[10px]"
                disabled={saveComputerAccess.isPending}
                onClick={() => saveComputerAccess.mutate(Array.from(selectedSet))}
              >
                {saveComputerAccess.isPending ? "Menyimpan…" : "Simpan"}
              </button>
            </div>
          </div>
          <div className="grid max-h-64 gap-2 overflow-auto md:grid-cols-2">
            {filteredComputers.map((computer) => {
              const allowed = selectedSet.has(computer.id);
              return (
                <label
                  key={computer.id}
                  className={`flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-[11px] ${
                    allowed
                      ? "border-[#5ea5ff] bg-[#0d243d]"
                      : "border-line bg-panel2"
                  }`}
                >
                  <div>
                    <div className="font-semibold text-muted">
                      {computer.name || computer.hostname || `PC-${computer.id}`}
                    </div>
                    <div className="text-muted2">{computer.hostname || "—"}</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={allowed}
                    onChange={() => toggleComputer(computer.id)}
                    className="h-4 w-4 accent-[#5ea5ff]"
                  />
                </label>
              );
            })}
            {filteredComputers.length === 0 ? (
              <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-muted2 md:col-span-2">
                Tidak ada komputer yang cocok
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {tab === "akses-hal" ? (
        <>
          <PageAccessTab
            user={user}
            isSuperadmin={isSuperadmin}
            onSave={(pages) => savePageAccess.mutate(pages)}
            pending={savePageAccess.isPending}
          />
                  </>
      ) : null}
    </div>
  );
}

function PageAccessTab({
  user,
  isSuperadmin,
  onSave,
  pending,
}: {
  user: PanelUserDetail;
  isSuperadmin: boolean;
  onSave: (pages: string[]) => void;
  pending: boolean;
}) {
  const [pages, setPages] = useState<string[]>(user.page_access || []);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setPages(user.page_access || []);
    setDirty(false);
  }, [user]);

  const toggle = (page: string, checked: boolean) => {
    setPages((prev) =>
      checked
        ? Array.from(new Set([...prev, page]))
        : prev.filter((p) => p !== page)
    );
    setDirty(true);
  };

  if (!isSuperadmin) {
    return (
      <div className="rounded-lg border border-line bg-panel2 px-3 py-6 text-center text-[11px] text-muted2">
        Hanya superadmin yang bisa mengatur izin halaman.
      </div>
    );
  }

  if ((user.role || "").toLowerCase() !== "admin") {
    return (
      <div className="rounded-lg border border-line bg-panel2 px-3 py-6 text-center text-[11px] text-muted2">
        Izin halaman hanya bisa diberikan ke role admin.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
        <div>
          <div className="font-semibold text-muted">Management CCTV</div>
          <div className="text-muted2">Akses halaman CCTV (wajib verifikasi password saat masuk)</div>
        </div>
        <input
          type="checkbox"
          checked={pages.includes("cctv")}
          onChange={(e) => toggle("cctv", e.target.checked)}
          className="h-4 w-4 accent-[#5ea5ff]"
        />
      </label>
      <label className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted">
        <div>
          <div className="font-semibold text-muted">Report</div>
          <div className="text-muted2">Akses laporan server, komputer & CCTV</div>
        </div>
        <input
          type="checkbox"
          checked={pages.includes("report")}
          onChange={(e) => toggle("report", e.target.checked)}
          className="h-4 w-4 accent-[#5ea5ff]"
        />
      </label>
      <div className="flex justify-end">
        <button
          type="button"
          className="btn btn-primary py-1.5 text-[10px]"
          disabled={!dirty || pending}
          onClick={() => onSave(pages)}
        >
          {pending ? "Menyimpan…" : "Simpan Izin"}
        </button>
      </div>
    </div>
  );
}
