"use client";

import { useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useConfirm, useToast } from "@/components/providers";
import { api, ApiError } from "@/lib/api";
import type { PanelUser } from "@/lib/types";
import { RoleBadge, RoleSelect } from "./role-badge";

export function UserTable({
  users,
  selectedId,
  onSelect,
  isSuperadmin,
  meUsername,
  superadminCount,
  onPassword,
}: {
  users: PanelUser[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  isSuperadmin: boolean;
  meUsername: string | undefined;
  superadminCount: number;
  onPassword: (u: PanelUser) => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();

  const rows = useMemo(
    () =>
      [...users].sort(
        (a, b) =>
          Number(b.online ?? false) - Number(a.online ?? false) ||
          a.username.localeCompare(b.username)
      ),
    [users]
  );

  const changeRole = useMutation({
    mutationFn: (v: { id: number; role: string }) =>
      api(`/panel-users/${v.id}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: v.role }),
      }),
    onSuccess: () => {
      toast.success("Role diperbarui");
      queryClient.invalidateQueries({ queryKey: ["panel-users"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengubah role"),
  });

  const removeUser = useMutation({
    mutationFn: (u: PanelUser) => api(`/panel-users/${u.id}`, { method: "DELETE" }),
    onSuccess: (_r, u) => {
      toast.success(`User ${u.username} dihapus`);
      queryClient.invalidateQueries({ queryKey: ["panel-users"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus user"),
  });

  const lastSuperadmin = (u: PanelUser) => u.role === "superadmin" && superadminCount <= 1;

  return (
    <div className="card">
      <div className="table-wrap overflow-auto">
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Kontak</th>
              <th>Role</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr
                key={u.id}
                className={`cursor-pointer transition ${
                  selectedId === u.id ? "bg-[#0d243d]" : "hover:bg-panel2"
                }`}
                onClick={() => onSelect(u.id)}
              >
                <td>
                  <strong>{u.username}</strong>
                  {u.full_name ? (
                    <div className="text-[10px] text-muted">{u.full_name}</div>
                  ) : null}
                  {u.username === meUsername ? (
                    <span className="text-[10px] text-ok">(anda)</span>
                  ) : null}
                </td>
                <td className="font-mono text-[10px] text-muted">
                  <div>{u.email || "-"}</div>
                  <div>{u.phone || ""}</div>
                </td>
                <td>
                  {isSuperadmin && u.username !== meUsername ? (
                    <RoleSelect
                      value={u.role}
                      disabled={changeRole.isPending || lastSuperadmin(u)}
                      onChange={(role) => changeRole.mutate({ id: u.id, role })}
                    />
                  ) : (
                    <RoleBadge role={u.role} />
                  )}
                </td>
                <td>
                  <span
                    className={`text-[10px] ${u.online ? "text-ok" : "text-muted2"}`}
                  >
                    {u.online ? "online" : "offline"}
                  </span>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <div className="flex gap-1.5">
                    {isSuperadmin ? (
                      <>
                        <button
                          className="action-btn flex items-center gap-1"
                          onClick={() => onPassword(u)}
                        >
                          <KeyRound size={11} />
                          Password
                        </button>
                        {u.username !== meUsername ? (
                          <button
                            className="action-btn text-bad"
                            disabled={removeUser.isPending || lastSuperadmin(u)}
                            title={
                              lastSuperadmin(u)
                                ? "Minimal harus tersisa satu superadmin"
                                : undefined
                            }
                            onClick={async () => {
                              if (
                                await confirm({
                                  message: `Hapus user "${u.username}"?`,
                                  confirmText: "Ya, hapus",
                                })
                              )
                                removeUser.mutate(u);
                            }}
                          >
                            Del
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-[10px] text-muted2">khusus superadmin</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-muted2">
                  Belum ada user panel
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
