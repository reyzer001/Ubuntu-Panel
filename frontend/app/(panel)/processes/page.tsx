"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { Gauge, GaugeArc, GaugeTrack } from "@/components/gauge";
import { api, ApiError } from "@/lib/api";
import type { ProcessInfo } from "@/lib/types";

/** Ring CPU per proses — seperti tabel Processes di gauge-ui.dev. */
function ProcessCpuRing({ cpu }: { cpu: number }) {
  return (
    <Gauge
      value={Math.min(cpu, 100)}
      min={0}
      max={100}
      startAngle={180}
      endAngle={540}
      padding={40}
      transition
      initialValue={0}
    >
      <GaugeTrack width={80} cap="butt" opacity={0.2} />
      <GaugeArc width={80} cap="butt" />
    </Gauge>
  );
}

export default function ProcessesPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["processes"],
    queryFn: () => api<{ processes: ProcessInfo[] }>("/processes"),
    refetchInterval: 10_000,
  });

  const kill = useMutation({
    mutationFn: (pid: number) =>
      api(`/processes/${pid}/kill`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Process terminated");
      queryClient.invalidateQueries({ queryKey: ["processes"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Kill failed"),
  });

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return [...(data?.processes ?? [])]
      .filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.user.toLowerCase().includes(q) ||
          String(p.pid).includes(q)
      )
      .slice(0, 200);
  }, [data, search]);

  const sort = useTableSort<ProcessInfo>(
    rows,
    {
      name: (p) => p.name,
      pid: (p) => p.pid,
      user: (p) => p.user,
      cpu: (p) => p.cpu,
      memory: (p) => p.memory_percent,
    },
    "cpu",
    "desc"
  );

  return (
    <>
      <PageHeader
        title="Processes"
        subtitle="Running processes on this server"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["processes"] })}
        refreshing={isLoading}
      />

      <div className="card">
        <div className="mb-4 flex flex-wrap justify-between gap-2.5">
          <input
            className="input min-w-[240px]"
            placeholder="Search process..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="table-wrap overflow-auto">
          <table className="proc-table text-xs tabular-nums">
            <thead className="text-muted-foreground">
              <tr className="[&>th]:pb-2 [&>th]:font-normal">
                <SortTh
                  label="Name"
                  k="name"
                  active={sort.key === "name"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="PID"
                  k="pid"
                  className="text-right"
                  active={sort.key === "pid"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="User"
                  k="user"
                  active={sort.key === "user"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="CPU"
                  k="cpu"
                  className="text-right"
                  active={sort.key === "cpu"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Mem"
                  k="memory"
                  className="text-right"
                  active={sort.key === "memory"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {sort.sorted.map((p) => (
                <tr key={p.pid} className="[&>td]:py-1">
                  <td className="font-mono">{p.name}</td>
                  <td className="text-right text-muted-foreground">{p.pid}</td>
                  <td>{p.user}</td>
                  <td>
                    <span className="flex items-center justify-end gap-2">
                      {p.cpu.toFixed(1)}%
                      <span className="size-4">
                        <ProcessCpuRing cpu={p.cpu} />
                      </span>
                    </span>
                  </td>
                  <td className="text-right">{p.memory_percent.toFixed(1)}%</td>
                  <td className="text-right">
                    <button
                      className="action-btn"
                      disabled={kill.isPending || p.pid <= 1}
                      onClick={async () => {
                        if (
                          await confirm({
                            message: `Kill process ${p.name} (PID ${p.pid})?`,
                            confirmText: "Ya, kill",
                          })
                        ) {
                          kill.mutate(p.pid);
                        }
                      }}
                    >
                      Kill
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-muted2">
                    No processes match your search
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
