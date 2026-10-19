"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { api, ApiError } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { useAuth } from "@/store/auth";
import { SudoModal } from "./components/sudo-modal";
import type {
  DbCleanupResult,
  DbCleanupStatus,
  MaintenanceStatus,
  MaintenanceTask,
} from "@/lib/types";

const TASK_LABELS: Record<string, string> = {
  apt_update: "apt-get update",
  apt_upgrade: "apt-get upgrade -y",
  apt_autoremove: "apt-get autoremove -y",
};

type CleanupResult = { action: string; success: boolean; output: string };

export default function MaintenancePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const isSuperadmin = useAuth((state) => state.user?.role === "superadmin");
  const [journalDays, setJournalDays] = useState(7);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [cleanupResults, setCleanupResults] = useState<CleanupResult[]>([]);
  const [sudoFor, setSudoFor] = useState<{
    label: string;
    run: (pw: string) => Promise<unknown>;
  } | null>(null);
  const [sudoPending, setSudoPending] = useState(false);
  const [sudoError, setSudoError] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["maintenance-status"],
    queryFn: () => api<MaintenanceStatus>("/maintenance/status"),
    refetchInterval: 30_000,
  });

  const taskQuery = useQuery({
    queryKey: ["maintenance-task", taskId],
    queryFn: () => api<MaintenanceTask>(`/maintenance/tasks/${taskId}`),
    enabled: !!taskId,
    refetchInterval: (q) =>
      q.state.data?.status === "running" ? 2000 : false,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["maintenance-status"] });
    queryClient.invalidateQueries({ queryKey: ["maintenance-task"] });
  };
  const onErr = (err: unknown, fallback: string) =>
    toast.error(err instanceof ApiError ? err.message : fallback);

  const cleanup = useMutation({
    mutationFn: (body: {
      journal_days?: number;
      apt_clean?: boolean;
      sudo_password: string;
    }) =>
      api<{ results: CleanupResult[] }>("/maintenance/cleanup", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (res) => {
      setCleanupResults(res.results);
      toast.success("Cleanup selesai");
      invalidate();
    },
  });

  const startTask = useMutation({
    mutationFn: (body: { kind: string; sudo_password: string }) =>
      api<{ task_id: string; kind: string }>("/maintenance/tasks", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (res) => {
      setTaskId(res.task_id);
      toast.success(`${TASK_LABELS[res.kind] ?? res.kind} dimulai`);
    },
  });

  const reboot = useMutation({
    mutationFn: (sudo_password: string) =>
      api("/maintenance/reboot", {
        method: "POST",
        body: JSON.stringify({ confirm: true, sudo_password }),
      }),
    onSuccess: () =>
      toast.warning("Server akan reboot…", {
        description: "Semua layanan akan terputus sementara.",
        duration: 8000,
      }),
  });

  const dbCleanupQuery = useQuery({
    queryKey: ["db-cleanup-status"],
    queryFn: () => api<DbCleanupStatus>("/system/cleanup/status"),
    refetchInterval: 30_000,
  });

  const dbCleanup = useMutation({
    mutationFn: () =>
      api<DbCleanupResult>("/system/cleanup", { method: "POST" }),
    onSuccess: (res) => {
      const dels = Object.entries(res.deleted)
        .filter(([, n]) => n > 0)
        .map(([k, n]) => `${k}: ${n} baris`)
        .join(", ");
      toast.success(
        dels ? `Bersih OK — ${dels}` : "Bersih OK — tidak ada baris lama",
        { description: "Baris > ambang retensi dihapus otomatis." }
      );
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["db-cleanup-status"] });
    },
    onError: (err) => onErr(err, "Pembersihan DB gagal"),
  });

  const dc = dbCleanupQuery.data;
  const st = statusQuery.data;
  const task = taskQuery.data;
  const needsPassword = !st?.is_root;
  const busy =
    startTask.isPending || cleanup.isPending || task?.status === "running";

  const runPrivileged = (
    label: string,
    run: (pw: string) => Promise<unknown>
  ) => {
    if (!isSuperadmin) return;
    setSudoError(null);
    if (!needsPassword) {
      run("").catch((err) => onErr(err, `Gagal: ${label}`));
      return;
    }
    setSudoFor({ label, run });
  };

  const submitSudo = async (pw: string) => {
    if (!sudoFor) return;
    setSudoPending(true);
    setSudoError(null);
    try {
      await sudoFor.run(pw);
      setSudoFor(null);
    } catch (err) {
      setSudoError(
        err instanceof ApiError ? err.message : "Gagal menjalankan aksi"
      );
    } finally {
      setSudoPending(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Maintenance"
        subtitle="Cleanup log & cache, update sistem, reboot"
        onRefresh={invalidate}
        refreshing={statusQuery.isLoading}
      />

      {!isSuperadmin ? (
        <div className="card mb-4 border-[#6b5620] bg-[#241b09] text-[11px] text-[#ffd58a]">
          Hanya <b>superadmin</b> yang dapat menjalankan aksi maintenance
          (cleanup, update sistem, reboot). Anda dapat melihat status saja.
        </div>
      ) : needsPassword ? (
        <div className="card mb-4 border-[#6b5620] bg-[#241b09] text-[11px] text-[#ffd58a]">
          Setiap aksi root (cleanup, update/upgrade, autoremove, reboot) akan
          meminta password sudo lewat dialog. Masukkan password login OS user
          <code className="mx-1">{st?.os_user ?? "?"}</code>— bukan password
          panel.
        </div>
      ) : null}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Disk /"
          icon={<span className="text-sm">▤</span>}
          value={`${st?.root_disk.percent ?? "-"}%`}
          valueTone={
            st
              ? st.root_disk.percent >= 90
                ? "negative"
                : st.root_disk.percent >= 75
                  ? "warning"
                  : undefined
              : undefined
          }
          bottomLeft={st ? formatBytes(st.root_disk.used) : "-"}
          bottomRight={st ? `dari ${formatBytes(st.root_disk.total)}` : ""}
        />
        <StatCard
          label="Journald"
          icon={<span className="text-sm">≡</span>}
          value={st?.journal_bytes != null ? formatBytes(st.journal_bytes) : "?"}
          bottomLeft="ukuran log systemd"
        />
        <StatCard
          label="APT Cache"
          icon={<span className="text-sm">▦</span>}
          value={formatBytes(st?.apt_cache_bytes ?? 0)}
          bottomLeft="/var/cache/apt/archives"
        />
        <StatCard
          label="Upgradable"
          icon={<span className="text-sm">↥</span>}
          value={st?.upgradable ?? "?"}
          bottomLeft="paket menunggu update"
          valueTone={(st?.upgradable ?? 0) > 50 ? "warning" : undefined}
        />
      </section>

      <div className="h-4" />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Cleanup</div>
              <div className="card-subtitle">pangkas journal lama & cache apt</div>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-[11px] text-muted">
              Simpan journal
              <input
                className="input w-20"
                type="number"
                min={1}
                max={3650}
                value={journalDays}
                onChange={(e) => setJournalDays(Number(e.target.value))}
              />
              hari
            </label>
            <button
              className="btn btn-primary"
              disabled={cleanup.isPending || !isSuperadmin}
              onClick={() =>
                runPrivileged(`vacuum journal ${journalDays} hari`, (pw) =>
                  cleanup.mutateAsync({
                    journal_days: journalDays,
                    sudo_password: pw,
                  })
                )
              }
            >
              Vacuum Journal
            </button>
            <button
              className="btn"
              disabled={cleanup.isPending || !isSuperadmin}
              onClick={() =>
                runPrivileged("clean apt cache", (pw) =>
                  cleanup.mutateAsync({ apt_clean: true, sudo_password: pw })
                )
              }
            >
              Clean APT Cache
            </button>
            <button
              className="btn"
              disabled={busy || !isSuperadmin}
              onClick={async () => {
                if (
                  await confirm({
                    message:
                      "Jalankan apt-get autoremove -y?\nIni MENGHAPUS paket yang dianggap tidak lagi diperlukan.",
                    confirmText: "Jalankan",
                  })
                )
                  runPrivileged("apt autoremove", (pw) =>
                    startTask.mutateAsync({
                      kind: "apt_autoremove",
                      sudo_password: pw,
                    })
                  );
              }}
            >
              Autoremove Paket
            </button>
          </div>
          {cleanupResults.length ? (
            <ul className="max-h-48 space-y-1.5 overflow-auto">
              {cleanupResults.map((r) => (
                <li
                  key={r.action}
                  className="rounded-lg border border-line bg-panel2 p-2"
                >
                  <div className="flex items-center gap-2">
                    <StatusBadge status={r.success ? "success" : "failed"} />
                    <span className="font-mono text-[10px]">{r.action}</span>
                  </div>
                  {r.output ? (
                    <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words text-[10px] leading-relaxed text-muted">
                      {r.output}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Update Sistem</div>
              <div className="card-subtitle">apt update → upgrade (bisa makan waktu lama)</div>
            </div>
          </div>
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              className="btn btn-primary"
              disabled={busy || !isSuperadmin}
              onClick={() =>
                runPrivileged("apt update", (pw) =>
                  startTask.mutateAsync({ kind: "apt_update", sudo_password: pw })
                )
              }
            >
              1. apt update
            </button>
            <button
              className="btn btn-primary"
              disabled={busy || !isSuperadmin}
              onClick={async () => {
                if (
                  await confirm({
                    message:
                      "Jalankan apt-get upgrade -y?\nProses bisa berjalan beberapa menit hingga selesai.",
                    confirmText: "Jalankan",
                    tone: "primary",
                  })
                )
                  runPrivileged("apt upgrade", (pw) =>
                    startTask.mutateAsync({
                      kind: "apt_upgrade",
                      sudo_password: pw,
                    })
                  );
              }}
            >
              2. apt upgrade
            </button>
          </div>

          {taskId && task ? (
            <div>
              <div className="mb-1.5 flex items-center justify-between text-[11px]">
                <span className="font-bold">{TASK_LABELS[task.kind] ?? task.kind}</span>
                <StatusBadge status={task.status === "done" ? "success" : task.status} />
              </div>

              {task.errors?.length ? (
                <div className="mb-2 rounded-lg border border-[#5b2b2b] bg-[#2a1414] p-2.5">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold text-[#ff9b9b]">
                    <XCircle size={13} />
                    Error ({task.errors.length})
                  </div>
                  <ul className="space-y-1 text-[10.5px] leading-relaxed text-[#ffb4b4]">
                    {task.errors.map((e, i) => (
                      <li key={i} className="break-words font-mono">
                        • {e}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {task.warnings?.length ? (
                <div className="mb-2 rounded-lg border border-[#6b5620] bg-[#241b09] p-2.5">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold text-[#ffd58a]">
                    <AlertTriangle size={13} />
                    Peringatan ({task.warnings.length})
                  </div>
                  <ul className="space-y-1 text-[10.5px] leading-relaxed text-[#e6c98a]">
                    {task.warnings.map((w, i) => (
                      <li key={i} className="break-words font-mono">
                        • {w}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {task.status === "done" && !task.errors?.length ? (
                <div className="mb-2 flex items-center gap-1.5 rounded-lg border border-[#2b5b3a] bg-[#14261a] p-2.5 text-[11px] text-[#9be0b0]">
                  <CheckCircle2 size={13} />
                  Selesai tanpa error.
                </div>
              ) : null}

              <details className="rounded-lg border border-line bg-panel2">
                <summary className="cursor-pointer select-none px-3 py-2 text-[11px] text-muted">
                  Output lengkap ({task.output.length} baris)
                </summary>
                <pre className="max-h-64 overflow-auto border-t border-line p-3 text-[10px] leading-relaxed text-muted">
                  {task.output.join("\n") || "menunggu output…"}
                </pre>
              </details>
            </div>
          ) : null}
        </div>
      </div>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Auto-cleanup Database</div>
            <div className="card-subtitle">
              hapus baris log lama otomatis supaya DB PostgreSQL tidak membengkak (jalur /system/cleanup)
            </div>
          </div>
          <button
            className="btn"
            disabled={dbCleanup.isPending}
            onClick={() => dbCleanup.mutate()}
          >
            {dbCleanup.isPending ? "Membersihkan…" : "Bersihkan Sekarang"}
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="text-muted">
                <th className="pb-2 pr-4">Tabel</th>
                <th className="pb-2 pr-4">Baris tersimpan</th>
                <th className="pb-2 pr-4">Retensi</th>
                <th className="pb-2">Keterangan</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line">
                <td className="py-2 pr-4 font-bold">Audit Log</td>
                <td className="py-2 pr-4">{dc?.rows.audit_logs?.toLocaleString() ?? "…"}</td>
                <td className="py-2 pr-4">{dc?.retention_days.audit_logs ?? "…"} hari</td>
                <td className="py-2 text-muted">riwayat aksi pengguna panel</td>
              </tr>
              <tr className="border-t border-line">
                <td className="py-2 pr-4 font-bold">AP Event</td>
                <td className="py-2 pr-4">{dc?.rows.ap_events?.toLocaleString() ?? "…"}</td>
                <td className="py-2 pr-4">{dc?.retention_days.ap_events ?? "…"} hari</td>
                <td className="py-2 text-muted">peristiwa scan access point</td>
              </tr>
              <tr className="border-t border-line">
                <td className="py-2 pr-4 font-bold">Backup Run</td>
                <td className="py-2 pr-4">{dc?.rows.backup_runs?.toLocaleString() ?? "…"}</td>
                <td className="py-2 pr-4">
                  {dc?.retention_days.backup_runs != null && dc.retention_days.backup_runs > 0
                    ? `${dc.retention_days.backup_runs} hari`
                    : "mati"}
                </td>
                <td className="py-2 text-muted">riwayat run yang sudah selesai</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[10px] text-muted">
          Berjalan otomatis setiap{" "}
          {dc
            ? (dc.interval_seconds / 3600).toLocaleString("id")
            : "…"}{" "}
          jam sekali & saat panel start. Atur lewat var env{" "}
          <code className="text-[#ffd58a]">
            CLEANUP_AUDIT_DAYS / CLEANUP_APEVENT_DAYS / CLEANUP_BACKUP_RUNS_DAYS
          </code>
          .
        </div>
      </div>

      <div className="h-4" />

      <div className="card border-[#6b5620]">
        <div className="card-header">
          <div>
            <div className="card-title">Reboot Server</div>
            <div className="card-subtitle">
              panel dan semua layanan akan mati sementara — pastikan tidak ada backup yang sedang berjalan
            </div>
          </div>
          <button
            className="btn btn-danger"
            disabled={reboot.isPending || !isSuperadmin}
            onClick={async () => {
              if (
                await confirm({
                  message: "REBOOT server sekarang? Semua layanan akan terputus.",
                  confirmText: "Ya, reboot sekarang",
                })
              )
                runPrivileged("reboot server", (pw) => reboot.mutateAsync(pw));
            }}
          >
            Reboot Sekarang
          </button>
        </div>
      </div>

      {sudoFor ? (
        <SudoModal
          label={sudoFor.label}
          osUser={st?.os_user}
          pending={sudoPending}
          error={sudoError}
          onSubmit={submitSudo}
          onClose={() => {
            setSudoFor(null);
            setSudoError(null);
          }}
        />
      ) : null}
    </>
  );
}
