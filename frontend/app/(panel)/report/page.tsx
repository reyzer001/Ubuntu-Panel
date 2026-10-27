"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  Cctv,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Cpu,
  Download,
  Gauge,
  FileSpreadsheet,
  FileText,
  Mail,
  MemoryStick,
  Monitor,
  PlugZap,
  RotateCcw,
  Send,
  Settings2,
  TrendingDown,
  TrendingUp,
  Wifi,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { api, apiDownload, ApiError } from "@/lib/api";
import { formatBytes, formatRate } from "@/lib/format";
import type {
  ReportCameraProblem,
  ReportComputerRow,
  ReportData,
  ReportDates,
  ReportDowntime,
  ReportMetricStat,
  ReportSettings,
  ReportSpeedComputer,
  SmtpTestResult,
} from "@/lib/types";
import { useAuth } from "@/store/auth";
import { EmailSettingsModal } from "./components/email-settings-modal";
import clsx from "clsx";

const HOURS = 24;

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("id-ID", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeOnly(d: Date): string {
  return d.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dateOnly(d: Date): string {
  return d.toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "2-digit",
  });
}

function fmtDateDay(value: string): string {
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("id-ID", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function todayKey(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function fmtRange(item: ReportDowntime): string {
  if (!item.start) return "—";
  const start = new Date(item.start);
  if (Number.isNaN(start.getTime())) return "—";
  if (item.ongoing || !item.end) {
    return `${dateOnly(start)} ${timeOnly(start)} – sekarang`;
  }
  const end = new Date(item.end);
  if (Number.isNaN(end.getTime())) {
    return `${dateOnly(start)} ${timeOnly(start)}`;
  }
  if (start.toDateString() === end.toDateString()) {
    return `${timeOnly(start)} – ${timeOnly(end)}`;
  }
  return `${dateOnly(start)} ${timeOnly(start)} – ${dateOnly(end)} ${timeOnly(end)}`;
}

function fmtDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}h ${hours}j ${minutes}m`;
  if (hours > 0) return `${hours}j ${minutes}m`;
  return `${minutes}m`;
}

function statValue(
  stat: ReportMetricStat | undefined,
  key: "avg" | "min" | "max",
  format: (value: number) => string
): string {
  const value = stat?.[key];
  return value === null || value === undefined ? "—" : format(value);
}

function statRange(
  stat: ReportMetricStat | undefined,
  format: (value: number) => string
): string {
  if (stat?.min === null || stat?.min === undefined) return "—";
  if (stat?.max === null || stat?.max === undefined) return "—";
  return `${format(stat.min)} – ${format(stat.max)}`;
}

function ProblemRow({ problem }: { problem: ReportCameraProblem }) {
  return (
    <tr>
      <td className="min-w-[150px]">
        <div className="text-[11px] font-semibold">
          {problem.name || "Tanpa nama"}
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-muted2">
          {problem.ip || "—"}
        </div>
      </td>
      <td>
        <StatusBadge status={problem.status?.toLowerCase() || "offline"} />
      </td>
      <td className="min-w-[170px] whitespace-normal py-2.5 leading-5 text-muted">
        {problem.downtime.map((item, index) => (
          <div key={`${item.start}-${index}`}>{fmtRange(item)}</div>
        ))}
      </td>
      <td className="whitespace-nowrap text-[11px] font-semibold text-warn">
        {fmtDuration(problem.total_downtime_seconds)}
      </td>
    </tr>
  );
}

function UsageBar({
  label,
  avg,
  max,
}: {
  label: string;
  avg: number;
  max: number;
}) {
  const value = Math.max(0, Math.min(avg, 100));
  const tone = avg >= 80 ? "bg-bad" : avg >= 60 ? "bg-warn" : "bg-ok";
  return (
    <div className="min-w-[118px]">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[9px] font-semibold uppercase tracking-wide text-muted2">
          {label}
        </span>
        <span className="text-[11px] font-semibold">{avg.toFixed(1)}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-panel3">
        <div
          className={clsx("h-full rounded-full", tone)}
          style={{ width: `${value}%` }}
        />
      </div>
      <div className="mt-0.5 text-[9px] text-muted2">
        puncak {max.toFixed(1)}%
      </div>
    </div>
  );
}

function ComputerRow({
  computer,
  rank,
}: {
  computer: ReportComputerRow;
  rank: number;
}) {
  return (
    <tr>
      <td className="w-8">
        <span
          className={clsx(
            "grid h-6 w-6 place-items-center rounded-full border text-[10px] font-bold",
            rank === 1
              ? "border-[#73520d] bg-[#241b09] text-warn"
              : "border-line bg-panel2 text-muted"
          )}
        >
          {rank}
        </span>
      </td>
      <td className="min-w-[160px]">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-semibold">
            {computer.name || computer.hostname || "Tanpa nama"}
          </span>
          <StatusBadge status={computer.status} />
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-muted2">
          {computer.ip || "—"}
          {computer.group_name ? ` · ${computer.group_name}` : ""}
        </div>
      </td>
      <td>
        <UsageBar label="CPU" avg={computer.cpu_avg} max={computer.cpu_max} />
      </td>
      <td>
        <UsageBar label="RAM" avg={computer.ram_avg} max={computer.ram_max} />
      </td>
    </tr>
  );
}

function fmtMbps(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return `${value.toFixed(2)} Mbps`;
}

function SpeedRankRow({
  computer,
  rank,
}: {
  computer: ReportSpeedComputer;
  rank: number;
}) {
  return (
    <tr>
      <td className="w-8">
        <span
          className={clsx(
            "grid h-6 w-6 place-items-center rounded-full border text-[10px] font-bold",
            rank === 1
              ? "border-[#73520d] bg-[#241b09] text-warn"
              : "border-line bg-panel2 text-muted"
          )}
        >
          {rank}
        </span>
      </td>
      <td className="min-w-[150px]">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-semibold">
            {computer.name || computer.hostname || "Tanpa nama"}
          </span>
          <StatusBadge status={computer.status} />
        </div>
        <div className="mt-0.5 font-mono text-[10px] text-muted2">
          {computer.ip || "—"}
          {computer.group_name ? ` · ${computer.group_name}` : ""}
        </div>
      </td>
      <td className="whitespace-nowrap text-[10px] text-muted">
        {computer.server_reach || computer.conn_type || "—"}
      </td>
      <td className="whitespace-nowrap text-right text-[11px] font-semibold text-[#5ea5ff]">
        {fmtMbps(computer.avg_download_mbps)}
      </td>
      <td className="whitespace-nowrap text-right text-[11px] text-muted">
        {fmtMbps(computer.avg_upload_mbps)}
      </td>
      <td className="whitespace-nowrap text-right text-[11px] font-semibold">
        {fmtMbps(computer.score)}
      </td>
      <td className="whitespace-nowrap text-right text-[10px] text-muted2">
        {computer.samples}
        <div>{fmtDateTime(computer.last_tested_at)}</div>
      </td>
    </tr>
  );
}

function SpeedRankTable({
  title,
  subtitle,
  rows,
  tone,
}: {
  title: string;
  subtitle: string;
  rows: ReportSpeedComputer[];
  tone: "fast" | "slow";
}) {
  const Icon = tone === "fast" ? TrendingUp : TrendingDown;
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title flex items-center gap-1.5">
            <Icon
              size={14}
              className={tone === "fast" ? "text-ok" : "text-warn"}
            />
            {title}
          </div>
          <div className="card-subtitle">{subtitle}</div>
        </div>
      </div>
      {rows.length > 0 ? (
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Komputer</th>
                <th>Jalur</th>
                <th className="text-right">Download</th>
                <th className="text-right">Upload</th>
                <th className="text-right">Skor</th>
                <th className="text-right">Sampel</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((computer, index) => (
                <SpeedRankRow
                  key={`${tone}-${computer.id ?? computer.name}`}
                  computer={computer}
                  rank={index + 1}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-line bg-panel2 px-3 py-4 text-[11px] text-muted2">
          Belum ada data speed test pada periode ini.
        </div>
      )}
    </div>
  );
}

function SpeedLimitBar({
  label,
  peak,
  limit,
  pct,
}: {
  label: string;
  peak: number | null;
  limit: number | null;
  pct: number | null;
}) {
  const width = Math.max(0, Math.min(pct ?? 0, 100));
  const tone =
    pct === null
      ? "bg-muted2"
      : pct >= 100
        ? "bg-bad"
        : pct >= 90
          ? "bg-warn"
          : "bg-ok";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted2">
          {label}
        </span>
        <span className="text-[11px] font-semibold">
          {pct === null ? "—" : `${pct.toFixed(1)}%`}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-panel3">
        <div
          className={clsx("h-full rounded-full", tone)}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="mt-1 text-[10px] text-muted2">
        Puncak {fmtMbps(peak)} · batas {fmtMbps(limit)}
      </div>
    </div>
  );
}

export default function ReportPage() {
  const toast = useToast();
  const { confirm } = useConfirm();
  const queryClient = useQueryClient();
  const isSuperadmin = useAuth((s) => s.user?.role === "superadmin");

  const [emailMenuOpen, setEmailMenuOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsKey, setSettingsKey] = useState(0);

  const reportQuery = useQuery({
    queryKey: ["report", HOURS],
    queryFn: () => api<ReportData>(`/report?hours=${HOURS}`),
    refetchInterval: 60_000,
  });

  const datesQuery = useQuery({
    queryKey: ["report-dates"],
    queryFn: () => api<ReportDates>("/report/dates?days=30"),
    refetchInterval: 300_000,
  });

  const settingsQuery = useQuery({
    queryKey: ["report-settings"],
    queryFn: () => api<ReportSettings>("/report/settings"),
    enabled: isSuperadmin,
  });

  const sendNow = useMutation({
    mutationFn: () =>
      api<{ recipients: string[] }>("/report/send", { method: "POST" }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["report-settings"] });
      toast.success(
        `Email report terkirim ke ${res.recipients.length} penerima`
      );
    },
    onError: (err) =>
      toast.error(
        err instanceof ApiError ? err.message : "Gagal mengirim email report"
      ),
  });

  const testSmtp = useMutation({
    mutationFn: () =>
      api<SmtpTestResult>("/report/smtp/test", {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (res) =>
      toast.success(res.message || "Koneksi SMTP berhasil"),
    onError: (err) =>
      toast.error(
        err instanceof ApiError ? err.message : "Gagal menguji koneksi SMTP"
      ),
  });

  const resetSamples = useMutation({
    mutationFn: () =>
      api<{
        computer_metric_samples: number;
        computer_metric_hourly: number;
        computer_speed_samples: number;
        reset_at: string;
      }>("/report/reset", { method: "POST" }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["report", HOURS] });
      queryClient.invalidateQueries({ queryKey: ["report-dates"] });
      toast.success(
        `Data PC direset: ${res.computer_metric_samples} sampel metrik, ` +
          `${res.computer_metric_hourly} rekap jam, ` +
          `${res.computer_speed_samples} sampel speed test`
      );
    },
    onError: (err) =>
      toast.error(
        err instanceof ApiError ? err.message : "Gagal mereset data jaringan"
      ),
  });

  const data = reportQuery.data;
  const dateRows = datesQuery.data?.dates ?? [];
  const retention = datesQuery.data?.retention;
  const computers = data?.computers;
  const cctv = data?.cctv;
  const speed = data?.speed;
  const isp = speed?.isp;
  const ispStatus = isp?.status ?? "unset";
  const ispLabel =
    ispStatus === "over"
      ? "Melewati batas"
      : ispStatus === "near"
        ? "Mendekati batas"
        : ispStatus === "safe"
          ? "Aman"
          : "Belum diatur";
  const ispTone =
    ispStatus === "over"
      ? "text-bad"
      : ispStatus === "near"
        ? "text-warn"
        : ispStatus === "safe"
          ? "text-ok"
          : "text-muted2";
  const settings = settingsQuery.data;
  const canSend =
    !!settings &&
    !!settings.smtp_host.trim() &&
    settings.recipients.length > 0;

  const openSettings = () => {
    setEmailMenuOpen(false);
    setSettingsKey((key) => key + 1);
    setSettingsOpen(true);
    if (!settings || settingsQuery.isError) {
      void settingsQuery.refetch();
    }
  };

  const stats = useMemo(
    () => ({
      cpu: computers?.cpu.avg ?? null,
      ram: computers?.ram.avg ?? null,
      rx: computers?.net.rx_total_bytes ?? 0,
      tx: computers?.net.tx_total_bytes ?? 0,
      rxRate: computers?.net.rx_avg_rate ?? 0,
      txRate: computers?.net.tx_avg_rate ?? 0,
      total: cctv?.total ?? 0,
      normal: cctv?.normal ?? 0,
      problem: cctv?.problem_count ?? 0,
    }),
    [computers, cctv]
  );

  const chartData = useMemo(
    () =>
      (computers?.series ?? []).map((point) => {
        const date = point.t ? new Date(point.t) : null;
        return {
          label:
            date && !Number.isNaN(date.getTime()) ? timeOnly(date) : "—",
          cpu: point.cpu,
          ram: point.ram,
        };
      }),
    [computers?.series]
  );

  const metricRows: Array<{
    label: string;
    stat?: ReportMetricStat;
    format: (value: number) => string;
  }> = [
    {
      label: "CPU rata-rata PC",
      stat: computers?.cpu,
      format: (v) => `${v.toFixed(1)}%`,
    },
    {
      label: "RAM rata-rata PC",
      stat: computers?.ram,
      format: (v) => `${v.toFixed(1)}%`,
    },
    {
      label: "Download",
      stat: {
        avg: computers?.net.rx_avg_rate ?? null,
        min: null,
        max: null,
      },
      format: (v) => formatRate(v),
    },
    {
      label: "Upload",
      stat: {
        avg: computers?.net.tx_avg_rate ?? null,
        min: null,
        max: null,
      },
      format: (v) => formatRate(v),
    },
  ];

  const download = async (kind: "pdf" | "csv") => {
    try {
      await apiDownload(
        `/report/export.${kind}?hours=${HOURS}`,
        `report.${kind}`
      );
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengunduh");
    }
  };

  const handleReset = async () => {
    if (
      await confirm({
        title: "Reset data jaringan",
        message:
          "Hapus permanen seluruh histori CPU/RAM/trafik internet PC dan " +
          "speed test PC? Data server (dashboard) tidak terpengaruh. " +
          "Tindakan ini tidak bisa dibatalkan.",
        confirmText: "Hapus data",
        tone: "danger",
      })
    ) {
      resetSamples.mutate();
    }
  };

  const handleSend = async () => {
    if (!canSend) {
      toast.warning("Atur pengirim dan penerima email terlebih dahulu");
      openSettings();
      return;
    }
    if (
      await confirm({
        title: "Kirim report sekarang",
        message:
          "Report akan dibuat dan dikirim ke semua penerima email yang terdaftar.",
        confirmText: "Kirim",
      })
    )
      sendNow.mutate();
  };

  return (
    <>
      <PageHeader
        title="Report"
        subtitle="Beban komputer, trafik internet, speedtest, dan kondisi CCTV"
        onRefresh={() => {
          void reportQuery.refetch();
          void datesQuery.refetch();
        }}
        refreshing={reportQuery.isFetching || datesQuery.isFetching}
        right={
          <>
            {isSuperadmin ? (
              <div className="relative">
                <button
                  className="btn flex items-center gap-2"
                  onClick={() => setEmailMenuOpen((open) => !open)}
                  aria-haspopup="menu"
                  aria-expanded={emailMenuOpen}
                >
                  <Mail size={13} /> Email
                  <ChevronDown
                    size={12}
                    className={clsx(
                      "transition-transform",
                      emailMenuOpen && "rotate-180"
                    )}
                  />
                </button>

                {emailMenuOpen ? (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setEmailMenuOpen(false)}
                    />
                    <div
                      role="menu"
                      className="absolute right-0 z-50 mt-1 w-56 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
                    >
                      <button
                        className="menu-item"
                        role="menuitem"
                        disabled={sendNow.isPending}
                        onClick={() => {
                          setEmailMenuOpen(false);
                          void handleSend();
                        }}
                      >
                        <Send size={13} /> Kirim Report
                      </button>
                      <button
                        className="menu-item"
                        role="menuitem"
                        onClick={openSettings}
                      >
                        <Settings2 size={13} /> Pengaturan SMTP
                      </button>
                      <button
                        className="menu-item"
                        role="menuitem"
                        disabled={
                          testSmtp.isPending || !settings?.smtp_host.trim()
                        }
                        onClick={() => {
                          setEmailMenuOpen(false);
                          testSmtp.mutate();
                        }}
                      >
                        <PlugZap size={13} />
                        {testSmtp.isPending
                          ? "Menguji Koneksi…"
                          : "Cek Koneksi SMTP"}
                      </button>
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}

            {isSuperadmin ? (
              <button
                className="btn flex items-center gap-2"
                disabled={resetSamples.isPending}
                onClick={() => void handleReset()}
                title="Hapus histori metrik, trafik, dan speed test PC"
              >
                <RotateCcw
                  size={13}
                  className={resetSamples.isPending ? "animate-spin" : ""}
                />
                {resetSamples.isPending ? "Reset…" : "Reset Data"}
              </button>
            ) : null}

            <div className="relative">
              <button
                className="btn flex items-center gap-2"
                onClick={() => setExportOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={exportOpen}
              >
                <Download size={13} /> Download
                <ChevronDown
                  size={12}
                  className={clsx(
                    "transition-transform",
                    exportOpen && "rotate-180"
                  )}
                />
              </button>

              {exportOpen ? (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setExportOpen(false)}
                  />
                  <div
                    role="menu"
                    className="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
                  >
                    <button
                      className="menu-item"
                      role="menuitem"
                      onClick={() => {
                        setExportOpen(false);
                        download("pdf");
                      }}
                    >
                      <FileText size={13} /> PDF
                    </button>
                    <button
                      className="menu-item"
                      role="menuitem"
                      onClick={() => {
                        setExportOpen(false);
                        download("csv");
                      }}
                    >
                      <FileSpreadsheet size={13} /> CSV
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          </>
        }
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Rata-rata CPU PC"
          icon={<Cpu size={15} />}
          value={
            stats.cpu === null ? "—" : `${stats.cpu.toFixed(1)}%`
          }
          bottomLeft={
            computers
              ? `${computers.with_data}/${computers.total} PC`
              : "Memuat…"
          }
          bottomRight={statRange(computers?.cpu, (v) => `${v.toFixed(1)}%`)}
        />
        <StatCard
          label="Rata-rata RAM PC"
          icon={<MemoryStick size={15} />}
          value={
            stats.ram === null ? "—" : `${stats.ram.toFixed(1)}%`
          }
          bottomLeft="Pemakaian memori PC"
          bottomRight={statRange(computers?.ram, (v) => `${v.toFixed(1)}%`)}
        />
        <StatCard
          label="Trafik Internet PC 24 Jam"
          icon={<Wifi size={15} />}
          value={formatBytes(stats.rx)}
          bottomLeft={`TX ${formatBytes(stats.tx)}`}
          bottomRight={`Rata-rata ${formatRate(stats.rxRate)}`}
        />
        <StatCard
          label="CCTV"
          icon={<Cctv size={15} />}
          value={`${stats.normal} / ${stats.total}`}
          bottomLeft={`${stats.problem} bermasalah`}
          bottomRight={cctv ? `${cctv.offline_now} offline` : "Memuat…"}
          valueTone={stats.problem > 0 ? "warning" : "positive"}
        />
      </section>

      <section className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title flex items-center gap-1.5">
                <Gauge size={14} className="text-[#5ea5ff]" />
                Speedtest Internet 24 Jam
              </div>
              <div className="card-subtitle">
                Rata-rata speed test PC → internet publik
              </div>
            </div>
          </div>
          <div className="p-3">
            <div className="text-[22px] font-bold leading-none">
              {fmtMbps(speed?.avg_score_mbps)}
            </div>
            <div className="mt-1 text-[10px] text-muted2">
              Skor gabungan download + upload
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-line bg-panel2 px-2.5 py-2">
                <div className="text-[9px] uppercase tracking-wide text-muted2">
                  Download
                </div>
                <div className="mt-0.5 text-[12px] font-semibold text-[#5ea5ff]">
                  {fmtMbps(speed?.avg_download_mbps)}
                </div>
              </div>
              <div className="rounded-lg border border-line bg-panel2 px-2.5 py-2">
                <div className="text-[9px] uppercase tracking-wide text-muted2">
                  Upload
                </div>
                <div className="mt-0.5 text-[12px] font-semibold text-muted">
                  {fmtMbps(speed?.avg_upload_mbps)}
                </div>
              </div>
            </div>
            <div className="mt-3 text-[10px] text-muted2">
              {speed?.sample_count ?? 0} sampel ·{" "}
              {speed?.computers_with_data ?? 0}/{speed?.total ?? 0} PC
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title flex items-center gap-1.5">
                <Wifi size={14} className="text-muted2" /> Batas ISP
              </div>
              <div className="card-subtitle">
                Perbandingan puncak speed test dengan batas ISP
              </div>
            </div>
            <span className={clsx("text-[11px] font-semibold", ispTone)}>
              {ispLabel}
            </span>
          </div>
          <div className="p-3">
            {ispStatus === "unset" ? (
              <div className="mb-3 rounded-lg border border-line bg-panel2 px-2.5 py-2 text-[10px] text-muted2">
                Batas ISP belum diatur. Isi di Pengaturan Report agar status
                utilisasi bisa dihitung.
              </div>
            ) : null}
            <div className="space-y-3">
              <SpeedLimitBar
                label="Download"
                peak={isp?.peak_download_mbps ?? null}
                limit={isp?.download_mbps ?? null}
                pct={isp?.utilization_download_pct ?? null}
              />
              <SpeedLimitBar
                label="Upload"
                peak={isp?.peak_upload_mbps ?? null}
                limit={isp?.upload_mbps ?? null}
                pct={isp?.utilization_upload_pct ?? null}
              />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title flex items-center gap-1.5">
                <TrendingUp size={14} className="text-warn" /> Rekor Bandwidth
                24 Jam
              </div>
              <div className="card-subtitle">
                Nilai ekstrem dari seluruh sampel speed test
              </div>
            </div>
          </div>
          <div className="space-y-2 p-3">
            {speed?.peak ? (
              <div className="rounded-lg border border-[#1c6636] bg-[#102118] px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-ok">
                    Tertinggi
                  </span>
                  <span className="text-[10px] text-muted2">
                    {fmtDateTime(
                      speed.peak.received_at || speed.peak.tested_at
                    )}
                  </span>
                </div>
                <div className="mt-1 text-[11px] font-semibold">
                  {speed.peak.name || "Tanpa nama"}
                </div>
                <div className="mt-0.5 text-[10px] text-muted">
                  D {fmtMbps(speed.peak.download_mbps)} · U{" "}
                  {fmtMbps(speed.peak.upload_mbps)}
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-line bg-panel2 px-2.5 py-2 text-[10px] text-muted2">
                Belum ada sampel.
              </div>
            )}
            {speed?.lowest ? (
              <div className="rounded-lg border border-[#73520d] bg-[#241b09] px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-warn">
                    Terendah
                  </span>
                  <span className="text-[10px] text-muted2">
                    {fmtDateTime(
                      speed.lowest.received_at || speed.lowest.tested_at
                    )}
                  </span>
                </div>
                <div className="mt-1 text-[11px] font-semibold">
                  {speed.lowest.name || "Tanpa nama"}
                </div>
                <div className="mt-0.5 text-[10px] text-muted">
                  D {fmtMbps(speed.lowest.download_mbps)} · U{" "}
                  {fmtMbps(speed.lowest.upload_mbps)}
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-line bg-panel2 px-2.5 py-2 text-[10px] text-muted2">
                Belum ada sampel.
              </div>
            )}
            <div className="text-[9px] leading-4 text-muted2">
              Speed test mengukur koneksi internet PC, bukan jalur ke server.
            </div>
          </div>
        </div>
      </section>

      <section className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SpeedRankTable
          title="5 PC Tercepat"
          subtitle="Rata-rata 24 jam berdasarkan skor gabungan download + upload"
          rows={speed?.top_fastest ?? []}
          tone="fast"
        />
        <SpeedRankTable
          title="5 PC Paling Lambat"
          subtitle="Rata-rata 24 jam berdasarkan skor gabungan download + upload"
          rows={speed?.top_slowest ?? []}
          tone="slow"
        />
      </section>

      {data ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-line bg-panel px-3 py-2 text-[11px] text-muted">
          <span className="flex items-center gap-1.5">
            <Monitor size={12} className="text-muted2" />
            {computers?.online ?? 0}/{computers?.total ?? 0} PC online
          </span>
          <span className="hidden h-3 w-px bg-line sm:block" />
          <span className="flex items-center gap-1.5">
            <Clock3 size={12} className="text-muted2" />
            {fmtDateTime(data.window_start)} – {fmtDateTime(data.window_end)}
          </span>
          <span className="hidden h-3 w-px bg-line sm:block" />
          <span>{computers?.sample_count ?? 0} sampel PC</span>
          <span className="hidden h-3 w-px bg-line sm:block" />
          <span>Diperbarui {fmtDateTime(data.generated_at)}</span>
        </div>
      ) : null}

      <div className="card mt-4">
        <div className="card-header">
          <div>
            <div className="card-title">Tanggal Tersedia</div>
            <div className="card-subtitle">
              Riwayat metrik PC yang masih disimpan · sampel mentah{" "}
              {retention?.raw_hours ?? 48} jam, rekap per jam{" "}
              {retention?.rollup_days ?? 30} hari
            </div>
          </div>
          <span className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-[10px] text-muted2">
            {dateRows.length} tanggal ·{" "}
            {datesQuery.data?.timezone ?? "WIB (UTC+7)"}
          </span>
        </div>

        {datesQuery.isLoading ? (
          <div className="px-3 py-4 text-[11px] text-muted2">
            Memuat tanggal…
          </div>
        ) : dateRows.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg border border-line bg-panel2 px-3 py-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted">
              <CalendarDays size={16} />
            </div>
            <div>
              <div className="text-[11px] text-muted">
                Belum ada histori tanggal.
              </div>
              <div className="mt-0.5 text-[10px] text-muted2">
                Data akan muncul setelah heartbeat agent mengirim metrik.
              </div>
            </div>
          </div>
        ) : (
          <div className="table-wrap overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>Tanggal</th>
                  <th>PC</th>
                  <th>Sampel Mentah</th>
                  <th>Rekap/Jam</th>
                  <th>Speed Test</th>
                  <th>Cakupan</th>
                  <th>Sumber</th>
                </tr>
              </thead>
              <tbody>
                {dateRows.map((row) => {
                  const isToday = row.date === todayKey();
                  return (
                    <tr
                      key={row.date}
                      className={isToday ? "bg-panel2/50" : undefined}
                    >
                      <td className="whitespace-nowrap">
                        <span className="flex items-center gap-2 text-[12px] font-semibold">
                          <CalendarDays
                            size={12}
                            className="text-muted2"
                          />
                          {fmtDateDay(row.date)}
                          {isToday ? (
                            <span className="rounded-full border border-[#1c6636] bg-[#102118] px-1.5 py-0.5 text-[9px] font-semibold text-ok">
                              Hari ini
                            </span>
                          ) : null}
                        </span>
                      </td>
                      <td>{row.computers.toLocaleString("id-ID")}</td>
                      <td>
                        {row.raw_samples.toLocaleString("id-ID")}
                      </td>
                      <td>
                        {row.hourly_buckets.toLocaleString("id-ID")}
                      </td>
                      <td>
                        {row.speed_samples.toLocaleString("id-ID")}
                      </td>
                      <td className="whitespace-nowrap text-[11px] text-muted">
                        {fmtDateTime(row.first_ts)} –{" "}
                        {fmtDateTime(row.last_ts)}
                      </td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {row.has_raw ? (
                            <span className="rounded-full border border-[#1c6636] bg-[#102118] px-1.5 py-0.5 text-[9px] font-semibold text-ok">
                              Raw
                            </span>
                          ) : null}
                          {row.has_hourly ? (
                            <span className="rounded-full border border-[#3f2d6b] bg-[#1b1430] px-1.5 py-0.5 text-[9px] font-semibold text-[#a78bfa]">
                              Rekap
                            </span>
                          ) : null}
                          {row.has_speed ? (
                            <span className="rounded-full border border-[#1e3a5f] bg-[#0e1c2e] px-1.5 py-0.5 text-[9px] font-semibold text-[#60a5fa]">
                              Speed
                            </span>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card mt-4">
        <div className="card-header">
          <div>
            <div className="card-title">Tren Beban Komputer</div>
            <div className="card-subtitle">
              Rata-rata CPU dan RAM seluruh PC per jam · {HOURS} jam terakhir
            </div>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-muted2">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#3b82f6]" />
              CPU
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#8b5cf6]" />
              RAM
            </span>
          </div>
        </div>
        <div className="h-[210px]">
          {chartData.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={chartData}
                margin={{ top: 5, right: 5, bottom: 0, left: -10 }}
              >
                <defs>
                  <linearGradient id="reportCpu" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="reportRam" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#24303d"
                  vertical={false}
                />
                <XAxis
                  dataKey="label"
                  tick={{ fill: "#5f6c7c", fontSize: 9 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={28}
                />
                <YAxis
                  domain={[0, 100]}
                  width={42}
                  tick={{ fill: "#5f6c7c", fontSize: 9 }}
                  unit="%"
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#151e28",
                    border: "1px solid #24303d",
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                  labelStyle={{ color: "#8794a4" }}
                  formatter={(value) => `${Number(value).toFixed(1)}%`}
                />
                <Area
                  type="monotone"
                  dataKey="cpu"
                  name="CPU"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#reportCpu)"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="ram"
                  name="RAM"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  fill="url(#reportRam)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-center text-[11px] text-muted2">
              Histori metrik komputer belum cukup untuk menggambar tren.
            </div>
          )}
        </div>
      </div>

      <div className="card mt-4">
        <div className="card-header">
          <div>
            <div className="card-title">5 Komputer Beban Tertinggi</div>
            <div className="card-subtitle">
              Rata-rata tertinggi CPU dan RAM dalam {HOURS} jam terakhir
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-[10px] text-muted">
              <b className="text-[11px] text-white">
                {computers?.total ?? 0}
              </b>{" "}
              Total
            </span>
            <span className="rounded-full border border-[#1c6636] bg-[#102118] px-2.5 py-1 text-[10px] text-ok">
              <b className="text-[11px]">{computers?.online ?? 0}</b> Online
            </span>
            <span className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-[10px] text-muted2">
              {computers?.with_data ?? 0} dengan data
            </span>
          </div>
        </div>

        {computers && computers.top.length > 0 ? (
          <div className="table-wrap overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Komputer</th>
                  <th>CPU</th>
                  <th>RAM</th>
                </tr>
              </thead>
              <tbody>
                {computers.top.map((computer, index) => (
                  <ComputerRow
                    key={computer.id}
                    computer={computer}
                    rank={index + 1}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-lg border border-line bg-panel2 px-3 py-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted">
              <Monitor size={16} />
            </div>
            <div>
              <div className="text-[11px] text-muted">
                Histori komputer belum tersedia.
              </div>
              <div className="mt-0.5 text-[10px] text-muted2">
                Data mulai terkumpul dari heartbeat agent dan direkap per jam.
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
        <div className="card xl:col-span-2">
          <div className="card-header">
            <div>
              <div className="card-title">Metrik Rata-rata PC</div>
              <div className="card-subtitle">
                {computers?.with_data ?? 0} dari {computers?.total ?? 0} PC
                memiliki data
              </div>
            </div>
          </div>
          <div className="table-wrap overflow-auto">
            <table>
              <thead>
                <tr>
                  <th>Metrik</th>
                  <th>Rata-rata</th>
                  <th>Min</th>
                  <th>Maks</th>
                </tr>
              </thead>
              <tbody>
                {metricRows.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td className="text-[12px] font-semibold">
                      {statValue(row.stat, "avg", row.format)}
                    </td>
                    <td className="text-muted">
                      {statValue(row.stat, "min", row.format)}
                    </td>
                    <td className="text-muted">
                      {statValue(row.stat, "max", row.format)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {computers && computers.sample_count === 0 ? (
            <div className="mt-3 rounded-lg border border-line bg-panel2 px-3 py-2.5 text-[11px] text-muted2">
              Belum ada sampel metrik PC. Agent mengirim data setiap heartbeat.
            </div>
          ) : null}
        </div>

        <div className="card xl:col-span-3">
          <div className="card-header">
            <div>
              <div className="card-title">CCTV Bermasalah</div>
              <div className="card-subtitle">
                Kamera dengan downtime dalam {HOURS} jam terakhir
              </div>
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-1.5">
            <span className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-[10px] text-muted">
              <b className="text-[11px] text-white">{stats.total}</b> Total
            </span>
            <span className="rounded-full border border-[#1c6636] bg-[#102118] px-2.5 py-1 text-[10px] text-ok">
              <b className="text-[11px]">{stats.normal}</b> Normal
            </span>
            <span className="rounded-full border border-[#73520d] bg-[#241b09] px-2.5 py-1 text-[10px] text-warn">
              <b className="text-[11px]">{stats.problem}</b> Bermasalah
            </span>
            {cctv ? (
              <span className="rounded-full border border-line bg-panel2 px-2.5 py-1 text-[10px] text-muted2">
                {cctv.offline_now} offline sekarang
              </span>
            ) : null}
          </div>

          {cctv && cctv.problems.length > 0 ? (
            <div className="table-wrap overflow-auto">
              <table>
                <thead>
                  <tr>
                    <th>CCTV</th>
                    <th>Status</th>
                    <th>Rentang Mati</th>
                    <th>Durasi</th>
                  </tr>
                </thead>
                <tbody>
                  {cctv.problems.map((problem) => (
                    <ProblemRow key={problem.id} problem={problem} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-line bg-panel2 px-3 py-8 text-center">
              <CheckCircle2 size={20} className="text-ok" />
              <div className="text-[11px] text-muted">
                {cctv
                  ? "Semua kamera normal dalam 24 jam terakhir."
                  : "Memuat data CCTV…"}
              </div>
            </div>
          )}
        </div>
      </div>

      {isSuperadmin ? (
        <div className="card mt-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line bg-panel2 text-muted">
                <Mail size={15} />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="card-title">Email Report</span>
                  <span
                    className={clsx(
                      "rounded-full px-2 py-1 text-[9px] font-bold",
                      settingsQuery.isError
                        ? "bg-panel2 text-bad"
                        : !settings
                          ? "bg-panel2 text-muted2"
                          : settings.enabled
                            ? "bg-[#102118] text-ok"
                            : "bg-panel2 text-muted2"
                    )}
                  >
                    {settingsQuery.isError
                      ? "GAGAL"
                      : !settings
                        ? "MEMUAT…"
                        : settings.enabled
                          ? "AKTIF"
                          : "NONAKTIF"}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-muted">
                  {settingsQuery.isError
                    ? "Gagal memuat pengaturan email. Buka Atur untuk mencoba lagi."
                    : settings
                      ? `${settings.recipients.length} penerima · jadwal ${settings.schedule}`
                      : "Memuat pengaturan…"}
                </div>
                <div className="mt-0.5 text-[10px] text-muted2">
                  {settings?.last_sent
                    ? `Terakhir dikirim ${fmtDateTime(settings.last_sent)}`
                    : "Belum pernah dikirim"}
                </div>
              </div>
            </div>
            <button
              className="btn flex items-center gap-2 self-start sm:self-auto"
              onClick={openSettings}
            >
              <Settings2 size={13} /> Atur
            </button>
          </div>
        </div>
      ) : null}

      {reportQuery.isError ? (
        <div className="mt-4 rounded-lg border border-line bg-panel2 px-3 py-4 text-[11px] text-bad">
          Gagal memuat report:{" "}
          {reportQuery.error instanceof ApiError
            ? reportQuery.error.message
            : "terjadi kesalahan"}
        </div>
      ) : null}

      {isSuperadmin && settingsOpen ? (
        <EmailSettingsModal
          key={settingsKey}
          settings={settings}
          loading={settingsQuery.isFetching}
          loadError={
            settingsQuery.isError
              ? settingsQuery.error instanceof ApiError
                ? settingsQuery.error.message
                : "Gagal memuat pengaturan email"
              : ""
          }
          onRetry={() => {
            void settingsQuery.refetch();
          }}
          onClose={() => setSettingsOpen(false)}
        />
      ) : null}
    </>
  );
}
