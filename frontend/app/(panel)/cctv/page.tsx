"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cctv,
  ExternalLink,
  Play,
  Square,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
  Settings,
  Download,
  Radar,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { useConfirm, useToast } from "@/components/providers";
import { api, ApiError, mediaUrl } from "@/lib/api";
import { useAuth } from "@/store/auth";
import type {
  Camera,
  CameraGroup,
  CameraSummary,
  DiscoverableCamera,
} from "@/lib/types";

type CredInput = { username: string; password: string };

type OfflineCamera = {
  id: number;
  name: string;
  ip: string;
  vendor: string;
  model: string;
  last_seen: string | null;
};

type CamForm = {
  id?: number;
  name: string;
  ip: string;
  port: number;
  rtsp_port: number;
  scheme: string;
  protocol: string;
  channel: number;
  vendor: string;
  model: string;
  group_id: number | null;
  snapshot_path: string;
  stream_path: string;
  notes: string;
  credentials: CredInput[];
};

const EMPTY_FORM: CamForm = {
  name: "",
  ip: "",
  port: 80,
  rtsp_port: 554,
  scheme: "http",
  protocol: "http",
  channel: 1,
  vendor: "",
  model: "",
  group_id: null,
  snapshot_path: "",
  stream_path: "",
  notes: "",
  credentials: [{ username: "admin", password: "" }],
};

const PAGE_OPTIONS = [20];

function defSnap(vendor: string, channel: number) {
  const v = (vendor || "").toLowerCase();
  if (v.includes("hikvision") || v.includes("ezviz")) return `/ISAPI/Streaming/channels/${channel}01/picture`;
  if (v.includes("dahua") || v.includes("amcrest")) return `/cgi-bin/snapshot.cgi?channel=${channel}`;
  if (v.includes("reolink")) return `/cgi-bin/api.cgi?cmd=Snap&channel=${channel}&rs=snap`;
  if (v.includes("axis")) return `/axis-cgi/jpg/image.cgi?camera=${channel}`;
  if (v.includes("uniview") || v.includes("unv")) return `/cgi-bin/snapshot.cgi?chn=${channel}`;
  return "/snapshot.jpg";
}
function defStream(vendor: string, channel: number) {
  const v = (vendor || "").toLowerCase();
  if (v.includes("hikvision") || v.includes("ezviz")) return `/Streaming/Channels/${channel}01`;
  if (v.includes("dahua") || v.includes("amcrest")) return `/cam/realmonitor?channel=${channel}&subtype=0`;
  if (v.includes("reolink")) return `/h264Preview_${String(channel).padStart(2,"0")}_main`;
  if (v.includes("axis")) return `/axis-media/media.amp?camera=${channel}`;
  return `/stream${channel}`;
}
export default function CctvPage() {
  const toast = useToast();
  const { confirm } = useConfirm();
  const queryClient = useQueryClient();

  // Standby livestream: grid selalu mulai dalam mode live.
  // Tick hanya untuk cache-buster snapshot (10 detik), bukan untuk live MJPEG.
  const unlocked = !!useAuth.getState().getElevated("cctv");

  const [password, setPassword] = useState("");
  const [pwError, setPwError] = useState("");
  const [tick, setTick] = useState(0);
  const [search, setSearch] = useState("");
  const [groupFilter, setGroupFilter] = useState<number | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "online" | "offline">("all");

  const [form, setForm] = useState<CamForm | null>(null);
  const [credCam, setCredCam] = useState<Camera | null>(null);
  const [detectCam, setDetectCam] = useState<Camera | null>(null);
  const [credRows, setCredRows] = useState<CredInput[]>([]);
  const [showImport, setShowImport] = useState(false);
  const [importSel, setImportSel] = useState<Set<number>>(new Set());
  const [newGroup, setNewGroup] = useState("");
  const [showGlobalSettings, setShowGlobalSettings] = useState(false);
  const [liveAll, setLiveAll] = useState(false);
  const [page, setPage] = useState(1);
  // Naik tiap sesi terverifikasi/diperpanjang → tile yang gagal ikut coba ulang.
  const [unlockEpoch, setUnlockEpoch] = useState(0);
  const [pageSize, setPageSize] = useState<number>(() => {
    if (typeof window === "undefined") return 20;
    const raw = window.localStorage.getItem("cctv-page-size");
    const n = raw ? Number(raw) : 20;
    return PAGE_OPTIONS.includes(n) ? n : 20;
  });
  const gridTopRef = useRef<HTMLDivElement>(null);

  const token = useAuth((s) => s.token);
  const meQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: () =>
      api<{ username: string; role?: string; page_access?: string[] }>(
        "/auth/me",
      ),
    enabled: !!token,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const isSuperadmin = meQuery.data?.role === "superadmin";
  const isAdmin = meQuery.data?.role === "admin";
  const hasAccess =
    isSuperadmin ||
    (isAdmin && (meQuery.data?.page_access ?? []).includes("cctv"));

  // keluar dari halaman = wajib verifikasi password lagi saat masuk
  useEffect(() => {
    return () => {
      useAuth.getState().clearElevated("cctv");
    };
  }, []);

  useEffect(() => {
    const iv = setInterval(() => {
      setTick((t) => t + 1);
    }, 10_000);
    return () => clearInterval(iv);
  }, []);

  const camsQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: () =>
      api<{ cameras: Camera[]; summary: CameraSummary }>("/cameras", {
        elevated: "cctv",
      }),
    enabled: unlocked && hasAccess,
    refetchInterval: 15_000,
  });

  const groupsQuery = useQuery({
    queryKey: ["camera-groups"],
    queryFn: () => api<{ groups: CameraGroup[] }>("/cameras/groups", { elevated: "cctv" }),
    enabled: unlocked && hasAccess,
  });

  // Ringkasan read-only untuk admin: jumlah ON/MATI + daftar kamera mati.
  // Tanpa step-up (endpoint khusus), admin cukup login.
  const overviewQuery = useQuery({
    queryKey: ["camera-status-overview"],
    queryFn: () =>
      api<{ summary: CameraSummary; offline_cameras: OfflineCamera[] }>(
        "/cameras/status-overview",
      ),
    enabled: hasAccess && isAdmin,
    refetchInterval: 15_000,
  });

  // Catatan: mode tersimpan di server ("cctv-default-mode") sengaja TIDAK
  // di-apply otomatis ke grid. Grid selalu standby livestream saat halaman
  // dibuka. Nilai server hanya dipakai sebagai tampilan di modal Pengaturan;
  // perubahan eksplisit user via modal/toggle yang mengubah liveAll.

  useEffect(() => {
    if (camsQuery.error instanceof ApiError && camsQuery.error.status === 428) {
      useAuth.getState().clearElevated("cctv");
    }
  }, [camsQuery.error]);

  useEffect(() => {
    setPwError("");
  }, [showGlobalSettings]);

  const stepUp = useMutation({
    mutationFn: (pw: string) =>
      api<{ elevated_token: string; expires_in: number }>("/auth/step-up", {
        method: "POST",
        body: JSON.stringify({ password: pw, scope: "cctv" }),
      }),
    onSuccess: (res) => {
      useAuth
        .getState()
        .setElevated("cctv", res.elevated_token, res.expires_in ?? 300);
      setPassword("");
      setPwError("");
      setTick((t) => t + 1);
      setUnlockEpoch((e) => e + 1);
    },
    onError: (err) =>
      setPwError(err instanceof ApiError ? err.message : "Verifikasi gagal"),
  });

  // Heartbeat sesi: perpanjang token verifikasi diam-diam sebelum basi
  // (5 menit), agar monitoring tidak terputus dan tidak minta password
  // manual berulang. Berhenti saat tab disembunyikan.
  const refreshSession = useMutation({
    mutationFn: () => {
      const et = useAuth.getState().getElevated("cctv");
      if (!et) throw new Error("no session");
      return api<{ elevated_token: string; expires_in: number }>(
        "/auth/step-up/refresh",
        {
          method: "POST",
          body: JSON.stringify({ elevated_token: et, scope: "cctv" }),
        },
      );
    },
    onSuccess: (res) => {
      useAuth
        .getState()
        .setElevated("cctv", res.elevated_token, res.expires_in ?? 300);
      setUnlockEpoch((e) => e + 1);
    },
    // Gagal refresh (mis. sesi sudah basi) bukan error fatal — 428 dari
    // query berikutnya akan menampilkan gerbang seperti biasa.
    onError: () => {},
  });
  const refreshMutate = refreshSession.mutate;
  useEffect(() => {
    if (!unlocked) return;
    const beat = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      const exp = useAuth.getState().getElevatedExpiry("cctv");
      if (exp == null) return;
      if (exp - Date.now() < 90_000) refreshMutate();
    };
    const iv = setInterval(beat, 60_000);
    beat();
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlocked]);

  const saveCam = useMutation({
    mutationFn: (f: CamForm) => {
      const payload = { ...f, credentials: f.credentials ?? [] };
      return f.id
        ? api(`/cameras/${f.id}`, {
            method: "PUT",
            body: JSON.stringify(payload),
            elevated: "cctv",
          })
        : api(`/cameras`, {
            method: "POST",
            body: JSON.stringify(payload),
            elevated: "cctv",
          });
    },
    onSuccess: () => {
      toast.success(form?.id ? "Kamera diperbarui" : "Kamera ditambahkan");
      setForm(null);
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["camera-groups"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan kamera"),
  });

  const saveCreds = useMutation({
    mutationFn: (body: { id: number; credentials: CredInput[] }) =>
      api(`/cameras/${body.id}/credentials`, {
        method: "PUT",
        body: JSON.stringify({ credentials: body.credentials }),
        elevated: "cctv",
      }),
    onSuccess: () => {
      toast.success("Kredensial diperbarui");
      setCredCam(null);
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan kredensial"),
  });

  const deleteCam = useMutation({
    mutationFn: (id: number) =>
      api(`/cameras/${id}`, { method: "DELETE", elevated: "cctv" }),
    onSuccess: () => {
      toast.success("Kamera dihapus");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus"),
  });

  const testCam = useMutation({
    mutationFn: (id: number) =>
      api<{ ok: boolean; message: string }>(`/cameras/${id}/test`, {
        method: "POST",
        elevated: "cctv",
      }),
    onSuccess: (res) =>
      res.ok ? toast.success(res.message) : toast.error(res.message),
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Tes gagal"),
  });

  const discoverQuery = useQuery({
    queryKey: ["cameras-discoverable"],
    queryFn: () =>
      api<{ devices: DiscoverableCamera[] }>("/cameras/discoverable", {
        elevated: "cctv",
      }),
    enabled: unlocked && hasAccess && showImport,
  });

  const importCams = useMutation({
    mutationFn: (ids: number[]) =>
      api<{ created: number }>("/cameras/import", {
        method: "POST",
        body: JSON.stringify({ ap_ids: ids }),
        elevated: "cctv",
      }),
    onSuccess: (res) => {
      toast.success(`${res.created} kamera diimpor`);
      setShowImport(false);
      setImportSel(new Set());
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["cameras-discoverable"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal impor"),
  });

  const importAllCctv = useMutation({
    mutationFn: () =>
      api<{ created: number; total: number }>("/cameras/import-auto-cctv", {
        method: "POST",
        elevated: "cctv",
      }),
    onSuccess: (res) => {
      toast.success(`${res.created} kamera otomatis diimpor dari AP CCTV (Total: ${res.total})`);
      setShowImport(false);
      setImportSel(new Set());
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["cameras-discoverable"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal impor otomatis"),
  });

  const addGroup = useMutation({
    mutationFn: (name: string) =>
      api("/cameras/groups", {
        method: "POST",
        body: JSON.stringify({ name }),
        elevated: "cctv",
      }),
    onSuccess: () => {
      setNewGroup("");
      queryClient.invalidateQueries({ queryKey: ["camera-groups"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menambah grup"),
  });

  const cameras = camsQuery.data?.cameras ?? [];
  // Ringkasan dari backend (status ping); fallback hitung dari data kamera.
  const summary = useMemo(() => {
    const s = camsQuery.data?.summary;
    if (s) return { total: s.total, online: s.online, offline: s.offline };
    return {
      total: cameras.length,
      online: cameras.filter((c) => c.status === "ONLINE").length,
      offline: cameras.filter((c) => c.status !== "ONLINE").length,
    };
  }, [camsQuery.data?.summary, cameras]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return cameras.filter((c) => {
      if (groupFilter !== "all" && c.group_id !== groupFilter) return false;
      if (statusFilter === "online" && c.status !== "ONLINE") return false;
      if (statusFilter === "offline" && c.status === "ONLINE") return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.ip.toLowerCase().includes(q) ||
        c.vendor.toLowerCase().includes(q) ||
        c.model.toLowerCase().includes(q)
      );
    });
  }, [cameras, search, groupFilter, statusFilter]);

  // Pagination frontend: slice hasil filter, default 20/halaman.
  // Standby livestream aman karena maksimal `pageSize` stream ter-mount bersamaan.
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paginated = useMemo(
    () => filtered.slice((page - 1) * pageSize, page * pageSize),
    [filtered, page, pageSize],
  );

  // Reset ke halaman 1 saat filter/search/pageSize berubah.
  // pageSize selectable (12/20/50/100), default 20, dipersist ke localStorage.
  useEffect(() => {
    setPage(1);
  }, [search, groupFilter, statusFilter, pageSize]);

  useEffect(() => {
    try {
      window.localStorage.setItem("cctv-page-size", String(pageSize));
    } catch {
      // abaikan (private mode dsb.)
    }
  }, [pageSize]);

  // Clamp halaman saat data menyusut (mis. hapus kamera / hasil filter berkurang).
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const gotoPage = (p: number) => {
    setPage(Math.min(Math.max(1, p), totalPages));
    gridTopRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  if (meQuery.isLoading) {
    return <div className="card p-6 text-xs text-muted2">Memuat...</div>;
  }

  if (!hasAccess) {
    return (
      <div>
        <PageHeader title="Management CCTV" />
        <div className="card flex min-h-48 flex-col items-center justify-center gap-2 p-8 text-center">
          <ShieldCheck size={28} className="text-bad" />
          <div className="text-sm font-semibold text-muted">Akses ditolak</div>
          <div className="max-w-md text-xs text-muted2">
            Halaman ini hanya untuk superadmin atau admin yang diberi izin oleh
            superadmin.
          </div>
        </div>
      </div>
    );
  }

  // Admin (di-grant): hanya lihat ringkasan status, tidak ada manajemen/password.
  if (isAdmin) {
    return (
      <AdminCctvOverview
        summary={overviewQuery.data?.summary}
        offline={overviewQuery.data?.offline_cameras ?? []}
        loading={overviewQuery.isLoading}
        refreshing={overviewQuery.isFetching}
        error={
          overviewQuery.error instanceof ApiError
            ? overviewQuery.error.message
            : ""
        }
        onRefresh={() => overviewQuery.refetch()}
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="Management CCTV"
        subtitle="Pantau kamera terdaftar (grid ala NVR). Panel login otomatis ke kamera — lantas menampilkan feed tanpa login di browser."
        onRefresh={() => camsQuery.refetch()}
        refreshing={camsQuery.isFetching}
        right={
          meQuery.data?.role === "superadmin" ? (
            <button
              type="button"
              className="btn flex items-center gap-2"
              onClick={() => { setShowGlobalSettings(true); }}
              title="Pengaturan Global CCTV"
            >
              <Settings size={13} />
              Pengaturan
            </button>
          ) : undefined
        }
      />

      <CctvGlobalSettingsModal
        key="global-settings"
        open={showGlobalSettings}
        isSuperadmin={meQuery.data?.role === "superadmin"}
        onClose={() => setShowGlobalSettings(false)}
        onDefaultModeChange={(m) => setLiveAll(m === "live")}
        onSaved={() => {
          setUnlockEpoch((e) => e + 1);
          queryClient.invalidateQueries({ queryKey: ["cameras"] });
        }}
      />

      {!unlocked ? (
        <PasswordGate
          password={password}
          setPassword={setPassword}
          error={pwError}
          pending={stepUp.isPending}
          onSubmit={(pw) => stepUp.mutate(pw || password)}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn flex items-center gap-1.5"
              onClick={() => setShowImport(true)}
            >
              <RefreshCw size={13} /> Impor dari AP
            </button>
            <button
              type="button"
              className="btn flex items-center gap-1.5 border-[#5ea5ff]/40 text-[#5ea5ff] hover:bg-[#0d243d]"
              disabled={importAllCctv.isPending}
              title="Otomatis impor semua perangkat AP dari grup/segmen CCTV"
              onClick={async () => {
                const ok = await confirm({
                  title: "Impor Otomatis Full CCTV",
                  message:
                    "Impor seluruh IP kamera dari inventori Access Point (Grup / Segmen CCTV) secara otomatis? Perangkat yang sudah ada tidak akan diduplikasi.",
                  confirmText: "Impor Semua",
                });
                if (ok) importAllCctv.mutate();
              }}
            >
              <Download size={13} /> {importAllCctv.isPending ? "Mengimpor…" : "Impor Otomatis Full CCTV"}
            </button>
            <button
              type="button"
              className="btn btn-primary flex items-center gap-1.5"
              onClick={() => setForm({ ...EMPTY_FORM })}
            >
              <Plus size={13} /> Tambah Kamera
            </button>
            <div className="ml-auto flex items-center gap-1.5">
              <button
                type="button"
                className={`btn flex items-center gap-1.5 py-1.5 text-[11px] ${!liveAll ? "btn-primary" : ""}`}
                title="Mode Grid Pintar: Semua 20 kamera aktif & diperbarui otomatis (bebas limit browser & hemat CPU)"
                onClick={() => setLiveAll(false)}
              >
                <RefreshCw size={13} /> Grid Cepat (Semua Aktif)
              </button>
              <button
                type="button"
                className={`btn flex items-center gap-1.5 py-1.5 text-[11px] ${liveAll ? "btn-primary" : ""}`}
                title="Livestream kontinu penuh (catatan: browser HTTP/1.1 membatasi maks 6 stream simultan)"
                onClick={() => setLiveAll(true)}
              >
                <Play size={13} /> Live Semua (Maks 6)
              </button>
            </div>
          </div>

          <div ref={gridTopRef} className="card flex flex-wrap items-center gap-2 p-3">
            <div className="flex items-center gap-1.5" title="Klik untuk memfilter grid">
              <button
                type="button"
                onClick={() => setStatusFilter("all")}
                title="Tampilkan semua kamera"
                className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold ${statusFilter === "all" ? "border-[#5ea5ff] bg-[#0d243d] text-[#5ea5ff]" : "border-line bg-panel2 text-muted hover:text-muted2"}`}
              >
                Total {summary.total}
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter("online")}
                title="Tampilkan kamera yang hidup saja"
                className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold ${statusFilter === "online" ? "border-[#5ea5ff] bg-[#0d243d] text-[#5ea5ff]" : "border-line bg-panel2 text-muted hover:text-muted2"}`}
              >
                ● Hidup {summary.online}
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter("offline")}
                title="Tampilkan kamera yang mati saja — isi kredensialnya manual per tile"
                className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold ${statusFilter === "offline" ? "border-[#ff6b6b] bg-[#3d0d0d] text-[#ff6b6b]" : "border-line bg-panel2 text-muted hover:text-muted2"}`}
              >
                ● Mati {summary.offline}
              </button>
            </div>
            <input
              className="input w-52"
              placeholder="Cari nama / IP / merk / model..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="input w-44"
              value={groupFilter === "all" ? "" : groupFilter}
              onChange={(e) =>
                setGroupFilter(e.target.value ? Number(e.target.value) : "all")
              }
            >
              <option value="">Semua grup</option>
              {(groupsQuery.data?.groups ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            <div className="ml-auto flex items-center gap-2 text-[11px] text-muted2">
              <span>
                {filtered.length} kamera
                {liveAll ? " · Livestream (Maks 6)" : " · Grid Cepat (Semua Aktif)"}
              </span>
              <span className="rounded border border-line bg-panel2 px-2.5 py-1 text-[11px] font-medium text-muted">
                20 / halaman
              </span>
            </div>
          </div>

          {cameras.length === 0 ? (
            <div className="card flex min-h-48 flex-col items-center justify-center gap-2 p-8 text-center">
              <Cctv size={28} className="opacity-40" />
              <div className="text-sm font-semibold text-muted">
                Belum ada kamera terdaftar.
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="card flex min-h-48 flex-col items-center justify-center gap-2 p-8 text-center">
              <Cctv size={28} className="opacity-40" />
              <div className="text-sm font-semibold text-muted">
                Tidak ada kamera yang cocok dengan filter.
              </div>
              <button
                type="button"
                className="btn py-1.5 text-[11px]"
                onClick={() => {
                  setSearch("");
                  setGroupFilter("all");
                  setStatusFilter("all");
                }}
              >
                Reset filter
              </button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {paginated.map((cam) => (
                <CameraTile
                  key={cam.id}
                  camera={cam}
                  tick={tick}
                  liveAll={liveAll}
                  epoch={unlockEpoch}
                  onEdit={() =>
                    setForm({
                      id: cam.id,
                      name: cam.name,
                      ip: cam.ip,
                      port: cam.port,
                      rtsp_port: cam.rtsp_port,
                      scheme: cam.scheme,
                      protocol: cam.protocol,
                      channel: cam.channel,
                      vendor: cam.vendor,
                      model: cam.model,
                      group_id: cam.group_id,
                      snapshot_path: cam.snapshot_path,
                      stream_path: cam.stream_path,
                      notes: cam.notes,
                      credentials: [],
                    })
                  }
                  onCreds={() => {
                    setCredCam(cam);
                    setCredRows(
                      cam.credentials.length
                        ? cam.credentials.map((c) => ({
                            username: c.username,
                            password: "",
                          }))
                        : [{ username: "admin", password: "" }],
                    );
                  }}
                  onTest={() => testCam.mutate(cam.id)}
                  onDetect={() => setDetectCam(cam)}
                  onDelete={async () => {
                    const ok = await confirm({
                      title: "Hapus kamera",
                      message: `Hapus "${cam.name || cam.ip}" dari daftar CCTV?`,
                      tone: "danger",
                      confirmText: "Hapus",
                    });
                    if (ok) deleteCam.mutate(cam.id);
                  }}
                />
              ))}
              </div>
              {totalPages > 1 || filtered.length > pageSize ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-muted">
                  <div>
                    Menampilkan {(page - 1) * pageSize + 1} –{" "}
                    {Math.min(page * pageSize, filtered.length)} dari{" "}
                    {filtered.length} kamera
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      className="btn btn-sm px-2.5 py-1 text-xs"
                      disabled={page <= 1}
                      onClick={() => gotoPage(page - 1)}
                    >
                      ← Sebelumnya
                    </button>
                    <span className="px-2 font-mono">
                      {page} / {totalPages}
                    </span>
                    <button
                      type="button"
                      className="btn btn-sm px-2.5 py-1 text-xs"
                      disabled={page >= totalPages}
                      onClick={() => gotoPage(page + 1)}
                    >
                      Berikutnya →
                    </button>
                  </div>
                </div>
              ) : null}
            </>
          )}

            <div className="card mt-5 p-3">
            <div className="mb-2 text-[11px] font-semibold text-muted">
              Grup Kamera
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {groupsQuery.data?.groups.map((g) => (
                <span
                  key={g.id}
                  className="rounded-md border border-line bg-panel2 px-2 py-1 text-[10px] text-muted"
                >
                  {g.name}
                </span>
              ))}
              <input
                className="input w-40"
                placeholder="Nama grup baru..."
                value={newGroup}
                onChange={(e) => setNewGroup(e.target.value)}
              />
              <button
                type="button"
                className="btn py-1.5 text-[10px]"
                disabled={!newGroup.trim() || addGroup.isPending}
                onClick={() => addGroup.mutate(newGroup.trim())}
              >
               Tambah Grup
             </button>
           </div>
           </div>
         </div>
       )}

      {form ? (
        <CamFormModal
          form={form}
          setForm={setForm}
          groups={groupsQuery.data?.groups ?? []}
          pending={saveCam.isPending}
          onSave={() => saveCam.mutate(form)}
          onClose={() => setForm(null)}
        />
      ) : null}

      {credCam ? (
        <CredentialsModal
          camera={credCam}
          rows={credRows}
          setRows={setCredRows}
          pending={saveCreds.isPending}
          onSave={() =>
            saveCreds.mutate({ id: credCam.id, credentials: credRows })
          }
          onClose={() => setCredCam(null)}
        />
      ) : null}

      {detectCam ? (
        <DetectModal
          camera={detectCam}
          onClose={() => setDetectCam(null)}
        />
      ) : null}

      {showImport ? (
        <ImportModal
          devices={discoverQuery.data?.devices ?? []}
          loading={discoverQuery.isLoading}
          selected={importSel}
          onToggle={(apId) =>
            setImportSel((s) => {
              const next = new Set(s);
              if (next.has(apId)) next.delete(apId);
              else next.add(apId);
              return next;
            })
          }
          onSelectAll={() =>
            setImportSel(
              new Set((discoverQuery.data?.devices ?? []).map((d) => d.ap_id)),
            )
          }
          onClearAll={() => setImportSel(new Set())}
          pending={importCams.isPending}
          pendingAll={importAllCctv.isPending}
          onImport={() => importCams.mutate(Array.from(importSel))}
          onImportAll={() => importAllCctv.mutate()}
          onClose={() => setShowImport(false)}
        />
      ) : null}
    </div>
  );
}

function AdminCctvOverview({
  summary,
  offline,
  loading,
  refreshing,
  error,
  onRefresh,
}: {
  summary?: CameraSummary;
  offline: OfflineCamera[];
  loading: boolean;
  refreshing: boolean;
  error: string;
  onRefresh: () => void;
}) {
  const total = summary?.total ?? 0;
  const online = summary?.online ?? 0;
  const offlineCount = summary?.offline ?? offline.length;

  return (
    <div>
      <PageHeader
        title="Management CCTV"
        subtitle="Ringkasan status kamera CCTV."
        onRefresh={onRefresh}
        refreshing={refreshing}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted2">
            Total Kamera
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-muted">{total}</span>
            <span className="text-xs text-muted2">terdaftar</span>
          </div>
        </div>
        <div className="card border-ok/25 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted2">
            CCTV ON
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-ok">{online}</span>
            <span className="text-xs text-muted2">menyala</span>
          </div>
        </div>
        <div className="card border-bad/30 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted2">
            CCTV MATI
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-3xl font-semibold text-bad">{offlineCount}</span>
            <span className="text-xs text-muted2">mati</span>
          </div>
        </div>
      </section>

      <div className="h-4" />

      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-muted">Daftar CCTV Mati</div>
          <div className="text-[11px] text-muted2">{offline.length} kamera</div>
        </div>

        {error ? (
          <div className="py-6 text-center text-xs text-bad">{error}</div>
        ) : loading ? (
          <div className="py-6 text-center text-xs text-muted2">Memuat...</div>
        ) : offline.length === 0 ? (
          <div className="flex min-h-32 flex-col items-center justify-center gap-2 py-6 text-center">
            <Cctv size={26} className="text-ok opacity-70" />
            <div className="text-sm font-semibold text-muted">
              Semua CCTV menyala
            </div>
            <div className="text-xs text-muted2">
              Tidak ada kamera yang mati saat ini.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wide text-muted2">
                  <th className="px-2 py-2 font-semibold">No</th>
                  <th className="px-2 py-2 font-semibold">Nama</th>
                  <th className="px-2 py-2 font-semibold">IP</th>
                  <th className="px-2 py-2 font-semibold">Merk</th>
                </tr>
              </thead>
              <tbody>
                {offline.map((c, i) => (
                  <tr
                    key={c.id}
                    className="border-b border-line/60 last:border-0"
                  >
                    <td className="px-2 py-2 text-muted2">{i + 1}</td>
                    <td className="px-2 py-2 text-muted">{c.name || "-"}</td>
                    <td className="px-2 py-2 font-mono text-bad">{c.ip || "-"}</td>
                    <td className="px-2 py-2 text-muted">{c.vendor || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function PasswordGate({
  password,
  setPassword,
  error,
  pending,
  onSubmit,
}: {
  password: string;
  setPassword: (v: string) => void;
  error: string;
  pending: boolean;
  onSubmit: (pw?: string) => void;
}) {
  const saved = useAuth((s) => s.cctvGlobalPassword);
  const setSaved = useAuth((s) => s.setCctvGlobalPassword);
  const [remember, setRemember] = useState(true);
  const [autoSent, setAutoSent] = useState(false);

  // Password tersimpan basi (mis. diganti di server) → hapus agar tidak
  // dikirim berulang dan memicu rate-limit; user ketik ulang sekali.
  useEffect(() => {
    if (error) setSaved(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error]);

  // Auto-masuk: isi + submit password tersimpan tanpa ketik/klik.
  useEffect(() => {
    if (saved && !password && !autoSent && !pending && !error && remember) {
      setPassword(saved);
      setAutoSent(true);
      if (remember && saved) setSaved(saved);
      onSubmit(saved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved, password, autoSent, pending]);

  const submit = () => {
    if (remember && password) setSaved(password);
    else if (!remember) setSaved(null);
    onSubmit(password);
  };

  return (
    <div className="card mx-auto flex max-w-md flex-col items-center gap-3 p-8 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-panel2">
        <KeyRound size={22} className="text-accent" />
      </div>
      <div className="text-sm font-semibold text-muted">Verifikasi Password</div>
      <div className="text-xs text-muted2">
        Masukkan password global CCTV atau password akun panel Anda.
        Verifikasi berlaku selama Anda berada di halaman ini.
      </div>
      <input
        type="password"
        className="input w-full text-center"
        placeholder="Password"
        value={password}
        autoFocus
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && password) submit();
        }}
      />
      <label className="flex items-center gap-2 text-[11px] text-muted">
        <input
          type="checkbox"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
          className="h-4 w-4 accent-[#5ea5ff]"
        />
        Ingat password (otomatis dibaca saat masuk halaman)
      </label>
      {error ? <div className="text-[11px] text-bad">{error}</div> : null}
      <button
        type="button"
        className="btn btn-primary w-full"
        disabled={!password || pending}
        onClick={submit}
      >
        {pending ? "Memverifikasi..." : "Buka CCTV"}
      </button>
    </div>
  );
}

function CameraTile({
  camera,
  tick,
  liveAll,
  epoch,
  onEdit,
  onCreds,
  onTest,
  onDetect,
  onDelete,
}: {
  camera: Camera;
  tick: number;
  liveAll: boolean;
  epoch: number;
  onEdit: () => void;
  onCreds: () => void;
  onTest: () => void;
  onDetect: () => void;
  onDelete: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const [override, setOverride] = useState<boolean | null>(null);
  // Diagnosis presisi dari backend saat tile gagal (locked/cooldown/
  // bad_credential/no_credentials). Null = belum/tidak perlu dicek.
  const [diag, setDiag] = useState<{ reason: string; message: string; retry_in?: number } | null>(null);
  const live = override ?? liveAll;
  const [liveRetries, setLiveRetries] = useState(0);
  const [liveLoading, setLiveLoading] = useState(false);
  // lazy-load: hanya stream live saat tile masuk viewport, agar
  // tidak semua kamera langsung membuka stream sekaligus.
  // Default true agar livestream standby langsung jalan; observer akan
  // mengoreksi saat tile benar-benar di luar viewport.
  const tileRef = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(true);

  // Toggle global Live Semua / Snapshot: reset override per-tile.
  useEffect(() => {
    setOverride(null);
    setFailed(false);
  }, [liveAll]);

  // Sesi diperbarui (verifikasi/refresh): tile yang gagal ikut coba ulang
  // otomatis sekali. Tile sehat tidak disentuh (src boleh ganti et tanpa
  // remount — lihat key img di bawah).
  const [lastEpoch, setLastEpoch] = useState(epoch);
  useEffect(() => {
    if (epoch !== lastEpoch) {
      setLastEpoch(epoch);
      if (failed) {
        setFailed(false);
        setDiag(null);
        setLiveRetries(0);
        setInView(true);
        if (live) setLiveLoading(true);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [epoch]);

  useEffect(() => {
    const el = tileRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) setInView(e.isIntersecting);
      },
      { rootMargin: "200px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Safety: kalau observer tidak pernah fire (mis. tile di dalam container
  // tersembunyi), paksa mulai setelah 800ms agar tidak blank permanen.
  useEffect(() => {
    const t = setTimeout(() => setInView((v) => (v ? v : true)), 800);
    return () => clearTimeout(t);
  }, []);

  const startLive = () => {
    setOverride(true);
    setFailed(false);
    setDiag(null);
    setLiveRetries(0);
    setInView(true);
    setLiveLoading(true);
  };

  const retrySnap = () => {
    setFailed(false);
    setDiag(null);
    setLiveRetries((r) => r + 1);
    setInView(true);
  };

  const [snapEpoch, setSnapEpoch] = useState(0);

  // Auto-refresh snapshot per tile saat mode snapshot & terlihat di viewport
  useEffect(() => {
    if (live || !inView || camera.status !== "ONLINE" || failed) return;
    // Stagger interval antar kamera agar tidak serentak menembak (1800ms + (id % 5)*250ms)
    const interval = 1800 + ((camera.id % 5) * 250);
    const timer = setTimeout(() => {
      setSnapEpoch((e) => e + 1);
    }, interval);
    return () => clearTimeout(timer);
  }, [snapEpoch, live, inView, camera.status, failed, camera.id]);

  // src livestream (MJPEG) vs snapshot berkala.
  // - Live: token sesi (et) DIBEKUKAN saat URL dibuat — heartbeat yang
  //   memperbarui et tidak ikut me-reload stream yang sehat (server hanya
  //   mengecek et saat koneksi dibuka). et segar dipakai saat retry/remount.
  // - Snapshot: et selalu segar + snapEpoch sebagai cache-buster berkala.
  const liveSrc = useMemo(() => {
    if (!live || !inView) return undefined;
    const base = mediaUrl(`/cameras/${camera.id}/stream`, "cctv");
    const sep = base.includes("?") ? "&" : "?";
    return `${base}${sep}_r=${liveRetries}`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id, live, liveRetries, inView]);
  const snapSrc = useMemo(() => {
    if (live || !inView) return undefined;
    const base = mediaUrl(`/cameras/${camera.id}/snapshot`, "cctv");
    const sep = base.includes("?") ? "&" : "?";
    return `${base}${sep}_s=${snapEpoch}&_r=${liveRetries}`;
  }, [camera.id, snapEpoch, live, liveRetries, inView]);
  const src = live ? liveSrc : snapSrc;

  // Reset state ketika mode (live/snapshot) atau visibilitas berubah.
  // JANGAN masukkan `src` ke dependency — `src` berubah saat liveRetries
  // berubah dan akan membuat loop reset tak terhingga.
  useEffect(() => {
    setFailed(false);
    // Jangan reset liveRetries di sini (dipakai untuk retry berurutan).
    if (live && inView) setLiveLoading(true);
    else setLiveLoading(false);
  }, [camera.id, live, inView]);

  // Hilangkan status loading otomatis setelah 2.5 detik agar overlay "Memuat live..."
  // tidak menutupi gambar stream yang sedang berjalan lancar (MJPEG multipart di browser
  // tidak selalu menembakkan event onLoad konvensional secara berulang).
  useEffect(() => {
    if (!liveLoading) return;
    const timer = setTimeout(() => {
      setLiveLoading(false);
    }, 2500);
    return () => clearTimeout(timer);
  }, [liveLoading]);

  // Saat tile gagal: tanya backend penyebab pastinya (sekali per kegagalan)
  // agar overlay bisa tulis "kamera mengunci login" vs "password tidak cocok".
  // <img> sendiri tidak bisa membaca status HTTP — makanya lewat endpoint ini.
  useEffect(() => {
    if (!failed || camera.status !== "ONLINE") return;
    let alive = true;
    setDiag(null);
    api<{ ok: boolean; reason: string; message: string; retry_in?: number }>(
      `/cameras/${camera.id}/credential-status`,
      { elevated: "cctv" },
    )
      .then((r) => {
        if (alive && !r.ok) setDiag({ reason: r.reason, message: r.message, retry_in: r.retry_in });
      })
      .catch(() => {
        // abaikan (mis. sesi basi) — overlay generik yang tampil
      });
    return () => {
      alive = false;
    };
  }, [failed, camera.id, camera.status]);

  return (
    <div ref={tileRef} className="overflow-hidden rounded-card border border-line bg-panel">
      <div className="relative aspect-video w-full bg-black/60">
        {camera.status === "ONLINE" && src && !failed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            // Key stabil terhadap rotasi token sesi (et): stream yang sehat
            // tidak ikut remount saat heartbeat memperbarui token.
            key={`${camera.id}-${live ? "live" : "snap"}-${liveRetries}`}
            src={src}
            alt={camera.name || camera.ip}
            className="h-full w-full object-cover cursor-pointer"
            onClick={() => {
              setOverride((v) => !(v ?? liveAll));
              setFailed(false);
              setDiag(null);
              setLiveRetries(0);
            }}
            title={live ? "Sedang Live Stream (klik untuk kembali ke mode grid)" : "Klik gambar untuk Live Stream kamera ini"}
            onLoad={() => { setLiveLoading(false); }}
            onError={() => {
              if (!inView) return;
              if (live && liveRetries < 5) {
                setTimeout(() => {
                  setLiveRetries((r) => r + 1);
                }, 1000);
                return;
              }
              setFailed(true);
              setLiveLoading(false);
            }}
          />
        ) : null}
        { !src && live && camera.status === "ONLINE" && !failed ? (
          <button
            type="button"
            className="absolute inset-0 grid w-full place-items-center bg-black/40 text-center text-[11px] text-muted2 hover:bg-black/30"
            onClick={startLive}
            title="Klik untuk memulai livestream"
          >
            <div>Live view (klik untuk mulai)</div>
          </button>
        ) : null}
        { !src && !live && camera.status === "ONLINE" && !failed ? (
          <div className="absolute inset-0 grid place-items-center bg-black/40 text-center text-[11px] text-muted2">
            <div>Snapshot (menunggu tile terlihat…)</div>
          </div>
        ) : null}
        {liveLoading && live && !failed ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/40 text-center text-[11px] text-muted2">
            <div>Memuat live...</div>
          </div>
        ) : null}
        {camera.status !== "ONLINE" || failed ? (
          <div className="absolute inset-0 grid place-items-center bg-black/60 text-center text-[11px] text-muted2">
            <div className="flex flex-col items-center gap-1.5 px-3">
              <Cctv size={22} className="mx-auto mb-1 opacity-50" />
              <div>
                {camera.status !== "ONLINE"
                  ? "Tidak terhubung (cek jaringan/IP)"
                  : diag?.message
                    ? `${diag.message}${diag.reason === "locked" && diag.retry_in ? ` (tunggu ±${diag.retry_in} dtk)` : ""}`
                    : live
                      ? "Password global tidak cocok — isi kredensial kamera ini secara manual"
                      : "Snapshot gagal — isi kredensial kamera ini secara manual"}
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  className="btn btn-primary py-1 text-[10px]"
                  onClick={onCreds}
                  title="Isi username/password kamera ini secara manual"
                >
                  <KeyRound size={11} className="mr-1 inline" /> Isi manual
                </button>
                {camera.status === "ONLINE" ? (
                  <button
                    type="button"
                    className="btn py-1 text-[10px]"
                    onClick={live ? startLive : retrySnap}
                  >
                    Coba lagi
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
        <div className="absolute left-2 top-2 flex items-center gap-1.5">
          <StatusBadge status={camera.status} />
          {camera.status === "ONLINE" && !failed ? (
            <span
              className={`rounded px-1.5 py-0.5 text-[9px] font-semibold tracking-wider ${
                live
                  ? "bg-red-500/90 text-white animate-pulse shadow"
                  : "bg-black/60 text-[#5ea5ff] border border-[#5ea5ff]/40"
              }`}
            >
              {live ? "● LIVE" : "GRID"}
            </span>
          ) : null}
        </div>
      </div>
      <div className="p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-[12px] font-semibold text-muted">
              {camera.name || camera.ip}
            </div>
            <div className="truncate font-mono text-[10px] text-muted2">
              {camera.ip}
              {camera.vendor ? ` · ${camera.vendor}` : ""}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              className="icon-btn"
              title={live ? "Stop Live" : "Live View"}
              onClick={() => {
                setOverride((v) => !(v ?? liveAll));
                setFailed(false);
                setDiag(null);
                setLiveRetries(0);
              }}
            >
              {live ? <Square size={13} /> : <Play size={13} />}
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Buka halaman kamera"
              onClick={() =>
                camera.web_url &&
                window.open(camera.web_url, "_blank", "noopener")
              }
            >
              <ExternalLink size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Tes login"
              onClick={onTest}
            >
              <ShieldCheck size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Deteksi path snapshot (cari URL gambar yang cocok)"
              onClick={onDetect}
            >
              <Radar size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Kredensial"
              onClick={onCreds}
            >
              <KeyRound size={13} />
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Edit"
              onClick={onEdit}
            >
              <Pencil size={13} />
            </button>
            <button
              type="button"
              className="icon-btn text-bad"
              title="Hapus"
              onClick={onDelete}
            >
              <Trash2 size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ModalShell({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-[9999] flex items-start justify-center overflow-y-auto bg-black/60 p-4" onClick={onClose}>
      <div
        className={`card mt-10 w-full ${wide ? "max-w-2xl" : "max-w-lg"} p-4 shadow-lg`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <div className="card-title">{title}</div>
          <button type="button" className="icon-btn" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CamFormModal({
  form,
  setForm,
  groups,
  pending,
  onSave,
  onClose,
}: {
  form: CamForm;
  setForm: (f: CamForm) => void;
  groups: CameraGroup[];
  pending: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const isEdit = !!form.id;
  const set = (patch: Partial<CamForm>) => setForm({ ...form, ...patch });

  useEffect(() => {
    const v = (form.vendor || "").trim();
    const c = Number(form.channel || 1) || 1;
    if (v) {
      const snap = form.snapshot_path || defSnap(v, c);
      const strm = form.stream_path || defStream(v, c);
      if (snap !== form.snapshot_path || strm !== form.stream_path) {
        set({ snapshot_path: snap, stream_path: strm });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.vendor, form.channel]);

  return (
    <ModalShell title={isEdit ? "Edit Kamera" : "Tambah Kamera"} onClose={onClose} wide>
      <div className="grid gap-2 md:grid-cols-2">
        <label className="text-[11px] text-muted">
          Nama
          <input
            className="input mt-1 w-full"
            value={form.name}
            onChange={(e) => set({ name: e.target.value })}
          />
        </label>
        <label className="text-[11px] text-muted">
          IP / Host
          <input
            className="input mt-1 w-full"
            value={form.ip}
            onChange={(e) => set({ ip: e.target.value })}
          />
        </label>
        <label className="text-[11px] text-muted">
          Scheme
          <select
            className="input mt-1 w-full"
            value={form.scheme}
            onChange={(e) => set({ scheme: e.target.value })}
          >
            <option value="http">http</option>
            <option value="https">https</option>
          </select>
        </label>
        <label className="text-[11px] text-muted">
          Protokol
          <select
            className="input mt-1 w-full"
            value={form.protocol}
            onChange={(e) => set({ protocol: e.target.value })}
          >
            <option value="http">http (MJPEG/snapshot)</option>
            <option value="rtsp">rtsp</option>
            <option value="onvif">onvif</option>
          </select>
        </label>
        <label className="text-[11px] text-muted">
          Port Web
          <input
            type="number"
            className="input mt-1 w-full"
            value={form.port}
            onChange={(e) => set({ port: Number(e.target.value) })}
          />
        </label>
        <label className="text-[11px] text-muted">
          Port RTSP
          <input
            type="number"
            className="input mt-1 w-full"
            value={form.rtsp_port}
            onChange={(e) => set({ rtsp_port: Number(e.target.value) })}
          />
        </label>
        <label className="text-[11px] text-muted">
          Channel
          <input
            type="number"
            className="input mt-1 w-full"
            value={form.channel}
            onChange={(e) => set({ channel: Number(e.target.value) })}
          />
        </label>
        <label className="text-[11px] text-muted">
          Grup
          <select
            className="input mt-1 w-full"
            value={form.group_id ?? ""}
            onChange={(e) =>
              set({ group_id: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">Tanpa grup</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-muted">
          Merk (opsional)
          <input
            className="input mt-1 w-full"
            value={form.vendor}
            onChange={(e) => set({ vendor: e.target.value })}
          />
        </label>
        <label className="text-[11px] text-muted">
          Model (opsional)
          <input
            className="input mt-1 w-full"
            value={form.model}
            onChange={(e) => set({ model: e.target.value })}
          />
        </label>
        <label className="text-[11px] text-muted md:col-span-2">
          Snapshot path (kosongkan = otomatis per merk)
          <input
            className="input mt-1 w-full"
            placeholder="/ISAPI/Streaming/channels/101/picture"
            value={form.snapshot_path}
            onChange={(e) => set({ snapshot_path: e.target.value })}
          />
        </label>
        <label className="text-[11px] text-muted md:col-span-2">
          Stream path (kosongkan = otomatis per merk)
          <input
            className="input mt-1 w-full"
            placeholder="/Streaming/Channels/101"
            value={form.stream_path}
            onChange={(e) => set({ stream_path: e.target.value })}
          />
        </label>
      </div>

      {!isEdit ? (
        <div className="mt-3">
          <div className="mb-1.5 flex items-center justify-between">
            <div className="text-[11px] font-semibold text-muted">
              Kredensial login (dicoba berurutan)
            </div>
            <button
              type="button"
              className="btn py-1 text-[10px]"
              onClick={() =>
                set({
                  credentials: [
                    ...form.credentials,
                    { username: "", password: "" },
                  ],
                })
              }
            >
              + Baris
            </button>
          </div>
          <div className="space-y-1.5">
            {form.credentials.map((cred, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  className="input flex-1"
                  placeholder="username"
                  value={cred.username}
                  onChange={(e) => {
                    const next = [...form.credentials];
                    next[i] = { ...next[i], username: e.target.value };
                    set({ credentials: next });
                  }}
                />
                <input
                  className="input flex-1"
                  type="password"
                  placeholder="password"
                  value={cred.password}
                  onChange={(e) => {
                    const next = [...form.credentials];
                    next[i] = { ...next[i], password: e.target.value };
                    set({ credentials: next });
                  }}
                />
                <button
                  type="button"
                  className="icon-btn text-bad"
                  onClick={() =>
                    set({
                      credentials: form.credentials.filter((_, j) => j !== i),
                    })
                  }
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-line bg-panel2 px-3 py-2 text-[10px] text-muted2">
          Kredensial tidak diubah di sini. Gunakan tombol <KeyRound size={11} className="inline" /> pada tile kamera untuk mengelola username/password.
        </div>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onClose}>
          Batal
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!form.ip || pending}
          onClick={onSave}
        >
          {pending ? "Menyimpan..." : "Simpan"}
        </button>
      </div>
    </ModalShell>
  );
}

function CredentialsModal({
  camera,
  rows,
  setRows,
  pending,
  onSave,
  onClose,
}: {
  camera: Camera;
  rows: CredInput[];
  setRows: (r: CredInput[]) => void;
  pending: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  return (
    <ModalShell
      title={`Kredensial — ${camera.name || camera.ip}`}
      onClose={onClose}
    >
      <div className="mb-2 text-[11px] text-muted2">
        Panel mencoba kredensial berikut berurutan: mulai dari yang terakhir
        berhasil, lalu ke #1. Password lama harus dimasukkan ulang (tidak
        ditampilkan demi keamanan).
      </div>
      <div className="space-y-1.5">
        {rows.map((cred, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className="input flex-1"
              placeholder="username"
              value={cred.username}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...next[i], username: e.target.value };
                setRows(next);
              }}
            />
            <input
              className="input flex-1"
              type="password"
              placeholder="password"
              value={cred.password}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...next[i], password: e.target.value };
                setRows(next);
              }}
            />
            <button
              type="button"
              className="icon-btn text-bad"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn mt-2 py-1 text-[10px]"
        onClick={() => setRows([...rows, { username: "", password: "" }])}
      >
        + Baris
      </button>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onClose}>
          Batal
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={pending}
          onClick={onSave}
        >
          {pending ? "Menyimpan..." : "Simpan Kredensial"}
        </button>
      </div>
    </ModalShell>
  );
}

type SnapCandidate = { path: string; content_type: string; size: number; via: string };

function DetectModal({
  camera,
  onClose,
}: {
  camera: Camera;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [cands, setCands] = useState<SnapCandidate[] | null>(null);

  const detectMut = useMutation({
    mutationFn: () =>
      api<{ snapshot_candidates: SnapCandidate[]; tried_credentials?: number }>(
        `/cameras/${camera.id}/autodetect`,
        { method: "POST", elevated: "cctv" },
      ),
    onSuccess: (res) => {
      setCands(res.snapshot_candidates ?? []);
      if ((res.snapshot_candidates ?? []).length === 0) {
        toast.error("Tidak ada path snapshot yang cocok. Isi kredensial manual dulu atau cek merk/channel.");
      }
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Deteksi gagal"),
  });

  // Jalankan sekali saat modal dibuka.
  useEffect(() => {
    detectMut.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  const applyMut = useMutation({
    mutationFn: (path: string) =>
      api(`/cameras/${camera.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: camera.name,
          ip: camera.ip,
          port: camera.port,
          rtsp_port: camera.rtsp_port,
          scheme: camera.scheme,
          protocol: camera.protocol,
          channel: camera.channel,
          vendor: camera.vendor,
          model: camera.model,
          group_id: camera.group_id,
          snapshot_path: path,
          stream_path: camera.stream_path,
          notes: camera.notes,
          credentials: [],
        }),
        elevated: "cctv",
      }),
    onSuccess: (_, path) => {
      toast.success(`Path snapshot disimpan: ${path}`);
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      onClose();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan path"),
  });

  return (
    <ModalShell title={`Deteksi path — ${camera.name || camera.ip}`} onClose={onClose}>
      <div className="mb-2 text-[11px] text-muted2">
        Panel mencoba (kredensial global, lalu manual) × belasan URL snapshot umum.
        Pilih path yang cocok untuk dipakai kamera ini.
      </div>
      {detectMut.isPending ? (
        <div className="py-6 text-center text-[11px] text-muted2">
          Memindai path snapshot…
        </div>
      ) : detectMut.isError ? (
        <div className="rounded-lg border border-dashed border-line py-6 text-center text-[11px] text-muted2">
          Deteksi gagal dimulai. Pastikan kredensial (global/manual) benar lalu ulangi.
          <div className="mt-2">
            <button
              type="button"
              className="btn py-1 text-[10px]"
              onClick={() => { setCands(null); detectMut.mutate(); }}
            >
              Ulangi Deteksi
            </button>
          </div>
        </div>
      ) : (cands ?? []).length === 0 ? (
        <div className="rounded-lg border border-dashed border-line py-6 text-center text-[11px] text-muted2">
          Tidak ada path yang cocok. Kemungkinan: kredensial salah, kamera tanpa
          snapshot HTTP, atau channel/vendor belum tepat (cek di Edit).
        </div>
      ) : (
        <div className="max-h-72 space-y-1.5 overflow-auto">
          {(cands ?? []).map((c) => (
            <div
              key={`${c.via}:${c.path}`}
              className="flex items-center justify-between gap-2 rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px]"
            >
              <div className="min-w-0">
                <div className="truncate font-mono text-[11px] text-muted">{c.path}</div>
                <div className="text-[10px] text-muted2">
                  via {c.via === "global" ? "password global" : `manual (${c.via.replace(/^manual:/, "")})`} · {(c.size / 1024).toFixed(1)} KB
                </div>
              </div>
              <button
                type="button"
                className="btn btn-primary shrink-0 py-1 text-[10px]"
                disabled={applyMut.isPending}
                onClick={() => applyMut.mutate(c.path)}
              >
                {applyMut.isPending ? "Menyimpan…" : "Pakai"}
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onClose}>
          Tutup
        </button>
      </div>
    </ModalShell>
  );
}

function ImportModal({
  devices,
  loading,
  selected,
  onToggle,
  onSelectAll,
  onClearAll,
  pending,
  pendingAll,
  onImport,
  onImportAll,
  onClose,
}: {
  devices: DiscoverableCamera[];
  loading: boolean;
  selected: Set<number>;
  onToggle: (apId: number) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  pending: boolean;
  pendingAll: boolean;
  onImport: () => void;
  onImportAll: () => void;
  onClose: () => void;
}) {
  return (
    <ModalShell title="Impor dari Access Point" onClose={onClose} wide>
      <div className="mb-2 text-[11px] text-muted2">
        Perangkat inventori yang terdeteksi sebagai kamera (Grup CCTV / Segmen CCTV / merk kamera) dan belum terdaftar.
      </div>
      {loading ? (
        <div className="py-6 text-center text-[11px] text-muted2">Memuat...</div>
      ) : devices.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line py-6 text-center text-[11px] text-muted2">
          Tidak ada perangkat baru yang bisa diimpor
        </div>
      ) : (
        <>
          <div className="mb-2 flex items-center justify-between text-[11px]">
            <div className="text-muted2">
              Ditemukan <span className="font-semibold text-muted">{devices.length}</span> perangkat
              {selected.size > 0 ? ` · ${selected.size} dipilih` : ""}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn py-1 text-[10px]"
                onClick={onSelectAll}
              >
                Pilih Semua ({devices.length})
              </button>
              {selected.size > 0 ? (
                <button
                  type="button"
                  className="btn py-1 text-[10px]"
                  onClick={onClearAll}
                >
                  Batal Pilih
                </button>
              ) : null}
            </div>
          </div>
          <div className="max-h-72 space-y-1.5 overflow-auto">
            {devices.map((d) => (
              <label
                key={d.ap_id}
                className={`flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-[11px] ${
                  selected.has(d.ap_id)
                    ? "border-[#5ea5ff] bg-[#0d243d]"
                    : "border-line bg-panel2"
                }`}
              >
                <div>
                  <div className="font-semibold text-muted">
                    {d.model || d.vendor || d.ip}
                  </div>
                  <div className="font-mono text-[10px] text-muted2">
                    {d.ip} · {d.mac}
                    {d.segment ? ` · ${d.segment}` : ""}
                  </div>
                </div>
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[#5ea5ff]"
                  checked={selected.has(d.ap_id)}
                  onChange={() => onToggle(d.ap_id)}
                />
              </label>
            ))}
          </div>
        </>
      )}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          className="btn border-[#5ea5ff]/40 text-[#5ea5ff] hover:bg-[#0d243d]"
          disabled={pending || pendingAll}
          onClick={onImportAll}
        >
          {pendingAll ? "Mengimpor Semua…" : "Impor Semua Otomatis (Full)"}
        </button>
        <div className="flex gap-2">
          <button type="button" className="btn" onClick={onClose}>
            Batal
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={selected.size === 0 || pending || pendingAll}
            onClick={onImport}
          >
            {pending ? "Mengimpor..." : `Impor Terpilih (${selected.size || 0})`}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

function CctvDefaultModeSettings({ isSuperadmin, onDefaultModeChange }: { isSuperadmin: boolean; onDefaultModeChange?: (mode: "live" | "snapshot") => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, refetch } = useQuery({
    queryKey: ["cctv-default-mode-settings"],
    queryFn: () => api<{ mode: string }>("/settings/cctv-default-mode"),
    enabled: isSuperadmin,
  });
  const setMut = useMutation({
    mutationFn: (mode: string) =>
      api("/settings/cctv-default-mode", {
        method: "PUT",
        body: JSON.stringify({ mode }),
      }),
    onSuccess: () => {
      toast.success("Mode grid disimpan");
      refetch();
      queryClient.invalidateQueries({ queryKey: ["cctv-default-mode"] });
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Gagal menyimpan");
    },
  });
  if (!isSuperadmin) return null;
  const mode = data?.mode === "snapshot" ? "snapshot" : "live";
  const applyMode = (m: "live" | "snapshot") => {
    onDefaultModeChange?.(m);
    setMut.mutate(m);
  };
  return (
    <div className="card p-3">
      <div className="mb-2 text-[11px] font-semibold text-muted">
        Mode Grid
      </div>
      <div className="mb-2 text-[10px] text-muted2">
        Mode tampilan kamera. Pilihan langsung mengubah tampilan grid sekaligus menyimpannya sebagai default.
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={`btn py-1.5 text-[10px] ${mode === "live" ? "btn-primary" : ""}`}
          disabled={setMut.isPending}
          onClick={() => applyMode("live")}
        >
          Livestream
        </button>
        <button
          type="button"
          className={`btn py-1.5 text-[10px] ${mode === "snapshot" ? "btn-primary" : ""}`}
          disabled={setMut.isPending}
          onClick={() => applyMode("snapshot")}
        >
          Snapshot
        </button>
      </div>
    </div>
  );
}

function CctvGlobalCamCredSettings({ isSuperadmin, onSaved }: { isSuperadmin: boolean; onSaved?: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState("");
  const { data, refetch } = useQuery({
    queryKey: ["cctv-global-camcred"],
    queryFn: () => api<{ set: boolean; username?: string; corrupt?: boolean }>("/settings/cctv-camera-cred"),
    enabled: isSuperadmin,
  });
  useEffect(() => {
    if (data?.username && !username) {
      setUsername(data.username);
    }
  }, [data?.username]);
  const setMut = useMutation({
    mutationFn: (payload: { username: string; password: string }) =>
      api("/settings/cctv-camera-cred", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (_, vars) => {
      toast.success("Kredensial global kamera disimpan");
      useAuth.getState().setCctvGlobalPassword(vars.password);
      setPw("");
      setPw2("");
      setError("");
      refetch();
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      onSaved?.();
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Gagal menyimpan";
      setError(msg);
      toast.error(msg);
    },
  });
  const clearMut = useMutation({
    mutationFn: () => api("/settings/cctv-camera-cred", { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Kredensial global kamera dihapus");
      setError("");
      refetch();
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      onSaved?.();
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Gagal menghapus";
      setError(msg);
      toast.error(msg);
    },
  });
  if (!isSuperadmin) return null;
  return (
    <div className="card mt-5 p-3">
      <div className="mb-2 text-[11px] font-semibold text-muted">
        Kredensial Global Kamera (digunakan untuk semua CCTV)
      </div>
      <div className="mb-2 text-[10px] text-muted2">
        Status: {data?.set ? "Sudah diset" : "Belum diset"} {data?.username ? `· user: ${data.username}` : ""}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input w-36"
          placeholder="Username"
          value={username}
          onChange={(e) => { setUsername(e.target.value); setError(""); }}
        />
        <input
          type="password"
          className="input w-40"
          placeholder="Password"
          value={pw}
          onChange={(e) => { setPw(e.target.value); setError(""); }}
        />
        <input
          type="password"
          className="input w-40"
          placeholder="Ulangi password"
          value={pw2}
          onChange={(e) => { setPw2(e.target.value); setError(""); }}
        />
        <button
          type="button"
          className="btn btn-primary py-1.5 text-[10px]"
          disabled={!username || !pw || pw !== pw2 || setMut.isPending}
          onClick={() => setMut.mutate({ username, password: pw })}
        >
          {setMut.isPending ? "Menyimpan..." : "Simpan"}
        </button>
        {data?.set ? (
          <button
            type="button"
            className="btn py-1.5 text-[10px]"
            disabled={clearMut.isPending}
            onClick={() => clearMut.mutate()}
          >
            {clearMut.isPending ? "Menghapus..." : "Hapus"}
          </button>
        ) : null}
      </div>
      {error ? <div className="mt-2 text-[10px] text-bad">{error}</div> : null}
      {data?.corrupt ? (
        <div className="mt-2 rounded-md border border-bad/40 bg-bad/10 px-2 py-1.5 text-[10px] text-bad">
          Password tersimpan rusak (tidak bisa dibaca server) sehingga tidak berlaku untuk kamera mana pun.
          Simpan ulang username + password di atas.
        </div>
      ) : null}
      <div className="mt-2 text-[9px] text-muted2">
        Sistem akan coba kredensial ini terlebih dahulu untuk semua kamera. Jika gagal, baru coba kredensial per-kamera. Password ini juga berlaku sebagai password masuk halaman CCTV.
      </div>
    </div>
  );
}

function CctvGlobalSettingsModal({
  open,
  onClose,
  isSuperadmin,
  onDefaultModeChange,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  isSuperadmin: boolean;
  onDefaultModeChange?: (mode: "live" | "snapshot") => void;
  onSaved?: () => void;
}) {
  if (!open) return null;
  return (
    <ModalShell title="Pengaturan Global CCTV" onClose={onClose} wide>
      <div className="space-y-4">
        <CctvDefaultModeSettings isSuperadmin={isSuperadmin} onDefaultModeChange={onDefaultModeChange} />
        <CctvGlobalCamCredSettings isSuperadmin={isSuperadmin} onSaved={onSaved} />
      </div>
    </ModalShell>
  );
}
