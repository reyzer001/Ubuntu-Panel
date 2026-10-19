"use client";

import { useEffect, useState } from "react";
import { KeyRound, ShieldAlert } from "lucide-react";

export function SudoModal({
  label,
  osUser,
  pending,
  error,
  onSubmit,
  onClose,
}: {
  label: string;
  osUser?: string;
  pending?: boolean;
  error?: string | null;
  onSubmit: (password: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");

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
      onMouseDown={(e) => e.target === e.currentTarget && !pending && onClose()}
    >
      <div
        className="dialog-card"
        role="dialog"
        aria-modal="true"
        aria-label="Password sudo"
      >
        <div className="flex items-start gap-3">
          <span className="dialog-icon dialog-icon-warning">
            <KeyRound size={18} strokeWidth={2.2} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-bold leading-snug">
              Password sudo diperlukan
            </div>
            <div className="mt-1 whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-muted">
              Aksi <span className="font-bold text-fg">{label}</span> butuh akses
              root. Masukkan password login OS
              {osUser ? (
                <>
                  {" "}
                  user <code className="text-[#ffd58a]">{osUser}</code>
                </>
              ) : null}{" "}
              — bukan password panel.
            </div>
          </div>
        </div>

        <label className="mt-4 block text-[11px] text-muted">
          Password sudo
          <input
            type="password"
            autoFocus
            autoComplete="off"
            className="input mt-1 w-full"
            placeholder="password akun OS"
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
          Password hanya dipakai sekali untuk menjalankan perintah dan tidak
          disimpan. Koneksi panel saat ini belum terenkripsi (HTTP).
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" disabled={pending} onClick={onClose}>
            Batal
          </button>
          <button
            className="btn btn-primary"
            disabled={pending || !value}
            onClick={submit}
          >
            {pending ? "Menjalankan…" : "Jalankan"}
          </button>
        </div>
      </div>
    </div>
  );
}
