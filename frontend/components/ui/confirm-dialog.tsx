"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import clsx from "clsx";
import { AlertTriangle, ShieldAlert, type LucideIcon } from "lucide-react";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "danger" | "warning" | "primary";
}

interface ConfirmState extends Required<ConfirmOptions> {
  id: number;
}

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions | string) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: async () => false,
});

export function useConfirm() {
  return useContext(ConfirmContext);
}

const TONE_MAP: Record<
  ConfirmOptions["tone"] & string,
  { icon: LucideIcon; iconCls: string; btnCls: string; defaultTitle: string }
> = {
  danger: {
    icon: ShieldAlert,
    iconCls: "dialog-icon-danger",
    btnCls: "btn-danger",
    defaultTitle: "Konfirmasi aksi",
  },
  warning: {
    icon: AlertTriangle,
    iconCls: "dialog-icon-warning",
    btnCls: "btn-warning",
    defaultTitle: "Perhatian",
  },
  primary: {
    icon: AlertTriangle,
    iconCls: "dialog-icon-primary",
    btnCls: "btn-primary",
    defaultTitle: "Konfirmasi",
  },
};

function normalize(opts: ConfirmOptions | string): ConfirmState {
  const o = typeof opts === "string" ? { message: opts } : opts;
  const tone = o.tone ?? "danger";
  return {
    id: 0,
    title: o.title ?? TONE_MAP[tone].defaultTitle,
    message: o.message,
    confirmText: o.confirmText ?? (tone === "danger" ? "Ya, lanjutkan" : "Lanjutkan"),
    cancelText: o.cancelText ?? "Batal",
    tone,
  };
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);
  const resolveRef = useRef<((ok: boolean) => void) | null>(null);

  const settle = (ok: boolean) => {
    resolveRef.current?.(ok);
    resolveRef.current = null;
    setState(null);
  };

  const confirm = (opts: ConfirmOptions | string) => {
    if (resolveRef.current) resolveRef.current(false);
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setState({ ...normalize(opts), id: Date.now() });
    });
  };

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") settle(false);
      if (e.key === "Enter") settle(true);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.id]);

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state ? (
        <div
          className="dialog-overlay"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) settle(false);
          }}
        >
          <div
            key={state.id}
            className="dialog-card"
            role="alertdialog"
            aria-modal="true"
            aria-label={state.title}
          >
            {(() => {
              const { icon: Icon, iconCls, btnCls } = TONE_MAP[state.tone];
              return (
                <>
                  <div className="flex items-start gap-3">
                    <span className={clsx("dialog-icon", iconCls)}>
                      <Icon size={18} strokeWidth={2.2} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-bold leading-snug">
                        {state.title}
                      </div>
                      <div className="mt-1.5 whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-muted">
                        {state.message}
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 flex justify-end gap-2">
                    <button className="btn" onClick={() => settle(false)}>
                      {state.cancelText}
                    </button>
                    <button
                      className={clsx("btn", btnCls)}
                      autoFocus
                      onClick={() => settle(true)}
                    >
                      {state.confirmText}
                    </button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      ) : null}
    </ConfirmContext.Provider>
  );
}
