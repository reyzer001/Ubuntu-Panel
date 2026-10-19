"use client"

import { useMemo, useState } from "react"
import { Cpu, MemoryStick, HardDrive, Activity } from "lucide-react"
import {
  Gauge,
  GaugeArc,
  GaugeInset,
  GaugeTrack,
} from "@/components/gauge"
import type { Metrics } from "@/lib/types"
import type { MetricsTransport } from "@/hooks/use-metrics-stream"
import { formatUptime } from "@/lib/format"
import clsx from "clsx"

type Range = "1m" | "5m" | "all"

const TRANSPORT_PILL: Record<MetricsTransport, { text: string; className: string; pulse: boolean }> = {
  ws: {
    text: "LIVE",
    className: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40",
    pulse: true,
  },
  polling: {
    text: "POLLING",
    className: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/40",
    pulse: true,
  },
  offline: {
    text: "OFFLINE",
    className: "bg-slate-500/15 text-slate-400 ring-1 ring-slate-500/40",
    pulse: false,
  },
}

interface ConcentricPerformanceMeterProps {
  metrics: Metrics | null
  range: Range
  onRangeChange: (r: Range) => void
  onSelectMetric?: (metric: "cpu" | "memory" | "storage" | "load") => void
  transport?: MetricsTransport
}

export function ConcentricPerformanceMeter({
  metrics,
  range,
  onRangeChange,
  onSelectMetric,
  transport = "offline",
}: ConcentricPerformanceMeterProps) {
  const tp = TRANSPORT_PILL[transport]
  const cpuPct = Math.min(100, Math.max(0, metrics?.cpu ?? 0))
  const ramPct = Math.min(100, Math.max(0, metrics?.ram ?? 0))
  const loadNormalized = metrics
    ? Math.min(100, Math.max(0, (metrics.load1 / (metrics.cpu_cores || 1)) * 100))
    : 0

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="card-title">System Performance</div>
          <div className="card-subtitle">Realtime concentric utilization</div>
        </div>
        <div className="flex gap-1.5">
          {(["1m", "5m", "all"] as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => onRangeChange(r)}
              className={clsx("btn px-2.5 py-1.5", range === r && "btn-primary")}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col items-center justify-between gap-6 py-2 md:flex-row md:items-center">
        {/* Visual Concentric Rings */}
        <div className="relative flex h-[210px] w-[210px] shrink-0 items-center justify-center">
          <Gauge
            value={cpuPct}
            min={0}
            max={100}
            startAngle={30}
            endAngle={330}
            padding={10}
            transition
            initialValue={0}
            className="h-full w-full"
          >
            {/* Outer Ring: CPU */}
            <GaugeTrack width={14} color="#1e293b" opacity={0.6} cap="round" />
            <GaugeArc width={14} color="#3b82f6" cap="round" />

            {/* Middle Ring: RAM */}
            <GaugeInset
              value={ramPct}
              min={0}
              max={100}
              startAngle={30}
              endAngle={330}
              transition
              initialValue={0}
            >
              <GaugeTrack width={14} offset={-24} color="#1e293b" opacity={0.6} cap="round" />
              <GaugeArc width={14} offset={-24} color="#8b5cf6" cap="round" />
            </GaugeInset>

            {/* Inner Ring: Load */}
            <GaugeInset
              value={loadNormalized}
              min={0}
              max={100}
              startAngle={30}
              endAngle={330}
              transition
              initialValue={0}
            >
              <GaugeTrack width={14} offset={-48} color="#1e293b" opacity={0.6} cap="round" />
              <GaugeArc width={14} offset={-48} color="#10b981" cap="round" />
            </GaugeInset>
          </Gauge>

          {/* Center info */}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">Core Load</span>
            <span className="font-mono text-2xl font-bold tracking-tight text-fg">
              {metrics?.load1.toFixed(2) ?? "0.00"}
            </span>
            <span className="text-[10px] text-muted">{metrics?.cpu_cores ?? 1} vCPU</span>
          </div>
        </div>

        {/* Legend & Breakdown Interactive Cards */}
        <div className="flex w-full flex-col justify-center gap-2.5">
          {/* CPU Row */}
          <button
            type="button"
            onClick={() => onSelectMetric?.("cpu")}
            className="group flex w-full items-center justify-between rounded-lg border border-line bg-panel2/40 px-3.5 py-2.5 text-left transition hover:border-[#3b82f6]/50 hover:bg-panel2"
          >
            <div className="flex items-center gap-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[#3b82f6] shadow-[0_0_8px_#3b82f6]" />
              <div className="flex items-center gap-1.5 text-xs font-medium text-fg">
                <Cpu size={14} className="text-[#3b82f6]" />
                <span>CPU Usage</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted">
                {((metrics?.cpu_kernel ?? 0) * 100).toFixed(0)}% kernel
              </span>
              <span className="font-mono text-xs font-bold text-fg">
                {cpuPct.toFixed(1)}%
              </span>
            </div>
          </button>

          {/* RAM Row */}
          <button
            type="button"
            onClick={() => onSelectMetric?.("memory")}
            className="group flex w-full items-center justify-between rounded-lg border border-line bg-panel2/40 px-3.5 py-2.5 text-left transition hover:border-[#8b5cf6]/50 hover:bg-panel2"
          >
            <div className="flex items-center gap-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[#8b5cf6] shadow-[0_0_8px_#8b5cf6]" />
              <div className="flex items-center gap-1.5 text-xs font-medium text-fg">
                <MemoryStick size={14} className="text-[#8b5cf6]" />
                <span>RAM Usage</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted">
                {metrics ? `${(metrics.ram_used / 1024 ** 3).toFixed(1)} / ${(metrics.ram_total / 1024 ** 3).toFixed(1)} GB` : "—"}
              </span>
              <span className="font-mono text-xs font-bold text-fg">
                {ramPct.toFixed(1)}%
              </span>
            </div>
          </button>

          {/* Load Intensity Row */}
          <button
            type="button"
            onClick={() => onSelectMetric?.("load")}
            className="group flex w-full items-center justify-between rounded-lg border border-line bg-panel2/40 px-3.5 py-2.5 text-left transition hover:border-[#10b981]/50 hover:bg-panel2"
          >
            <div className="flex items-center gap-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[#10b981] shadow-[0_0_8px_#10b981]" />
              <div className="flex items-center gap-1.5 text-xs font-medium text-fg">
                <Activity size={14} className="text-[#10b981]" />
                <span>Load Intensity</span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted">
                {metrics?.load1 ?? "—"} / {metrics?.load5 ?? "—"} / {metrics?.load15 ?? "—"}
              </span>
              <span className="font-mono text-xs font-bold text-fg">
                {loadNormalized.toFixed(1)}%
              </span>
            </div>
          </button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line/60 pt-2 text-[10px] text-muted">
        <span className="tabular-nums">
          Uptime <strong className="font-semibold text-fg">{metrics ? formatUptime(metrics.uptime) : "—"}</strong>
          <span className="text-muted2"> · </span>
          Load{" "}
          <strong className="font-semibold text-fg">
            {metrics ? `${metrics.load1.toFixed(2)} / ${metrics.load5.toFixed(2)} / ${metrics.load15.toFixed(2)}` : "—"}
          </strong>
        </span>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider",
            tp.className
          )}
        >
          <span className="relative flex h-1.5 w-1.5">
            {tp.pulse ? (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
            ) : null}
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
          </span>
          {tp.text}
        </span>
      </div>
    </div>
  )
}
