"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  ToastStack,
  type ToastItem,
  type ToastOptions,
  type ToastVariant,
} from "@/components/ui/toast";
import { ConfirmProvider } from "@/components/ui/confirm-dialog";

export { useConfirm, type ConfirmOptions } from "@/components/ui/confirm-dialog";

const MAX_TOASTS = 4;

const DURATION_MAP: Record<ToastVariant, number> = {
  success: 3200,
  info: 3200,
  warning: 4500,
  error: 6000,
};

export interface ToastApi {
  /** Kompatibel dengan pemakaian lama: tampilkan pesan netral/info. */
  show: (message: string, opts?: Omit<ToastOptions, "description">) => void;
  success: (title: string, opts?: ToastOptions) => void;
  error: (title: string, opts?: ToastOptions) => void;
  warning: (title: string, opts?: ToastOptions) => void;
  info: (title: string, opts?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi>({
  show: () => {},
  success: () => {},
  error: () => {},
  warning: () => {},
  info: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 10_000, refetchOnWindowFocus: false },
        },
      })
  );

  return (
    <QueryClientProvider client={client}>
      <ToastHost>
        <ConfirmProvider>{children}</ConfirmProvider>
      </ToastHost>
    </QueryClientProvider>
  );
}

function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const timersRef = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (
      variant: ToastVariant,
      title: string,
      opts?: { description?: string; duration?: number }
    ) => {
      if (!title.trim()) return;
      const id = ++idRef.current;
      const duration = opts?.duration ?? DURATION_MAP[variant];
      setItems((prev) => [
        ...prev.slice(-(MAX_TOASTS - 1)),
        { id, variant, title, description: opts?.description, duration },
      ]);
      const timer = window.setTimeout(() => dismiss(id), duration);
      timersRef.current.set(id, timer);
    },
    [dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      show: (message, opts) => push("info", message, opts),
      success: (title, opts) => push("success", title, opts),
      error: (title, opts) => push("error", title, opts),
      warning: (title, opts) => push("warning", title, opts),
      info: (title, opts) => push("info", title, opts),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastStack items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
