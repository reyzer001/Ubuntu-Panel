"use client"

import { Gauge, GaugeArc, GaugeTrack, GaugeValue } from "@/components/gauge"

const ACTIVE_THRESHOLD = 10

function coreColor(value: number) {
  if (value >= 90) return "#ef4444"
  if (value >= 75) return "#f59e0b"
  if (value >= ACTIVE_THRESHOLD) return "#3b82f6"
  return "#64748b"
}

export function CoreGaugeGrid({ cores }: { cores?: number[] }) {
  const list = cores ?? []

  if (list.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-panel2/40 p-4 text-center text-xs text-muted">
        Per-core data belum tersedia. Tunggu sampel metrik berikutnya.
      </div>
    )
  }

  const active = list.filter((value) => value >= ACTIVE_THRESHOLD).length

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs font-semibold text-fg">
        <span>Per-Core Utilization</span>
        <span className="text-[11px] font-medium text-muted">
          <span className="font-mono font-bold text-ok">{active}</span> /{" "}
          {list.length} core bekerja
        </span>
      </div>
      <div className="grid max-h-[320px] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3 md:grid-cols-4">
        {list.map((value, index) => {
          const isActive = value >= ACTIVE_THRESHOLD
          const color = coreColor(value)
          return (
            <div
              key={index}
              className="rounded-lg border p-2 text-center transition"
              style={{
                borderColor: isActive ? `${color}80` : undefined,
                backgroundColor: isActive ? `${color}0d` : undefined,
              }}
            >
              <div className="relative mx-auto h-[86px] w-[86px]">
                <Gauge
                  value={value}
                  min={0}
                  max={100}
                  startAngle={30}
                  endAngle={330}
                  padding={6}
                  transition
                  initialValue={0}
                >
                  <GaugeTrack width={12} color="#1e293b" opacity={0.7} cap="round" />
                  <GaugeArc width={12} color={color} cap="round" />
                  <GaugeValue
                    y={0}
                    fontSize={58}
                    font="mono"
                    format={(v) => `${Math.round(v)}%`}
                  />
                </Gauge>
              </div>
              <div className="mt-1 flex items-center justify-center gap-1.5 text-[10px]">
                <span className="font-semibold text-fg">Core {index}</span>
                <span
                  className="rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide"
                  style={{
                    color,
                    backgroundColor: `${color}1a`,
                  }}
                >
                  {isActive ? "Active" : "Idle"}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
