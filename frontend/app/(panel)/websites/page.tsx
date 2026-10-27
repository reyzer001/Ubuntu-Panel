"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Globe, Hammer, Loader2, Link2, Trash2, Terminal, XCircle, RefreshCw, FolderOpen, Box, Activity, Clock, HardDrive, ArrowDownToLine, Play, Square, RotateCw, UploadCloud, MoreHorizontal, Plus, Radar } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatusBadge } from "@/components/ui/status-badge";
import { useTableSort } from "@/components/ui/table-sort";
import { api, ApiError, apiUpload } from "@/lib/api";
import type { BrowseResult, WebApp, WebService, WebsiteDetail, SyncResult, ContainerDetail, DependencyInfo, DeployJob, ReconcileResult, UnmanagedProject, AdoptResult, ServiceCheckResult } from "@/lib/types";

type Row = {
  dir: string;
  command: string;
  port: string;
  label: string;
};

const EMPTY_ROW: Row = { dir: "", command: "", port: "", label: "" };

function baseName(p: string): string {
  const parts = p.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || p;
}

export default function WebsitesPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();

  const [name, setName] = useState("");
  const [runtime, setRuntime] = useState<"native" | "docker" | "docker-compose">("native");
  const [phpVersion, setPhpVersion] = useState("");
  const [dockerfile, setDockerfile] = useState("Dockerfile");
  const [composeFile, setComposeFile] = useState("docker-compose.yml");
  const phpOptions = ["", "7.0", "7.1", "7.2", "7.3", "7.4", "8.0", "8.1", "8.2", "8.3", "8.4", "8.5"];
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY_ROW }]);
  const [formError, setFormError] = useState("");
  // form "Run a Website" default tertutup supaya halaman tidak dipenuhi input
  const [formOpen, setFormOpen] = useState(false);
  // menu aksi tambahan per website (dipakai kolom "⋯")
  const [moreFor, setMoreFor] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [logsFor, setLogsFor] = useState<number | null>(null);
  const [terminalFor, setTerminalFor] = useState<number | null>(null);
  const [terminalCommand, setTerminalCommand] = useState("");
  const [terminalOutput, setTerminalOutput] = useState<string[]>([]);
  const [detailFor, setDetailFor] = useState<number | null>(null);
  const [checkFor, setCheckFor] = useState<number | null>(null);
  const [dockerLogsFor, setDockerLogsFor] = useState<number | null>(null);
  const [composeLogsFor, setComposeLogsFor] = useState<number | null>(null);

  // update via upload (deploy zip)
  const [deployFor, setDeployFor] = useState<number | null>(null);
  const [deployServiceId, setDeployServiceId] = useState(0);
  const [deployZipFile, setDeployZipFile] = useState<File | null>(null);
  const [deployZipName, setDeployZipName] = useState("");
  const [deployRestart, setDeployRestart] = useState(false);
  const [deploySyncDocker, setDeploySyncDocker] = useState(true);
  const [deployJobId, setDeployJobId] = useState<string | null>(null);
  const [deployUploadPct, setDeployUploadPct] = useState<number | null>(null);

  // folder browser modal
  const [browserOpen, setBrowserOpen] = useState(false);
  const [browserRow, setBrowserRow] = useState(0);
  const [browsePath, setBrowsePath] = useState<BrowserState | null>(null);

  type BrowserState = BrowseResult & { selected: string };

  const appsQuery = useQuery({
    queryKey: ["web-apps"],
    queryFn: () => api<{ apps: WebApp[] }>("/websites"),
    refetchInterval: (q) => {
      const apps = q.state.data?.apps ?? [];
      const hasActive = apps.some((a) => a.online > 0);
      const hasPendingTunnel = apps.some((a) =>
        a.services.some((s) => s.tunnel_pid && !s.tunnel_url)
      );
      if (hasPendingTunnel) return 2000;
      if (hasActive) return 4000;
      return 10_000;
    },
  });

  // project compose yang jalan tapi belum terdaftar di panel (read-only)
  const reconcileQuery = useQuery({
    queryKey: ["web-reconcile"],
    queryFn: () => api<ReconcileResult>("/websites/reconcile"),
    refetchInterval: 30_000,
  });

  const adoptProject = useMutation({
    mutationFn: (p: UnmanagedProject) =>
      api<AdoptResult>("/websites/adopt", {
        method: "POST",
        body: JSON.stringify({
          project_dir: p.project_dir,
          compose_file: p.compose_file,
          compose_project: p.project,
          name: p.name_suggest,
        }),
      }),
    onSuccess: (res) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["web-reconcile"] });
      toast.success(`${res.name} sekarang dikelola panel`);
    },
    onError: (err) => onErr(err, "Gagal mengadopsi project"),
  });

  const openBrowser = async (idx: number) => {
    setBrowserRow(idx);
    setBrowserOpen(true);
    try {
      const res = await api<BrowseResult>("/websites/browse");
      setBrowsePath({ ...res, selected: res.path });
    } catch {
      toast.error("Failed to open folder browser");
    }
  };

  const drillDown = async (p: string) => {
    try {
      const res = await api<BrowseResult>(
        `/websites/browse?path=${encodeURIComponent(p)}`
      );
      setBrowsePath({ ...res, selected: res.path });
    } catch {
      toast.error("Failed to read folder");
    }
  };

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["web-apps"] });
  };
  const onErr = (err: unknown, fallback: string) =>
    toast.error(err instanceof ApiError ? err.message : fallback);

  // ---------------------------------------------------------- mutations
  const runSite = useMutation({
    mutationFn: () =>
      api<{ id: number; results: { label: string; error: string | null }[] }>(
        "/websites",
        {
          method: "POST",
          body: JSON.stringify({
            name,
            start: true,
            runtime,
            php_version: phpVersion,
            dockerfile,
            compose_file: composeFile.trim(),
            services: rows.map((r) => ({
              dir: r.dir.trim(),
              command: r.command.trim(),
              port: r.port.trim() ? Number(r.port) : 0,
              label: r.label.trim(),
            })),
          }),
        }
      ),
    onSuccess: (res: { id: number; results: { label: string; error: string | null }[] }) => {
      invalidate();
      const failed = res.results.filter((r) => r.error);
      if (failed.length === 0) {
        toast.success("Website is running");
      } else if (failed.length === res.results.length) {
        toast.error(`Failed to start: ${failed.map((f) => f.error).join(", ")}`);
      } else {
        toast.warning(
          `Partially running — failed: ${failed.map((f) => f.label).join(", ")}`
        );
      }
      setName("");
      setRuntime("native");
      setPhpVersion("");
      setDockerfile("Dockerfile");
      setComposeFile("docker-compose.yml");
      setRows([{ ...EMPTY_ROW }]);
      setFormError("");
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Failed to run website"),
  });

  const startApp = useMutation({
    mutationFn: (id: number) => api(`/websites/${id}/start`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err) => onErr(err, "Failed to start"),
  });
  const stopApp = useMutation({
    mutationFn: (id: number) => api(`/websites/${id}/stop`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      toast.success("Stopped");
    },
    onError: (err) => onErr(err, "Failed to stop"),
  });
  const deleteApp = useMutation({
    mutationFn: (id: number) => api(`/websites/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Removed from list (processes stopped)");
    },
    onError: (err) => onErr(err, "Failed to delete"),
  });
  const startSvc = useMutation({
    mutationFn: (id: number) => api(`/websites/services/${id}/start`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      if (checkFor != null) checkQuery.refetch();
    },
    onError: (err) => onErr(err, "Failed to start service"),
  });
  const stopSvc = useMutation({
    mutationFn: (id: number) => api(`/websites/services/${id}/stop`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      if (checkFor != null) checkQuery.refetch();
    },
    onError: (err) => onErr(err, "Failed to stop service"),
  });
  const exposeSvc = useMutation({
    mutationFn: (id: number) =>
      api<{ ok: boolean; tunnel_url: string | null }>(
        `/websites/services/${id}/expose`,
        { method: "POST" }
      ),
    onSuccess: (res) => {
      invalidate();
      if (checkFor != null) checkQuery.refetch();
      if (res.tunnel_url) {
        toast.success(`Online: ${res.tunnel_url}`);
      } else {
        toast.success("Tunnel started, URL will appear shortly…");
      }
    },
    onError: (err) => onErr(err, "Failed to expose service"),
  });
  const unexposeSvc = useMutation({
    mutationFn: (id: number) =>
      api<{ ok: boolean; killed: number[] }>(`/websites/services/${id}/unexpose`, { method: "POST" }),
    onSuccess: (res) => {
      invalidate();
      if (checkFor != null) checkQuery.refetch();
      toast.success(
        res.killed?.length
          ? `Service taken offline (${res.killed.length} proses dihentikan)`
          : "Service taken offline"
      );
    },
    onError: (err) => onErr(err, "Failed to stop tunnel"),
  });
  const setTunnelAuto = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api<{ ok: boolean; tunnel_auto: boolean }>(
        `/websites/services/${id}/tunnel-auto`,
        { method: "PUT", body: JSON.stringify({ enabled }) }
      ),
    onSuccess: () => {
      invalidate();
      if (checkFor != null) checkQuery.refetch();
    },
    onError: (err) => onErr(err, "Failed to set auto online"),
  });
  const buildDocker = useMutation({
    mutationFn: (id: number) =>
      api<{ output: string }>(`/websites/${id}/build`, { method: "POST" }),
    onSuccess: (res) => { invalidate(); toast.success(res.output); },
    onError: (err) => onErr(err, "Docker build failed"),
  });
  const deleteDocker = useMutation({
    mutationFn: (id: number) =>
      api<{ ok: boolean; output: string }>(`/websites/${id}/docker-delete`, { method: "POST" }),
    onSuccess: (res) => { invalidate(); toast.success(res.output || "Docker cleaned up"); },
    onError: (err) => onErr(err, "Failed to delete docker resources"),
  });
  const runLocal = useMutation({
    mutationFn: (id: number) =>
      api<{ port: number }>(`/websites/${id}/local`, { method: "POST" }),
    onSuccess: (res) => {
      invalidate();
      const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
      window.open(`http://${host}:${res.port}`, "_blank");
    },
    onError: (err) => onErr(err, "Localhost failed"),
  });
  const composeUp = useMutation({
    mutationFn: (id: number) => api(`/websites/${id}/compose-up`, { method: "POST" }),
    onSuccess: () => { invalidate(); toast.success("Compose up"); },
    onError: (err) => onErr(err, "Compose up failed"),
  });
  const composeDown = useMutation({
    mutationFn: (id: number) => api(`/websites/${id}/compose-down`, { method: "POST" }),
    onSuccess: () => { invalidate(); toast.success("Compose down"); },
    onError: (err) => onErr(err, "Compose down failed"),
  });
  const composeLogsQuery = useQuery({
    queryKey: ["web-compose-logs", composeLogsFor],
    queryFn: () =>
      api<{ lines: string[] }>(`/websites/${composeLogsFor}/compose-logs?lines=300`),
    enabled: composeLogsFor != null,
    refetchInterval: 5000,
  });

  const websiteTerminal = useMutation({
    mutationFn: ({ id, command }: { id: number; command: string }) =>
      api<{ output: string }>(`/terminal/website/${id}`, {
        method: "POST",
        body: JSON.stringify({ command }),
      }),
    onSuccess: (res) => setTerminalOutput((lines) => [...lines, res.output]),
    onError: (err) => onErr(err, "Website terminal failed"),
  });

  const syncToDocker = useMutation({
    mutationFn: (id: number) =>
      api<{ ok: boolean; results: SyncResult[] }>(`/websites/${id}/sync`, { method: "POST" }),
    onSuccess: (res) => {
      invalidate();
      const failed = res.results.filter((r) => r.error);
      if (failed.length === 0) {
        toast.success(`Synced ${res.results.reduce((a, r) => a + (r.files_synced ?? 0), 0)} files to Docker`);
      } else if (failed.length < res.results.length) {
        toast.warning(`Partially synced — failed: ${failed.map((f) => f.label).join(", ")}`);
      } else {
        toast.error(`Sync failed: ${failed.map((f) => f.error).join(", ")}`);
      }
    },
    onError: (err) => onErr(err, "Sync to Docker failed"),
  });

  const detailQuery = useQuery({
    queryKey: ["web-detail", detailFor],
    queryFn: () => api<WebsiteDetail>(`/websites/${detailFor}/detail`),
    enabled: detailFor != null,
  });

  const dockerLogsQuery = useQuery({
    queryKey: ["web-docker-logs", dockerLogsFor],
    queryFn: () => api<{ lines: string[] }>(`/websites/${dockerLogsFor}/docker-logs?lines=300`),
    enabled: dockerLogsFor != null,
    refetchInterval: 5000,
  });

  const depsQuery = useQuery({
    queryKey: ["web-deps", detailFor],
    queryFn: () => api<{ dependencies: DependencyInfo[] }>(`/websites/${detailFor}/dependencies`),
    enabled: detailFor != null,
  });

  const restartContainer = useMutation({
    mutationFn: ({ name }: { name: string }) =>
      api(`/docker/${name}/action`, {
        method: "POST",
        body: JSON.stringify({ action: "restart" }),
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Container restarted");
    },
    onError: (err) => onErr(err, "Failed to restart container"),
  });

  const logsQuery = useQuery({
    queryKey: ["web-logs", logsFor],
    queryFn: () => api<{ lines: string[] }>(`/websites/services/${logsFor}/logs`),
    enabled: logsFor != null,
    refetchInterval: 3000,
  });

  // check tunnel/service state (tombol "Cek") — auto-refresh selama modal terbuka
  const checkQuery = useQuery({
    queryKey: ["web-check", checkFor],
    queryFn: () => api<ServiceCheckResult>(`/websites/services/${checkFor}/check`),
    enabled: checkFor != null,
    refetchInterval: checkFor != null ? 4000 : false,
    refetchIntervalInBackground: true,
  });
  const checkSvc =
    checkFor != null
      ? appsQuery.data?.apps.flatMap((a) => a.services).find((s) => s.id === checkFor) ?? null
      : null;

  // ------------------------------------------------------ deploy via upload
  const deployUpload = useMutation({
    mutationFn: ({
      appId,
      serviceId,
      file,
      restart,
      syncDocker,
    }: {
      appId: number;
      serviceId: number;
      file: File;
      restart: boolean;
      syncDocker: boolean;
    }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("service_id", String(serviceId));
      form.append("restart", restart ? "1" : "0");
      form.append("sync_docker", syncDocker ? "1" : "0");
      return apiUpload<{ ok: boolean; job_id: string }>(
        `/websites/${appId}/upload`,
        form,
        setDeployUploadPct
      );
    },
    onSuccess: (res) => {
      setDeployUploadPct(null);
      setDeployJobId(res.job_id);
      toast.success("Zip ter-upload — update berjalan di background");
    },
    onError: (err) => onErr(err, "Upload gagal"),
  });

  const deployQuery = useQuery({
    queryKey: ["web-deploy", deployJobId],
    queryFn: () => api<DeployJob>(`/websites/deploys/${deployJobId}`),
    enabled: deployJobId != null,
    refetchInterval: (q) =>
      q.state.data &&
      (q.state.data.status === "done" || q.state.data.status === "failed")
        ? false
        : 1500,
  });

  const deployNotifiedRef = useRef<"done" | "failed" | null>(null);
  const deployJob = deployQuery.data;
  useEffect(() => {
    if (!deployJob) return;
    if (deployJob.status !== "done" && deployJob.status !== "failed") return;
    const finalStatus = deployJob.status;
    invalidate();
    if (deployNotifiedRef.current !== finalStatus) {
      deployNotifiedRef.current = finalStatus;
      if (finalStatus === "done") {
        toast.success("Update selesai — website tetap online");
      } else {
        toast.error(deployJob.error || "Update gagal — lihat log");
      }
    }
  }, [deployJob, deployJob?.status, invalidate]);

  const openDeploy = (appId: number) => {
    setDeployFor(appId);
    setDeployServiceId(0);
    setDeployZipFile(null);
    setDeployZipName("");
    setDeployRestart(false);
    setDeploySyncDocker(true);
    setDeployJobId(null);
    setDeployUploadPct(null);
    deployNotifiedRef.current = null;
  };

  const closeDeploy = () => {
    setDeployFor(null);
    setDeployJobId(null);
    setDeployZipFile(null);
    setDeployZipName("");
    setDeployUploadPct(null);
  };

  // ------------------------------------------------------------- derived
  const apps = appsQuery.data?.apps ?? [];
  const anyRunning = useMemo(
    () => apps.some((a) => a.services.some((s) => s.pid)),
    [apps]
  );

  const deployApp = deployFor
    ? apps.find((a) => a.id === deployFor)
    : undefined;
  const deploySvc = deployApp
    ? deployApp.services.find((s) => s.id === deployServiceId) ??
      deployApp.services[0]
    : undefined;

  const appSort = useTableSort<WebApp>(
    apps,
    {
      name: (a) => a.name,
      status: (a) => (a.services.some((s) => s.status === "ONLINE") ? 1 : 0),
      port: (a) => a.services[0]?.resolved_port || a.services[0]?.port || 0,
    },
    "name"
  );

  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const submitRun = () => {
    const missing = rows.findIndex((r) => !r.dir.trim() || !r.command.trim());
    if (missing >= 0) {
      setFormError(
        `Row ${missing + 1}: folder and command are required`
      );
      return;
    }
    for (const r of rows) {
      if (r.port.trim() && !/^\d+$/.test(r.port.trim())) {
        setFormError(`Port must be a number (leave empty for auto port)`);
        return;
      }
    }
    setFormError("");
    runSite.mutate();
  };

  const openUrl = (s: WebService) => {
    const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
    window.open(`http://${host}:${s.resolved_port}`, "_blank");
  };

  return (
    <>
      <PageHeader
        title="Websites"
        subtitle="Run & expose localhost projects — pick folder, enter command, go online with Cloudflare Tunnel"
        onRefresh={invalidate}
        refreshing={appsQuery.isLoading}
      />

      {/* ------------------------------------ unmanaged / detected projects */}
      {(reconcileQuery.data?.unmanaged.length ?? 0) > 0 ? (
        <div className="card mb-4 border-[#4a3a12]">
          <div className="card-header">
            <div>
              <div className="card-title flex items-center gap-2">
                <Radar size={15} className="text-yellow-500" />
                Terdeteksi tapi belum dikelola ({reconcileQuery.data!.unmanaged.length})
              </div>
              <div className="card-subtitle">
                Project docker-compose sedang jalan tapi belum terdaftar di panel.
                Adopsi dulu supaya bisa Start/Stop/Logs dari sini.
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {reconcileQuery.data!.unmanaged.map((p) => (
              <div
                key={`${p.project}@${p.project_dir}`}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel2 px-3 py-2"
              >
                <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-ok shadow-[0_0_8px_#22c55e]" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold">{p.name_suggest}</div>
                  <div className="truncate font-mono text-[10px] text-muted2" title={p.project_dir}>
                    {p.project_dir} · {p.compose_file} · project: {p.project}
                  </div>
                </div>
                <span className="text-[10px] text-muted2">
                  {p.running_services.join(", ")}
                  {p.ports.length ? ` · ${p.ports[0]}` : ""}
                </span>
                <button
                  className="btn btn-primary py-1.5 text-xs"
                  disabled={adoptProject.isPending}
                  onClick={() => adoptProject.mutate(p)}
                  title="Daftarkan ke panel tanpa menyentuh container yang jalan"
                >
                  {adoptProject.isPending ? "Mengadopsi…" : "Adopsi"}
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* --------------------------------------------------- run form */}
      <div className="card mb-4">
        <button
          className="flex w-full items-center gap-2 text-left"
          onClick={() => setFormOpen((v) => !v)}
          aria-expanded={formOpen}
        >
          <ChevronDown
            size={15}
            className={`shrink-0 text-muted2 transition-transform ${formOpen ? "" : "-rotate-90"}`}
          />
          <span className="card-title">Tambah Website</span>
          <span className="card-subtitle ml-1">
            {formOpen
              ? "leave port empty for an automatic one based on the framework"
              : "klik untuk membuka form"}
          </span>
        </button>

        {formOpen ? (
        <>
        <div className="mb-4 mt-4 flex flex-wrap items-end gap-3">
          <label className="text-[11px] text-muted">
            Site Name (optional)
            <input
              className="input mt-1 w-64"
              placeholder={rows[0]?.dir ? baseName(rows[0].dir) : "my-project"}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="text-[11px] text-muted">
            Runtime
            <select className="input mt-1" value={runtime} onChange={(e) => setRuntime(e.target.value as "native" | "docker" | "docker-compose")}>
              <option value="native">Native process</option>
              <option value="docker">Docker</option>
              <option value="docker-compose">Docker Compose</option>
            </select>
          </label>
          <label className="text-[11px] text-muted">
            PHP version
            <select className="input mt-1 w-32" value={phpVersion} onChange={(e) => setPhpVersion(e.target.value)}>
              {phpOptions.map((version) => (
                <option key={version || "auto"} value={version}>
                  {version ? `PHP ${version}` : "Auto"}
                </option>
              ))}
            </select>
          </label>
          {runtime === "docker" ? (
            <label className="text-[11px] text-muted">
              Dockerfile
              <input className="input mt-1 w-40" value={dockerfile} onChange={(e) => setDockerfile(e.target.value)} />
            </label>
          ) : null}
          {runtime === "docker-compose" ? (
            <label className="text-[11px] text-muted">
              Compose file
              <input className="input mt-1 w-48" value={composeFile} onChange={(e) => setComposeFile(e.target.value)} placeholder="docker-compose.yml" />
            </label>
          ) : null}
        </div>

        {rows.map((row, i) => (
          <div
            key={i}
            className="mb-2 flex flex-col gap-2 rounded-xl border border-line bg-panel2 p-3 lg:flex-row lg:items-end"
          >
            <label className="text-[11px] text-muted lg:w-[38%]">
              Folder {rows.length > 1 ? `#${i + 1}` : ""}
              <button
                type="button"
                className="input mt-1 flex w-full items-center justify-between text-left"
                onClick={() => openBrowser(i)}
              >
                <span className={row.dir ? "" : "text-muted2"}>
                  {row.dir || "Click to choose the project folder…"}
                </span>
                <span className="ml-2 shrink-0 rounded-md border border-line px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-muted2">
                  Browse
                </span>
              </button>
            </label>
            <label className="flex-1 text-[11px] text-muted">
              Command
              <input
                className="input mt-1 w-full font-mono text-xs"
                placeholder="npm run dev / python manage.py runserver / php artisan serve"
                value={row.command}
                onChange={(e) => setRow(i, { command: e.target.value })}
              />
            </label>
            <label className="text-[11px] text-muted lg:w-28">
              Port
              <input
                className="input mt-1 w-full"
                placeholder="auto"
                value={row.port}
                onChange={(e) => setRow(i, { port: e.target.value })}
              />
            </label>
            {rows.length > 1 ? (
              <button
                type="button"
                className="action-btn text-bad"
                onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              >
                Remove
              </button>
            ) : null}
          </div>
        ))}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            className="btn"
            disabled={rows.length >= 8}
            onClick={() => setRows((rs) => [...rs, { ...EMPTY_ROW }])}
          >
            <Plus size={12} /> Add Folder / Part
          </button>
          <span className="text-[11px] text-muted2">
            multi-folder (backend + frontend) runs as one entry in the list
          </span>
          <div className="ml-auto flex items-center gap-2">
            {formError ? (
              <span className="text-[11px] text-bad">{formError}</span>
            ) : null}
            <button
              className="btn"
              onClick={() => {
                setFormOpen(false);
                setRows([{ ...EMPTY_ROW }]);
                setFormError("");
              }}
            >
              Cancel
            </button>
            <button
              className="btn btn-primary"
              disabled={runSite.isPending}
              onClick={submitRun}
            >
              {runSite.isPending ? "Starting…" : "▶ Run"}
            </button>
          </div>
        </div>
        </>
        ) : null}
      </div>

      {/* --------------------------------------------------- site list */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Website List</div>
            <div className="card-subtitle">
              {anyRunning ? "status refreshes every few seconds" : "nothing running yet"}
            </div>
          </div>
        </div>

        {apps.length === 0 && !appsQuery.isLoading ? (
          <div className="py-8 text-center text-sm text-muted2">
            No websites yet — fill the form above and hit Run
          </div>
        ) : null}

        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted">Sort:</span>
          {[
            { k: "name", label: "Name" },
            { k: "status", label: "Status" },
            { k: "port", label: "Port" },
          ].map((c) => (
            <button
              key={c.k}
              className={`btn px-2 py-1 text-[11px] ${
                appSort.key === c.k ? "btn-primary" : ""
              }`}
              onClick={() => appSort.toggle(c.k)}
            >
              {c.label}{" "}
              {appSort.key === c.k ? (
                <span className="text-[9px]">{appSort.dir === "asc" ? "▲" : "▼"}</span>
              ) : null}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {appSort.sorted.map((app) => {
            // Default tertutup: website docker-compose tidak punya parts native,
            // jadi tidak perlu panel tambahan terbuka begitu saja.
            const isOpen = expanded[app.id] ?? false;
            const allOnline = app.online === app.total && app.total > 0;
            return (
              <div key={app.id} className="rounded-xl border border-line bg-panel2">
                <div className="flex flex-wrap items-center gap-3 p-3">
                  <button
                    className="action-btn"
                    title="Show parts"
                    onClick={() =>
                      setExpanded((e) => ({ ...e, [app.id]: !isOpen }))
                    }
                  >
                    {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <span
                    className={`h-[8px] w-[8px] shrink-0 rounded-full ${
                      allOnline
                        ? "bg-ok shadow-[0_0_8px_#22c55e]"
                        : app.online > 0
                          ? "bg-yellow-500 shadow-[0_0_8px_#eab308]"
                          : "bg-bad"
                    }`}
                  />
                  <strong
                    className="cursor-pointer hover:underline"
                    title="Click to view full details"
                    onClick={() => setDetailFor(app.id)}
                  >
                    {app.name}
                  </strong>
                  <span className="rounded-md border border-line px-1.5 py-0.5 text-[9px] uppercase text-muted2">
                    {app.runtime}
                  </span>
                  {app.runtime === "docker" && app.docker_status ? (
                    <span className={`rounded-md border px-1.5 py-0.5 text-[9px] uppercase ${
                      app.docker_status === "BUILT"
                        ? "border-[#1c6636] bg-[#102118] text-[#9df2b8]"
                        : "border-[#6b2525] bg-[#241112] text-[#ffadad]"
                    }`}>
                      {app.docker_status}
                    </span>
                  ) : null}
                  <StatusBadge status={allOnline ? "online" : app.online > 0 ? "info" : "offline"} />
                  <span className="text-[11px] text-muted2">
                    {app.online}/{app.total} online ·{" "}
                    {app.runtime === "docker-compose"
                      ? `${app.compose_status?.services.length ?? 0} containers`
                      : app.services.length > 1
                        ? `${app.services.length} parts`
                        : app.services[0]?.dir}
                  </span>
                  <div className="ml-auto flex gap-1.5">
                    {/* Aksi utama: satu tombol Start/Stop sesuai status saat ini.
                        Compose memakai up/down sesuai status container agar tidak
                        ada dua tombol yang tumpang tindih. */}
                    {app.runtime === "docker-compose" ? (
                      allOnline ? (
                        <button
                          className="btn py-1.5 text-xs text-bad"
                          disabled={composeDown.isPending}
                          onClick={() => composeDown.mutate(app.id)}
                        >
                          {composeDown.isPending ? "Stopping…" : "Stop"}
                        </button>
                      ) : (
                        <button
                          className="btn btn-primary py-1.5 text-xs"
                          disabled={composeUp.isPending}
                          onClick={() => composeUp.mutate(app.id)}
                        >
                          {composeUp.isPending ? "Starting…" : "Start"}
                        </button>
                      )
                    ) : allOnline ? (
                      <button
                        className="btn py-1.5 text-xs"
                        disabled={stopApp.isPending}
                        onClick={() => stopApp.mutate(app.id)}
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        className="btn btn-primary py-1.5 text-xs"
                        disabled={startApp.isPending}
                        onClick={() => startApp.mutate(app.id)}
                      >
                        Start
                      </button>
                    )}

                    {/* Aksi sekunder disembunyikan di menu "⋯" supaya baris
                        website tidak dipenuhi belasan tombol. */}
                    <div className="relative">
                      <button
                        className="action-btn"
                        title="More actions"
                        aria-haspopup="menu"
                        aria-expanded={moreFor === app.id}
                        onClick={() =>
                          setMoreFor((cur) => (cur === app.id ? null : app.id))
                        }
                      >
                        <MoreHorizontal size={14} />
                      </button>

                      {moreFor === app.id ? (
                        <>
                          <div
                            className="fixed inset-0 z-40"
                            onClick={() => setMoreFor(null)}
                          />
                          <div
                            role="menu"
                            className="absolute right-0 z-50 mt-1 w-52 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
                          >
                            <button
                              className="menu-item"
                              onClick={() => {
                                setMoreFor(null);
                                runLocal.mutate(app.id);
                              }}
                            >
                              <Link2 size={12} /> Localhost
                            </button>
                            <button
                              className="menu-item"
                              onClick={() => {
                                setMoreFor(null);
                                openDeploy(app.id);
                              }}
                            >
                              <UploadCloud size={12} /> Update (upload zip)
                            </button>
                            <button
                              className="menu-item"
                              onClick={() => {
                                setMoreFor(null);
                                setDetailFor(app.id);
                              }}
                            >
                              <Activity size={12} /> Details
                            </button>
                            <button
                              className="menu-item"
                              onClick={() => {
                                setMoreFor(null);
                                setTerminalFor((current) =>
                                  current === app.id ? null : app.id
                                );
                                setTerminalOutput([]);
                              }}
                            >
                              <Terminal size={12} /> Terminal
                            </button>
                            {app.runtime === "docker-compose" ? (
                              <button
                                className="menu-item"
                                onClick={() => {
                                  setMoreFor(null);
                                  setComposeLogsFor((cur) =>
                                    cur === app.id ? null : app.id
                                  );
                                }}
                              >
                                <Activity size={12} /> Containers & logs
                              </button>
                            ) : (
                              <button
                                className="menu-item"
                                onClick={() => {
                                  setMoreFor(null);
                                  setExpanded((e) => ({ ...e, [app.id]: !isOpen }));
                                }}
                              >
                                <Box size={12} /> Parts
                              </button>
                            )}

                            {app.runtime === "docker" ? (
                              <>
                                <div className="my-1 border-t border-line" />
                                <button
                                  className="menu-item"
                                  disabled={buildDocker.isPending}
                                  onClick={() => {
                                    setMoreFor(null);
                                    buildDocker.mutate(app.id);
                                  }}
                                >
                                  {buildDocker.isPending ? (
                                    <><Loader2 size={12} className="spinner" /> Building…</>
                                  ) : (
                                    <><Hammer size={12} /> Build Docker</>
                                  )}
                                </button>
                                {app.docker_container ? (
                                  <button
                                    className="menu-item"
                                    disabled={syncToDocker.isPending}
                                    onClick={() => {
                                      setMoreFor(null);
                                      syncToDocker.mutate(app.id);
                                    }}
                                  >
                                    {syncToDocker.isPending ? (
                                      <><Loader2 size={12} className="spinner" /> Syncing…</>
                                    ) : (
                                      <><RefreshCw size={12} /> Sync to Docker</>
                                    )}
                                  </button>
                                ) : null}
                                {app.docker_container ? (
                                  <button
                                    className="menu-item text-bad"
                                    disabled={deleteDocker.isPending}
                                    onClick={async () => {
                                      setMoreFor(null);
                                      if (
                                        await confirm({
                                          message: `Delete docker resources for "${app.name}"? Container "${app.docker_container}" and image will be removed.`,
                                          confirmText: "Yes, delete",
                                        })
                                      )
                                        deleteDocker.mutate(app.id);
                                    }}
                                  >
                                    <Trash2 size={12} /> Delete Docker
                                  </button>
                                ) : null}
                              </>
                            ) : null}

                            {app.runtime === "docker-compose" ? (
                              <>
                                <div className="my-1 border-t border-line" />
                                <button
                                  className="menu-item"
                                  onClick={() => {
                                    setMoreFor(null);
                                    composeUp.mutate(app.id);
                                  }}
                                >
                                  <Play size={12} /> Compose Up (rebuild)
                                </button>
                                <button
                                  className="menu-item text-bad"
                                  onClick={() => {
                                    setMoreFor(null);
                                    composeDown.mutate(app.id);
                                  }}
                                >
                                  <Square size={12} /> Compose Down
                                </button>
                              </>
                            ) : null}

                            <div className="my-1 border-t border-line" />
                            <button
                              className="menu-item text-bad"
                              disabled={deleteApp.isPending}
                              onClick={async () => {
                                setMoreFor(null);
                                if (
                                  await confirm({
                                    message: `Remove "${app.name}" from the list? Running processes will be stopped.`,
                                    confirmText: "Yes, remove",
                                  })
                                )
                                  deleteApp.mutate(app.id);
                              }}
                            >
                              <Trash2 size={12} /> Remove from list
                            </button>
                          </div>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>

                {app.compose_error ? (
                  <div className="border-t border-line px-3 py-1.5 text-[11px] text-bad">
                    {app.compose_error}
                  </div>
                ) : null}

                {/* Container + log compose: hidden by default, dibuka lewat menu ⋯ */}
                {app.runtime === "docker-compose" &&
                (composeLogsFor === app.id || app.compose_status?.services.some((s) => s.status !== "ONLINE")) ? (
                  <div className="border-t border-line px-3 py-2">
                    <div className="mb-1.5 flex items-center justify-between">
                      <div className="text-[10px] uppercase tracking-wider text-muted2">
                        Containers
                      </div>
                      <button
                        className="action-btn"
                        onClick={() =>
                          setComposeLogsFor((cur) => (cur === app.id ? null : app.id))
                        }
                      >
                        {composeLogsFor === app.id ? "Hide logs" : "Show logs"}
                      </button>
                    </div>
                    <div className="mb-2 space-y-1">
                      {(app.compose_status?.services ?? []).map((s) => (
                        <div
                          key={s.name}
                          className="flex flex-wrap items-center gap-2 text-[11px]"
                        >
                          <span
                            className={`h-[6px] w-[6px] shrink-0 rounded-full ${
                              s.status === "ONLINE" ? "bg-ok" : "bg-bad"
                            }`}
                          />
                          <span className="font-mono text-[#d9e0e8]">{s.name}</span>
                          <span className="text-muted2">{s.health}</span>
                          {s.ports.length ? (
                            <span className="font-mono text-[10px] text-muted2">
                              {s.ports.join(" ")}
                            </span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                    {composeLogsFor === app.id ? (
                      <pre className="max-h-56 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-green-200">
                        {composeLogsQuery.data?.lines.join("\n") || "no output yet…"}
                      </pre>
                    ) : null}
                  </div>
                ) : null}

                {terminalFor === app.id ? (
                  <div className="border-t border-line bg-[#060a0d] p-3 font-mono text-[11px]">
                    <div className="mb-2 max-h-36 overflow-auto whitespace-pre-wrap text-[#aab6c3]">
                      {terminalOutput.length ? terminalOutput.join("\n") : `Project terminal: ${app.services[0]?.dir ?? ""}`}
                    </div>
                    <form
                      className="flex items-center gap-2"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const command = terminalCommand.trim();
                        if (!command) return;
                        setTerminalOutput((lines) => [...lines, `$ ${command}`]);
                        setTerminalCommand("");
                        websiteTerminal.mutate({ id: app.id, command });
                      }}
                    >
                      <span className="text-[#6ee28a]">$</span>
                      <input
                        className="w-full border-0 bg-transparent font-mono text-[11px] text-white outline-none"
                        value={terminalCommand}
                        onChange={(event) => setTerminalCommand(event.target.value)}
                        placeholder="php artisan --version / npm install / composer install"
                        autoFocus
                      />
                    </form>
                  </div>
                ) : null}

                {isOpen ? (
                  <div className="border-t border-line px-3 pb-3 pt-2">
                    {app.runtime === "docker" && app.docker_container ? (
                      <div className="mb-3 rounded-lg border border-[#1d3d66] bg-[#111f34] p-3">
                        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[#9fc5ff]">
                          Docker Info
                        </div>
                        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[11px] md:grid-cols-4">
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Container</span>
                            <div className="truncate font-mono text-[#d9e0e8]">{app.docker_container}</div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Image</span>
                            <div className="truncate font-mono text-[#d9e0e8]">{app.docker_image || "-"}</div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Dockerfile</span>
                            <div className="truncate font-mono text-[#d9e0e8]">{app.dockerfile || "-"}</div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Status</span>
                            <div className={`font-bold ${app.docker_status === "BUILT" ? "text-[#9df2b8]" : "text-[#ffadad]"}`}>
                              {app.docker_status || "-"}
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : null}
                    {app.services.map((s) => (
                      <ServiceRow
                        key={s.id}
                        svc={s}
                        onStart={() => startSvc.mutate(s.id)}
                        onStop={() => stopSvc.mutate(s.id)}
                        onOpen={() => openUrl(s)}
                        onExpose={() => exposeSvc.mutate(s.id)}
                        onUnexpose={() => unexposeSvc.mutate(s.id)}
                        onCheck={() => setCheckFor((cur) => (cur === s.id ? null : s.id))}
                        showLogs={() =>
                          setLogsFor((cur) => (cur === s.id ? null : s.id))
                        }
                        pending={startSvc.isPending || stopSvc.isPending}
                        exposePending={exposeSvc.isPending || unexposeSvc.isPending}
                      />
                    ))}
                    {logsFor != null ? (
                      <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-line bg-black/40 p-3 text-[10px] leading-relaxed text-green-200">
                        {logsQuery.data?.lines.join("\n") || "no output yet…"}
                      </pre>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {/* -------------------------------------------- website detail modal */}
      {detailFor ? (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4"
          onClick={() => { setDetailFor(null); setDockerLogsFor(null); }}
        >
          <div
            className="card max-h-[90vh] w-full max-w-3xl overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div>
                <div className="card-title flex items-center gap-2">
                  {detailQuery.data?.name || "Loading..."}
                  {detailQuery.data ? (
                    <>
                      <StatusBadge
                        status={detailQuery.data.online === detailQuery.data.total && detailQuery.data.total > 0 ? "online" : detailQuery.data.online > 0 ? "info" : "offline"}
                      />
                      <span className="rounded-md border border-line px-1.5 py-0.5 text-[9px] uppercase text-muted2">
                        {detailQuery.data.runtime}
                      </span>
                      {detailQuery.data.docker_status ? (
                        <span className={`rounded-md border px-1.5 py-0.5 text-[9px] uppercase ${
                          detailQuery.data.docker_status === "BUILT"
                            ? "border-[#1c6636] bg-[#102118] text-[#9df2b8]"
                            : "border-[#6b2525] bg-[#241112] text-[#ffadad]"
                        }`}>
                          {detailQuery.data.docker_status}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                </div>
                <div className="font-mono text-[11px] text-muted">
                  {detailQuery.data?.services[0]?.dir || "…"}
                </div>
              </div>
              <button className="btn" onClick={() => { setDetailFor(null); setDockerLogsFor(null); }}>
                ×
              </button>
            </div>

            {detailQuery.isLoading ? (
              <div className="py-10 text-center text-sm text-muted2">Loading detail…</div>
            ) : detailQuery.isError || !detailQuery.data ? (
              <div className="py-6 text-center text-xs text-bad">
                Gagal memuat detail: {detailQuery.error instanceof Error ? detailQuery.error.message : "unknown"}
              </div>
            ) : (
              <div className="space-y-5 p-1">
                {/* info umum */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] md:grid-cols-3">
                  <Info label="Name" value={detailQuery.data.name} />
                  <Info label="Runtime" value={detailQuery.data.runtime} />
                  <Info label="PHP Version" value={detailQuery.data.php_version || "-"} />
                  <Info label="Created" value={detailQuery.data.created_at} mono />
                  <Info label="Services" value={`${detailQuery.data.services.length} service(s)`} />
                  <Info label="Status" value={`${detailQuery.data.online}/${detailQuery.data.total} online`} />
                </div>

                {/* docker info */}
                {detailQuery.data.runtime === "docker" && detailQuery.data.docker_container ? (
                  <section>
                    <SectionTitle>
                      <Box size={12} className="mr-1 inline" />
                      Docker Container
                    </SectionTitle>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] md:grid-cols-3">
                      <Info label="Container" value={detailQuery.data.docker_container} mono />
                      <Info label="Image" value={detailQuery.data.docker_image || "-"} mono />
                      <Info label="Dockerfile" value={detailQuery.data.dockerfile || "-"} mono />
                      <Info label="Status" value={detailQuery.data.docker_status || "-"} />
                      {detailQuery.data.container_detail ? (
                        <>
                          <Info label="Uptime" value={detailQuery.data.container_detail.uptime ?? "-"} />
                          <Info label="Health" value={detailQuery.data.container_detail.health ?? "-"} />
                          <Info label="Restart Policy" value={detailQuery.data.container_detail.restart_policy || "-"} />
                          <Info label="Command" value={detailQuery.data.container_detail.command || "-"} mono />
                        </>
                      ) : null}
                    </div>

                    {/* port mapping */}
                    {detailQuery.data.container_detail && detailQuery.data.container_detail.port_map.length > 0 ? (
                      <div className="mt-3">
                        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted2">Ports</div>
                        <table className="w-full text-[11px]">
                          <thead>
                            <tr className="text-left text-muted2">
                              <th className="pb-1">Host</th>
                              <th className="pb-1">Container</th>
                            </tr>
                          </thead>
                          <tbody className="font-mono">
                            {detailQuery.data.container_detail.port_map.map((p, i) => (
                              <tr key={i} className="border-t border-line">
                                <td className="py-1">{p.host_port ?? "—"}</td>
                                <td>{p.container}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}

                    {/* networks */}
                    {detailQuery.data.container_detail && detailQuery.data.container_detail.networks.length > 0 ? (
                      <div className="mt-3">
                        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted2">Networks</div>
                        <div className="flex flex-wrap gap-1">
                          {detailQuery.data.container_detail.networks.map((n) => (
                            <span key={n} className="rounded-md border border-line bg-panel2 px-2 py-0.5 font-mono text-[10px]">
                              {n}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {/* docker logs */}
                    <div className="mt-3">
                      <div className="mb-1 flex items-center justify-between">
                        <div className="text-[10px] uppercase tracking-wider text-muted2">Container Logs</div>
                        <button
                          className="action-btn text-[10px]"
                          onClick={() => setDockerLogsFor(dockerLogsFor === detailFor ? null : detailFor)}
                        >
                          {dockerLogsFor === detailFor ? "Hide Logs" : "Show Logs"}
                        </button>
                      </div>
                      {dockerLogsFor === detailFor ? (
                        <pre className="max-h-48 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-green-200">
                          {dockerLogsQuery.data?.lines.join("\n") || "loading logs..."}
                        </pre>
                      ) : null}
                    </div>
                  </section>
                ) : null}

                {/* services */}
                <section>
                  <SectionTitle>Services ({detailQuery.data.services.length})</SectionTitle>
                  <div className="space-y-2">
                    {detailQuery.data.services.map((svc) => (
                      <div key={svc.id} className="rounded-lg border border-line bg-panel2 p-3">
                        <div className="mb-2 flex items-center gap-2">
                          <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${svc.status === "ONLINE" ? "bg-ok shadow-[0_0_8px_#22c55e]" : "bg-bad"}`} />
                          <strong className="text-xs">{svc.label}</strong>
                          <StatusBadge status={svc.status === "ONLINE" ? "online" : "offline"} />
                          {svc.tunnel_url ? (
                            <a
                              href={svc.tunnel_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[10px] text-ok underline"
                            >
                              {svc.tunnel_url.replace("https://", "")}
                            </a>
                          ) : null}
                        </div>
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] md:grid-cols-4">
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Folder</span>
                            <div className={`truncate font-mono ${svc.dir_exists ? "text-[#d9e0e8]" : "text-[#ff6b6b]"}`}>
                              {svc.dir}
                              {svc.dir_exists === false ? " (not found)" : ""}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Command</span>
                            <div className="truncate font-mono text-[#d9e0e8]">{svc.command}</div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Port</span>
                            <div className="font-mono text-[#d9e0e8]">
                              {svc.resolved_port > 0 ? svc.resolved_port : "-"}
                              {svc.port === 0 ? " (auto)" : ""}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase text-muted2">Folder Size</span>
                            <div className="font-mono text-[#d9e0e8]">
                              {svc.dir_size != null ? `${(svc.dir_size / 1024 / 1024).toFixed(1)} MB` : "-"}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* dependencies / version requirements */}
                {depsQuery.data && depsQuery.data.dependencies.length > 0 ? (
                  <section>
                    <SectionTitle>Dependency Versions</SectionTitle>
                    <div className="space-y-3">
                      {depsQuery.data.dependencies.map((dep, i) => (
                        <div key={i} className="rounded-lg border border-line bg-panel2 p-3">
                          <div className="mb-2 flex items-center gap-2">
                            <strong className="text-xs">{dep.label}</strong>
                            {dep.error ? (
                              <span className="text-[10px] text-bad">{dep.error}</span>
                            ) : (
                              <span className="rounded-md border border-line px-1.5 py-0.5 text-[9px] uppercase text-muted2">
                                {dep.language}
                              </span>
                            )}
                          </div>

                          {!dep.error ? (
                            <div className="space-y-2 text-[11px]">
                              {/* PHP */}
                              {dep.php ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-md bg-[#1a1a2e] px-2 py-0.5 text-[10px] font-bold text-[#9fc5ff]">
                                    PHP {dep.php.version}
                                  </span>
                                  {dep.php.extensions.length > 0 ? (
                                    <span className="text-[10px] text-muted">
                                      Extensions: {dep.php.extensions.join(", ")}
                                    </span>
                                  ) : null}
                                </div>
                              ) : null}

                              {/* Node */}
                              {dep.node ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-md bg-[#1a2e1a] px-2 py-0.5 text-[10px] font-bold text-[#9df2b8]">
                                    {dep.node.package_manager}
                                    {dep.node.version ? ` (Node ${dep.node.version})` : ""}
                                  </span>
                                </div>
                              ) : null}

                              {/* Python */}
                              {dep.python ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-md bg-[#2e2a1a] px-2 py-0.5 text-[10px] font-bold text-[#ffd58a]">
                                    Python {dep.python.version || "detected"}
                                  </span>
                                  {dep.python.packages.length > 0 ? (
                                    <span className="text-[10px] text-muted">
                                      {dep.python.packages.slice(0, 10).join(", ")}
                                      {dep.python.packages.length > 10 ? ` +${dep.python.packages.length - 10} more` : ""}
                                    </span>
                                  ) : null}
                                </div>
                              ) : null}

                              {/* Frameworks */}
                              {dep.frameworks.length > 0 ? (
                                <div className="flex flex-wrap gap-1">
                                  {dep.frameworks.map((fw) => (
                                    <span key={fw} className="rounded-md bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                                      {fw}
                                    </span>
                                  ))}
                                </div>
                              ) : null}

                              {/* Services */}
                              {dep.services.length > 0 ? (
                                <div>
                                  <span className="text-[10px] text-muted2">Required services:</span>
                                  <div className="mt-1 flex flex-wrap gap-1">
                                    {dep.services.map((svc) => (
                                      <span key={svc} className="rounded-md border border-[#6b5620] bg-[#241b09] px-2 py-0.5 text-[10px] text-[#ffd58a]">
                                        {svc}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              ) : null}

                              {/* Env files */}
                              {dep.env_files.length > 0 ? (
                                <div className="text-[10px] text-muted">
                                  Env files: {dep.env_files.join(", ")}
                                </div>
                              ) : null}

                              {/* Dockerfile */}
                              {dep.dockerfile ? (
                                <div className="text-[10px] text-ok">✓ Dockerfile present</div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </section>
                ) : depsQuery.isLoading ? (
                  <section>
                    <SectionTitle>Dependency Versions</SectionTitle>
                    <div className="py-4 text-center text-xs text-muted2">Scanning dependencies...</div>
                  </section>
                ) : null}

                {/* actions */}
                <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-3">
                  {detailQuery.data.runtime === "docker" && detailQuery.data.docker_container ? (
                    <>
                      <button
                        className="btn py-1.5 text-xs text-[#9fc5ff]"
                        disabled={syncToDocker.isPending}
                        onClick={() => syncToDocker.mutate(detailFor!)}
                      >
                        {syncToDocker.isPending ? (
                          <><Loader2 size={12} className="mr-1 inline spinner" /> Syncing…</>
                        ) : (
                          <><RefreshCw size={12} className="mr-1 inline" /> Sync to Docker</>
                        )}
                      </button>
                      <button
                        className="btn py-1.5 text-xs"
                        disabled={restartContainer.isPending}
                        onClick={() => restartContainer.mutate({ name: detailQuery.data!.docker_container })}
                      >
                        <RotateCw size={12} className="mr-1 inline" /> Restart Container
                      </button>
                    </>
                  ) : null}
                  {detailQuery.data.runtime === "docker-compose" ? (
                    <>
                      <button
                        className="btn py-1.5 text-xs text-ok"
                        disabled={composeUp.isPending}
                        onClick={() => composeUp.mutate(detailFor!)}
                      >
                        {composeUp.isPending ? (
                          <><Loader2 size={12} className="mr-1 inline spinner" /> Starting…</>
                        ) : (
                          <><Play size={12} className="mr-1 inline" /> Compose Up</>
                        )}
                      </button>
                      <button
                        className="btn py-1.5 text-xs text-bad"
                        disabled={composeDown.isPending}
                        onClick={() => composeDown.mutate(detailFor!)}
                      >
                        {composeDown.isPending ? (
                          <><Loader2 size={12} className="mr-1 inline spinner" /> Stopping…</>
                        ) : (
                          <><Square size={12} className="mr-1 inline" /> Compose Down</>
                        )}
                      </button>
                      {detailQuery.data.compose_error ? (
                        <span
                          className="w-full text-[11px] text-bad"
                          title={detailQuery.data.compose_error}
                        >
                          {detailQuery.data.compose_error}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                  <button
                    className="btn py-1.5 text-xs text-[#9fc5ff]"
                    onClick={() => openDeploy(detailFor!)}
                    title="Update folder website dengan upload zip — tanpa downtime"
                  >
                    <UploadCloud size={12} className="mr-1 inline" /> Update via Upload
                  </button>
                  {detailQuery.data.runtime !== "docker-compose" ? (
                    <>
                      <button
                        className="btn btn-primary py-1.5 text-xs"
                        disabled={startApp.isPending}
                        onClick={() => { startApp.mutate(detailFor!); }}
                      >
                        <Play size={12} className="mr-1 inline" /> Start All
                      </button>
                      <button
                        className="btn py-1.5 text-xs text-bad"
                        disabled={stopApp.isPending}
                        onClick={() => { stopApp.mutate(detailFor!); }}
                      >
                        <Square size={12} className="mr-1 inline" /> Stop All
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* -------------------------------------------- folder browser */}
      {browserOpen && browsePath ? (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4"
          onClick={() => setBrowserOpen(false)}
        >
          <div
            className="card w-full max-w-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div>
                <div className="card-title">Choose Project Folder</div>
                <div className="font-mono text-[11px] text-muted">
                  {browsePath.path}
                </div>
              </div>
              <button className="btn" onClick={() => setBrowserOpen(false)}>
                ×
              </button>
            </div>
            <div className="max-h-80 space-y-0.5 overflow-auto p-2">
              {browsePath.parent ? (
                <button
                  className="w-full rounded-lg px-3 py-1.5 text-left text-xs hover:bg-panel2"
                  onClick={() => drillDown(browsePath.parent!)}
                >
                  ↑ .. (up)
                </button>
              ) : null}
              {browsePath.dirs.map((d) => (
                <button
                  key={d}
                  className={`w-full rounded-lg px-3 py-1.5 text-left text-xs hover:bg-panel2 ${
                    browsePath.selected === `${browsePath.path}/${d}`
                      ? "bg-accent/20"
                      : ""
                  }`}
                  onClick={() => drillDown(`${browsePath.path}/${d}`)}
                >
                  ▸ {d}
                </button>
              ))}
              {browsePath.dirs.length === 0 ? (
                <div className="px-3 py-6 text-center text-xs text-muted2">
                  no subfolders here
                </div>
              ) : null}
            </div>
            <div className="flex justify-end gap-2 border-t border-line p-3">
              <button className="btn" onClick={() => setBrowserOpen(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  setRow(browserRow, { dir: browsePath.selected });
                  setBrowserOpen(false);
                }}
              >
                Use This Folder
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* -------------------------------------------- update via upload modal */}
      {deployFor ? (
        <div
          className="fixed inset-0 z-[120] grid place-items-center bg-black/60 p-4"
          onClick={closeDeploy}
        >
          <div
            className="card max-h-[90vh] w-full max-w-xl overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div>
                <div className="card-title flex items-center gap-2">
                  <UploadCloud size={15} className="text-accent" />
                  Update Website via Upload
                </div>
                <div className="mt-1 font-mono text-[11px] text-muted">
                  {deployApp?.name || "…"}
                </div>
              </div>
              <button className="btn" onClick={closeDeploy}>
                ×
              </button>
            </div>

            <div className="space-y-4 p-3">
              <p className="text-[11px] leading-relaxed text-muted2">
                Unggah <b>zip folder proyek</b> yang sudah diperbarui dari
                komputer lokal. File diganti langsung di lokasi folder — website{" "}
                <b>tetap online</b> dan auto-reload langsung membaca versi baru.{" "}
                <code className="font-mono">.env</code>,{" "}
                <code className="font-mono">node_modules</code>,{" "}
                <code className="font-mono">vendor</code>,{" "}
                <code className="font-mono">.next</code> dan{" "}
                <code className="font-mono">venv</code> dipertahankan.
              </p>

              {deployJob ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge
                      status={
                        deployJob.status === "done"
                          ? "online"
                          : deployJob.status === "failed"
                            ? "offline"
                            : "info"
                      }
                    />
                    <span className="text-[11px] text-muted">
                      {deployJob.status === "running"
                        ? "Mengupdate…"
                        : deployJob.status === "done"
                          ? "Selesai — website tetap online"
                          : "Gagal"}
                    </span>
                    <span className="ml-auto text-[10px] text-muted2">
                      {deployJob.service_label}
                    </span>
                  </div>

                  <div>
                    <div className="mb-1 flex justify-between text-[10px] text-muted2">
                      <span>{deployJob.stage}</span>
                      <span>{deployJob.progress}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded bg-panel2">
                      <div
                        className={`h-full transition-all ${
                          deployJob.status === "failed" ? "bg-bad" : "bg-ok"
                        }`}
                        style={{ width: `${deployJob.progress}%` }}
                      />
                    </div>
                  </div>

                  {deployJob.error ? (
                    <div className="rounded-lg border border-bad/40 bg-bad/10 p-2 text-[11px] text-bad">
                      {deployJob.error}
                    </div>
                  ) : null}

                  <pre className="max-h-60 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-green-200">
                    {deployJob.log.join("\n") || "menunggu output…"}
                  </pre>

                  <div className="flex justify-end gap-2 border-t border-line pt-3">
                    <button className="btn btn-primary" onClick={closeDeploy}>
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {deployApp && deployApp.services.length > 1 ? (
                    <label className="block text-[11px] text-muted">
                      Update folder (bagian)
                      <select
                        className="input mt-1 w-full"
                        value={deployServiceId}
                        onChange={(e) => setDeployServiceId(Number(e.target.value))}
                      >
                        <option value={0}>
                          {deployApp.services[0]?.label || "bagian pertama"}
                        </option>
                        {deployApp.services.slice(1).map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}

                  <div className="rounded-lg border border-line bg-panel2 p-3">
                    <div className="mb-0.5 text-[10px] uppercase tracking-wider text-muted2">
                      Folder tujuan
                    </div>
                    <div className="truncate font-mono text-[11px] text-[#d9e0e8]">
                      {deploySvc?.dir ?? "-"}
                    </div>
                    <div className="truncate font-mono text-[10px] text-muted2">
                      {deploySvc?.command ?? ""}
                    </div>
                  </div>

                  <label className="block text-[11px] text-muted">
                    File zip folder proyek
                    <input
                      type="file"
                      accept=".zip"
                      className="input mt-1 w-full"
                      onChange={(e) => {
                        const f = e.target.files?.[0] ?? null;
                        setDeployZipFile(f);
                        setDeployZipName(f?.name ?? "");
                        setDeployUploadPct(null);
                      }}
                    />
                    {deployZipName ? (
                      <span className="mt-1 block truncate font-mono text-[10px] text-ok">
                        {deployZipName}
                      </span>
                    ) : null}
                  </label>

                  <label className="flex items-center gap-2 text-[11px] text-muted">
                    <input
                      type="checkbox"
                      checked={deploySyncDocker}
                      disabled={deployApp?.runtime !== "docker"}
                      onChange={(e) => setDeploySyncDocker(e.target.checked)}
                    />
                    Sync ke Docker container setelah update
                  </label>
                  <label className="flex items-center gap-2 text-[11px] text-muted">
                    <input
                      type="checkbox"
                      checked={deployRestart}
                      onChange={(e) => setDeployRestart(e.target.checked)}
                    />
                    Restart service setelah update (dev-server auto-reload tidak
                    perlu)
                  </label>

                  {deployUpload.isPending ? (
                    <div>
                      <div className="mb-1 flex justify-between text-[10px] text-muted2">
                        <span>Mengunggah zip…</span>
                        <span>{deployUploadPct ?? 0}%</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded bg-panel2">
                        <div
                          className="h-full bg-accent transition-all"
                          style={{ width: `${deployUploadPct ?? 0}%` }}
                        />
                      </div>
                    </div>
                  ) : null}

                  <div className="flex justify-end gap-2 border-t border-line pt-3">
                    <button className="btn" onClick={closeDeploy}>
                      Cancel
                    </button>
                    <button
                      className="btn btn-primary"
                      disabled={!deployZipFile || deployUpload.isPending}
                      onClick={() => {
                        if (!deployZipFile || !deployApp) return;
                        const serviceId = deploySvc?.id ?? 0;
                        deployUpload.mutate({
                          appId: deployApp.id,
                          serviceId,
                          file: deployZipFile,
                          restart: deployRestart,
                          syncDocker: deploySyncDocker,
                        });
                      }}
                    >
                      {deployUpload.isPending ? "Mengunggah…" : "Upload & Update"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* -------------------------------------------- check service modal */}
      {checkFor ? (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-black/60 p-4"
          onClick={() => setCheckFor(null)}
        >
          <div
            className="card max-h-[90vh] w-full max-w-3xl overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-header">
              <div className="flex items-center gap-2">
                <Radar size={15} />
                <span className="card-title">
                  Cek Status — {checkSvc?.label ?? `#${checkFor}`} (auto-refresh 4s)
                </span>
              </div>
              <button className="btn btn-sm" onClick={() => setCheckFor(null)}>
                Tutup
              </button>
            </div>

            {checkQuery.isLoading ? (
              <div className="flex items-center gap-2 p-6 text-xs text-muted">
                <Loader2 size={14} className="animate-spin" /> Memeriksa…
              </div>
            ) : checkQuery.error ? (
              <div className="p-4 text-xs text-bad">
                {(checkQuery.error as Error)?.message ?? "Gagal memeriksa"}
              </div>
            ) : checkQuery.data ? (
              <div className="space-y-4 p-4">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[11px] md:grid-cols-3">
                  <Info
                    label="Status Service"
                    value={checkQuery.data.service.status}
                  />
                  <Info
                    label="PID"
                    value={
                      checkQuery.data.service.pid
                        ? `${checkQuery.data.service.pid} ${
                            checkQuery.data.service.pid_alive ? "(hidup)" : "(mati)"
                          }`
                        : "-"
                    }
                    mono
                  />
                  <Info
                    label="Port"
                    value={
                      checkQuery.data.service.resolved_port > 0
                        ? `${checkQuery.data.service.resolved_port}${
                            checkQuery.data.service.port_listening
                              ? " (merespon)"
                              : " (tidak)"
                          }`
                        : "not running"
                    }
                    mono
                  />
                </div>

                {/* bagian tunnel */}
                <div className="rounded-lg border border-line bg-panel2/60 p-3">
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted">
                    Cloudflare Tunnel
                  </div>

                  {checkQuery.data.tunnel.running ? (
                    <div className="space-y-1.5 text-[11px]">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge
                          status={
                            checkQuery.data.tunnel.reachable
                              ? "online"
                              : checkQuery.data.tunnel.url
                                ? "info"
                                : "offline"
                          }
                        />
                        <span className="font-mono text-muted2">
                          PID {checkQuery.data.tunnel.running_pid}
                        </span>
                        {checkQuery.data.tunnel.url ? (
                          <a
                            href={checkQuery.data.tunnel.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="max-w-[260px] truncate font-mono text-ok underline decoration-ok/40 underline-offset-2"
                          >
                            {checkQuery.data.tunnel.url}
                          </a>
                        ) : (
                          <span className="text-muted">URL belum muncul…</span>
                        )}
                      </div>
                      {checkQuery.data.tunnel.reachable != null ? (
                        <div className="text-muted2">
                          {checkQuery.data.tunnel.reachable
                            ? `Reachable • HTTP ${checkQuery.data.tunnel.status_code}`
                            : `Tidak terjangkau: ${
                                checkQuery.data.tunnel.error ?? "?"
                              }`}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="space-y-1.5 text-[11px]">
                      <StatusBadge status="offline" />
                      <div className="text-muted">
                        Tunnel tidak berjalan. Klik "Go Online" untuk membuat URL
                        baru.
                      </div>
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-[11px] text-muted">
                      <input
                        type="checkbox"
                        checked={checkSvc?.tunnel_auto ?? false}
                        disabled={setTunnelAuto.isPending}
                        onChange={(e) =>
                          setTunnelAuto.mutate({
                            id: checkFor,
                            enabled: e.target.checked,
                          })
                        }
                      />
                      Auto re-online (buat URL baru otomatis saat tunnel mati /
                      server restart)
                    </label>
                    <div className="ml-auto flex gap-2">
                      {checkQuery.data.tunnel.running ? (
                        <button
                          className="btn btn-danger btn-sm"
                          disabled={unexposeSvc.isPending}
                          onClick={() => unexposeSvc.mutate(checkFor)}
                        >
                          Matikan (Stop Tunnel)
                        </button>
                      ) : (
                        <button
                          className="btn btn-primary btn-sm"
                          disabled={
                            exposeSvc.isPending ||
                            checkQuery.data.service.status !== "ONLINE"
                          }
                          onClick={() => exposeSvc.mutate(checkFor)}
                        >
                          Go Online
                        </button>
                      )}
                      {checkQuery.data.service.status !== "ONLINE" ? (
                        <button
                          className="btn btn-sm"
                          disabled={startSvc.isPending}
                          onClick={() => startSvc.mutate(checkFor)}
                        >
                          Start Service
                        </button>
                      ) : (
                        <button
                          className="btn btn-sm text-bad"
                          disabled={stopSvc.isPending}
                          onClick={() => stopSvc.mutate(checkFor)}
                        >
                          Stop Service
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* log tunnel */}
                <div>
                  <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                    Log Tunnel
                  </div>
                  <pre className="max-h-40 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-green-200/80">
                    {checkQuery.data.tunnel.log_tail.length
                      ? checkQuery.data.tunnel.log_tail.join("\n")
                      : "belum ada log tunnel…"}
                  </pre>
                </div>
                {/* log service */}
                <div>
                  <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted">
                    Log Service
                  </div>
                  <pre className="max-h-40 overflow-auto rounded-lg border border-line bg-black/40 p-3 font-mono text-[10px] leading-relaxed text-[#aab6c3]">
                    {checkQuery.data.service.log_tail.length
                      ? checkQuery.data.service.log_tail.join("\n")
                      : "belum ada output…"}
                  </pre>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

function ServiceRow({
  svc,
  onStart,
  onStop,
  onOpen,
  onExpose,
  onUnexpose,
  onCheck,
  showLogs,
  pending,
  exposePending,
}: {
  svc: WebService;
  onStart: () => void;
  onStop: () => void;
  onOpen: () => void;
  onExpose: () => void;
  onUnexpose: () => void;
  onCheck: () => void;
  showLogs: () => void;
  pending: boolean;
  exposePending: boolean;
}) {
  const [copied, setCopied] = useState(false);
  // tunnel dianggap ekspos bila ada URL ATAU proses tunnel tercatat — bukan
  // cuma URL (bila URL belum muncul tapi proses sudah jalan, tombol Go Online
  // SELALU bersembunyi supaya tidak memicu 409 "sudah ter-expose").
  const isExposed = Boolean(svc.tunnel_url) || Boolean(svc.tunnel_pid);
  const awaitingUrl = Boolean(svc.tunnel_pid) && !svc.tunnel_url;

  const copyUrl = async () => {
    if (!svc.tunnel_url) return;
    try {
      await navigator.clipboard.writeText(svc.tunnel_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      window.open(svc.tunnel_url, "_blank");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg px-2 py-2 hover:bg-panel2/60">
      <span
        className={`h-[7px] w-[7px] shrink-0 rounded-full ${
          svc.status === "ONLINE"
            ? "bg-ok shadow-[0_0_8px_#22c55e]"
            : "bg-bad"
        }`}
      />
      <strong className="min-w-24 text-xs">{svc.label}</strong>
      <StatusBadge status={svc.status === "ONLINE" ? "online" : "offline"} />
      <span className="font-mono text-[10px] text-muted2">{svc.dir}</span>
      <span className="font-mono text-[10px] text-muted">{svc.command}</span>
      <span className="text-[10px] text-muted2">
        {svc.resolved_port > 0
          ? `port ${svc.resolved_port}${svc.port === 0 ? " (auto)" : ""}`
          : "not running"}
      </span>

      {/* tunnel URL */}
      {isExposed ? (
        <>
          {awaitingUrl ? (
            <span className="flex items-center gap-1.5 rounded-md border border-line bg-panel2 px-2 py-0.5 text-[10px] text-muted">
              <Loader2 size={11} className="animate-spin" />
              Menunggu URL…
            </span>
          ) : (
            <span className="flex items-center gap-1.5 rounded-md border border-ok/30 bg-ok/10 px-2 py-0.5 text-[10px] text-ok">
              <Globe size={11} />
              <a
                href={svc.tunnel_url!}
                target="_blank"
                rel="noopener noreferrer"
                className="max-w-[220px] truncate font-mono underline decoration-ok/40 underline-offset-2 hover:text-green-300"
              >
                {svc.tunnel_url!.replace("https://", "")}
              </a>
              <button
                className="ml-0.5 text-muted2 hover:text-white"
                title={copied ? "Copied!" : "Copy URL"}
                onClick={copyUrl}
              >
                <Link2 size={10} />
              </button>
            </span>
          )}
          {svc.tunnel_auto ? (
            <span
              className="rounded-md border border-line px-1.5 py-0.5 text-[9px] uppercase text-muted2"
              title="Auto re-online aktif: tunnel mati/server restart otomatis dibuatkan URL baru"
            >
              auto-online
            </span>
          ) : null}
        </>
      ) : null}

      <div className="ml-auto flex gap-1.5">
        {svc.status === "ONLINE" ? (
          <button className="action-btn" onClick={onOpen}>
            Open
          </button>
        ) : null}
        <button
          className="action-btn"
          onClick={onCheck}
          title="Cek status service & tunnel secara real-time"
        >
          <Radar size={12} className="mr-0.5" />
          Cek
        </button>
        <button className="action-btn" onClick={showLogs}>
          Logs
        </button>
        {svc.status === "ONLINE" ? (
          <button className="action-btn text-bad" disabled={pending} onClick={onStop}>
            Stop
          </button>
        ) : (
          <button className="action-btn" disabled={pending} onClick={onStart}>
            Start
          </button>
        )}
        {/* expose / unexpose button */}
        {svc.status === "ONLINE" && !isExposed ? (
          <button
            className="action-btn text-ok"
            disabled={exposePending}
            onClick={onExpose}
            title="Expose this service to the internet via Cloudflare Tunnel"
          >
            <Globe size={12} className="mr-0.5" />
            Go Online
          </button>
        ) : null}
        {isExposed ? (
          <button
            className="action-btn text-bad"
            disabled={exposePending}
            onClick={onUnexpose}
            title="Take this service offline"
          >
            <XCircle size={12} className="mr-0.5" />
            Take Offline
          </button>
        ) : null}
      </div>
    </div>
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
