"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface ToastOptions {
  title?: string;
  description?: string;
  duration?: number;
}

export interface ToastItem extends Required<Pick<ToastOptions, "title">> {
  id: number;
  variant: ToastVariant;
  description?: string;
  duration: number;
}

const VARIANT_MAP: Record<
  ToastVariant,
  { icon: LucideIcon; cls: string; barCls: string }
> = {
  success: { icon: CheckCircle2, cls: "toast-success", barCls: "bg-[#9df2b8]" },
  error: { icon: XCircle, cls: "toast-error", barCls: "bg-[#ffabab]" },
  warning: { icon: AlertTriangle, cls: "toast-warning", barCls: "bg-[#ffd58a]" },
  info: { icon: Info, cls: "toast-info", barCls: "bg-[#9fc5ff]" },
};

export function ToastStack({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="toast-viewport" aria-live="polite">
      {items.map((t) => (
        <ToastCard key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastCard({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: (id: number) => void;
}) {
  const { icon: Icon, cls, barCls } = VARIANT_MAP[item.variant];

  return (
    <div className={clsx("toast-item toast-show", cls)} role="alert">
      <div className="mt-0.5 shrink-0">
        <Icon size={16} strokeWidth={2.4} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="pr-1 text-[11px] font-bold leading-snug">{item.title}</div>
        {item.description ? (
          <div className="mt-0.5 whitespace-pre-wrap break-words text-[11px] leading-snug text-muted">
            {item.description}
          </div>
        ) : null}
      </div>
      <button
        className="toast-close"
        aria-label="Tutup notifikasi"
        onClick={() => onDismiss(item.id)}
      >
        <X size={13} />
      </button>
      <span
        className={clsx("toast-progress", barCls)}
        style={{ animationDuration: `${item.duration}ms` }}
      />
    </div>
  );
}
