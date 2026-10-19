"use client"

import { ArrowDown, ArrowUp } from "lucide-react"
import {
  Gauge,
  GaugeArc,
  GaugeTrack,
  GaugeValue,
  GaugeText,
} from "@/components/gauge"

const RX_COLOR = "#3b82f6"
const TX_COLOR = "#8b5cf6"
const MUTED_FG = "#8794a4"

function getRateMax(bytesPerSec: number): number {
  const kb = bytesPerSec / 1024
  if (kb <= 100) return 100 * 1024
  if (kb <= 500) return 500 * 1024
  if (kb <= 1024) return 1024 * 1024
  if (kb <= 5 * 1024) return 5 * 1024 * 1024
  if (kb <= 10 * 1024) return 10 * 1024 * 1024
  if (kb <= 50 * 1024) return 50 * 1024 * 1024
  if (kb <= 100 * 1024) return 100 * 1024 * 1024
  return Math.ceil(bytesPerSec / (100 * 1024 * 1024)) * 100 * 1024 * 1024
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

export function MiniNetworkGauge({
  variant,
  rate,
}: {
  variant: "download" | "upload"
  rate: number
}) {
  const isRx = variant === "download"
  const color = isRx ? RX_COLOR : TX_COLOR
  const safeRate = Math.max(0, Number.isFinite(rate) ? rate : 0)
  const max = getRateMax(safeRate)
  const split = formatRateSplit(safeRate)

  return (
    <div className="flex flex-col items-center rounded-lg border border-line bg-panel2/60 p-2 text-center">
      <div className="flex items-center gap-1 text-[11px] font-medium" style={{ color }}>
        {isRx ? <ArrowDown size={13} /> : <ArrowUp size={13} />}
        <span>{isRx ? "Download" : "Upload"}</span>
      </div>

      <div className="relative my-0.5 h-[80px] w-[110px]">
        <Gauge
          value={safeRate}
          min={0}
          max={max}
          padding={16}
          transition
          initialValue={0}
        >
          <GaugeTrack width={20} cap="butt" />
          <GaugeArc width={20} cap="butt" color={color} />
          <GaugeValue
            y={-2}
            fontSize={58}
            font="mono"
            format={() => split.value}
          />
          <GaugeText y={36} fontSize={18} color={MUTED_FG}>
            {split.unit}
          </GaugeText>
        </Gauge>
      </div>

      <div className="text-[10px] text-muted">
        max {formatRateSplit(max).value} {formatRateSplit(max).unit}
      </div>
    </div>
  )
}
