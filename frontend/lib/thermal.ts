import type { TemperatureSensor } from "@/lib/types"

export interface ThermalThresholds {
  warm: number
  hot: number
}

export const DEFAULT_THERMAL_THRESHOLDS: ThermalThresholds = {
  warm: 70,
  hot: 85,
}

const CPU_CHIP_RE = /coretemp|k10temp|zenpower|x86_pkg_temp/i
const CPU_PRIMARY_RE = /package|tctl|tdie|physical id|cpu/i

export function tempTone(temp: number, thresholds = DEFAULT_THERMAL_THRESHOLDS) {
  if (temp >= thresholds.hot) {
    return { label: "Hot", color: "#ef4444", bar: "bg-bad" }
  }
  if (temp >= thresholds.warm) {
    return { label: "Warm", color: "#f59e0b", bar: "bg-warn" }
  }
  return { label: "Normal", color: "#22c55e", bar: "bg-ok" }
}

export function sensorRank(sensor: TemperatureSensor) {
  if (CPU_PRIMARY_RE.test(sensor.label)) return 0
  if (CPU_CHIP_RE.test(sensor.chip)) return 1
  return 2
}

export function pickPrimarySensor(
  sensors: TemperatureSensor[]
): TemperatureSensor | null {
  const ordered = [...sensors].sort((a, b) => sensorRank(a) - sensorRank(b))
  return (
    ordered.find((sensor) => CPU_PRIMARY_RE.test(sensor.label)) ??
    ordered[0] ??
    null
  )
}
