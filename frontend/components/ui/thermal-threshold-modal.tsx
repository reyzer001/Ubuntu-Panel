"use client"

import { useEffect, useState } from "react"
import { SlidersHorizontal, X } from "lucide-react"
import {
  DEFAULT_THERMAL_THRESHOLDS,
  type ThermalThresholds,
} from "@/lib/thermal"

interface ThermalThresholdModalProps {
  open: boolean
  initial: ThermalThresholds
  saving?: boolean
  onClose: () => void
  onSave: (thresholds: ThermalThresholds) => void
}

export function ThermalThresholdModal({
  open,
  initial,
  saving = false,
  onClose,
  onSave,
}: ThermalThresholdModalProps) {
  const [warm, setWarm] = useState(String(initial.warm))
  const [hot, setHot] = useState(String(initial.hot))

  useEffect(() => {
    if (!open) return
    setWarm(String(initial.warm))
    setHot(String(initial.hot))
  }, [open, initial.warm, initial.hot])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  const warmValue = Number(warm)
  const hotValue = Number(hot)
  const finite = Number.isFinite(warmValue) && Number.isFinite(hotValue)
  const error = !finite
    ? "Nilai threshold harus berupa angka."
    : warmValue < 0 || warmValue >= 125
      ? "Warm threshold harus 0 - 124 °C."
      : hotValue <= 0 || hotValue > 125
        ? "Hot threshold harus 1 - 125 °C."
        : hotValue <= warmValue
          ? "Hot threshold harus lebih besar dari Warm."
          : ""

  const submit = () => {
    if (error) return
    onSave({ warm: warmValue, hot: hotValue })
  }

  return (
    <div
      className="dialog-overlay"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className="dialog-card max-w-[420px] p-5"
        role="dialog"
        aria-modal="true"
        aria-label="Thermal Thresholds"
      >
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-line bg-panel2 text-muted">
              <SlidersHorizontal size={17} />
            </div>
            <div>
              <div className="text-sm font-bold text-fg">Thermal Thresholds</div>
              <div className="text-[11px] text-muted">
                Global untuk semua user panel
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

        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="block">
            <span className="info-label">Warm ≥</span>
            <div className="mt-1 flex items-center gap-1.5 rounded-lg border border-line bg-panel2 px-3 py-2">
              <input
                type="number"
                min={0}
                max={124}
                step={0.5}
                value={warm}
                onChange={(event) => setWarm(event.target.value)}
                className="w-full bg-transparent font-mono text-sm font-bold text-fg outline-none"
              />
              <span className="text-xs text-muted">°C</span>
            </div>
          </label>
          <label className="block">
            <span className="info-label">Hot ≥</span>
            <div className="mt-1 flex items-center gap-1.5 rounded-lg border border-line bg-panel2 px-3 py-2">
              <input
                type="number"
                min={1}
                max={125}
                step={0.5}
                value={hot}
                onChange={(event) => setHot(event.target.value)}
                className="w-full bg-transparent font-mono text-sm font-bold text-fg outline-none"
              />
              <span className="text-xs text-muted">°C</span>
            </div>
          </label>
        </div>

        <div className="mt-3 rounded-lg border border-line bg-panel2/50 px-3 py-2 text-[10px] leading-relaxed text-muted">
          Default: Warm {DEFAULT_THERMAL_THRESHOLDS.warm}°C, Hot{" "}
          {DEFAULT_THERMAL_THRESHOLDS.hot}°C. Dipakai untuk status kartu, warna
          sensor, dan garis threshold pada grafik.
        </div>

        {error ? (
          <div className="mt-2 text-[11px] text-bad">{error}</div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2 border-t border-line pt-3">
          <button type="button" onClick={onClose} className="btn px-3 py-1.5 text-xs">
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!!error || saving}
            className="btn btn-primary px-3 py-1.5 text-xs"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  )
}
