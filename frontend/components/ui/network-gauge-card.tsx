"use client"

import type { ReactNode } from "react"
import { ArrowDown, ArrowUp, Network as NetworkIcon } from "lucide-react"
import {
  Gauge,
  GaugeArc,
  GaugeText,
  GaugeTicks,
  GaugeTickLabels,
  GaugeTrack,
  GaugeValue,
} from "@/components/gauge"

const MUTED_FG = "#8794a4"
const RX_COLOR = "#3b82f6" // blue
const TX_COLOR = "#8b5cf6" // purple
const CONN_COLOR = "#10b981" // emerald

/**
 * Tentukan skala atas dinamis (dalam bytes/detik) untuk download & upload
 * agar jarum / arc selalu proporsional dan tidak selalu mentok atau kosong.
 */
function getRateMax(bytesPerSec: number): number {
  const kb = bytesPerSec / 1024
  if (kb <= 100) return 100 * 1024 // 100 KB/s
  if (kb <= 500) return 500 * 1024 // 500 KB/s
  if (kb <= 1024) return 1024 * 1024 // 1 MB/s
  if (kb <= 5 * 1024) return 5 * 1024 * 1024 // 5 MB/s
  if (kb <= 10 * 1024) return 10 * 1024 * 1024 // 10 MB/s
  if (kb <= 50 * 1024) return 50 * 1024 * 1024 // 50 MB/s
  if (kb <= 100 * 1024) return 100 * 1024 * 1024 // 100 MB/s
  return Math.ceil(bytesPerSec / (100 * 1024 * 1024)) * 100 * 1024 * 1024
}

function getConnMax(connections: number): number {
  if (connections <= 50) return 50
  if (connections <= 100) return 100
  if (connections <= 250) return 250
  if (connections <= 500) return 500
  if (connections <= 1000) return 1000
  return Math.ceil(connections / 500) * 500
}

function formatRateSplit(bytesPerSec: number): { value: string; unit: string } {
  if (!Number.isFinite(bytesPerSec) || bytesPerSec <= 0) {
    return { value: "0", unit: "KB/s" }
  }
  const mb = bytesPerSec / (1024 * 1024)
  if (mb >= 1) {
    return { value: mb < 10 ? mb.toFixed(1) : mb.toFixed(0), unit: "MB/s" }
  }
  const kb = bytesPerSec / 1024
  return { value: kb < 10 ? kb.toFixed(1) : kb.toFixed(0), unit: "KB/s" }
}

export interface NetworkGaugeCardProps {
  variant: "download" | "upload" | "connections"
  value: number
  listeningCount?: number
  subtext?: ReactNode
  statusText?: ReactNode
}

export function NetworkGaugeCard({
  variant,
  value,
  listeningCount,
  subtext,
  statusText,
}: NetworkGaugeCardProps) {
  if (variant === "connections") {
    const safeVal = Math.max(0, Number.isFinite(value) ? value : 0)
    const maxVal = getConnMax(safeVal)

    return (
      <div className="rounded-card border border-line bg-panel p-[17px]">
        <div className="flex items-center justify-between text-[11px] text-muted">
          <span>Connections</span>
          <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2 text-ok">
            <NetworkIcon size={15} />
          </div>
        </div>

        <div className="mt-1 h-[170px]">
          <Gauge
            value={safeVal}
            min={0}
            max={maxVal}
            padding={24}
            transition
            initialValue={0}
          >
            <GaugeTrack width={28} cap="butt" />
            <GaugeArc width={28} cap="butt" color={CONN_COLOR} />
            <GaugeTicks count={40} length={6} width={2} offset={-30} cap="butt" opacity={0.4} />
            <GaugeTicks count={8} length={14} width={4} offset={-34} cap="butt" />
            <GaugeTickLabels
              count={5}
              offset={-66}
              fontSize={22}
              weight="semibold"
              format={(v) => Math.round(v).toString()}
            />
            <GaugeValue y={-8} fontSize={84} font="mono" decimals={0} />
            <GaugeText y={52} fontSize={22} color={MUTED_FG}>
              established
            </GaugeText>
          </Gauge>
        </div>

        <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
          <span>
            {subtext ?? (listeningCount !== undefined ? `${listeningCount} listening ports` : "Established")}
          </span>
          <span className="text-ok font-medium">{statusText ?? "Stable"}</span>
        </div>
      </div>
    )
  }

  const isRx = variant === "download"
  const safeRate = Math.max(0, Number.isFinite(value) ? value : 0)
  const maxVal = getRateMax(safeRate)
  const rateSplit = formatRateSplit(safeRate)
  const arcColor = isRx ? RX_COLOR : TX_COLOR
  const maxSplit = formatRateSplit(maxVal)

  return (
    <div className="rounded-card border border-line bg-panel p-[17px]">
      <div className="flex items-center justify-between text-[11px] text-muted">
        <span>{isRx ? "Download" : "Upload"}</span>
        <div
          className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2"
          style={{ color: arcColor }}
        >
          {isRx ? <ArrowDown size={15} /> : <ArrowUp size={15} />}
        </div>
      </div>

      <div className="mt-1 h-[170px]">
        <Gauge
          value={safeRate}
          min={0}
          max={maxVal}
          padding={24}
          transition
          initialValue={0}
        >
          <GaugeTrack width={28} cap="butt" />
          <GaugeArc width={28} cap="butt" color={arcColor} />
          <GaugeTicks count={50} length={6} width={2} offset={-30} cap="butt" opacity={0.4} />
          <GaugeTicks count={10} length={14} width={4} offset={-34} cap="butt" />
          <GaugeTickLabels
            count={5}
            offset={-66}
            fontSize={22}
            weight="semibold"
            format={(v) => {
              if (v === 0) return "0"
              const s = formatRateSplit(v)
              return `${s.value}`
            }}
          />
          <GaugeValue
            y={-8}
            fontSize={84}
            font="mono"
            format={() => rateSplit.value}
          />
          <GaugeText y={52} fontSize={22} color={MUTED_FG}>
            {rateSplit.unit} · max {maxSplit.value} {maxSplit.unit}
          </GaugeText>
        </Gauge>
      </div>

      <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
        <span>{subtext ?? "Realtime rate"}</span>
        <span className="text-ok font-medium">{statusText ?? "Live"}</span>
      </div>
    </div>
  )
}
