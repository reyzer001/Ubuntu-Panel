"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Mail, PlugZap, Plus, Send, Wifi, X } from "lucide-react";
import { useToast } from "@/components/providers";
import { api, ApiError } from "@/lib/api";
import type { ReportSettings, SmtpTestResult } from "@/lib/types";
import clsx from "clsx";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const CRON_PRESETS = [
  { label: "Harian 07:00", value: "0 7 * * *" },
  { label: "Harian 00:00", value: "0 0 * * *" },
  { label: "Senin 07:00", value: "0 7 * * 1" },
  { label: "Tanggal 1, 07:00", value: "0 7 1 * *" },
];

type Security = "tls" | "ssl" | "none";

type FormState = {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  from_addr: string;
  security: Security;
  schedule: string;
  recipients: string[];
  hours: number;
  isp_download_mbps: string;
  isp_upload_mbps: string;
};

function initialForm(settings?: ReportSettings): FormState {
  if (!settings) {
    return {
      enabled: false,
      smtp_host: "",
      smtp_port: 587,
      smtp_username: "",
      smtp_password: "",
      from_addr: "",
      security: "tls",
      schedule: "0 7 * * *",
      recipients: [],
      hours: 24,
      isp_download_mbps: "",
      isp_upload_mbps: "",
    };
  }
  const security: Security = settings.smtp_ssl
    ? "ssl"
    : settings.smtp_tls
      ? "tls"
      : "none";
  return {
    enabled: settings.enabled,
    smtp_host: settings.smtp_host,
    smtp_port: settings.smtp_port || 587,
    smtp_username: settings.smtp_username,
    smtp_password: "",
    from_addr: settings.from_addr,
    security,
    schedule: settings.schedule || "0 7 * * *",
    recipients: [...(settings.recipients || [])],
    hours: settings.hours || 24,
    isp_download_mbps:
      settings.isp_download_mbps != null
        ? String(settings.isp_download_mbps)
        : "",
    isp_upload_mbps:
      settings.isp_upload_mbps != null
        ? String(settings.isp_upload_mbps)
        : "",
  };
}

export function EmailSettingsModal({
  settings,
  loading = false,
  loadError = "",
  onRetry,
  onClose,
}: {
  settings?: ReportSettings;
  loading?: boolean;
  loadError?: string;
  onRetry?: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(() => initialForm(settings));
  const [recipientInput, setRecipientInput] = useState("");
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState<SmtpTestResult | null>(null);
  const synced = useRef(settings !== undefined);

  const set = (patch: Partial<FormState>) =>
    setForm((current) => ({ ...current, ...patch }));

  useEffect(() => {
    if (settings && !synced.current) {
      setForm(initialForm(settings));
      synced.current = true;
    }
  }, [settings]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = useMutation({
    mutationFn: (body: FormState) =>
      api<ReportSettings>("/report/settings", {
        method: "PUT",
        body: JSON.stringify({
          ...body,
          smtp_tls: body.security === "tls",
          smtp_ssl: body.security === "ssl",
          recipients: body.recipients,
          isp_download_mbps:
            body.isp_download_mbps.trim() === ""
              ? null
              : Number(body.isp_download_mbps),
          isp_upload_mbps:
            body.isp_upload_mbps.trim() === ""
              ? null
              : Number(body.isp_upload_mbps),
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report-settings"] });
      toast.success("Pengaturan email report disimpan");
      onClose();
    },
    onError: (err) =>
      setError(
        err instanceof ApiError ? err.message : "Gagal menyimpan pengaturan"
      ),
  });

  const test = useMutation({
    mutationFn: () =>
      api<SmtpTestResult>("/report/smtp/test", {
        method: "POST",
        body: JSON.stringify({
          smtp_host: form.smtp_host,
          smtp_port: form.smtp_port,
          smtp_username: form.smtp_username,
          smtp_password: form.smtp_password,
          smtp_tls: form.security === "tls",
          smtp_ssl: form.security === "ssl",
          from_addr: form.from_addr,
        }),
      }),
    onSuccess: (res) => {
      const result = {
        ok: res.ok !== false,
        message: res.message || "Koneksi SMTP berhasil",
      };
      setTestResult(result);
      toast.success(result.message);
    },
    onError: (err) => {
      const message =
        err instanceof ApiError ? err.message : "Gagal menguji koneksi SMTP";
      setTestResult({ ok: false, message });
      toast.error(message);
    },
  });

  const addRecipient = () => {
    const email = recipientInput.trim();
    if (!email) return;
    if (!EMAIL_RE.test(email)) {
      setError("Format email penerima tidak valid");
      return;
    }
    if (
      form.recipients.some((item) => item.toLowerCase() === email.toLowerCase())
    ) {
      setError("Email tersebut sudah ada di daftar penerima");
      return;
    }
    set({ recipients: [...form.recipients, email] });
    setRecipientInput("");
    setError("");
  };

  const removeRecipient = (email: string) => {
    set({ recipients: form.recipients.filter((item) => item !== email) });
  };

  const submit = () => {
    setError("");
    let recipients = form.recipients;
    const pending = recipientInput.trim();
    if (pending) {
      if (!EMAIL_RE.test(pending)) {
        setError("Format email penerima tidak valid");
        return;
      }
      if (
        !recipients.some(
          (item) => item.toLowerCase() === pending.toLowerCase()
        )
      ) {
        recipients = [...recipients, pending];
      }
    }
    if (form.enabled && !form.smtp_host.trim()) {
      setError("SMTP host wajib diisi saat pengiriman otomatis aktif");
      return;
    }
    if (form.enabled && recipients.length === 0) {
      setError("Tambahkan minimal satu penerima email");
      return;
    }
    if (
      form.enabled &&
      !form.from_addr.trim() &&
      !form.smtp_username.trim()
    ) {
      setError("Isi email pengirim atau username SMTP");
      return;
    }
    if (!form.schedule.trim()) {
      setError("Jadwal cron wajib diisi");
      return;
    }
    if (
      !Number.isFinite(form.smtp_port) ||
      form.smtp_port < 1 ||
      form.smtp_port > 65535
    ) {
      setError("Port SMTP tidak valid");
      return;
    }
    for (const [value, label] of [
      [form.isp_download_mbps, "Batas download ISP"],
      [form.isp_upload_mbps, "Batas upload ISP"],
    ] as const) {
      if (value.trim() === "") continue;
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        setError(`${label} harus berupa angka lebih dari 0`);
        return;
      }
    }
    save.mutate({ ...form, recipients });
  };

  const runTest = () => {
    setError("");
    setTestResult(null);
    if (!form.smtp_host.trim()) {
      setError("SMTP host wajib diisi");
      return;
    }
    if (
      !Number.isFinite(form.smtp_port) ||
      form.smtp_port < 1 ||
      form.smtp_port > 65535
    ) {
      setError("Port SMTP tidak valid");
      return;
    }
    test.mutate();
  };

  return (
    <div
      className="dialog-overlay"
      onMouseDown={(event) =>
        event.target === event.currentTarget && onClose()
      }
    >
      <div
        className="dialog-card !max-w-2xl max-h-[88vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-label="Pengaturan Email Report"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="card-title">Pengaturan Email</div>
            <div className="card-subtitle">
              Atur pengirim, penerima, dan jadwal pengiriman report
            </div>
          </div>
          <button
            type="button"
            className="btn flex h-8 w-8 items-center justify-center !p-0"
            onClick={onClose}
            title="Tutup"
          >
            <X size={14} />
          </button>
        </div>

        {!settings ? (
          <div className="rounded-lg border border-line bg-panel2 px-3 py-4 text-[11px]">
            {loadError ? (
              <>
                <div className="text-bad">{loadError}</div>
                {onRetry ? (
                  <button
                    type="button"
                    className="btn mt-2"
                    onClick={onRetry}
                  >
                    Coba lagi
                  </button>
                ) : null}
              </>
            ) : (
              <div className="text-muted2">
                {loading
                  ? "Memuat pengaturan email…"
                  : "Pengaturan email belum tersedia."}
              </div>
            )}
          </div>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
          <section>
            <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-muted2">
              <Send size={12} /> Pengirim
            </div>

            <label className="flex cursor-pointer items-center justify-between rounded-lg border border-line bg-panel2 px-3 py-2.5">
              <div>
                <div className="text-[11px] font-semibold text-muted">
                  Kirim otomatis
                </div>
                <div className="text-[10px] text-muted2">
                  Email dikirim sesuai jadwal cron di bawah
                </div>
              </div>
              <input
                type="checkbox"
                className="h-4 w-4 accent-[#5ea5ff]"
                checked={form.enabled}
                onChange={(event) => set({ enabled: event.target.checked })}
              />
            </label>

            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-muted">
                SMTP Host
                <input
                  className="input mt-1 w-full"
                  placeholder="smtp.gmail.com"
                  value={form.smtp_host}
                  onChange={(event) =>
                    set({ smtp_host: event.target.value })
                  }
                />
              </label>
              <label className="text-[11px] text-muted">
                Port
                <input
                  type="number"
                  className="input mt-1 w-full"
                  value={form.smtp_port}
                  onChange={(event) =>
                    set({ smtp_port: Number(event.target.value) })
                  }
                />
              </label>
              <label className="text-[11px] text-muted">
                Username SMTP
                <input
                  className="input mt-1 w-full"
                  placeholder="ops@example.com"
                  value={form.smtp_username}
                  onChange={(event) =>
                    set({ smtp_username: event.target.value })
                  }
                />
              </label>
              <label className="text-[11px] text-muted">
                Password SMTP
                <input
                  type="password"
                  className="input mt-1 w-full"
                  placeholder={
                    settings.smtp_password_set
                      ? "Tersimpan (kosongkan jika tidak diubah)"
                      : "Password SMTP"
                  }
                  value={form.smtp_password}
                  onChange={(event) =>
                    set({ smtp_password: event.target.value })
                  }
                />
                <span className="mt-1 block text-[10px] text-muted2">
                  Gmail: gunakan App Password 16 karakter (aktifkan 2FA),
                  bukan password login.
                </span>
              </label>
              <label className="text-[11px] text-muted">
                Email Pengirim
                <input
                  type="email"
                  className="input mt-1 w-full"
                  placeholder="panel@example.com"
                  value={form.from_addr}
                  onChange={(event) =>
                    set({ from_addr: event.target.value })
                  }
                />
              </label>
              <label className="text-[11px] text-muted">
                Keamanan
                <select
                  className="input mt-1 w-full"
                  value={form.security}
                  onChange={(event) =>
                    set({ security: event.target.value as Security })
                  }
                >
                  <option value="tls">STARTTLS</option>
                  <option value="ssl">SSL</option>
                  <option value="none">Tidak ada</option>
                </select>
              </label>
              <label className="text-[11px] text-muted sm:col-span-2">
                Jadwal Cron
                <input
                  className="input mt-1 w-full"
                  placeholder="0 7 * * *"
                  value={form.schedule}
                  onChange={(event) => set({ schedule: event.target.value })}
                />
              </label>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-muted2">Preset:</span>
              {CRON_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className={clsx(
                    "rounded-full border px-2.5 py-1 text-[10px] transition-colors",
                    form.schedule === preset.value
                      ? "border-[#2865b2] bg-[#1b4d90] text-white"
                      : "border-line bg-panel2 text-muted hover:bg-panel3"
                  )}
                  onClick={() => set({ schedule: preset.value })}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="mt-1.5 text-[10px] text-muted2">
              Format cron: menit jam tanggal bulan hari. Contoh 0 7 * * * =
              setiap hari pukul 07:00 waktu server.
            </div>
          </section>

          <section className="mt-5 border-t border-line pt-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-muted2">
              <Mail size={12} /> Penerima
            </div>

            <div className="space-y-1.5">
              {form.recipients.length === 0 ? (
                <div className="rounded-lg border border-dashed border-line px-3 py-4 text-center text-[11px] text-muted2">
                  Belum ada penerima. Tambahkan email di bawah.
                </div>
              ) : (
                form.recipients.map((email) => (
                  <div
                    key={email}
                    className="flex items-center justify-between gap-3 rounded-lg border border-line bg-panel2 px-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-2 text-[11px] text-muted">
                      <Mail size={12} className="shrink-0 text-muted2" />
                      <span className="truncate">{email}</span>
                    </div>
                    <button
                      type="button"
                      className="action-btn shrink-0"
                      onClick={() => removeRecipient(email)}
                      title={`Hapus ${email}`}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="mt-2 flex gap-2">
              <input
                type="email"
                className="input w-full"
                placeholder="nama@domain.com"
                value={recipientInput}
                onChange={(event) => setRecipientInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addRecipient();
                  }
                }}
              />
              <button
                type="button"
                className="btn btn-primary flex shrink-0 items-center gap-1.5"
                onClick={addRecipient}
              >
                <Plus size={13} /> Tambah
              </button>
            </div>
          </section>

          <section className="mt-5 border-t border-line pt-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-muted2">
              <Wifi size={12} /> Batas ISP
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="text-[11px] text-muted">
                Batas download (Mbps)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className="input mt-1 w-full"
                  placeholder="Contoh: 100"
                  value={form.isp_download_mbps}
                  onChange={(event) =>
                    set({ isp_download_mbps: event.target.value })
                  }
                />
              </label>
              <label className="text-[11px] text-muted">
                Batas upload (Mbps)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className="input mt-1 w-full"
                  placeholder="Contoh: 50"
                  value={form.isp_upload_mbps}
                  onChange={(event) =>
                    set({ isp_upload_mbps: event.target.value })
                  }
                />
              </label>
            </div>
            <div className="mt-1.5 text-[10px] text-muted2">
              Opsional. Dipakai untuk membandingkan puncak speed test dengan
              batas bandwidth ISP. Kosongkan jika belum diketahui.
            </div>
          </section>

          {error ? (
            <div className="mt-4 rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-bad">
              {error}
            </div>
          ) : null}

          {testResult ? (
            <div
              className={clsx(
                "mt-4 rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px]",
                testResult.ok ? "text-ok" : "text-bad"
              )}
            >
              {testResult.message}
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-line pt-4">
            <button
              type="button"
              className="btn mr-auto flex items-center gap-1.5"
              onClick={runTest}
              disabled={test.isPending || save.isPending}
            >
              <PlugZap size={13} />
              {test.isPending ? "Menguji…" : "Test Koneksi"}
            </button>
            <button type="button" className="btn" onClick={onClose}>
              Batal
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={save.isPending || test.isPending}
            >
              {save.isPending ? "Menyimpan…" : "Simpan Pengaturan"}
            </button>
          </div>
          </form>
        )}
      </div>
    </div>
  );
}
