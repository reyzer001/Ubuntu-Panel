"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  ExternalLink,
  KeyRound,
  ShieldAlert,
} from "lucide-react";
import clsx from "clsx";
import { useToast } from "@/components/providers";
import { api, ApiError } from "@/lib/api";
import type { MyzrokStatus } from "@/lib/types";
import { useAuth } from "@/store/auth";

type Mode = "enable" | "disable";

export function MyzrokToggle() {
  const role = useAuth((s) => s.user?.role);
  const isSuperadmin = role === "superadmin";
  const toast = useToast();
  const queryClient = useQueryClient();

  const [mode, setMode] = useState<Mode | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const statusQuery = useQuery({
    queryKey: ["myzrok-status"],
    queryFn: () => api<MyzrokStatus>("/myzrok/status"),
    enabled: isSuperadmin,
    refetchInterval: 10_000,
    retry: false,
  });

  const status = statusQuery.data;
  const running = Boolean(status?.running);

  const toggle = useMutation({
    mutationFn: async ({
      mode,
      password,
    }: {
      mode: Mode;
      password: string;
    }) => {
      const step = await api<{ elevated_token: string; expires_in: number }>(
        "/auth/step-up",
        {
          method: "POST",
          body: JSON.stringify({ password, scope: "myzrok" }),
        }
      );
      useAuth
        .getState()
        .setElevated("myzrok", step.elevated_token, step.expires_in ?? 300);
      return api<MyzrokStatus>(`/myzrok/${mode}`, {
        method: "POST",
        elevated: "myzrok",
      });
    },
    onSuccess: (data, vars) => {
      queryClient.setQueryData(["myzrok-status"], data);
      setMode(null);
      setError("");
      toast.success(
        vars.mode === "enable"
          ? "Akses publik aktif"
          : "Akses publik dimatikan",
        {
          description:
            vars.mode === "enable" ? data.login_url : undefined,
        }
      );
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 428) {
        useAuth.getState().clearElevated("myzrok");
      }
      setError(
        err instanceof ApiError ? err.message : "Gagal memproses permintaan"
      );
    },
    onSettled: () => {
      useAuth.getState().clearElevated("myzrok");
    },
  });

  useEffect(() => {
    if (
      statusQuery.error instanceof ApiError &&
      statusQuery.error.status === 428
    ) {
      useAuth.getState().clearElevated("myzrok");
    }
  }, [statusQuery.error]);

  if (!isSuperadmin) return null;

  const openDialog = () => {
    setError("");
    setMode(running ? "disable" : "enable");
  };

  const copyLink = async () => {
    if (!status?.login_url) return;
    try {
      await navigator.clipboard.writeText(status.login_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Gagal menyalin link");
    }
  };

  return (
    <>
      <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-2.5 py-1.5">
        <span
          className={clsx(
            "h-2 w-2 shrink-0 rounded-full",
            running
              ? "bg-ok shadow-[0_0_8px_#22c55e]"
              : "bg-muted2"
          )}
        />
        <div className="hidden leading-tight sm:block">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted2">
            Public
          </div>
          <div
            className={clsx(
              "text-[10px] font-semibold",
              running ? "text-ok" : "text-muted"
            )}
          >
            {running ? "Online" : "Offline"}
          </div>
        </div>
        {running && status?.login_url ? (
          <>
            <button
              type="button"
              className="action-btn"
              title="Buka halaman login"
              onClick={() =>
                window.open(
                  status.login_url,
                  "_blank",
                  "noopener,noreferrer"
                )
              }
            >
              <ExternalLink size={12} />
            </button>
            <button
              type="button"
              className="action-btn"
              title="Salin link login"
              onClick={copyLink}
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
            </button>
          </>
        ) : null}
        <button
          type="button"
          role="switch"
          aria-checked={running}
          aria-label="Akses publik lewat myzrok"
          title={running ? "Matikan akses publik" : "Aktifkan akses publik"}
          disabled={statusQuery.isLoading || toggle.isPending}
          onClick={openDialog}
          className={clsx(
            "relative h-5 w-9 shrink-0 rounded-full border transition-colors",
            running
              ? "border-ok/60 bg-ok/30"
              : "border-line bg-panel2"
          )}
        >
          <span
            className={clsx(
              "absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-transform",
              running ? "translate-x-[18px]" : "translate-x-0.5"
            )}
          />
        </button>
      </div>

      {mode ? (
        <PasswordDialog
          mode={mode}
          pending={toggle.isPending}
          error={error}
          onClose={() => {
            if (toggle.isPending) return;
            setMode(null);
            setError("");
          }}
          onSubmit={(password) => toggle.mutate({ mode, password })}
        />
      ) : null}
    </>
  );
}

function PasswordDialog({
  mode,
  pending,
  error,
  onSubmit,
  onClose,
}: {
  mode: Mode;
  pending: boolean;
  error: string;
  onSubmit: (password: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");
  const enable = mode === "enable";

  useEffect(() => {
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !pending) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [pending, onClose]);

  const submit = () => {
    if (pending || !value) return;
    onSubmit(value);
  };

  return (
    <div
      className="dialog-overlay"
      role="presentation"
      onMouseDown={(e) =>
        e.target === e.currentTarget && !pending && onClose()
      }
    >
      <div
        className="dialog-card"
        role="dialog"
        aria-modal="true"
        aria-label="Verifikasi password akses publik"
      >
        <div className="flex items-start gap-3">
          <span className="dialog-icon dialog-icon-warning">
            <KeyRound size={18} strokeWidth={2.2} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-bold leading-snug">
              {enable ? "Aktifkan akses publik" : "Matikan akses publik"}
            </div>
            <div className="mt-1 text-[11.5px] leading-relaxed text-muted">
              {enable
                ? "Panel akan diakses lewat myzrok dengan link menuju halaman login. Masukkan password akun panel Anda untuk melanjutkan."
                : "Akses publik akan dihentikan dan link myzrok tidak bisa dipakai lagi. Masukkan password akun panel Anda untuk konfirmasi."}
            </div>
          </div>
        </div>

        <label className="mt-4 block text-[11px] text-muted">
          Password
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            className="input mt-1 w-full"
            placeholder="password akun panel"
            value={value}
            disabled={pending}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
        </label>

        {error ? (
          <div className="mt-2 flex items-start gap-1.5 text-[11px] text-[#ff9b9b]">
            <ShieldAlert size={13} className="mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        ) : null}

        <div className="mt-2 text-[10px] leading-relaxed text-muted">
          Password hanya dipakai sekali untuk verifikasi dan tidak disimpan.
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" disabled={pending} onClick={onClose}>
            Batal
          </button>
          <button
            className={clsx(
              "btn",
              enable ? "btn-primary" : "btn-danger"
            )}
            disabled={pending || !value}
            onClick={submit}
          >
            {pending
              ? enable
                ? "Mengaktifkan…"
                : "Mematikan…"
              : enable
                ? "Aktifkan"
                : "Matikan"}
          </button>
        </div>
      </div>
    </div>
  );
}
