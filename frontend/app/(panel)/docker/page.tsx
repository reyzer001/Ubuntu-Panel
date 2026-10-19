"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Globe, Layers, Loader2, PlayCircle, StopCircle, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError } from "@/lib/api";
import type { ContainerDetail, ContainerInfo } from "@/lib/types";

type ContainerAction = "start" | "stop" | "restart";

export default function DockerPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const [search, setSearch] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ image: "", name: "", ports: "" });
  const [formError, setFormError] = useState("");
  const [detailName, setDetailName] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["docker"],
    queryFn: () =>
      api<{ available: boolean; containers: ContainerInfo[]; error: string }>(
        "/docker/containers"
      ),
      refetchInterval: 15_000,
  });
  const data = query.data;

  const action = useMutation({
    mutationFn: (vars: { name: string; action: ContainerAction }) =>
      api(`/docker/${vars.name}/action`, {
        method: "POST",
        body: JSON.stringify({ action: vars.action }),
      }),
    onSuccess: (_res, vars) => {
      toast.success(`${vars.name} ${vars.action}ed`);
      queryClient.invalidateQueries({ queryKey: ["docker"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Action failed"),
  });

  const deploy = useMutation({
    mutationFn: () =>
      api<{ success: boolean; output: string }>("/docker/deploy", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: (res) => {
      toast.success(res.output || "Container started");
      setAddOpen(false);
      setForm({ image: "", name: "", ports: "" });
      setFormError("");
      queryClient.invalidateQueries({ queryKey: ["docker"] });
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError ? err.message : "Failed to start container";
      if (addOpen) setFormError(msg);
      else toast.error(msg);
    },
  });

  const removeContainer = useMutation({
    mutationFn: (vars: { name: string; remove_image: boolean }) =>
      api<{ success: boolean; output: string }>(`/docker/${vars.name}`, {
        method: "DELETE",
        body: JSON.stringify({ remove_image: vars.remove_image }),
      }),
    onSuccess: (res) => {
      toast.success(res.output || "Container removed");
      queryClient.invalidateQueries({ queryKey: ["docker"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Failed to remove container"),
  });

  const containers = data?.containers ?? [];

  const detailQuery = useQuery({
    queryKey: ["docker-detail", detailName],
    queryFn: () => api<ContainerDetail>(`/docker/${detailName}/detail`),
    enabled: detailName != null,
  });

  const summary = useMemo(() => {
    const running = containers.filter((c) => c.status === "running").length;
    return { total: containers.length, running, stopped: containers.length - running };
  }, [containers]);

  const webRunning = useMemo(
    () =>
      containers.filter(
        (c) => c.status === "running" && (c.host_ports ?? []).length > 0
      ),
    [containers]
  );

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return containers.filter(
      (c) => c.name.toLowerCase().includes(q) || c.image.toLowerCase().includes(q)
    );
  }, [containers, search]);

  const sort = useTableSort<ContainerInfo>(
    rows,
    {
      name: (c) => c.name,
      image: (c) => c.image,
      status: (c) => c.status,
      cpu: (c) => c.cpu,
      memory: (c) => c.memory,
      ports: (c) => c.ports,
    },
    "name"
  );

  const submitDeploy = () => {
    if (!form.image.trim()) {
      setFormError("Image is required (e.g. nginx:latest)");
      return;
    }
    setFormError("");
    deploy.mutate();
  };

  const openPort = (port: number) => {
    const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
    window.open(`http://${host}:${port}`, "_blank");
  };

  return (
    <>
      <PageHeader
        title="Docker Management"
        subtitle="Container management"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["docker"] })}
        refreshing={query.isLoading}
      />

      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard
          label="Total Containers"
          icon={<Layers size={16} className="text-muted" />}
          value={summary.total}
          bottomLeft="all containers on host"
        />
        <StatCard
          label="Running"
          icon={<PlayCircle size={16} className="text-ok" />}
          value={summary.running}
          valueTone={summary.running > 0 ? "positive" : undefined}
          bottomLeft="active now"
        />
        <StatCard
          label="Stopped"
          icon={<StopCircle size={16} className="text-bad" />}
          value={summary.stopped}
          valueTone={summary.stopped > 0 ? "warning" : undefined}
          bottomLeft="exited / created only"
        />
      </div>

      {webRunning.length > 0 ? (
        <div className="card mb-4">
          <div className="card-header">
            <div>
              <div className="card-title flex items-center gap-2">
                <Globe size={14} className="text-ok" />
                Website Running di Docker
              </div>
              <div className="card-subtitle">
                container aktif yang mempublikasikan port web — klik untuk membuka
              </div>
            </div>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {webRunning.map((c) =>
              (c.host_ports ?? []).map((p) => (
                <button
                  key={`${c.name}-${p}`}
                  className="flex items-center gap-3 rounded-xl border border-line bg-panel2 p-3 text-left hover:border-accent"
                  onClick={() => openPort(p)}
                >
                  <span className="h-[8px] w-[8px] shrink-0 rounded-full bg-ok shadow-[0_0_8px_#22c55e]" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-bold">{c.name}</span>
                    <span className="block truncate font-mono text-[10px] text-muted2">
                      {c.image} · port {p}
                    </span>
                  </span>
                  <ExternalLink size={14} className="shrink-0 text-muted" />
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}

      {data && !data.available ? (
        <div className="card mb-4 border-[#6b5620] bg-[#241b09] text-[11px] text-[#ffd58a]">
          {data.error || "Docker is not available on this host."}
        </div>
      ) : null}

      <div className="card">
        <div className="mb-4 flex flex-wrap justify-between gap-2.5">
          <input
            className="input min-w-[240px]"
            placeholder="Search container..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={() => {
              setFormError("");
              setAddOpen(true);
            }}
          >
            + Add Container
          </button>
        </div>

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh
                  label="Container"
                  k="name"
                  active={sort.key === "name"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Image"
                  k="image"
                  active={sort.key === "image"}
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
                  label="CPU"
                  k="cpu"
                  active={sort.key === "cpu"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Memory"
                  k="memory"
                  active={sort.key === "memory"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <SortTh
                  label="Ports"
                  k="ports"
                  active={sort.key === "ports"}
                  dir={sort.dir}
                  onToggle={sort.toggle}
                />
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sort.sorted.map((c) => (
                <tr
                  key={c.name}
                  className="cursor-pointer hover:bg-panel2/60"
                  onClick={() => setDetailName(c.name)}
                  title="Klik untuk detail service & dependency"
                >
                  <td>
                    <strong>{c.name}</strong>
                  </td>
                  <td>{c.image}</td>
                  <td>
                    <StatusBadge status={c.status === "running" ? "running" : "stopped"} />
                  </td>
                  <td>{c.cpu}</td>
                  <td>{c.memory}</td>
                  <td className="font-mono text-[11px]">{c.ports}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1.5">
                      {(["restart", "stop", "start"] as ContainerAction[]).map(
                        (a) => (
                          <button
                            key={a}
                            className="action-btn capitalize"
                            disabled={action.isPending}
                            onClick={() => action.mutate({ name: c.name, action: a })}
                          >
                            {a}
                          </button>
                        )
                      )}
                      <button
                        className="action-btn text-bad"
                        disabled={removeContainer.isPending}
                        title="Remove this container"
                        onClick={async () => {
                          if (
                            await confirm({
                              message: `Delete container "${c.name}"? This will stop and remove it permanently.`,
                              confirmText: "Yes, delete",
                            })
                          )
                            removeContainer.mutate({ name: c.name, remove_image: false });
                        }}
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-muted2">
                    No containers found
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {data?.available && summary.total > 0 ? (
          <div className="mt-3 space-y-1 border-t border-line pt-3 text-[11px]">
            <div className="text-muted2">
              <span className="mr-1 inline-block h-[7px] w-[7px] rounded-full bg-ok shadow-[0_0_8px_#22c55e]" />
              Berjalan ({summary.running}):
              <span className="ml-1 text-muted">
                {containers.filter((c) => c.status === "running").map((c) => `${c.name} (${c.image})`).join(", ") || "-"}
              </span>
            </div>
            <div className="text-muted2">
              <span className="mr-1 inline-block h-[7px] w-[7px] rounded-full bg-bad" />
              Berhenti ({summary.stopped}):
              <span className="ml-1 text-muted">
                {containers.filter((c) => c.status !== "running").map((c) => `${c.name} (${c.image})`).join(", ") || "-"}
              </span>
            </div>
          </div>
        ) : null}
      </div>

      {/* -------------------------------------------- add container modal */}
      {addOpen ? (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4"
          onClick={() => setAddOpen(false)}
        >
          <div
            className="card w-full max-w-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div>
                <div className="card-title">Add Container</div>
                <div className="card-subtitle">
                  pull image and run a new container
                </div>
              </div>
              <button className="btn" onClick={() => setAddOpen(false)}>
                ×
              </button>
            </div>

            <div className="space-y-3 p-1">
              <label className="block text-[11px] text-muted">
                Image *
                <input
                  className="input mt-1 w-full font-mono text-xs"
                  placeholder="nginx:latest, mysql:8, redis:7 …"
                  value={form.image}
                  onChange={(e) => setForm({ ...form, image: e.target.value })}
                />
              </label>
              <label className="block text-[11px] text-muted">
                Container Name (optional)
                <input
                  className="input mt-1 w-full font-mono text-xs"
                  placeholder="my-app"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>
              <label className="block text-[11px] text-muted">
                Port Mapping (optional)
                <input
                  className="input mt-1 w-full font-mono text-xs"
                  placeholder="8080:80, 443:443"
                  value={form.ports}
                  onChange={(e) => setForm({ ...form, ports: e.target.value })}
                />
                <span className="mt-1 block text-[10px] text-muted2">
                  format HOST:CONTAINER — pisahkan beberapa mapping dengan koma
                </span>
              </label>

              {formError ? (
                <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-bad">
                  {formError}
                </div>
              ) : null}

              <div className="flex justify-end gap-2 pt-1">
                <button className="btn" onClick={() => setAddOpen(false)}>
                  Cancel
                </button>
                <button
                  className="btn btn-primary"
                  disabled={deploy.isPending}
                  onClick={submitDeploy}
                >
                  {deploy.isPending ? "Starting…" : "▶ Run Container"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      {/* ------------------------------------------ container detail modal */}
      {detailName ? (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4"
          onClick={() => setDetailName(null)}
        >
          <div
            className="card max-h-[90vh] w-full max-w-3xl overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div>
                <div className="card-title flex items-center gap-2">
                  {detailName}
                  {detailQuery.data ? (
                    <>
                      <StatusBadge
                        status={
                          detailQuery.data.status === "running" ? "running" : "stopped"
                        }
                      />
                      {detailQuery.data.health ? (
                        <StatusBadge status={detailQuery.data.health} />
                      ) : null}
                    </>
                  ) : null}
                </div>
                <div className="font-mono text-[11px] text-muted">
                  {detailQuery.data?.image || "…"}
                </div>
              </div>
              <button className="btn" onClick={() => setDetailName(null)}>
                ×
              </button>
            </div>

            {detailQuery.isLoading ? (
              <div className="py-10 text-center text-sm text-muted2">Loading detail…</div>
            ) : detailQuery.isError || !detailQuery.data ? (
              <div className="py-6 text-center text-xs text-bad">
                Gagal memuat detail:{" "}
                {detailQuery.error instanceof Error
                  ? detailQuery.error.message
                  : "unknown"}
              </div>
            ) : (
              <div className="space-y-5 p-1">
                {/* info umum */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] md:grid-cols-3">
                  <Info label="Status" value={detailQuery.data.status} />
                  <Info label="Uptime" value={detailQuery.data.uptime ?? "-"} />
                  <Info label="Health" value={detailQuery.data.health ?? "-"} />
                  <Info label="Restart Policy" value={detailQuery.data.restart_policy || "-"} />
                  <Info label="Created" value={detailQuery.data.created} mono />
                  <Info label="Started At" value={detailQuery.data.started_at ?? "-"} mono />
                  {detailQuery.data.command ? (
                    <Info label="Command" value={detailQuery.data.command} mono wide />
                  ) : null}
                  {detailQuery.data.entrypoint ? (
                    <Info label="Entrypoint" value={detailQuery.data.entrypoint} mono wide />
                  ) : null}
                </div>

                {/* port mapping */}
                <section>
                  <SectionTitle>Ports (HOST → Container)</SectionTitle>
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-left text-muted2">
                        <th className="pb-1">Host</th>
                        <th className="pb-1">Container</th>
                        <th className="pb-1">Bind IP</th>
                      </tr>
                    </thead>
                    <tbody className="font-mono">
                      {detailQuery.data.port_map.map((p, i) => (
                        <tr key={i} className="border-t border-line">
                          <td className="py-1">
                            {p.host_port != null ? p.host_port : "—"}
                          </td>
                          <td>{p.container}</td>
                          <td className="text-muted2">{p.host_ip || "*"}</td>
                        </tr>
                      ))}
                      {detailQuery.data.port_map.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="py-2 text-muted2">
                            tidak ada port terekspos
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </section>

                {/* service/proses di dalam container */}
                <section>
                  <SectionTitle>
                    Service / Proses di Dalam ({detailQuery.data.processes.rows.length})
                  </SectionTitle>
                  {detailQuery.data.processes.rows.length > 0 ? (
                    <pre className="max-h-52 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-green-200">
                      {[
                        detailQuery.data.processes.titles.join("  "),
                        ...detailQuery.data.processes.rows.map((r) => r.join("  ")),
                      ].join("\n")}
                    </pre>
                  ) : (
                    <div className="rounded-lg border border-line bg-panel2 px-3 py-2 text-[11px] text-muted2">
                      {detailQuery.data.status === "running"
                        ? "tidak bisa membaca proses"
                        : "container berhenti — tidak ada proses berjalan"}
                    </div>
                  )}
                </section>

                {/* dependency */}
                <section>
                  <SectionTitle>Dependency</SectionTitle>
                  <div className="grid gap-3 md:grid-cols-2">
                    <div>
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-muted2">
                        Networks
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {detailQuery.data.networks.length > 0 ? (
                          detailQuery.data.networks.map((n) => (
                            <span
                              key={n}
                              className="rounded-md border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px]"
                            >
                              {n}
                            </span>
                          ))
                        ) : (
                          <span className="text-[11px] text-muted2">-</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-muted2">
                        Env Vars ({detailQuery.data.env_keys.length})
                      </div>
                      <div className="flex max-h-24 flex-wrap gap-1 overflow-auto">
                        {detailQuery.data.env_keys.length > 0 ? (
                          detailQuery.data.env_keys.map((k) => (
                            <span
                              key={k}
                              className="rounded-md border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px] text-muted"
                              title={k}
                            >
                              {k}
                            </span>
                          ))
                        ) : (
                          <span className="text-[11px] text-muted2">-</span>
                        )}
                      </div>
                    </div>
                    <div className="md:col-span-2">
                      <div className="mb-1 text-[10px] uppercase tracking-wider text-muted2">
                        Volumes / Mounts
                      </div>
                      {detailQuery.data.mounts.length > 0 ? (
                        <div className="space-y-0.5 font-mono text-[10px] text-muted">
                          {detailQuery.data.mounts.map((m, i) => (
                            <div key={i} className="truncate">
                              {m.source || "?"} → {m.destination || "?"}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[11px] text-muted2">-</span>
                      )}
                    </div>
                  </div>
                </section>

                <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-3">
                  {(detailQuery.data.host_ports ?? []).length > 0 &&
                  detailQuery.data.status === "running"
                    ? detailQuery.data.host_ports.map((p) => (
                        <button
                          key={p}
                          className="btn btn-primary py-1.5 text-xs"
                          onClick={() => openPort(p)}
                        >
                          <ExternalLink size={12} className="mr-1 inline" />
                          Buka http://{window.location.hostname}:{p}
                        </button>
                      ))
                    : null}
                  <button
                    className="btn py-1.5 text-xs text-bad"
                    disabled={removeContainer.isPending}
                    onClick={async () => {
                      const confirmed = await confirm({
                        message: `Delete container "${detailName}"? This will stop and remove it permanently.`,
                        confirmText: "Yes, delete",
                      });
                      if (confirmed) {
                        removeContainer.mutate({ name: detailName!, remove_image: false });
                        setDetailName(null);
                      }
                    }}
                  >
                    <Trash2 size={12} className="mr-1 inline" />
                    Delete Container
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}

function Info({
  label,
  value,
  mono,
  wide,
}: {
  label: string;
  value: string;
  mono?: boolean;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "col-span-2 md:col-span-3" : ""}>
      <div className="text-[10px] uppercase tracking-wider text-muted2">{label}</div>
      <div className={`truncate ${mono ? "font-mono" : ""}`} title={value}>
        {value || "-"}
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 border-b border-line pb-1 text-[11px] font-bold uppercase tracking-wider text-muted">
      {children}
    </div>
  );
}
