"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck,
  UserPlus,
  Users as UsersIcon,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/ui/stat-card";
import { api } from "@/lib/api";
import type { ManagedComputer, PanelUser } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { UserTable } from "./components/user-table";
import { UserDetail } from "./components/user-detail";
import { CreateUserModal } from "./components/create-user-modal";
import { PasswordModal } from "./components/password-modal";

export default function UserManagementPage() {
  const queryClient = useQueryClient();
  const me = useAuth((s) => s.user);

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [passFor, setPassFor] = useState<PanelUser | null>(null);

  const usersQuery = useQuery({
    queryKey: ["panel-users"],
    queryFn: () => api<{ users: PanelUser[] }>("/panel-users"),
    refetchInterval: 30_000,
  });

  const computersQuery = useQuery({
    queryKey: ["computers"],
    queryFn: () => api<{ computers: ManagedComputer[] }>("/computers"),
    staleTime: 5 * 60_000,
  });

  const users = useMemo(() => usersQuery.data?.users ?? [], [usersQuery.data]);
  const computers = useMemo(
    () => computersQuery.data?.computers ?? [],
    [computersQuery.data]
  );

  const summary = useMemo(() => {
    const by = (r: string) => users.filter((u) => u.role === r).length;
    return {
      total: users.length,
      online: users.filter((u) => u.online).length,
      superadmin: by("superadmin"),
      admin: by("admin"),
      viewer: by("viewer"),
    };
  }, [users]);

  const isSuperadmin = me?.role === "superadmin";

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["panel-users"] });
    if (selectedUserId)
      queryClient.invalidateQueries({
        queryKey: ["panel-user-detail", selectedUserId],
      });
  };

  return (
    <>
      <PageHeader
        title="User Management"
        subtitle="Kelola akun panel & role akses"
        onRefresh={invalidate}
        refreshing={usersQuery.isLoading}
      />

      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-2">
        <StatCard
          label="Total Akun"
          icon={<UsersIcon size={16} className="text-muted" />}
          value={summary.total}
          bottomLeft="akun panel terdaftar"
        />
        <StatCard
          label="Online"
          icon={<ShieldCheck size={16} className="text-[#34d399]" />}
          value={summary.online}
          bottomLeft="user aktif dalam 5 menit"
          valueTone="positive"
        />
      </div>

      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted2">
          klik baris untuk melihat detail user
        </span>
        {isSuperadmin ? (
          <button
            className="btn btn-primary flex items-center gap-1.5"
            onClick={() => setShowCreate(true)}
          >
            <UserPlus size={14} />
            + Tambah User
          </button>
        ) : null}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <UserTable
          users={users}
          selectedId={selectedUserId}
          onSelect={setSelectedUserId}
          isSuperadmin={isSuperadmin}
          meUsername={me?.username}
          superadminCount={summary.superadmin}
          onPassword={setPassFor}
        />
        <UserDetail
          userId={selectedUserId}
          computers={computers}
          isSuperadmin={isSuperadmin}
          onUpdated={invalidate}
        />
      </div>

      {showCreate ? (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onDone={invalidate}
        />
      ) : null}
      {passFor ? (
        <PasswordModal
          user={passFor}
          onClose={() => setPassFor(null)}
          onDone={invalidate}
        />
      ) : null}
    </>
  );
}
