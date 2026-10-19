"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useToast } from "@/components/providers";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError } from "@/lib/api";
import type { ServiceInfo } from "@/lib/types";

type ServiceAction = "start" | "restart" | "stop";

export default function ServicesPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["services"],
    queryFn: () => api<{ services: ServiceInfo[] }>("/services"),
    refetchInterval: 15_000,
  });

  const action = useMutation({
    mutationFn: (vars: { name: string; action: ServiceAction }) =>
      api(`/services/${vars.name}/${vars.action}`, { method: "POST" }),
    onSuccess: (_res, vars) => {
      toast.success(`${vars.name}: ${vars.action} command executed`);
      queryClient.invalidateQueries({ queryKey: ["services"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Action failed"),
  });

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return (data?.services ?? []).filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
    );
  }, [data, search]);

  const sort = useTableSort<ServiceInfo>(
    rows,
    {
      name: (s) => s.name,
      description: (s) => s.description,
      status: (s) => s.status,
      enabled: (s) => s.enabled,
    },
    "name"
  );

  return (
    <>
      <PageHeader
        title="Services"
        subtitle="Manage systemd services"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["services"] })}
        refreshing={isLoading}
      />

      <div className="card">
        <div className="mb-4 flex flex-wrap justify-between gap-2.5">
          <input
            className="input min-w-[240px]"
            placeholder="Search service..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["services"] });
              toast.info("Service list refreshed");
            }}
          >
            ↻ Scan Services
          </button>
        </div>

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh
                  label="Service"
                  k="name"
                  active={sort.key === "name"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Description"
                  k="description"
                  active={sort.key === "description"}
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
                <SortTh
                  label="Enabled"
                  k="enabled"
                  active={sort.key === "enabled"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sort.sorted.map((s) => (
                <tr key={s.unit}>
                  <td>
                    <strong>{s.name}</strong>
                  </td>
                  <td>{s.description}</td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td>
                    <StatusBadge
                      status={
                        s.enabled === "enabled"
                          ? "active"
                          : s.enabled === "disabled"
                            ? "stopped"
                            : "info"
                      }
                    />
                  </td>
                  <td>
                    <div className="row-actions flex gap-1.5">
                      {(["start", "restart", "stop"] as ServiceAction[]).map(
                        (a) => (
                          <button
                            key={a}
                            className="action-btn capitalize"
                            disabled={action.isPending}
                            onClick={() => action.mutate({ name: s.name, action: a })}
                          >
                            {a}
                          </button>
                        )
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-muted2">
                    No services match your search
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
