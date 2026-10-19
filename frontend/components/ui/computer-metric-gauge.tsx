"use client"

import type { ReactNode } from "react"
import { Cpu, MemoryStick, ArrowDown, ArrowUp, Zap } from "lucide-react"
import {
  Gauge,
  GaugeArc,
  GaugeTrack,
  GaugeValue,
  GaugeText,
  GaugeTicks,
} from "@/components/gauge"

interface ComputerMetricGaugeProps {
  type: "cpu" | "mem" | "download" | "upload" | "latency"
  value: number | null | undefined
  secondaryValue?: number | null | undefined
  subtext?: string
  bare?: boolean
}

export function ComputerMetricGauge({
  type,
  value,
  secondaryValue,
  subtext,
  bare = false,
}: ComputerMetricGaugeProps) {
  const hasValue = value != null && Number.isFinite(value)
  const numVal = hasValue ? (value as number) : 0

  let title = ""
  let icon: ReactNode = null
  let max = 100
  let color = "#3b82f6"
  let unit = "%"
  let displayVal = hasValue ? `${Math.round(numVal)}` : "—"

  if (type === "cpu") {
    title = "CPU Load"
    icon = <Cpu size={13} className="text-[#3b82f6]" />
    max = 100
    color = numVal >= 90 ? "#ef4444" : numVal >= 75 ? "#f59e0b" : "#3b82f6"
    unit = "%"
    displayVal = hasValue ? `${Math.round(numVal)}` : "—"
  } else if (type === "mem") {
    title = "RAM Usage"
    icon = <MemoryStick size={13} className="text-[#8b5cf6]" />
    max = 100
    color = numVal >= 90 ? "#ef4444" : numVal >= 75 ? "#f59e0b" : "#8b5cf6"
    unit = "%"
    displayVal = hasValue ? `${Math.round(numVal)}` : "—"
  } else if (type === "download") {
    title = "Download"
    icon = <ArrowDown size={13} className="text-[#06b6d4]" />
    max = numVal > 100 ? Math.ceil(numVal / 50) * 50 : 100
    color = "#06b6d4"
    unit = "Mbps"
    displayVal = hasValue ? (numVal >= 10 ? numVal.toFixed(0) : numVal.toFixed(1)) : "—"
  } else if (type === "upload") {
    title = "Upload"
    icon = <ArrowUp size={13} className="text-[#a855f7]" />
    max = numVal > 50 ? Math.ceil(numVal / 25) * 25 : 50
    color = "#a855f7"
    unit = "Mbps"
    displayVal = hasValue ? (numVal >= 10 ? numVal.toFixed(0) : numVal.toFixed(1)) : "—"
  } else if (type === "latency") {
    title = "Latency"
    icon = <Zap size={13} className="text-[#10b981]" />
    max = 150
    color = numVal > 100 ? "#ef4444" : numVal > 40 ? "#f59e0b" : "#10b981"
    unit = "ms"
    displayVal = hasValue ? `${Math.round(numVal)}` : "—"
  }

  return (
    <div
      className={
        bare
          ? "flex flex-col items-center justify-between text-center"
          : "flex flex-col items-center justify-between rounded-xl border border-line bg-panel2/50 p-2.5 text-center transition hover:border-line-hover hover:bg-panel2/80"
      }
    >
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
        {icon}
        <span>{title}</span>
      </div>

      <div className="relative my-1 flex h-[82px] w-[95px] items-center justify-center">
        <Gauge
          value={hasValue ? Math.min(max, numVal) : 0}
          min={0}
          max={max}
          startAngle={35}
          endAngle={325}
          padding={14}
          transition
          initialValue={0}
        >
          <GaugeTrack width={18} color="#1e293b" opacity={0.6} cap="round" />
          {hasValue && (
            <GaugeArc width={18} color={color} cap="round" />
          )}
          <GaugeTicks count={20} length={4} width={2} offset={-20} cap="butt" opacity={0.3} />
          <GaugeValue
            y={-2}
            fontSize={52}
            font="mono"
            format={() => displayVal}
          />
          <GaugeText y={34} fontSize={18} color="#8794a4">
            {unit}
          </GaugeText>
        </Gauge>
      </div>

      <div className="text-[10px] text-muted truncate max-w-full px-1">
        {subtext ?? (
          type === "latency" && secondaryValue != null
            ? `srv: ${Math.round(secondaryValue)} ms`
            : hasValue
              ? `scale: ${max}${unit}`
              : "No metrics"
        )}
      </div>
    </div>
  )
}
