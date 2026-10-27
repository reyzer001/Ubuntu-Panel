"use client"

import { useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  X,
  Cpu,
  MemoryStick,
  HardDrive,
  Activity,
  ArrowRight,
  TrendingUp,
  Clock,
  Server,
  Layers,
} from "lucide-react"
import { api } from "@/lib/api"
import { formatBytes, formatRate, formatUptime, toneBarClass, usageTone } from "@/lib/format"
import type { FilesystemInfo, Metrics, ProcessInfo, SystemInfo } from "@/lib/types"
import { CoreGaugeGrid } from "@/components/ui/core-gauge-grid"

export type MetricType = "cpu" | "memory" | "storage" | "load"

interface MetricDetailModalProps {
  type: MetricType | null
  metrics: Metrics | null
  systemInfo?: SystemInfo | null
  filesystems?: FilesystemInfo[]
  onClose: () => void
}

export function MetricDetailModal({
  type,
  metrics,
  systemInfo,
  filesystems = [],
  onClose,
}: MetricDetailModalProps) {
  useEffect(() => {
    if (!type) return
    document.body.style.overflow = "hidden"
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => {
      document.body.style.overflow = ""
      window.removeEventListener("keydown", onKey)
    }
  }, [type, onClose])

  // Ambil data processes saat modal CPU atau Memory terbuka
  const shouldFetchProcesses = type === "cpu" || type === "memory"
  const { data: procsData, isLoading: procsLoading } = useQuery({
    queryKey: ["processes", "modal", type],
    queryFn: () => api<{ processes: ProcessInfo[] }>("/processes"),
    enabled: shouldFetchProcesses,
    staleTime: 5000,
  })

  // Top 5 processes sesuai kriteria
  const topProcesses = useMemo(() => {
    const list = procsData?.processes ?? []
    if (type === "cpu") {
      return [...list].sort((a, b) => b.cpu - a.cpu).slice(0, 5)
    }
    if (type === "memory") {
      return [...list].sort((a, b) => b.memory_percent - a.memory_percent).slice(0, 5)
    }
    return []
  }, [procsData, type])

  if (!type) return null

  const getHeader = () => {
    switch (type) {
      case "cpu":
        return {
          title: "CPU Performance Detail",
          icon: <Cpu size={20} className="text-[#3b82f6]" />,
          colorClass: "bg-[#111f34] border-[#1d3d66]",
        }
      case "memory":
        return {
          title: "Memory / RAM Detail",
          icon: <MemoryStick size={20} className="text-[#8b5cf6]" />,
          colorClass: "bg-[#201534] border-[#44236b]",
        }
      case "storage":
        return {
          title: "Storage & Filesystems",
          icon: <HardDrive size={20} className="text-[#38bdf8]" />,
          colorClass: "bg-[#0f2430] border-[#164e63]",
        }
      case "load":
        return {
          title: "System Load & Intensity",
          icon: <Activity size={20} className="text-[#10b981]" />,
          colorClass: "bg-[#0f281e] border-[#134e35]",
        }
    }
  }

  const hdr = getHeader()

  return (
    <div
      className="dialog-overlay"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={`dialog-card max-h-[90vh] overflow-y-auto p-6 ${
          type === "cpu" ? "max-w-[900px]" : "max-w-[560px]"
        }`}
        role="dialog"
        aria-modal="true"
        aria-label={hdr.title}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line pb-3.5">
          <div className="flex items-center gap-3">
            <div className={`grid h-9 w-9 place-items-center rounded-xl border ${hdr.colorClass}`}>
              {hdr.icon}
            </div>
            <div>
              <div className="text-sm font-bold text-fg">{hdr.title}</div>
              <div className="text-[11px] text-muted">
                {systemInfo?.hostname ?? "Server"} · {systemInfo?.os ?? "Linux"}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded-lg border border-line bg-panel2 text-muted transition hover:text-fg"
          >
            <X size={15} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="mt-4 space-y-4">
          {type === "cpu" && (
            <>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <div className="info-item">
                  <div className="info-label">Current Usage</div>
                  <div className="info-value text-[#3b82f6]">
                    {metrics ? `${metrics.cpu.toFixed(1)}%` : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Kernel / Sys</div>
                  <div className="info-value">
                    {metrics ? `${((metrics.cpu_kernel ?? 0) * 100).toFixed(1)}%` : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Logical Cores</div>
                  <div className="info-value">{metrics?.cpu_cores ?? "—"} vCPU</div>
                </div>
                <div className="info-item">
                  <div className="info-label">Architecture</div>
                  <div className="info-value">{systemInfo?.arch ?? "x86_64"}</div>
                </div>
              </div>

              <div className="rounded-lg border border-line bg-panel2/50 p-3">
                <div className="text-[11px] font-medium text-muted">Processor Model</div>
                <div className="mt-1 font-mono text-xs font-semibold text-fg">
                  {systemInfo?.cpu_model || "Generic CPU"}
                </div>
              </div>

              <CoreGaugeGrid cores={metrics?.cpu_per_core} />

              {/* Top CPU consuming processes */}
              <div>
                <div className="mb-2 flex items-center justify-between text-xs font-semibold text-fg">
                  <span>Top CPU Processes</span>
                  <a href="/processes" className="flex items-center gap-1 text-[11px] text-info hover:underline">
                    Manage Processes <ArrowRight size={12} />
                  </a>
                </div>
                <div className="overflow-hidden rounded-lg border border-line">
                  <table className="w-full text-[11px]">
                    <thead className="border-b border-line bg-panel2 text-muted">
                      <tr>
                        <th className="px-3 py-1.5 text-left font-medium">PID</th>
                        <th className="px-3 py-1.5 text-left font-medium">Command</th>
                        <th className="px-3 py-1.5 text-left font-medium">User</th>
                        <th className="px-3 py-1.5 text-right font-medium">CPU%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {procsLoading ? (
                        <tr>
                          <td colSpan={4} className="py-4 text-center text-muted">
                            Loading processes…
                          </td>
                        </tr>
                      ) : topProcesses.length > 0 ? (
                        topProcesses.map((p) => (
                          <tr key={p.pid} className="border-b border-line/40 last:border-b-0 hover:bg-panel2/30">
                            <td className="px-3 py-1.5 font-mono text-muted">{p.pid}</td>
                            <td className="px-3 py-1.5 font-medium text-fg truncate max-w-[180px]">{p.name}</td>
                            <td className="px-3 py-1.5 text-muted">{p.user}</td>
                            <td className="px-3 py-1.5 text-right font-mono font-bold text-info">
                              {p.cpu.toFixed(1)}%
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={4} className="py-3 text-center text-muted">
                            No active processes found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {type === "memory" && (
            <>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <div className="info-item">
                  <div className="info-label">Used RAM</div>
                  <div className="info-value text-[#8b5cf6]">
                    {metrics ? formatBytes(metrics.ram_used) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Total RAM</div>
                  <div className="info-value">
                    {metrics ? formatBytes(metrics.ram_total) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Cached / Buffers</div>
                  <div className="info-value">
                    {metrics ? formatBytes(metrics.mem_cached) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Swap Used</div>
                  <div className="info-value">
                    {metrics ? `${metrics.swap.toFixed(0)}%` : "—"}
                  </div>
                </div>
              </div>

              {/* Memory breakdown progress */}
              {metrics && (
                <div className="rounded-lg border border-line bg-panel2/50 p-3">
                  <div className="mb-2 flex items-center justify-between text-xs">
                    <span className="text-muted">Memory Allocation</span>
                    <span className="font-mono font-bold text-fg">
                      {metrics.ram.toFixed(1)}% Used
                    </span>
                  </div>
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-panel">
                    <div
                      style={{ width: `${(metrics.mem_active / metrics.ram_total) * 100}%` }}
                      className="bg-[#8b5cf6]"
                      title="Active"
                    />
                    <div
                      style={{ width: `${(metrics.mem_inactive / metrics.ram_total) * 100}%` }}
                      className="bg-[#a78bfa]"
                      title="Inactive"
                    />
                    <div
                      style={{ width: `${(metrics.mem_cached / metrics.ram_total) * 100}%` }}
                      className="bg-[#64748b]"
                      title="Cached"
                    />
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[10px] text-muted">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-[#8b5cf6]" /> Active: {formatBytes(metrics.mem_active)}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-[#a78bfa]" /> Inactive: {formatBytes(metrics.mem_inactive)}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-[#64748b]" /> Cache: {formatBytes(metrics.mem_cached)}
                    </span>
                  </div>
                </div>
              )}

              {/* Top Memory consuming processes */}
              <div>
                <div className="mb-2 flex items-center justify-between text-xs font-semibold text-fg">
                  <span>Top Memory Consumers</span>
                  <a href="/processes" className="flex items-center gap-1 text-[11px] text-info hover:underline">
                    Manage Processes <ArrowRight size={12} />
                  </a>
                </div>
                <div className="overflow-hidden rounded-lg border border-line">
                  <table className="w-full text-[11px]">
                    <thead className="border-b border-line bg-panel2 text-muted">
                      <tr>
                        <th className="px-3 py-1.5 text-left font-medium">PID</th>
                        <th className="px-3 py-1.5 text-left font-medium">Command</th>
                        <th className="px-3 py-1.5 text-left font-medium">RSS Memory</th>
                        <th className="px-3 py-1.5 text-right font-medium">RAM%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {procsLoading ? (
                        <tr>
                          <td colSpan={4} className="py-4 text-center text-muted">
                            Loading processes…
                          </td>
                        </tr>
                      ) : topProcesses.length > 0 ? (
                        topProcesses.map((p) => (
                          <tr key={p.pid} className="border-b border-line/40 last:border-b-0 hover:bg-panel2/30">
                            <td className="px-3 py-1.5 font-mono text-muted">{p.pid}</td>
                            <td className="px-3 py-1.5 font-medium text-fg truncate max-w-[180px]">{p.name}</td>
                            <td className="px-3 py-1.5 text-muted">{formatBytes(p.memory)}</td>
                            <td className="px-3 py-1.5 text-right font-mono font-bold text-[#8b5cf6]">
                              {p.memory_percent.toFixed(1)}%
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={4} className="py-3 text-center text-muted">
                            No active processes found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {type === "storage" && (
            <>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                <div className="info-item">
                  <div className="info-label">Used Space</div>
                  <div className="info-value text-info">
                    {metrics ? formatBytes(metrics.disk_used) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Total Capacity</div>
                  <div className="info-value">
                    {metrics ? formatBytes(metrics.disk_total) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Disk Read</div>
                  <div className="info-value">
                    {metrics ? formatRate(metrics.disk_read_rate ?? 0) : "—"}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">Disk Write</div>
                  <div className="info-value">
                    {metrics ? formatRate(metrics.disk_write_rate ?? 0) : "—"}
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between text-xs font-semibold text-fg">
                  <span>Mounted Filesystems</span>
                  <a href="/storage" className="flex items-center gap-1 text-[11px] text-info hover:underline">
                    Manage Storage <ArrowRight size={12} />
                  </a>
                </div>
                <div className="space-y-2.5">
                  {filesystems.map((fs) => (
                    <div key={fs.mountpoint} className="rounded-lg border border-line bg-panel2/40 p-3">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <div className="flex items-center gap-2">
                          <HardDrive size={13} className="text-muted" />
                          <span className="font-bold text-fg">{fs.mountpoint}</span>
                          <span className="text-[10px] text-muted">({fs.fstype})</span>
                        </div>
                        <div className="font-mono text-[11px]">
                          {formatBytes(fs.used)} / {formatBytes(fs.total)} ({fs.percent}%)
                        </div>
                      </div>
                      <div className="progress mt-2">
                        <div
                          className={`progress-bar ${toneBarClass[usageTone(fs.percent)]}`}
                          style={{ width: `${Math.min(100, fs.percent)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {type === "load" && (
            <>
              <div className="grid grid-cols-3 gap-2.5">
                <div className="info-item">
                  <div className="info-label">Load (1 min)</div>
                  <div className="info-value text-ok">{metrics?.load1 ?? "—"}</div>
                </div>
                <div className="info-item">
                  <div className="info-label">Load (5 min)</div>
                  <div className="info-value">{metrics?.load5 ?? "—"}</div>
                </div>
                <div className="info-item">
                  <div className="info-label">Load (15 min)</div>
                  <div className="info-value">{metrics?.load15 ?? "—"}</div>
                </div>
              </div>

              <div className="rounded-lg border border-line bg-panel2/50 p-3.5 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted">Normalized Load Ratio (per Core)</span>
                  <span className="font-mono font-bold text-fg">
                    {metrics ? `${((metrics.load1 / (metrics.cpu_cores || 1)) * 100).toFixed(0)}%` : "—"}
                  </span>
                </div>
                <div className="progress">
                  <div
                    className={`progress-bar ${
                      metrics && (metrics.load1 / (metrics.cpu_cores || 1)) >= 1
                        ? "bg-bad"
                        : metrics && (metrics.load1 / (metrics.cpu_cores || 1)) >= 0.75
                          ? "bg-warn"
                          : "bg-ok"
                    }`}
                    style={{
                      width: `${Math.min(
                        100,
                        metrics ? (metrics.load1 / (metrics.cpu_cores || 1)) * 100 : 0
                      )}%`,
                    }}
                  />
                </div>
                <div className="text-[11px] leading-relaxed text-muted">
                  Nilai rasio beban terhadap {metrics?.cpu_cores ?? 1} CPU cores. Nilai di bawah 100% menandakan server memiliki kapasitas cadangan untuk menjalankan task baru tanpa queue delay.
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="rounded-lg border border-line bg-panel2/40 p-3">
                  <div className="flex items-center gap-2 text-xs font-medium text-fg">
                    <Clock size={14} className="text-muted" />
                    <span>System Uptime</span>
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold text-fg">
                    {metrics ? formatUptime(metrics.uptime) : "—"}
                  </div>
                </div>
                <div className="rounded-lg border border-line bg-panel2/40 p-3">
                  <div className="flex items-center gap-2 text-xs font-medium text-fg">
                    <Layers size={14} className="text-muted" />
                    <span>Total Processes</span>
                  </div>
                  <div className="mt-1 font-mono text-sm font-bold text-fg">
                    {metrics?.process_count ?? "—"} PIDs
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="mt-5 flex justify-end border-t border-line pt-3">
          <button type="button" onClick={onClose} className="btn px-4 py-1.5 text-xs">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
