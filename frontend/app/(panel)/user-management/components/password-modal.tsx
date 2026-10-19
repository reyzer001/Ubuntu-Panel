"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/providers";
import type { PanelUser } from "@/lib/types";

export function PasswordModal({
  user,
  onClose,
  onDone,
}: {
  user: PanelUser;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const [value, setValue] = useState("");

  const changePass = useMutation({
    mutationFn: () =>
      api(`/panel-users/${user.id}/password`, {
        method: "PATCH",
        body: JSON.stringify({ password: value }),
      }),
    onSuccess: () => {
      toast.success(`Password ${user.username} diganti`);
      onDone();
      onClose();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengganti password"),
  });

  return (
    <div
      className="dialog-overlay"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="dialog-card" role="dialog" aria-modal="true" aria-label="Ganti Password">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="text-[13px] font-bold">Ganti Password</div>
            <div className="font-mono text-[11px] text-muted">{user.username}</div>
          </div>
          <button className="btn" onClick={onClose}>
            ×
          </button>
        </div>
        <label className="block text-[11px] text-muted">
          Password Baru
          <input
            type="password"
            autoFocus
            className="input mt-1 w-full"
            placeholder="minimal 4 karakter"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn" onClick={onClose}>
            Batal
          </button>
          <button
            className="btn btn-primary"
            disabled={changePass.isPending || value.length < 4}
            onClick={() => changePass.mutate()}
          >
            {changePass.isPending ? "Menyimpan…" : "Simpan"}
          </button>
        </div>
      </div>
    </div>
  );
}
