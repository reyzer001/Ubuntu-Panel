"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, apiDownload, ApiError } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { BackupJob, BackupRun } from "@/lib/types";

const JOB_TYPES = [
  { value: "panel", label: "Panel (database + .env)" },
  { value: "directory", label: "Directory" },
  { value: "config", label: "Config" },
  { value: "mysql", label: "MySQL Dump" },
  { value: "postgres", label: "PostgreSQL Dump" },
];

const CRON_PRESETS = [
  { label: "Harian 03:00", value: "0 3 * * *" },
  { label: "Tengah malam", value: "0 0 * * *" },
  { label: "Mingguan", value: "0 3 * * 0" },
  { label: "Tiap jam", value: "0 * * * *" },
  { label: "Manual", value: "" },
];

const EMPTY_FORM = {
  name: "",
  type: "panel",
  source: "",
  destination: "/var/backups/ubuntu-panel",
  schedule: "",
  retention_days: 7,
};

function fmtTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString();
}

export default function BackupPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const jobsQuery = useQuery({
    queryKey: ["backup-jobs"],
    queryFn: () => api<{ jobs: BackupJob[] }>("/backup/jobs"),
    refetchInterval: (q) =>
      q.state.data?.jobs.some((j) => j.last_run?.status === "RUNNING")
        ? 3000
        : false,
  });
  const runsQuery = useQuery({
    queryKey: ["backup-runs"],
    queryFn: () => api<{ runs: BackupRun[] }>("/backup/runs?limit=50"),
    refetchInterval: 10_000,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["backup-jobs"] });
    queryClient.invalidateQueries({ queryKey: ["backup-runs"] });
  };
  const onErr = (err: unknown, fallback: string) =>
    toast.error(err instanceof ApiError ? err.message : fallback);

  const saveJob = useMutation({
    mutationFn: (body: typeof form) =>
      api(editId ? `/backup/jobs/${editId}` : "/backup/jobs", {
        method: editId ? "PUT" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success(editId ? "Job diperbarui" : "Job dibuat");
      setForm({ ...EMPTY_FORM });
      setShowForm(false);
      setEditId(null);
      invalidateAll();
    },
    onError: (err) => onErr(err, "Gagal menyimpan job"),
  });

  const deleteJob = useMutation({
    mutationFn: (id: number) =>
      api(`/backup/jobs/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Job dihapus");
      invalidateAll();
    },
    onError: (err) => onErr(err, "Gagal menghapus job"),
  });

  const toggleJob = useMutation({
    mutationFn: (job: BackupJob) =>
      api(`/backup/jobs/${job.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: job.name,
          type: job.type,
          source: job.source,
          destination: job.destination,
          schedule: job.schedule,
          retention_days: job.retention_days,
          enabled: !job.enabled,
        }),
      }),
    onSuccess: invalidateAll,
    onError: (err) => onErr(err, "Gagal mengubah job"),
  });

  const runJob = useMutation({
    mutationFn: (id: number) =>
      api(`/backup/jobs/${id}/run`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Backup dimulai");
      setTimeout(invalidateAll, 800);
    },
    onError: (err) => onErr(err, "Gagal menjalankan backup"),
  });

  const restoreRun = useMutation({
    mutationFn: (vars: { run: BackupRun; confirm: boolean }) =>
      api<{ restored_to: string; message: string }>(
        `/backup/runs/${vars.run.id}/restore`,
        {
          method: "POST",
          body: JSON.stringify({ confirm: vars.confirm }),
        }
      ),
    onSuccess: (res) => {
      toast.success(`${res.message} → ${res.restored_to}`);
    },
    onError: (err) => onErr(err, "Restore gagal"),
  });

  const jobs = jobsQuery.data?.jobs ?? [];
  const runs = runsQuery.data?.runs ?? [];

  const jobsSort = useTableSort(
    jobs,
    {
      name: (j) => j.name,
      type: (j) => j.type,
      source: (j) => j.source,
      schedule: (j) => j.schedule,
      retention_days: (j) => j.retention_days,
      last_run: (j) => j.last_run?.started_at ?? "",
      next_run: (j) => j.next_run ?? "",
    },
    "name"
  );

  const historySort = useTableSort(
    runs,
    {
      started_at: (r) => r.started_at ?? "",
      job_name: (r) => r.job_name,
      status: (r) => r.status,
      size_bytes: (r) => r.size_bytes,
      message: (r) => r.message,
    },
    "started_at",
    "desc"
  );

  const stats = useMemo(() => {
    const successRuns = runs.filter((r) => r.status === "SUCCESS");
    const last = runs[0] ?? null;
    const cutoff = Date.now() - 24 * 3600 * 1000;
    const runs24h = runs.filter((r) => {
      if (!r.started_at) return false;
      const t = new Date(
        r.started_at + (r.started_at.endsWith("Z") ? "" : "Z")
      ).getTime();
      return !Number.isNaN(t) && t >= cutoff;
    }).length;
    return {
      totalJobs: jobs.length,
      enabled: jobs.filter((j) => j.enabled).length,
      last,
      totalSize: successRuns.reduce((a, r) => a + r.size_bytes, 0),
      runs24h,
    };
  }, [jobs, runs]);

  const startEdit = (job: BackupJob) => {
    setEditId(job.id);
    setForm({
      name: job.name,
      type: job.type,
      source: job.source,
      destination: job.destination,
      schedule: job.schedule,
      retention_days: job.retention_days,
    });
    setShowForm(true);
  };

  const handleRestore = async (run: BackupRun) => {
    const isDb = run.file_path.endsWith(".sql.gz");
    if (
      await confirm({
        title: "Restore backup",
        message: isDb
          ? `Restore "${run.job_name}" akan MENIMPA isi database tujuan. Lanjutkan?`
          : `Extract backup "${run.job_name}" ke folder restored-<timestamp>? Data live tidak ditimpa.`,
        confirmText: "Ya, restore",
        tone: "warning",
      })
    )
      restoreRun.mutate({ run, confirm: isDb });
  };

  const submitForm = (e: React.FormEvent) => {
    e.preventDefault();
    saveJob.mutate({
      ...form,
      name: form.name.trim(),
      source: form.type === "panel" ? "" : form.source.trim(),
      schedule: form.schedule.trim(),
      retention_days: Number(form.retention_days) || 7,
    });
  };

  return (
    <>
      <PageHeader
        title="Backup"
        subtitle="Job backup terjadwal, riwayat, retensi & restore"
        onRefresh={invalidateAll}
        refreshing={jobsQuery.isLoading}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Jobs" icon={<span className="text-sm">▤</span>} value={stats.totalJobs} bottomLeft={`${stats.enabled} aktif`} />
        <StatCard
          label="Last Backup"
          icon={<span className="text-sm">⏱</span>}
          value={stats.last ? fmtTime(stats.last.started_at).split(",")[0] : "-"}
          bottomLeft={stats.last?.job_name ?? "belum ada"}
          bottomRight={
            stats.last ? <StatusBadge status={stats.last.status.toLowerCase()} /> : null
          }
          valueTone={
            stats.last
              ? stats.last.status === "SUCCESS"
                ? "positive"
                : stats.last.status === "FAILED"
                  ? "negative"
                  : undefined
              : undefined
          }
        />
        <StatCard label="Total Size" icon={<span className="text-sm">▦</span>} value={formatBytes(stats.totalSize)} bottomLeft="akumulasi arsip sukses" />
        <StatCard label="Run 24 Jam" icon={<span className="text-sm">▦</span>} value={stats.runs24h} bottomLeft="eksekusi berhasil & gagal" />
      </section>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Backup Jobs</div>
            <div className="card-subtitle">panel · directory · config · mysql · postgres</div>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => {
              if (showForm) {
                setShowForm(false);
                setEditId(null);
                setForm({ ...EMPTY_FORM });
              } else {
                setShowForm(true);
              }
            }}
          >
            {showForm ? "Tutup" : "+ New Job"}
          </button>
        </div>

        {showForm ? (
          <form className="mb-5 grid grid-cols-1 gap-2 rounded-xl border border-line bg-panel2 p-3 sm:grid-cols-2 lg:grid-cols-3" onSubmit={submitForm}>
            <label className="text-[11px] text-muted">
              Nama Job
              <input
                className="input mt-1 w-full"
                placeholder="backup-www"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            </label>
            <label className="text-[11px] text-muted">
              Tipe
              <select
                className="input mt-1 w-full"
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
              >
                {JOB_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </label>
            {form.type !== "panel" ? (
              <label className="text-[11px] text-muted">
                {form.type === "mysql" || form.type === "postgres"
                  ? "Nama Database"
                  : "Path Sumber"}
                <input
                  className="input mt-1 w-full"
                  placeholder={form.type === "directory" ? "/var/www/app" : form.type === "config" ? "/etc/nginx" : "mydb"}
                  value={form.source}
                  onChange={(e) => setForm({ ...form, source: e.target.value })}
                />
              </label>
            ) : null}
            <label className="text-[11px] text-muted">
              Folder Tujuan
              <input
                className="input mt-1 w-full"
                placeholder="/var/backups/ubuntu-panel"
                value={form.destination}
                onChange={(e) => setForm({ ...form, destination: e.target.value })}
                required
              />
            </label>
            <label className="text-[11px] text-muted">
              Jadwal Cron (kosong = manual)
              <input
                className="input mt-1 w-full"
                placeholder="0 3 * * *"
                value={form.schedule}
                onChange={(e) => setForm({ ...form, schedule: e.target.value })}
              />
              <div className="mt-1.5 flex flex-wrap gap-1">
                {CRON_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    className={`btn px-2 py-0.5 text-[10px] ${
                      form.schedule === p.value ? "btn-primary" : ""
                    }`}
                    onClick={() => setForm({ ...form, schedule: p.value })}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </label>
            <label className="text-[11px] text-muted">
              Retensi (hari)
              <input
                className="input mt-1 w-full"
                type="number"
                min={1}
                max={3650}
                value={form.retention_days}
                onChange={(e) => setForm({ ...form, retention_days: Number(e.target.value) })}
              />
            </label>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3">
              <button type="submit" className="btn btn-primary" disabled={saveJob.isPending}>
                {editId ? "Simpan Perubahan" : "Buat Job"}
              </button>
              <span className="text-[10px] text-muted2">contoh cron harian 03:00 → `0 3 * * *`</span>
            </div>
          </form>
        ) : null}

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Nama" k="name" active={jobsSort.key === "name"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Tipe" k="type" active={jobsSort.key === "type"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Sumber" k="source" active={jobsSort.key === "source"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Jadwal" k="schedule" active={jobsSort.key === "schedule"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Retensi" k="retention_days" active={jobsSort.key === "retention_days"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Run Terakhir" k="last_run" active={jobsSort.key === "last_run"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <SortTh label="Run Berikutnya" k="next_run" active={jobsSort.key === "next_run"} dir={jobsSort.dir} onToggle={jobsSort.toggle} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobsSort.sorted.map((job) => (
                <tr key={job.id}>
                  <td><strong>{job.name}</strong></td>
                  <td>{job.type}</td>
                  <td className="max-w-[220px] truncate text-muted" title={job.destination}>
                    {job.type === "panel" ? "(db + .env)" : job.source}
                  </td>
                  <td>{job.schedule || <span className="text-muted2">manual</span>}</td>
                  <td>{job.retention_days}d</td>
                  <td>
                    {job.last_run ? (
                      <div className="flex items-center gap-2">
                        <StatusBadge status={job.last_run.status.toLowerCase()} />
                        <span className="text-[10px] text-muted">{fmtTime(job.last_run.started_at)}</span>
                      </div>
                    ) : (
                      <span className="text-muted2">-</span>
                    )}
                  </td>
                  <td className="text-[11px] text-muted">{job.next_run ? fmtTime(job.next_run) : "-"}</td>
                  <td>
                    <div className="flex gap-1.5">
                      <button className="action-btn" disabled={runJob.isPending} onClick={() => runJob.mutate(job.id)}>
                        Run
                      </button>
                      <button className="action-btn" onClick={() => startEdit(job)}>Edit</button>
                      <button className="action-btn" disabled={toggleJob.isPending} onClick={() => toggleJob.mutate(job)}>
                        {job.enabled ? "Off" : "On"}
                      </button>
                      <button
                        className="action-btn text-bad"
                        disabled={deleteJob.isPending}
                        onClick={async () => {
                          if (
                            await confirm({
                              message: `Hapus job "${job.name}" beserta riwayatnya?`,
                              confirmText: "Ya, hapus",
                            })
                          )
                            deleteJob.mutate(job.id);
                        }}
                      >
                        Del
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && !jobsQuery.isLoading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-muted2">
                    Belum ada job — buat satu untuk mulai mem-backup
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Riwayat Backup</div>
            <div className="card-subtitle">50 eksekusi terakhir — unduh atau restore</div>
          </div>
        </div>
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Waktu" k="started_at" active={historySort.key === "started_at"} dir={historySort.dir} onToggle={historySort.toggle} />
                <SortTh label="Job" k="job_name" active={historySort.key === "job_name"} dir={historySort.dir} onToggle={historySort.toggle} />
                <SortTh label="Status" k="status" active={historySort.key === "status"} dir={historySort.dir} onToggle={historySort.toggle} />
                <SortTh label="Ukuran" k="size_bytes" active={historySort.key === "size_bytes"} dir={historySort.dir} onToggle={historySort.toggle} />
                <SortTh label="Catatan" k="message" active={historySort.key === "message"} dir={historySort.dir} onToggle={historySort.toggle} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {historySort.sorted.map((run) => (
                <tr key={run.id}>
                  <td className="whitespace-nowrap text-[11px]">{fmtTime(run.started_at)}</td>
                  <td><strong>{run.job_name}</strong></td>
                  <td><StatusBadge status={run.status.toLowerCase()} /></td>
                  <td>{run.size_bytes ? formatBytes(run.size_bytes) : "-"}</td>
                  <td className="max-w-[280px] truncate text-[11px] text-muted" title={run.message}>
                    {run.message}
                  </td>
                  <td>
                    {run.status === "SUCCESS" ? (
                      <div className="flex gap-1.5">
                        <button
                          className="action-btn"
                          onClick={() =>
                            apiDownload(
                              `/backup/runs/${run.id}/download`,
                              `${run.job_name}.tar.gz`
                            ).catch((err) => onErr(err, "Download gagal"))
                          }
                        >
                          Unduh
                        </button>
                        <button className="action-btn" disabled={restoreRun.isPending} onClick={() => handleRestore(run)}>
                          Restore
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-muted2">
                    Belum ada riwayat
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[10px] leading-relaxed text-muted">
          Restore arsip (<span className="font-mono">.tar.gz</span>) diekstrak ke folder{" "}
          <span className="font-mono">restored-*</span> — data live tidak ditimpa. Restore
          dump SQL (<span className="font-mono">.sql.gz</span>) <strong className="text-warn">menimpa</strong> isi database.
        </p>
      </div>
    </>
  );
}
