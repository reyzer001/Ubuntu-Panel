"use client";

import type { ReactNode } from "react";
import clsx from "clsx";

export function StatCard({
  label,
  icon,
  value,
  bottomLeft,
  bottomRight,
  valueTone,
}: {
  label: string;
  icon: ReactNode;
  value: ReactNode;
  bottomLeft?: ReactNode;
  bottomRight?: ReactNode;
  valueTone?: "positive" | "warning" | "negative" | undefined;
}) {
  return (
    <div className="rounded-card border border-line bg-panel p-[17px]">
      <div className="flex items-center justify-between text-[11px] text-muted">
        <span>{label}</span>
        <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2">
          {icon}
        </div>
      </div>
      <div
        className={clsx(
          "mt-3.5 text-[26px] font-bold",
          valueTone === "positive" && "text-ok",
          valueTone === "warning" && "text-warn",
          valueTone === "negative" && "text-bad"
        )}
      >
        {value}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted">
        <span>{bottomLeft}</span>
        <span>{bottomRight}</span>
      </div>
    </div>
  );
}
