import clsx from "clsx";

export function formatBytes(bytes: number, digits = 1): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : digits)} ${units[i]}`;
}

export function formatRate(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond)) return "0 B/s";
  // trafik idle (<1 KB/s) sebelumnya dibulatkan jadi "0 KB/s"
  // sehingga dikira sensor mati — tampilkan B/s apa adanya.
  if (bytesPerSecond < 1024)
    return `${Math.max(0, Math.round(bytesPerSecond))} B/s`;
  const mb = bytesPerSecond / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(1)} MB/s`;
  const kb = bytesPerSecond / 1024;
  return `${kb.toFixed(0)} KB/s`;
}

export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${String(hours).padStart(2, "0")}h`;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${minutes}m`;
}

export type Tone = "blue" | "purple" | "orange" | "red";

export function usageTone(percent: number): Tone {
  if (percent >= 90) return "red";
  if (percent >= 75) return "orange";
  if (percent >= 50) return "purple";
  return "blue";
}

export const toneBarClass: Record<Tone, string> = {
  blue: "bg-ok",
  purple: "bg-ok",
  orange: "bg-warn",
  red: "bg-bad",
};

export function cx(...parts: Array<string | false | null | undefined>): string {
  return clsx(...parts);
}
