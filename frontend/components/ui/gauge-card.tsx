"use client"

import type { ReactNode } from "react"
import {
  Gauge,
  GaugeArc,
  GaugeInset,
  GaugeMarks,
  GaugeStack,
  GaugeText,
  GaugeTicks,
  GaugeTickLabels,
  GaugeTrack,
  GaugeValue,
  GaugeZones,
} from "@/components/gauge"
import { usageTone, type Tone } from "@/lib/format"

// warna monokrom persis seperti MonitorDashboard gauge-ui.dev
const FG = "#eef3f8"
const MUTED_FG = "#8794a4"
const CARD = "#111821"

// zona ambang load: normal < 75, elevated 75-90, kritis >= 90
const LOAD_ZONES = [
  { to: 75, color: "transparent" },
  { to: 100, color: FG },
]

const TONE_HEX: Record<Tone, string> = {
  blue: "#22c55e",
  purple: "#22c55e",
  orange: "#f59e0b",
  red: "#ef4444",
}

const defaultFormat = (v: number) => `${Math.round(v)}%`

export function GaugeCard({
  variant,
  label,
  icon,
  subtext,
  statusText,
  gaugeValue,
  gaugeMax = 100,
  kernel = 0.2,
  active = 0,
  inactive = 0,
  cached = 0,
  swap = 0,
  gaugeText,
  format,
  onClick,
}: {
  variant: "cpu" | "memory" | "storage" | "load"
  label: string
  icon: ReactNode
  subtext?: ReactNode
  statusText?: ReactNode
  /** persen (cpu/storage/load) atau GB terpakai (memory) */
  gaugeValue: number
  /** total GB (memory) */
  gaugeMax?: number
  /** share sistem dari CPU sibuk (cpu) */
  kernel?: number
  /** GB aktif (memory) */
  active?: number
  /** GB tidak aktif (memory) */
  inactive?: number
  /** GB cache (memory) */
  cached?: number
  /** persen swap terpakai (memory) */
  swap?: number
  /** teks keterangan di bawah nilai gauge */
  gaugeText?: string
  format?: (value: number) => string
  onClick?: () => void
}) {
  const pct = gaugeMax <= 0 ? 0 : Math.min(100, (gaugeValue / gaugeMax) * 100)
  const tone = TONE_HEX[usageTone(pct)]
  const valueFormat = (v: number) => (format ? format(v) : defaultFormat(v))

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                onClick()
              }
            }
          : undefined
      }
      className={`rounded-card border border-line bg-panel p-[17px] transition ${
        onClick
          ? "cursor-pointer hover:border-line-hover hover:bg-panel2/30 hover:shadow-lg focus:outline-none focus:ring-1 focus:ring-line-hover"
          : ""
      }`}
    >
      <div className="flex items-center justify-between text-[11px] text-muted">
        <span>{label}</span>
        <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2">{icon}</div>
      </div>
      <div className="mt-1 h-[170px]">
        {variant === "cpu" && (
          <Gauge value={gaugeValue} min={0} max={100} padding={24} transition initialValue={0}>
            <GaugeTrack width={28} cap="butt" />
            <GaugeStack
              width={28}
              parts={[
                { weight: 1 - kernel, color: FG },
                { weight: kernel, color: MUTED_FG, opacity: 0.6 },
              ]}
            />
            <GaugeTicks count={50} length={6} width={2} offset={-30} cap="butt" opacity={0.4} />
            <GaugeTicks count={10} length={14} width={4} offset={-34} cap="butt" />
            <GaugeTickLabels count={5} offset={-66} fontSize={22} weight="semibold" />
            <GaugeValue y={-8} fontSize={88} font="mono" format={valueFormat} />
            <GaugeText y={52} fontSize={24} color={MUTED_FG}>
              % busy
            </GaugeText>
          </Gauge>
        )}
        {variant === "memory" && (
          <Gauge value={gaugeValue} min={0} max={gaugeMax} padding={20} transition initialValue={0}>
            <GaugeTrack width={32} cap="butt" />
            <GaugeStack
              width={32}
              parts={[
                { weight: active, color: FG },
                { weight: inactive, color: FG, opacity: 0.55 },
                { weight: cached, color: MUTED_FG, opacity: 0.35 },
              ]}
            />
            <GaugeMarks count={4} length={36} width={6} cap="butt" color={CARD} />
            <GaugeInset value={swap} min={0} max={100} transition initialValue={0}>
              <GaugeTrack width={10} offset={-40} cap="butt" />
              <GaugeArc width={10} offset={-40} cap="butt" color={MUTED_FG} />
            </GaugeInset>
            <GaugeValue y={-8} fontSize={80} font="mono" decimals={1} />
            <GaugeText y={52} fontSize={24} color={MUTED_FG}>
              of {gaugeMax.toFixed(0)} GB
            </GaugeText>
          </Gauge>
        )}
        {variant === "storage" && (
          <Gauge value={gaugeValue} min={0} max={gaugeMax} padding={24} transition initialValue={0}>
            <GaugeTrack width={28} cap="butt" />
            <GaugeArc width={28} cap="butt" color={FG} />
            <GaugeTicks count={50} length={6} width={2} offset={-30} cap="butt" opacity={0.4} />
            <GaugeTicks count={10} length={14} width={4} offset={-34} cap="butt" />
            <GaugeTickLabels count={5} offset={-66} fontSize={22} weight="semibold" format={(v) => v.toFixed(0)} />
            <GaugeValue y={-8} fontSize={88} font="mono" decimals={0} />
            <GaugeText y={52} fontSize={24} color={MUTED_FG}>
              of {gaugeMax.toFixed(0)} GB
            </GaugeText>
          </Gauge>
        )}
        {variant === "load" && (
          <Gauge value={gaugeValue} min={0} max={100} padding={24} transition initialValue={0}>
            <GaugeTrack width={28} cap="butt" />
            <GaugeZones zones={LOAD_ZONES} width={28} />
            <GaugeTicks count={50} length={6} width={2} offset={-30} cap="butt" opacity={0.4} />
            <GaugeTicks count={10} length={14} width={4} offset={-34} cap="butt" />
            <GaugeTickLabels count={5} offset={-66} fontSize={22} weight="semibold" />
            <GaugeValue y={-8} fontSize={88} font="mono" format={valueFormat} />
            <GaugeText y={52} fontSize={24} color={MUTED_FG}>
              {gaugeText ?? "load avg"}
            </GaugeText>
          </Gauge>
        )}
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
        <span>{subtext}</span>
        <span style={{ color: tone }}>{statusText}</span>
      </div>
    </div>
  )
}
