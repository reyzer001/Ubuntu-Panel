"use client";

import clsx from "clsx";

const MAP: Record<string, { cls: string; label: string }> = {
  running: { cls: "status-running", label: "RUNNING" },
  active: { cls: "status-running", label: "ACTIVE" },
  online: { cls: "status-running", label: "UP" },
  offline: { cls: "status-stopped", label: "OFFLINE" },
  allow: { cls: "status-running", label: "ALLOW" },
  success: { cls: "status-running", label: "SUCCESS" },
  done: { cls: "status-running", label: "DONE" },
  limit: { cls: "status-warning", label: "LIMIT" },
  stopped: { cls: "status-stopped", label: "STOPPED" },
  exited: { cls: "status-stopped", label: "EXITED" },
  dead: { cls: "status-stopped", label: "DEAD" },
  deny: { cls: "status-stopped", label: "DENY" },
  down: { cls: "status-stopped", label: "DOWN" },
  failed: { cls: "status-stopped", label: "FAILED" },
  warning: { cls: "status-warning", label: "WARNING" },
   info: { cls: "status-info", label: "INFO" },
  waiting: { cls: "status-warning", label: "WAITING" },
};

export function StatusBadge({ status }: { status: string }) {
  const item =
    MAP[status.toLowerCase()] ?? { cls: "status-info", label: status.toUpperCase() };
  return (
    <span className={clsx("status", item.cls)}>{item.label}</span>
  );
}
