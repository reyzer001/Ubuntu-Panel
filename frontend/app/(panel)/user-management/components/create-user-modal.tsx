"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/providers";
import { RoleSelect } from "./role-badge";
import { isValidEmail, isValidPhone } from "./validations";

type FormState = {
  username: string;
  password: string;
  role: string;
  full_name: string;
  email: string;
  phone: string;
};

const EMPTY: FormState = {
  username: "",
  password: "",
  role: "viewer",
  full_name: "",
  email: "",
  phone: "",
};

export function CreateUserModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState("");

  const create = useMutation({
    mutationFn: () => api("/panel-users", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: () => {
      toast.success(`User ${form.username} dibuat`);
      queryClient.invalidateQueries({ queryKey: ["panel-users"] });
      onDone();
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Gagal membuat user"),
  });

  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const submit = () => {
    if (!form.username.trim()) return setError("Username wajib diisi");
    if (form.password.length < 4) return setError("Password minimal 4 karakter");
    if (form.email.trim() && !isValidEmail(form.email.trim()))
      return setError("Format email tidak valid");
    if (form.phone.trim() && !isValidPhone(form.phone.trim()))
      return setError("Nomor telepon tidak valid");
    create.mutate();
  };

  return (
    <div
      className="dialog-overlay"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="dialog-card !max-w-lg"
        role="dialog"
        aria-modal="true"
        aria-label="Tambah User Baru"
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="text-[13px] font-bold">Tambah User Baru</div>
            <div className="text-[11px] text-muted">buat akun login panel beserta rolenya</div>
          </div>
          <button className="btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="text-[11px] text-muted">
            Username *
            <input
              className="input mt-1 w-full"
              placeholder="mis. operator1"
              value={form.username}
              onChange={(e) => set({ username: e.target.value })}
            />
          </label>
          <label className="text-[11px] text-muted">
            Nama Lengkap
            <input
              className="input mt-1 w-full"
              placeholder="mis. Budi Santoso"
              value={form.full_name}
              onChange={(e) => set({ full_name: e.target.value })}
            />
          </label>
          <label className="text-[11px] text-muted">
            Email
            <input
              type="email"
              className="input mt-1 w-full"
              placeholder="nama@domain.com"
              value={form.email}
              onChange={(e) => set({ email: e.target.value })}
            />
          </label>
          <label className="text-[11px] text-muted">
            Nomor Telepon
            <input
              type="tel"
              className="input mt-1 w-full"
              placeholder="+62 812 3456 7890"
              value={form.phone}
              onChange={(e) => set({ phone: e.target.value })}
            />
          </label>
          <label className="text-[11px] text-muted">
            Role
            <RoleSelect
              className="mt-1 w-full"
              value={form.role}
              onChange={(role) => set({ role })}
            />
          </label>
          <label className="text-[11px] text-muted">
            Password *
            <input
              type="password"
              className="input mt-1 w-full"
              placeholder="minimal 4 karakter"
              value={form.password}
              onChange={(e) => set({ password: e.target.value })}
            />
          </label>
        </div>

        {error ? (
          <div className="mt-3 rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-bad">
            {error}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button className="btn" onClick={onClose}>
            Batal
          </button>
          <button className="btn btn-primary" disabled={create.isPending} onClick={submit}>
            {create.isPending ? "Menyimpan…" : "+ Tambah User"}
          </button>
        </div>
      </div>
    </div>
  );
}
