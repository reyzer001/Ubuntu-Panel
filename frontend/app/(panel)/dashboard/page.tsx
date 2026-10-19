"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Cpu,
  HardDrive,
  MemoryStick,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/page-header";
import { ConcentricPerformanceMeter } from "@/components/ui/concentric-performance-meter";
import { GaugeCard } from "@/components/ui/gauge-card";
import { MetricDetailModal, type MetricType } from "@/components/ui/metric-detail-modal";
import { MiniNetworkGauge } from "@/components/ui/mini-network-gauge";
import { StatusBadge } from "@/components/ui/status-badge";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import { api } from "@/lib/api";
import { toneBarClass, usageTone } from "@/lib/format";
import type {
  BackupJob,
  FilesystemInfo,
  LogEntry,
  Metrics,
  ServiceInfo,
  SystemInfo,
} from "@/lib/types";
import clsx from "clsx";

const CRITICAL = ["nginx", "postgresql", "postgres", "docker", "redis", "ssh"];

type Range = "1m" | "5m" | "all";

const RANGE_POINTS: Record<Range, number> = { "1m": 30, "5m": 150, all: Infinity };

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [range, setRange] = useState<Range>("5m");
  const [selectedMetric, setSelectedMetric] = useState<MetricType | null>(null);

  const { data: info } = useQuery({
    queryKey: ["system-info"],
    queryFn: () => api<SystemInfo>("/system/info"),
  });
  const { data: metricsRest } = useQuery({
    queryKey: ["metrics"],
    queryFn: () => api<Metrics>("/system/metrics"),
    refetchInterval: 15_000,
  });
  const { data: servicesData } = useQuery({
    queryKey: ["services"],
    queryFn: () => api<{ services: ServiceInfo[] }>("/services"),
  });
  const { data: logsData } = useQuery({
    queryKey: ["logs", "dashboard"],
    queryFn: () => api<{ entries: LogEntry[] }>("/logs?lines=50"),
  });
  const { data: fsData } = useQuery({
    queryKey: ["filesystems"],
    queryFn: () =>
      api<{ filesystems: FilesystemInfo[] }>("/storage/filesystems"),
  });
  const { data: backupData } = useQuery({
    queryKey: ["backup-jobs"],
    queryFn: () => api<{ jobs: BackupJob[] }>("/backup/jobs"),
    staleTime: 30_000,
  });

  const { metrics: live, history, transport } = useMetricsStream();
  const m = live ?? metricsRest ?? null;

  const chartData = useMemo(() => {
    const points = history.slice(-RANGE_POINTS[range]);
    return points.map((p) => ({
      t: p.t.slice(11, 16),
      cpu: Number(p.cpu.toFixed(1)),
      ram: Number(p.ram.toFixed(1)),
    }));
  }, [history, range]);

  const criticalServices = (servicesData?.services ?? [])
    .filter((s) => CRITICAL.some((k) => s.name.includes(k)))
    .slice(0, 5);

  const topFilesystems = [...(fsData?.filesystems ?? [])]
    .sort((a, b) => b.percent - a.percent)
    .slice(0, 3);

  // ringkasan backup: run terakhir apa pun + jadwal terdekat
  const backupJobs = backupData?.jobs ?? [];
  const lastBackup = backupJobs
    .map((j) => j.last_run)
    .filter(Boolean)
    .sort((a, b) =>
      (new Date(b!.started_at ?? 0).getTime() || 0) - (new Date(a!.started_at ?? 0).getTime() || 0)
    )[0] ?? null;
  const nextBackup = backupJobs
    .map((j) => j.next_run)
    .filter(Boolean)
    .sort()[0] ?? null;

  return (
    <>
      <PageHeader
        title="Server Overview"
        subtitle={`Monitoring ${info?.hostname ?? "server"} · ${
          transport === "ws" ? "live" : transport === "polling" ? "polling" : "offline"
        }`}
        onRefresh={() => queryClient.invalidateQueries()}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GaugeCard
          variant="cpu"
          label="CPU Usage"
          icon={<Cpu size={15} className="text-muted" />}
          gaugeValue={m ? m.cpu : 0}
          kernel={m?.cpu_kernel ?? 0.2}
          format={(v) => `${v.toFixed(0)}%`}
          subtext={`${m?.cpu_cores ?? "—"} vCPU`}
          onClick={() => setSelectedMetric("cpu")}
          statusText={
            (m?.cpu ?? 0) >= 90
              ? "High"
              : (m?.cpu ?? 0) >= 75
                ? "Elevated"
                : "Normal"
          }
        />
        <GaugeCard
          variant="memory"
          label="Memory"
          icon={<MemoryStick size={15} className="text-muted" />}
          gaugeValue={m ? m.ram_used / 1024 ** 3 : 0}
          gaugeMax={m ? m.ram_total / 1024 ** 3 : 100}
          active={m ? m.mem_active / 1024 ** 3 : 0}
          inactive={m ? m.mem_inactive / 1024 ** 3 : 0}
          cached={m ? m.mem_cached / 1024 ** 3 : 0}
          swap={m?.swap ?? 0}
          subtext={m ? `${m.ram.toFixed(0)}% terpakai` : "—"}
          onClick={() => setSelectedMetric("memory")}
          statusText={
            (m?.ram ?? 0) >= 90
              ? "High"
              : (m?.ram ?? 0) >= 75
                ? "Elevated"
                : "Normal"
          }
        />
        <GaugeCard
          variant="storage"
          label="Storage"
          icon={<HardDrive size={15} className="text-muted" />}
          gaugeValue={m ? m.disk_used / 1024 ** 3 : 0}
          gaugeMax={m ? m.disk_total / 1024 ** 3 : 100}
          subtext={m ? `${m.disk.toFixed(0)}% terpakai` : "—"}
          onClick={() => setSelectedMetric("storage")}
          statusText={
            (m?.disk ?? 0) >= 90
              ? "High"
              : (m?.disk ?? 0) >= 75
                ? "Watch"
                : "Normal"
          }
        />
        <GaugeCard
          variant="load"
          label="Load Average"
          icon={<Activity size={15} className="text-muted" />}
          gaugeValue={(() => {
            const cores = m?.cpu_cores ?? 1;
            const load = m?.load1 ?? 0;
            return Math.min((load / cores) * 100, 100);
          })()}
          gaugeMax={100}
          gaugeText={`of ${m?.cpu_cores ?? "—"} cores`}
          format={(v) => ((v / 100) * (m?.cpu_cores ?? 1)).toFixed(2)}
          subtext={`1 min · ${m?.cpu_cores ?? "—"} core`}
          onClick={() => setSelectedMetric("load")}
          statusText={(() => {
            const cores = m?.cpu_cores ?? 1;
            const load = m?.load1 ?? 0;
            const pct = (load / cores) * 100;
            if (pct >= 90) return "High";
            if (pct >= 75) return "Elevated";
            return "Normal";
          })()}
        />
      </section>

      <div className="h-4" />

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ConcentricPerformanceMeter
          metrics={m}
          range={range}
          onRangeChange={setRange}
          onSelectMetric={(met) => setSelectedMetric(met)}
          transport={transport}
        />

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Critical Services</div>
              <div className="card-subtitle">systemd services</div>
            </div>
            <a href="/services" className="btn">
              View all
            </a>
          </div>
          <div>
            {criticalServices.map((s) => (
              <div
                key={s.unit}
                className="flex items-center justify-between border-b border-line py-2.5 last:border-b-0"
              >
                <div>
                  <div className="text-[11px] font-bold">{s.name}</div>
                  <div className="mt-0.5 text-[9px] text-muted">
                    {s.description}
                  </div>
                </div>
                <StatusBadge status={s.status} />
              </div>
            ))}
            {criticalServices.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted2">
                No well-known services detected
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <div className="h-4" />

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Backup Status</div>
              <div className="card-subtitle">Last &amp; next scheduled</div>
            </div>
            <a href="/backup" className="btn">
              Manage
            </a>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <div className="info-item">
              <div className="info-label">Last Backup</div>
              <div className="info-value">
                {lastBackup?.started_at
                  ? new Date(lastBackup.started_at + "Z").toLocaleDateString()
                  : "—"}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Status</div>
              <div className="info-value">
                {lastBackup ? (
                  <StatusBadge status={lastBackup.status.toLowerCase()} />
                ) : (
                  "—"
                )}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Next Backup</div>
              <div className="info-value">
                {nextBackup
                  ? new Date(nextBackup + "Z").toLocaleString([], {
                      dateStyle: "short",
                      timeStyle: "short",
                    })
                  : "—"}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Jobs</div>
              <div className="info-value">
                {backupJobs.filter((j) => j.enabled).length} aktif
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Storage</div>
              <div className="card-subtitle">Filesystem utilization</div>
            </div>
            <a href="/storage" className="btn">
              Manage
            </a>
          </div>
          {topFilesystems.map((fs) => (
            <div key={fs.mountpoint} className="mb-5 last:mb-0">
              <div className="mb-2 flex justify-between text-[11px]">
                <span>{fs.mountpoint}</span>
                <span className="text-muted">{fs.percent}%</span>
              </div>
              <div className="progress">
                <div
                  className={`progress-bar ${toneBarClass[usageTone(fs.percent)]}`}
                  style={{ width: `${Math.min(100, fs.percent)}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Network</div>
              <div className="card-subtitle">Current traffic</div>
            </div>
            <a href="/network" className="btn">
              Details
            </a>
          </div>
          <div className="grid grid-cols-2 gap-2.5 mb-2.5">
            <div className="info-item">
              <div className="info-label">Interface IP</div>
              <div className="info-value">{info?.primary_ip || "—"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">Hostname</div>
              <div className="info-value truncate">{info?.hostname ?? "—"}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <MiniNetworkGauge variant="download" rate={live?.net_rx_rate ?? 0} />
            <MiniNetworkGauge variant="upload" rate={live?.net_tx_rate ?? 0} />
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Recent Activity</div>
              <div className="card-subtitle">Latest server events</div>
            </div>
            <a href="/logs" className="btn">
              Logs
            </a>
          </div>
          {(logsData?.entries ?? []).slice(0, 4).map((log, i) => (
            <div key={`${log.time}-${i}`} className="mb-3 flex gap-2.5 last:mb-0">
              <div
                className={clsx(
                  "mt-1 h-[7px] w-[7px] shrink-0 rounded-full",
                  log.level === "ERROR" && "bg-bad",
                  log.level === "WARN" && "bg-warn",
                  log.level === "INFO" && "bg-ok"
                )}
              />
              <div>
                <div className="text-[10px] leading-snug">{log.message}</div>
                <div className="mt-0.5 text-[9px] text-muted">
                  {log.time} · {log.source}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <MetricDetailModal
        type={selectedMetric}
        metrics={m}
        systemInfo={info}
        filesystems={fsData?.filesystems}
        onClose={() => setSelectedMetric(null)}
      />
    </>
  );
}
