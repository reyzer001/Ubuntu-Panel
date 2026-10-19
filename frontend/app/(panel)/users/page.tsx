"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError } from "@/lib/api";
import type { UserAccount } from "@/lib/types";

export default function UsersPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const [search, setSearch] = useState("");
  const [newUser, setNewUser] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<{ users: UserAccount[] }>("/users"),
  });

  const create = useMutation({
    mutationFn: (username: string) =>
      api("/users", { method: "POST", body: JSON.stringify({ username }) }),
    onSuccess: (_res, username) => {
      toast.success(`User ${username} created`);
      setNewUser("");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Failed to create user"),
  });

  const remove = useMutation({
    mutationFn: (username: string) =>
      api(`/users/${encodeURIComponent(username)}`, { method: "DELETE" }),
    onSuccess: (_res, username) => {
      toast.success(`User ${username} deleted`);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Failed to delete user"),
  });

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return (data?.users ?? []).filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        String(u.uid).includes(q)
    );
  }, [data, search]);

  const sort = useTableSort<UserAccount>(
    rows,
    {
      username: (u) => u.username,
      uid: (u) => u.uid,
      group: (u) => u.group,
      home: (u) => u.home,
      shell: (u) => u.shell,
      status: (u) => u.status,
    },
    "username"
  );

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Local users and accounts"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["users"] })}
        refreshing={isLoading}
      />

      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5">
          <input
            className="input min-w-[240px]"
            placeholder="Search user..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (newUser.trim()) create.mutate(newUser.trim());
            }}
          >
            <input
              className="input w-44"
              placeholder="New username"
              value={newUser}
              onChange={(e) => setNewUser(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={create.isPending || !newUser.trim()}
            >
              + Create User
            </button>
          </form>
        </div>

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh
                  label="User"
                  k="username"
                  active={sort.key === "username"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="UID"
                  k="uid"
                  active={sort.key === "uid"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Group"
                  k="group"
                  active={sort.key === "group"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Home"
                  k="home"
                  active={sort.key === "home"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Shell"
                  k="shell"
                  active={sort.key === "shell"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Status"
                  k="status"
                  active={sort.key === "status"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sort.sorted.map((u) => (
                <tr key={u.username}>
                  <td>
                    <strong>{u.username}</strong>
                  </td>
                  <td>{u.uid}</td>
                  <td>{u.group}</td>
                  <td>{u.home}</td>
                  <td>{u.shell}</td>
                  <td>
                    <StatusBadge
                      status={u.status === "Active" ? "active" : "info"}
                    />
                  </td>
                  <td>
                    <button
                      className="action-btn"
                      disabled={
                        remove.isPending ||
                        u.username === "root" ||
                        u.uid >= 1000 === false
                      }
                      onClick={async () => {
                        if (
                          await confirm({
                            message: `Delete user ${u.username} and its home directory?`,
                            confirmText: "Ya, hapus",
                          })
                        ) {
                          remove.mutate(u.username);
                        }
                      }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-muted2">
                    No users match your search
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-[10px] text-muted2">
          Only regular users (UID ≥ 1000) can be deleted. System accounts are
          protected.
        </p>
      </div>
    </>
  );
}
