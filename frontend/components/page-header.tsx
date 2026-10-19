"use client";

import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  onRefresh,
  refreshing,
  right,
}: {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
  right?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle ? (
          <p className="mt-1.5 text-xs text-muted">{subtitle}</p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        {right}
        {onRefresh ? (
          <button
            className="btn flex items-center gap-2"
            onClick={onRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        ) : null}
      </div>
    </div>
  );
}
