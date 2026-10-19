"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as XLSX from "xlsx";
import {
  Check,
  ChevronDown,
  Copy,
  Download,
  Laptop,
  Link2,
  MonitorCheck,
  MonitorX,
  Network,
  Printer,
  Radio,
  RefreshCw,
  Search,
  Share2,
  Tags,
  Terminal,
  Unlink,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { ComputerMetricGauge } from "@/components/ui/computer-metric-gauge";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError, apiDownload, API_URL } from "@/lib/api";
import type { AgentArtifacts, ManagedComputer, PrinterListResult, PrinterResolveResult, PresenceResult, TopologyStatus, TopologyResult } from "@/lib/types";
import { useAuth } from "@/store/auth";

export default function ComputerManagementPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const isSuperadmin = useAuth((state) => state.user?.role === "superadmin");
  const [showDownload, setShowDownload] = useState(false);
  const [overloadModal, setOverloadModal] = useState<null | { metric: "cpu" | "mem" | "internet" }>(null);
  const [overloadSortKey, setOverloadSortKey] = useState<string>("cpu");
  const [overloadSortDir, setOverloadSortDir] = useState<"asc" | "desc">("desc");
  const [selectedComputer, setSelectedComputer] = useState<ManagedComputer | null>(null);
  const [presenceResult, setPresenceResult] = useState<{
    computer: ManagedComputer;
    result: PresenceResult;
  } | null>(null);
  const [presenceError, setPresenceError] = useState<{
    computer: ManagedComputer;
    message: string;
  } | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [groupFilter, setGroupFilter] = useState("all");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [agentArtifacts, setAgentArtifacts] = useState<AgentArtifacts | null>(null);
  const [topoResult, setTopoResult] = useState<TopologyResult | null>(null);
  const [printerOwnerId, setPrinterOwnerId] = useState("");
  const [printerResult, setPrinterResult] = useState<PrinterResolveResult | null>(null);
  const [showUnshared, setShowUnshared] = useState(false);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);
  const bulkMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!bulkMenuOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (bulkMenuRef.current && !bulkMenuRef.current.contains(e.target as Node)) {
        setBulkMenuOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setBulkMenuOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [bulkMenuOpen]);

  const topoStatus = useQuery({
    queryKey: ["computer-topology"],
    queryFn: () => api<TopologyStatus>("/computers/topology"),
    refetchInterval: 15_000,
  });

  const topoCheck = useMutation({
    mutationFn: (ids: number[]) =>
      api<TopologyResult>("/computers/topology-check", {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    onSuccess: (res) => {
      setTopoResult(res);
      toast.success(
        `${res.checked} diperiksa · ${res.online_ap} online via AP · ${res.updated_ip} IP diperbarui`
      );
      queryClient.invalidateQueries({ queryKey: ["computers"] });
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? err.message : "Gagal cek IP topologi";
      toast.error(
        err instanceof ApiError && err.status === 503
          ? `${msg} — tunggu beberapa detik lalu coba lagi`
          : msg,
      );
    },
  });

  useEffect(() => {
    let alive = true;
    api<AgentArtifacts>("/computers/agent-artifacts")
      .then((art) => alive && setAgentArtifacts(art))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const downloadAgent = (platform: "windows" | "linux") => {
    const art = platform === "windows" ? agentArtifacts?.windows : agentArtifacts?.linux;
    if (!art?.available) return;
    apiDownload(
      `/computers/agent-download?platform=${platform}`,
      platform === "windows" ? "panel-agent.exe" : "panel-agent",
    ).catch(() => toast.error("Gagal mengunduh binary agent"));
  };

  const printersQuery = useQuery({
    queryKey: ["printers", showUnshared],
    queryFn: () =>
      api<PrinterListResult>(
        `/printers${showUnshared ? "?only_shared=false" : ""}`,
      ),
    refetchInterval: 20_000,
  });

  const resolvePrinter = useMutation({
    mutationFn: (payload: { owner_id?: number; owner?: string; printer?: string; include_unshared?: boolean }) =>
      api<PrinterResolveResult>("/printers/resolve", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (res) =>
      setPrinterResult(res),
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Printer tidak ditemukan"),
  });

  const sharePrinter = useMutation({
    mutationFn: ({ id, share }: { id: number; share: boolean }) =>
      api<{ success: boolean; detail: string }>(
        `/printers/${id}/${share ? "share" : "unshare"}`,
        { method: "POST", body: JSON.stringify({}) },
      ),
    onSuccess: (res) => {
      toast.success(res.detail);
      queryClient.invalidateQueries({ queryKey: ["printers"] });
      queryClient.invalidateQueries({ queryKey: ["computers"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengubah share printer"),
  });

  const runPrinterLookup = () => {
    const raw = printerOwnerId.trim();
    if (!raw) {
      toast.info("Masukkan ID komputer pemilik printer");
      return;
    }
    resolvePrinter.mutate(
      /^\d+$/.test(raw)
        ? { owner_id: Number(raw), include_unshared: showUnshared }
        : { owner: raw, include_unshared: showUnshared },
    );
  };

  const query = useQuery({
    queryKey: ["computers"],
    queryFn: () =>
      api<{
        computers: ManagedComputer[];
        interval: number;
      }>("/computers"),
    refetchInterval: 10_000,
  });
  const computers = query.data?.computers ?? [];
  const interval = query.data?.interval ?? 10;
  const groups = useMemo(
    () => Array.from(new Set(computers.map((computer) => computer.group_name).filter(Boolean))).sort(),
    [computers],
  );
  const filteredComputers = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return computers.filter((computer) => {
      const matchesGroup = groupFilter === "all"
        || (groupFilter === "ungrouped" ? !computer.group_name : computer.group_name === groupFilter);
      if (!matchesGroup) return false;
      if (!term) return true;
      return [computer.name, computer.hostname, computer.ip, computer.mac, computer.os_info, computer.group_name]
        .some((value) => value?.toLowerCase().includes(term));
    });
  }, [computers, groupFilter, searchTerm]);
  const computerSort = useTableSort(
    filteredComputers,
    {
      name: (computer) => computer.name,
      group: (computer) => computer.group_name,
      ip: (computer) => computer.ip,
      mac: (computer) => computer.mac,
      connection: (computer) => computer.conn_type,
      reach: (computer) => computer.server_reach,
      os: (computer) => computer.os_info,
      internet: (computer) => computer.internet_up == null ? "-" : computer.internet_up ? "online" : "offline",
      latency: (computer) => computer.latency_ms ?? -1,
      cpu: (computer) => computer.cpu ?? -1,
      status: (computer) => computer.status,
    },
    "name",
  );

  const summary = useMemo(() => {
    const online = computers.filter((c) => c.status === "online").length;
    const offline = computers.filter((c) => c.status === "offline").length;
    const wifi = computers.filter((c) => c.conn_type === "WIFI").length;
    const lan = computers.filter((c) => c.conn_type === "LAN").length;
    return {
      total: computers.length,
      online,
      offline,
      wifi,
      lan,
    };
  }, [computers]);

  const pendingCount = useMemo(() => computers.filter((c) => c.pending_cmd).length, [computers]);

  const overload = useMemo(() => {
    const online = computers.filter((c) => c.status === "online");
    const avg = (vals: (number | null | undefined)[]) => {
      const xs = vals.filter((v): v is number => v != null && Number.isFinite(v));
      if (!xs.length) return { value: null as number | null, samples: 0 };
      return { value: Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10, samples: xs.length };
    };
    const cpu = avg(online.map((c) => c.cpu));
    const mem = avg(online.map((c) => c.mem));
    const lat = avg(online.map((c) => c.latency_ms));
    const srv = avg(online.map((c) => c.latency_srv_ms));
    return {
      cpuHigh: online.filter((c) => (c.cpu ?? -1) >= 90).length,
      memHigh: online.filter((c) => (c.mem ?? -1) >= 90).length,
      inetDown: online.filter((c) => c.internet_up === false).length,
      avgCpu: cpu.value,
      cpuSamples: cpu.samples,
      avgMem: mem.value,
      memSamples: mem.samples,
      avgLat: lat.value,
      avgSrvLat: srv.value,
      latSamples: lat.samples,
    };
  }, [computers]);

  const openOverload = (metric: "cpu" | "mem" | "internet") => {
    setOverloadSortKey(metric === "mem" ? "mem" : metric === "internet" ? "latency" : "cpu");
    setOverloadSortDir("desc");
    setOverloadModal({ metric });
  };

  const toggleOverloadSort = (k: string) => {
    if (k === overloadSortKey) {
      setOverloadSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setOverloadSortKey(k);
      setOverloadSortDir(k === "name" ? "asc" : "desc");
    }
  };

  const overloadFocus = useMemo(() => {
    switch (overloadSortKey) {
      case "cpu":
        return "cpu";
      case "mem":
        return "mem";
      case "internet":
      case "latency":
      case "download":
      case "upload":
        return "internet";
      default:
        return overloadModal?.metric ?? "cpu";
    }
  }, [overloadSortKey, overloadModal]);

  const overloadChips = [
    { metric: "cpu", label: "CPU" },
    { metric: "mem", label: "RAM" },
    { metric: "internet", label: "Internet" },
  ] as const;

  const overloadColCount = overloadFocus === "internet" ? 6 : 4;

  const overloadRows = useMemo(() => {
    const base = computers.filter((c) => c.status === "online");
    const get = (c: ManagedComputer): string | number => {
      switch (overloadSortKey) {
        case "cpu":
          return c.cpu ?? -1;
        case "mem":
          return c.mem ?? -1;
        case "internet":
          return c.internet_up == null ? -1 : c.internet_up ? 1 : 0;
        case "latency":
          return c.latency_ms ?? -1;
        case "download":
          return c.download_mbps ?? -1;
        case "upload":
          return c.upload_mbps ?? -1;
        case "status":
          return c.status;
        default:
          return c.name;
      }
    };
    return [...base].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      let cmp: number;
      if (typeof va === "number" && typeof vb === "number") cmp = va - vb;
      else cmp = String(va).toLowerCase().localeCompare(String(vb).toLowerCase(), undefined, { numeric: true });
      return overloadSortDir === "asc" ? cmp : -cmp;
    });
  }, [computers, overloadModal, overloadSortKey, overloadSortDir]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["computers"] });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/computers/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Komputer dihapus dari panel");
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal menghapus"),
  });

  const command = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      api<{ detail: string }>(`/computers/${id}/command`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }),
    onSuccess: (res) => {
      toast.info(res.detail);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengirim perintah"),
  });

  const bulkUpdate = useMutation({
    mutationFn: (ids: number[]) =>
      api<{ detail: string }>("/computers/bulk-command", {
        method: "POST",
        body: JSON.stringify({ ids, action: "update" }),
      }),
    onSuccess: (res) => {
      toast.success(res.detail);
      setSelectedIds([]);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengirim update massal"),
  });

  const cancelCommand = useMutation({
    mutationFn: (id: number) =>
      api<{ detail: string }>(`/computers/${id}/cancel-command`, {
        method: "POST",
      }),
    onSuccess: (res) => {
      toast.info(res.detail);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal membatalkan perintah"),
  });

  const bulkCancel = useMutation({
    mutationFn: () =>
      api<{ detail: string }>("/computers/bulk-cancel", {
        method: "POST",
        body: JSON.stringify({ ids: [] }),
      }),
    onSuccess: (res) => {
      toast.success(res.detail);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal membatalkan perintah tertunda"),
  });

  const presenceCheck = useMutation({
    mutationFn: (id: number) => api<PresenceResult>(`/computers/${id}/presence`),
    onSuccess: (result, id) => {
      const computer = computers.find((com) => com.id === id);
      setPresenceError(null);
      if (computer) setPresenceResult({ computer, result });
    },
    onError: (err, id) => {
      const msg = err instanceof ApiError ? err.message : "Gagal cek kehadiran jaringan";
      const hint =
        err instanceof ApiError && err.status === 503
          ? " — server sibuk, tunggu beberapa detik lalu coba lagi"
          : err instanceof ApiError && err.status === 404
            ? " — komputer tidak ditemukan, refresh daftar dulu"
            : "";
      toast.error(`${msg}${hint}`);
      const computer = computers.find((com) => com.id === id);
      if (computer) {
        setPresenceError({ computer, message: `${msg}${hint}` });
        setPresenceResult(null);
      }
    },
  });

  const installSoftware = useMutation({
    mutationFn: ({ id, package_id }: { id: number; package_id: string }) =>
      api<{ detail: string }>(`/computers/${id}/software`, {
        method: "POST",
        body: JSON.stringify({ package_id }),
      }),
    onSuccess: (res) => { toast.success(res.detail); invalidate(); },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Gagal mengirim instalasi"),
  });

  const bulkInstallSoftware = async () => {
    const package_id = window.prompt("Paket: 7zip, vlc, notepad-plus-plus, atau google-chrome", "7zip");
    if (!package_id || !selectedIds.length) return;
    const ok = await confirm({
      title: "Instalasi Software Massal",
      message: `Install ${package_id} pada ${selectedIds.length} komputer terpilih?`,
      confirmText: "Ya, install",
      tone: "warning",
    });
    if (!ok) return;
    try {
      const res = await api<{ detail: string }>("/computers/software/bulk-install", {
        method: "POST",
        body: JSON.stringify({ computer_ids: selectedIds, package_id: package_id.trim().toLowerCase() }),
      });
      toast.success(res.detail);
      setSelectedIds([]);
      invalidate();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gagal mengirim instalasi massal");
    }
  };

  const rename = useMutation({
    mutationFn: ({ id, name, group_name }: { id: number; name?: string; group_name?: string }) =>
      api<{ computer: ManagedComputer }>(`/computers/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name, group_name }),
      }),
    onSuccess: (res) => {
      toast.success(`Nama diganti menjadi "${res.computer.name}"`);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengganti nama"),
  });

  const sendCommand = async (
    c: ManagedComputer,
    action: "restart" | "shutdown" | "update" | "cleanup-nodelete"
  ) => {
    const isCleanup = action === "cleanup-nodelete";
    const ok = await confirm({
      title: action === "restart" ? "Restart Komputer" : action === "shutdown" ? "Matikan Komputer (Shutdown)" : action === "update" ? "Update Agent" : "Bersihkan C:\\nodelete",
      message:
        isCleanup
          ? `Hapus sisa rollout lama (C:\\nodelete + varian user-mode legacy) di "${c.name}"?\n\nAgent v1.5.1+ mengeksekusi saat heartbeat berikutnya (maks ${interval}s). PC offline ikut antre ≤24 jam dan dibersihkan otomatis saat nyala. Folder aktif %ProgramData%\\PanelAgent tidak disentuh.`
          : `Kirim perintah ${action === "restart" ? "RESTART" : action === "shutdown" ? "SHUTDOWN (mati)" : "UPDATE AGENT"} ke "${c.name}"?\n\n` +
            `Agent akan mengeksekusi saat heartbeat berikutnya (maks ${interval}s). ` +
            (action === "shutdown" ? "Komputer akan MATI." : action === "restart" ? "Komputer akan restart." : "Aplikasi agent akan diperbarui dan dimulai ulang."),
      confirmText: isCleanup ? "Ya, bersihkan" : "Ya, kirim perintah",
      tone: "warning",
    });
    if (ok) command.mutate({ id: c.id, action });
  };

  const bulkCleanup = useMutation({
    mutationFn: (ids: number[]) =>
      api<{ detail: string; count: number }>("/computers/bulk-command", {
        method: "POST",
        body: JSON.stringify({ ids, action: "cleanup-nodelete" }),
      }),
    onSuccess: (res) => {
      toast.success(res.detail);
      setSelectedIds([]);
      invalidate();
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Gagal mengirim cleanup massal"),
  });

  const cleanupSelected = async () => {
    const selectedComputers = computers.filter((computer) => selectedIds.includes(computer.id));
    const outdated = selectedComputers.filter((computer) =>
      (computer.agent_version || "").localeCompare("1.5.1", undefined, { numeric: true }) < 0
    );
    const ok = await confirm({
      title: "Bersihkan C:\\nodelete Massal",
      message:
        `Hapus sisa C:\\nodelete di ${selectedComputers.length} komputer terpilih? ` +
        `PC offline ikut antre dan dibersihkan otomatis saat kembali online (≤24 jam).` +
        (outdated.length ? `\n\nPERHATIAN: ${outdated.length} PC masih agent < v1.5.1 dan akan mengabaikan perintah ini — update agent dulu.` : ""),
      confirmText: "Ya, bersihkan semua",
      tone: "warning",
    });
    if (ok) bulkCleanup.mutate(selectedIds);
  };

  const checkSelected = () => {
    setBulkMenuOpen(false);
    topoCheck.mutate(selectedIds.length ? selectedIds.slice() : []);
  };

  const cancelAllPending = async () => {
    setBulkMenuOpen(false);
    const ok = await confirm({
      title: "Batalkan semua perintah tertunda",
      message: `Batalkan ${pendingCount} perintah tertunda (umumnya sisa update yang belum diambil PC yang offline)?`,
      confirmText: "Ya, batalkan semua",
      tone: "warning",
    });
    if (ok) bulkCancel.mutate();
  };

  const bulkBusy =
    bulkUpdate.isPending ||
    topoCheck.isPending ||
    bulkCleanup.isPending ||
    bulkCancel.isPending;

  const renameComputer = (c: ManagedComputer) => {
    const n = window.prompt("Nama baru (identitas MAC tidak berubah):", c.name);
    if (n && n.trim() && n.trim() !== c.name) rename.mutate({ id: c.id, name: n.trim() });
    const group = window.prompt("Group komputer (kosongkan untuk menghapus group):", c.group_name);
    if (group !== null && group.trim() !== c.group_name) rename.mutate({ id: c.id, group_name: group.trim() });
  };

  const installAppOn = (c: ManagedComputer) => {
    const package_id = window.prompt("Paket: 7zip, vlc, notepad-plus-plus, atau google-chrome", "7zip");
    if (package_id) installSoftware.mutate({ id: c.id, package_id: package_id.trim().toLowerCase() });
  };

  const deleteComputer = async (c: ManagedComputer, closeDetail = false) => {
    if (
      await confirm({
        message: `Hapus komputer "${c.name}"? Agent di PC tidak akan bisa mengirim data lagi.`,
        confirmText: "Ya, hapus",
      })
    ) {
      remove.mutate(c.id);
      if (closeDetail) setSelectedComputer(null);
    }
  };

  const cancelPendingOn = async (c: ManagedComputer) => {
    if (
      await confirm({
        message: `Batalkan perintah "${c.pending_cmd}" yang tertunda di "${c.name}"?`,
        confirmText: "Ya, batalkan",
      })
    )
      cancelCommand.mutate(c.id);
  };

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text);
    toast.info("Perintah disalin ke clipboard");
  };

  const exportComputers = () => {
    const rows = filteredComputers.map((computer) => ({
      "Nama Komputer": computer.name || "-",
      Group: computer.group_name || "Tanpa grup",
      Merk: computer.merk || "Tidak diketahui",
      IP: computer.ip || "-",
      MAC: computer.mac || "-",
    }));
    const worksheet = XLSX.utils.json_to_sheet(rows);
    worksheet["!cols"] = [
      { wch: 28 },
      { wch: 18 },
      { wch: 28 },
      { wch: 18 },
      { wch: 20 },
    ];
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Komputer");
    const content = XLSX.write(workbook, { bookType: "xlsx", type: "array" });
    const blob = new Blob([content], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `computer-management-${new Date().toISOString().slice(0, 10)}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
    toast.info(`${rows.length} komputer diekspor ke Excel`);
  };

  useEffect(() => {
    setPage(1);
  }, [searchTerm, groupFilter]);

  const totalPages = Math.max(1, Math.ceil(computerSort.sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedComputers = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return computerSort.sorted.slice(start, start + pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [computerSort.sorted, safePage]);

  const visibleIds = computerSort.sorted.map((computer) => computer.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
  const toggleAllVisible = () => {
    setSelectedIds((current) =>
      allVisibleSelected
        ? current.filter((id) => !visibleIds.includes(id))
        : Array.from(new Set([...current, ...visibleIds])),
    );
  };
  const toggleSelected = (id: number) => {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((selectedId) => selectedId !== id) : [...current, id],
    );
  };
  const updateSelected = async () => {
    const selectedComputers = computers.filter((computer) => selectedIds.includes(computer.id));
    const ok = await confirm({
      title: "Update Agent Massal",
      message: `Kirim perintah update ke ${selectedComputers.length} komputer terpilih? PC yang offline akan dilewati (tidak menumpuk jadi "waiting").`,
      confirmText: "Ya, update semua",
      tone: "warning",
    });
    if (ok) bulkUpdate.mutate(selectedIds);
  };

  const host =
    typeof window !== "undefined" ? window.location.hostname : "localhost";
  const scriptUrl = `${API_URL}/api/computers/agent-script`;
  const curlCmdLinux = `curl -sSL "${scriptUrl}" | python3 - --setup`;
  const winCmd = `python panel_agent.py --setup --server http://192.168.11.126:8000`;

  return (
    <>
      <PageHeader
        title="Computer Management"
        subtitle={`Pantau PC klien secara otomatis — cukup jalankan Panel Agent di PC tujuan, data langsung masuk ke panel ini`}
        onRefresh={invalidate}
        refreshing={query.isLoading}
        right={
          <button
            className="btn flex items-center gap-2"
            onClick={() => setShowDownload(true)}
            title="Unduh Panel Agent"
          >
            <Download size={13} />
            Agent
          </button>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Total PC"
          icon={<Laptop size={16} className="text-muted" />}
          value={summary.total}
          bottomLeft="perangkat terhubung"
        />
        <StatCard
          label="Online"
          icon={<MonitorCheck size={16} className="text-ok" />}
          value={summary.online}
          valueTone={summary.online > 0 ? "positive" : undefined}
          bottomLeft={`heartbeat tiap ${interval}s`}
        />
        <StatCard
          label="Offline"
          icon={<MonitorX size={16} className="text-bad" />}
          value={summary.offline}
          valueTone={summary.offline > 0 ? "warning" : undefined}
          bottomLeft="tidak merespons"
        />
        <StatCard
          label="Jalur Jaringan"
          icon={<Radio size={16} className="text-accent" />}
          value={`${summary.lan} LAN / ${summary.wifi} WiFi`}
          bottomLeft="distribusi koneksi"
        />
      </div>

      {/* ----------------- Rata-rata CPU / RAM / Internet (klik untuk daftar) */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <button
          className="flex flex-col rounded-card border border-line bg-panel p-4 transition-colors hover:border-accent/50"
          onClick={() => openOverload("cpu")}
          title="Lihat daftar CPU tertinggi / terendah"
        >
          <div className="flex-1">
            <ComputerMetricGauge
              bare
              type="cpu"
              value={overload.avgCpu}
              subtext={
                overload.avgCpu != null
                  ? `rata-rata ${overload.cpuSamples} PC · ${overload.cpuHigh} ≥90%`
                  : "Belum ada data"
              }
            />
          </div>
          <div className="mt-2 min-h-4 text-center text-[10px] text-muted">klik untuk daftar · ▲▼ bisa di-sort</div>
        </button>
        <button
          className="flex flex-col rounded-card border border-line bg-panel p-4 transition-colors hover:border-accent/50"
          onClick={() => openOverload("mem")}
          title="Lihat daftar RAM tertinggi / terendah"
        >
          <div className="flex-1">
            <ComputerMetricGauge
              bare
              type="mem"
              value={overload.avgMem}
              subtext={
                overload.avgMem != null
                  ? `rata-rata ${overload.memSamples} PC · ${overload.memHigh} ≥90%`
                  : "Belum ada data"
              }
            />
          </div>
          <div className="mt-2 min-h-4 text-center text-[10px] text-muted">klik untuk daftar · ▲▼ bisa di-sort</div>
        </button>
        <button
          className="flex flex-col rounded-card border border-line bg-panel p-4 transition-colors hover:border-accent/50"
          onClick={() => openOverload("internet")}
          title="Lihat daftar latency tertinggi / terendah"
        >
          <div className="flex-1">
            <ComputerMetricGauge
              bare
              type="latency"
              value={overload.avgLat}
              secondaryValue={overload.avgSrvLat}
              subtext={
                overload.avgLat != null
                  ? `rata-rata ${overload.latSamples} PC · ${overload.inetDown} internet mati`
                  : "Belum ada data"
              }
            />
          </div>
          <div className="mt-2 min-h-4 text-center text-[10px] text-muted">klik untuk daftar · ▲▼ bisa di-sort</div>
        </button>
      </div>

      {/* --------------------------------------------------------- daftar */}
      <div className="card">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-1 flex-col gap-2 sm:flex-row">
            <label className="relative flex min-w-0 flex-1 items-center">
              <Search size={15} className="pointer-events-none absolute left-3 text-muted2" />
              <input
                className="input w-full pl-9"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search nama, hostname, IP, MAC, OS..."
                aria-label="Search komputer"
              />
            </label>
            <label className="flex items-center gap-2">
              <Tags size={15} className="text-muted2" />
              <select
                className="input min-w-40"
                value={groupFilter}
                onChange={(event) => setGroupFilter(event.target.value)}
                aria-label="Filter group komputer"
              >
                <option value="all">Semua group</option>
                <option value="ungrouped">Tanpa grup</option>
                {groups.map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {selectedIds.length > 0 ? (
              <span className="text-xs text-muted">{selectedIds.length} terpilih</span>
            ) : null}
            <div className="relative" ref={bulkMenuRef}>
              <button
                className="btn flex items-center gap-2"
                onClick={() => setBulkMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={bulkMenuOpen}
                aria-label="Aksi massal: update, install, check, export"
                title="Update / Install / Check / Export"
              >
                <Network size={15} className="text-muted2" />
                {bulkBusy ? "Memproses…" : `Aksi${selectedIds.length ? ` (${selectedIds.length})` : ""}`}
                <ChevronDown
                  size={14}
                  className={`transition-transform ${bulkMenuOpen ? "rotate-180" : ""}`}
                />
              </button>
              {bulkMenuOpen ? (
                <div
                  role="menu"
                  aria-label="Aksi massal komputer"
                  className="absolute right-0 z-30 mt-1.5 w-72 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
                >
                  <BulkMenuItem
                    disabled={selectedIds.length === 0 || bulkUpdate.isPending}
                    reason={
                      selectedIds.length === 0
                        ? "Pilih dulu komputer di tabel"
                        : bulkUpdate.isPending
                          ? "Sedang mengirim update…"
                          : undefined
                    }
                    onSelect={() => {
                      setBulkMenuOpen(false);
                      updateSelected();
                    }}
                    icon={<RefreshCw size={14} />}
                    title={
                      bulkUpdate.isPending
                        ? "Mengirim update…"
                        : selectedIds.length
                          ? `Update ${selectedIds.length} terpilih`
                          : "Update (pilih dulu)"
                    }
                    desc="Kirim perintah update agent"
                  />
                  <BulkMenuItem
                    disabled={selectedIds.length === 0}
                    reason={selectedIds.length === 0 ? "Pilih dulu komputer di tabel" : undefined}
                    onSelect={() => {
                      setBulkMenuOpen(false);
                      bulkInstallSoftware();
                    }}
                    icon={<Download size={14} />}
                    title={
                      selectedIds.length
                        ? `Install software (${selectedIds.length} terpilih)`
                        : "Install software (pilih dulu)"
                    }
                    desc="7zip · vlc · notepad++ · chrome"
                  />
                  {isSuperadmin ? (
                    <BulkMenuItem
                      disabled={selectedIds.length === 0 || bulkCleanup.isPending}
                      reason={
                        selectedIds.length === 0
                          ? "Pilih dulu komputer di tabel"
                          : bulkCleanup.isPending
                            ? "Sedang mengirim cleanup…"
                            : undefined
                      }
                      onSelect={() => {
                        setBulkMenuOpen(false);
                        cleanupSelected();
                      }}
                      icon={<Unlink size={14} />}
                      title={
                        bulkCleanup.isPending
                          ? "Mengirim cleanup…"
                          : selectedIds.length
                            ? `Cleanup C:\\nodelete (${selectedIds.length} terpilih)`
                            : "Cleanup C:\\nodelete (pilih dulu)"
                      }
                      desc="PC offline ikut antre ≤24 jam"
                    />
                  ) : null}
                  <div className="border-t border-line" />
                  <BulkMenuItem
                    disabled={topoCheck.isPending}
                    reason={topoCheck.isPending ? "Sedang mencocokkan IP…" : undefined}
                    onSelect={checkSelected}
                    icon={<Network size={14} />}
                    title={
                      topoCheck.isPending
                        ? "Mencocokkan IP…"
                        : selectedIds.length
                          ? `Check IP ${selectedIds.length} terpilih`
                          : "Check IP semua"
                    }
                    desc="Cocokkan IP dengan Access Point"
                  />
                  <BulkMenuItem
                    disabled={pendingCount === 0 || bulkCancel.isPending}
                    reason={
                      pendingCount === 0
                        ? "Tidak ada perintah tertunda"
                        : bulkCancel.isPending
                          ? "Sedang membatalkan…"
                          : undefined
                    }
                    onSelect={cancelAllPending}
                    icon={<X size={14} />}
                    title={
                      bulkCancel.isPending ? "Membatalkan…" : `Batal menunggu (${pendingCount})`
                    }
                    desc="Batalkan perintah yang menggantung"
                  />
                  <BulkMenuItem
                    disabled={query.isLoading}
                    reason={query.isLoading ? "Daftar komputer masih dimuat…" : undefined}
                    onSelect={() => {
                      setBulkMenuOpen(false);
                      exportComputers();
                    }}
                    icon={<Share2 size={14} />}
                    title="Export Excel"
                    desc="Ekspor hasil filter saat ini"
                  />
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#263647] bg-[#101820] px-4 py-2 text-xs text-muted">
          <span className="flex items-center gap-2">
            <Network size={13} className="text-accent" />
            <span className="font-semibold text-slate-200">Auto-check IP topologi</span>
            <span>setiap {topoStatus.data?.interval ?? "-"} detik</span>
            <span className="opacity-70">· cocok IP perangkat ONLINE di Access Point</span>
          </span>
          <span className="opacity-80">
            {topoStatus.data?.running ? "sedang berjalan…" : ""}
            {topoStatus.data?.last_run
              ? `terakhir ${topoStatus.data.last_run.replace("T", " ").slice(5, 19)}Z · ${topoStatus.data.last_result}`
              : "belum pernah berjalan"}
          </span>
        </div>

        {topoResult ? (
          <div className="mb-3 rounded-lg border border-[#263647] bg-[#101820] px-4 py-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-200">
                Hasil cek IP topologi
              </span>
              <button className="action-btn" onClick={() => setTopoResult(null)} title="Tutup">
                <X size={14} />
              </button>
            </div>
            <div className="mt-1 text-xs text-muted">
              {topoResult.checked} komputer diperiksa · {topoResult.online_ap} online (cocok IP AP) ·{" "}
              {topoResult.updated_ip} IP diperbarui
            </div>
            {topoResult.note ? (
              <div className="mt-1 text-xs text-yellow-300/90">{topoResult.note}</div>
            ) : null}
            {topoResult.updated.length ? (
              <ul className="mt-2 space-y-1 text-xs">
                {topoResult.updated.map((u) => (
                  <li key={u.id} className="text-emerald-300">
                    {u.name}: IP diperbarui {u.ip_from || "-"} → {u.ip_to}{" "}
                    <span className="text-muted2">(dari AP {u.ap_ip} · {u.ap_status})</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <th className="w-10">
                  <button
                    className="action-btn"
                    onClick={toggleAllVisible}
                    disabled={!visibleIds.length}
                    title={allVisibleSelected ? "Batalkan semua pilihan" : "Pilih semua hasil filter"}
                    aria-label={allVisibleSelected ? "Batalkan semua pilihan" : "Pilih semua hasil filter"}
                  >
                    {allVisibleSelected ? <Check size={14} /> : <span className="text-xs">□</span>}
                  </button>
                </th>
                <SortTh label="Komputer" k="name" active={computerSort.key === "name"} dir={computerSort.dir} onToggle={computerSort.toggle} />
                <SortTh label="Group" k="group" active={computerSort.key === "group"} dir={computerSort.dir} onToggle={computerSort.toggle} />
                <SortTh label="IP" k="ip" active={computerSort.key === "ip"} dir={computerSort.dir} onToggle={computerSort.toggle} />
                <SortTh label="MAC Address" k="mac" active={computerSort.key === "mac"} dir={computerSort.dir} onToggle={computerSort.toggle} />
                <SortTh label="Koneksi" k="connection" active={computerSort.key === "connection"} dir={computerSort.dir} onToggle={computerSort.toggle} />
                <SortTh label="Status" k="status" active={computerSort.key === "status"} dir={computerSort.dir} onToggle={computerSort.toggle} />
              </tr>
            </thead>
            <tbody>
              {pagedComputers.map((c) => (
                <tr key={c.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(c.id)}
                      onChange={() => toggleSelected(c.id)}
                      aria-label={`Pilih ${c.name}`}
                    />
                  </td>
                  <td>
                    <button
                      className="text-left font-semibold text-accent hover:text-white hover:underline"
                      onClick={() => setSelectedComputer(c)}
                      title="Lihat informasi lengkap komputer"
                    >
                      {c.name}
                    </button>
                    {c.hostname && c.hostname !== c.name ? (
                      <div className="text-[10px] text-muted2">{c.hostname}</div>
                    ) : null}
                    <ComputerHint c={c} currentVersion={agentArtifacts?.version} />
                  </td>
                  <td className="text-[11px]">
                    {c.group_name ? (
                      <span className="status status-running">{c.group_name}</span>
                    ) : (
                      <span className="text-muted2">Tanpa grup</span>
                    )}
                  </td>
                  <td className="font-mono text-[11px]">{c.ip || "-"}</td>
                  <td className="font-mono text-[11px]">{c.mac || "-"}</td>
                  <td className="text-[11px]">
                    {c.conn_type === "WIFI" ? (
                      <span
                        className="status status-warning"
                        title={`SSID: ${c.ssid || "-"} · WiFi IP: ${c.wifi_ip || "-"} · AP: ${c.ap_ip || "-"} · BSSID: ${c.ap_mac || "-"} · interface: ${c.iface_name || "-"}`}
                      >
                        WIFI
                      </span>
                    ) : c.conn_type === "LAN" ? (
                      <span
                        className="status status-running"
                        title={c.iface_name ? `interface: ${c.iface_name}` : "Koneksi LAN"}
                      >
                        LAN
                      </span>
                    ) : (
                      <span className="text-muted2">-</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={c.status} />
                    {c.status === "online" && (
                      <span className="ml-1">
                        <span
                          className={`rounded px-1 text-[9px] font-semibold align-middle ${
                            c.online_source === "ap"
                              ? "bg-sky-500/20 text-sky-300"
                              : c.online_source === "both"
                              ? "bg-[#263647] text-slate-300"
                              : "bg-[#263647] text-slate-500"
                          }`}
                          title={
                            c.online_source === "ap"
                              ? "Online karena IP cocok perangkat ONLINE di Access Point (cocok IP AP)"
                              : c.online_source === "both"
                              ? "Online via heartbeat ANDA cocok IP Access Point"
                              : "Online via heartbeat agent"
                          }
                        >
                          {c.online_source === "ap" ? "via AP" : c.online_source === "both" ? "HB+AP" : "HB"}
                        </span>
                      </span>
                    )}
                    {c.autostart_mode === "task-scheduler" && (
                      <span
                        className="ml-1 rounded bg-emerald-500/20 px-1 text-[9px] font-semibold text-emerald-300 align-middle"
                        title="Auto-start saat boot sebagai SYSTEM (Task Scheduler) — aktif untuk semua user"
                      >
                        boot/SYSTEM
                      </span>
                    )}
                    {c.autostart_mode === "hkcu-run" && (
                      <span
                        className="ml-1 rounded bg-amber-500/20 px-1 text-[9px] font-semibold text-amber-300 align-middle"
                        title="Agent hanya jalan saat user ini login (HKCU Run) — tidak auto-start saat boot. Jalankan ulang installer agent sebagai Administrator untuk mode SYSTEM."
                      >
                        login-only
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {filteredComputers.length === 0 && !query.isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-muted2">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Laptop size={32} className="text-muted/40" />
                      <div className="font-medium text-sm text-muted">Belum Ada PC Klien Terhubung</div>
                      <div className="max-w-md text-xs text-muted2">
                        Unduh <code>panel_agent.py</code> melalui tombol Agent di atas dan jalankan di PC klien (Windows / Linux / macOS) untuk mulai memantau secara otomatis.
                      </div>
                    </div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {computerSort.sorted.length > 0 ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-muted">
            <div>
              Menampilkan {(safePage - 1) * pageSize + 1} –{" "}
              {Math.min(safePage * pageSize, computerSort.sorted.length)} dari{" "}
              {computerSort.sorted.length} komputer
            </div>
            <div className="flex items-center gap-1.5">
              <button
                className="btn btn-sm px-2.5 py-1 text-xs"
                disabled={safePage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ← Sebelumnya
              </button>
              <span className="px-2 font-mono">
                {safePage} / {totalPages}
              </span>
              <button
                className="btn btn-sm px-2.5 py-1 text-xs"
                disabled={safePage >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Berikutnya →
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {/* ------------------------------------------- sharing printer berbasis ID */}
      <div className="card mt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="rounded-lg border border-accent/30 bg-accent/10 p-2 text-accent">
              <Printer size={20} />
            </div>
            <div>
              <div className="font-semibold text-sm">Sharing Printer Berbasis ID</div>
              <div className="text-xs text-muted2">
                PC lain cukup masukkan <b>ID komputer pemilik printer</b> — panel menampilkan IP
                terkini (tetap jalan walau pemilik ganti IP / DHCP) + perintah connect siap-tempel.
              </div>
            </div>
          </div>
          <button
            className="btn btn-sm flex items-center gap-1.5"
            onClick={() => printersQuery.refetch()}
            disabled={printersQuery.isFetching}
          >
            <RefreshCw size={13} /> {printersQuery.isFetching ? "Memuat…" : "Refresh"}
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {/* lookup berdasarkan ID */}
          <div className="rounded-lg border border-line bg-black/20 p-3">
            <div className="mb-2 text-[11px] font-semibold uppercase text-muted2">
              Cari printer milik PC (input ID)
            </div>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                value={printerOwnerId}
                onChange={(e) => setPrinterOwnerId(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runPrinterLookup(); }}
                placeholder="ID komputer, mis. 12 (atau nama/hostname)"
                aria-label="ID komputer pemilik printer"
              />
              <button
                className="btn btn-primary flex items-center gap-1.5"
                onClick={runPrinterLookup}
                disabled={resolvePrinter.isPending}
              >
                <Search size={14} /> {resolvePrinter.isPending ? "Mencari…" : "Cari"}
              </button>
            </div>
            <div className="mt-1 text-[10px] text-muted2">
              ID = kolom <b>ID</b> pada tabel komputer di atas. Pemilik harus menjalankan Panel
              Agent v1.4+ agar printernya terdeteksi.
            </div>

            {printerResult ? (
              <div className="mt-3 rounded border border-line bg-black/30 p-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-200">
                    {printerResult.owner.name} · #{printerResult.owner.id}
                  </span>
                  <span className={printerResult.owner.online ? "text-green-400" : "text-muted2"}>
                    {printerResult.owner.online ? "online" : printerResult.owner.status}
                  </span>
                </div>
                <div className="mt-1 font-mono text-[11px] text-muted2">
                  IP terkini: {printerResult.owner.ip || "-"}
                </div>
                {printerResult.printers.length ? (
                  printerResult.printers.map((p) => (
                    <div key={p.id} className="mt-2 rounded border border-line bg-black/40 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-white">{p.name}</span>
                        <span className={p.is_shared ? "text-[10px] text-green-400" : "text-[10px] text-yellow-400"}>
                          {p.is_shared ? `share: ${p.share_name}` : "belum di-share"}
                        </span>
                      </div>
                      {p.connect?.powershell ? (
                        <div className="mt-1.5">
                          <div className="mb-1 flex items-center justify-between text-[10px] text-muted2">
                            <span>PowerShell (jalankan di PC klien)</span>
                            <button
                              className="flex items-center gap-1 text-muted hover:text-white"
                              onClick={() => copy(p.connect!.powershell!)}
                            >
                              <Copy size={11} /> Salin
                            </button>
                          </div>
                          <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded bg-black/60 p-2 text-[10px] text-green-300 select-all">
                            {p.connect.powershell}
                          </pre>
                        </div>
                      ) : null}
                      {p.connect?.cmd ? (
                        <div className="mt-1.5">
                          <div className="mb-1 flex items-center justify-between text-[10px] text-muted2">
                            <span>CMD (alternatif)</span>
                            <button
                              className="flex items-center gap-1 text-muted hover:text-white"
                              onClick={() => copy(p.connect!.cmd!)}
                            >
                              <Copy size={11} /> Salin
                            </button>
                          </div>
                          <code className="block break-all rounded bg-black/60 p-2 text-[10px] text-green-300 select-all">
                            {p.connect.cmd}
                          </code>
                        </div>
                      ) : null}
                      {p.connect?.shell ? (
                        <div className="mt-1.5">
                          <div className="mb-1 flex items-center justify-between text-[10px] text-muted2">
                            <span>Shell (klien Linux)</span>
                            <button
                              className="flex items-center gap-1 text-muted hover:text-white"
                              onClick={() => copy(p.connect!.shell!)}
                            >
                              <Copy size={11} /> Salin
                            </button>
                          </div>
                          <code className="block break-all rounded bg-black/60 p-2 text-[10px] text-green-300 select-all">
                            {p.connect.shell}
                          </code>
                        </div>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <div className="mt-2 text-[11px] text-muted2">
                    Tidak ada printer yang di-share di PC ini. Aktifkan share dulu dari daftar di
                    sebelah kanan (atau centang tampilkan yang belum di-share untuk lookup semua).
                  </div>
                )}
              </div>
            ) : null}
          </div>

          {/* daftar semua printer */}
          <div className="rounded-lg border border-line bg-black/20 p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-[11px] font-semibold uppercase text-muted2">
                {showUnshared
                  ? `Printer dilaporkan (${printersQuery.data?.shared ?? 0} share / ${printersQuery.data?.total ?? 0})`
                  : `Printer di-share (${printersQuery.data?.total ?? 0})`}
              </div>
              <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-muted2">
                <input
                  type="checkbox"
                  className="accent-current"
                  checked={showUnshared}
                  onChange={(e) => setShowUnshared(e.target.checked)}
                />
                Tampilkan yang belum di-share
              </label>
            </div>
            {printersQuery.data?.printers.length ? (
              <div className="max-h-80 overflow-auto">
                <table className="text-xs">
                  <thead>
                    <tr>
                      <th>Pemilik</th>
                      <th>Printer</th>
                      <th>Share</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {printersQuery.data.printers.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <div className="font-medium text-slate-200">
                            {p.owner_name} <span className="text-muted2">#{p.computer_id}</span>
                          </div>
                          <div className="font-mono text-[10px] text-muted2">{p.owner_ip || "-"}</div>
                        </td>
                        <td>
                          <div>{p.name}</div>
                          <div className="text-[10px] text-muted2">{p.driver || p.port || p.platform}</div>
                        </td>
                        <td>
                          <span className={p.is_shared ? "text-green-400" : "text-yellow-400"}>
                            {p.is_shared ? p.share_name : "—"}
                          </span>
                        </td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <button
                              className="action-btn"
                              title="Tampilkan perintah connect"
                              onClick={() => {
                                setPrinterOwnerId(String(p.computer_id));
                                resolvePrinter.mutate({
                                  owner_id: p.computer_id,
                                  printer: p.name,
                                  include_unshared: showUnshared,
                                });
                              }}
                            >
                              <Link2 size={13} />
                            </button>
                            {p.is_shared ? (
                              <button
                                className="action-btn"
                                title="Matikan share"
                                disabled={sharePrinter.isPending}
                                onClick={() => sharePrinter.mutate({ id: p.id, share: false })}
                              >
                                <Unlink size={13} />
                              </button>
                            ) : (
                              <button
                                className="action-btn"
                                title="Aktifkan share (PC pemilik harus admin/SYSTEM)"
                                disabled={sharePrinter.isPending}
                                onClick={() => sharePrinter.mutate({ id: p.id, share: true })}
                              >
                                <Share2 size={13} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-[11px] text-muted2">
                {showUnshared
                  ? "Belum ada printer dilaporkan. Pastikan PC pemilik menjalankan Panel Agent v1.4+ dan printer USB/lokal terpasang."
                  : "Belum ada printer yang di-share. Centang \"Tampilkan yang belum di-share\" untuk melihat semua printer lalu aktifkan share."}
              </div>
            )}
          </div>
        </div>

        <div className="mt-3 rounded border border-yellow-500/30 bg-yellow-500/5 p-2 text-[10px] text-yellow-200">
          <b>Prasyarat:</b> PC pemilik — File and Printer Sharing aktif & firewall izinkan TCP 445 ·
          PC klien — aktifkan guest SMB sekali:{" "}
          <code>Set-SmbClientConfiguration -EnableInsecureGuestLogons $true -Force</code> · jaringan
          antar-VLAN harus saling routing (port 445 terbuka).
        </div>
      </div>

      {showDownload ? (
        <div
          className="dialog-overlay"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setShowDownload(false);
          }}
        >
          <div
            className="dialog-card max-h-[90vh] max-w-2xl overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label="Unduh Panel Agent"
          >
            <div className="flex items-start justify-between gap-4 border-b border-line pb-3.5">
              <div className="flex items-center gap-3">
                <div className="rounded-lg border border-accent/30 bg-accent/10 p-2 text-accent">
                  <Terminal size={20} />
                </div>
                <div>
                  <div className="text-base font-bold text-white">Pasang Panel Agent di PC Klien</div>
                  <div className="mt-1 text-xs text-muted2">
                    Zero-config auto-discovery — Hostname, IP, OS, RAM/CPU & MAC otomatis masuk ke sini.
                  </div>
                </div>
              </div>
              <button
                className="action-btn shrink-0"
                onClick={() => setShowDownload(false)}
                title="Tutup"
                aria-label="Tutup unduhan agent"
              >
                <X size={16} />
              </button>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="btn btn-primary btn-sm flex items-center gap-1.5"
                onClick={() =>
                  apiDownload("/computers/agent-script", "panel_agent.py").catch(() =>
                    toast.error("Gagal mengunduh agent script")
                  )
                }
              >
                <Download size={14} />
                Unduh panel_agent.py
              </button>
              <button
                className="btn btn-sm flex items-center gap-1.5"
                onClick={() => downloadAgent("windows")}
                disabled={!agentArtifacts?.windows?.available}
                title={
                  agentArtifacts?.windows?.available
                    ? `Unduh ${agentArtifacts.windows.filename} (v${agentArtifacts.version})`
                    : "Binary .exe belum dibuat — lihat panduan Windows di bawah"
                }
              >
                <Download size={14} />
                Unduh .exe
              </button>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-line bg-black/30 p-3">
                <div className="mb-1.5 flex items-center justify-between font-medium text-white text-xs">
                  <span>Linux / macOS (1-Baris Otomatis)</span>
                  <button
                    className="flex items-center gap-1 text-[11px] text-muted hover:text-white"
                    onClick={() => copy(curlCmdLinux)}
                  >
                    <Copy size={12} /> Salin
                  </button>
                </div>
                <div className="break-all rounded bg-black/60 p-2 font-mono text-[11px] text-green-300 select-all">
                  {curlCmdLinux}
                </div>
                <div className="mt-2 text-[11px] text-muted2">
                  • Mengunduh script, memasang autostart <code>systemd --user</code> (tanpa sudo), dan langsung berjalan di background.
                </div>
              </div>
              <div className="rounded-lg border border-line bg-black/30 p-3">
                <div className="mb-1.5 flex items-center justify-between font-medium text-white text-xs">
                  <span>Windows (Dobel-Klik / CMD)</span>
                  <button
                    className="flex items-center gap-1 text-[11px] text-muted hover:text-white"
                    onClick={() => copy(winCmd)}
                  >
                    <Copy size={12} /> Salin
                  </button>
                </div>
                <div className="break-all rounded bg-black/60 p-2 font-mono text-[11px] text-green-300 select-all">
                  {winCmd}
                </div>
                <div className="mt-2 text-[11px] text-muted2">
                  • Cukup unduh dan dobel-klik <code>panel_agent.py</code> (atau jalankan dengan <code>--setup</code> untuk autostart tiap login).
                </div>
                <div className="mt-2 flex flex-col gap-1.5 rounded border border-line bg-black/20 p-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white text-[11px]">Tanpa perlu Python (dobel-klik saja):</span>
                    {agentArtifacts?.windows?.available ? (
                      <button className="btn btn-sm btn-primary flex items-center gap-1.5" onClick={() => downloadAgent("windows")}>
                        <Download size={13} />
                        Unduh .exe
                      </button>
                    ) : (
                      <span className="text-[10px] text-yellow-400">belum tersedia</span>
                    )}
                  </div>
                  {agentArtifacts?.windows?.available ? (
                    <div className="text-[10px] text-muted2">
                      {agentArtifacts.windows.filename} · v{agentArtifacts.version} ·{" "}
                      {(agentArtifacts.windows.size || 0) / 1024 / 1024 > 1
                        ? `${((agentArtifacts.windows.size || 0) / 1024 / 1024).toFixed(1)} MB`
                        : `${Math.max(1, Math.round((agentArtifacts.windows.size || 0) / 1024))} KB`}{" "}
                      · alamat server sudah ditanam ({API_URL.replace(/^https?:\/\//, "")})
                    </div>
                  ) : (
                    <div className="text-[10px] text-muted2">
                      Bangun sekali di PC Windows: <code>agent/build-windows.bat</code> (alamat server
                      otomatis ditanam), lalu salin <code>dist/panel-agent.exe</code> ke folder{" "}
                      <code>agent/dist/</code> di server. Setelah itu tombol unduh di atas aktif.
                    </div>
                  )}
                  <div className="border-t border-line pt-1 text-[10px] text-muted2">
                    Mode admin (jalur manual): jalankan <code>panel_agent.py --setup</code> (atau
                    <code> panel-agent.exe</code> — bila ada) <b>sebagai Administrator</b> sekali saja.
                    Agent dipasang ke <code>%ProgramData%</code> + Task Scheduler SYSTEM (jalan saat boot, semua akun).
                  </div>
                  <div className="border-t border-line pt-1 text-[10px] text-muted2">
                    <b>Install lewat satu baris perintah</b> (di PowerShell/CMD, tanpa unduh manual, butuh Python 3 di PC):
                    <div className="mt-1 rounded bg-black/30 px-2 py-1 font-mono font-semibold text-emerald-400 break-all">
                      powershell -c "irm '{API_URL}/api/computers/agent-install.ps1' | iex"
                    </div>
                    Minta hak admin sekali → dipasang ke <code>%ProgramData%</code> + Task Scheduler SYSTEM
                    (jalan saat boot, semua akun, badge <b>boot/SYSTEM</b>). PC yang sudah terdaftar →
                    otomatis <b>UPDATE</b> (token dicek & dipakai ulang, tidak jadi duplikat).
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <button className="btn" onClick={() => setShowDownload(false)}>Tutup</button>
            </div>
          </div>
        </div>
      ) : null}

      {overloadModal ? (
        <div
          className="dialog-overlay"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOverloadModal(null);
          }}
        >
          <div
            className="dialog-card max-h-[90vh] max-w-4xl overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label="Daftar overload komputer"
          >
            <div className="flex items-start justify-between gap-4 border-b border-line pb-3.5">
              <div>
                <div className="text-base font-bold text-white">
                  {overloadFocus === "cpu"
                    ? `CPU Tertinggi / Terendah (${overloadRows.length})`
                    : overloadFocus === "mem"
                      ? `RAM Tertinggi / Terendah (${overloadRows.length})`
                      : `Internet, Latency & Speed (${overloadRows.length})`}
                </div>
                <div className="mt-1 text-xs text-muted2">
                  Klik header kolom untuk sort tertinggi ↔ terendah. Klik nama PC untuk buka detail.
                </div>
              </div>
              <button
                className="action-btn shrink-0"
                onClick={() => setOverloadModal(null)}
                title="Tutup"
                aria-label="Tutup daftar overload"
              >
                <X size={16} />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {overloadChips.map((chip) => (
                <button
                  key={chip.metric}
                  className={`btn btn-sm ${overloadFocus === chip.metric ? "btn-primary" : ""}`}
                  onClick={() => openOverload(chip.metric)}
                  aria-pressed={overloadFocus === chip.metric}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            <div className="table-wrap mt-3 overflow-auto rounded border border-line bg-black/20">
              <table className="proc-table whitespace-nowrap text-xs tabular-nums">
                <thead className="text-muted-foreground">
                  <tr className="[&>th]:px-3 [&>th]:pb-2 [&>th]:font-normal">
                    <SortTh label="Komputer" k="name" active={overloadSortKey === "name"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    {(overloadFocus === "cpu" || overloadFocus === "mem") && (
                      <SortTh label="CPU %" k="cpu" className="text-right" active={overloadSortKey === "cpu"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    {(overloadFocus === "cpu" || overloadFocus === "mem") && (
                      <SortTh label="RAM %" k="mem" className="text-right" active={overloadSortKey === "mem"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    {overloadFocus === "internet" && (
                      <SortTh label="Internet" k="internet" active={overloadSortKey === "internet"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    {overloadFocus === "internet" && (
                      <SortTh label="Latency" k="latency" className="text-right" active={overloadSortKey === "latency"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    {overloadFocus === "internet" && (
                      <SortTh label="Download" k="download" className="text-right" active={overloadSortKey === "download"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    {overloadFocus === "internet" && (
                      <SortTh label="Upload" k="upload" className="text-right" active={overloadSortKey === "upload"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                    )}
                    <SortTh label="Status" k="status" active={overloadSortKey === "status"} dir={overloadSortDir} onToggle={toggleOverloadSort} />
                  </tr>
                </thead>
                <tbody>
                  {overloadRows.map((c) => (
                    <tr key={c.id} className="[&>td]:px-3 [&>td]:py-2">
                      <td>
                        <button
                          className="text-left font-semibold text-accent hover:text-white hover:underline"
                          onClick={() => {
                            setOverloadModal(null);
                            setSelectedComputer(c);
                          }}
                          title="Lihat informasi lengkap komputer"
                        >
                          {c.name}
                        </button>
                        <div className="font-mono text-[10px] text-muted2">{c.ip || "-"}</div>
                      </td>
                      {(overloadFocus === "cpu" || overloadFocus === "mem") && (
                        <td className="text-right font-mono">{c.cpu != null ? `${Math.round(c.cpu)}%` : "-"}</td>
                      )}
                      {(overloadFocus === "cpu" || overloadFocus === "mem") && (
                        <td className="text-right font-mono">{c.mem != null ? `${Math.round(c.mem)}%` : "-"}</td>
                      )}
                      {overloadFocus === "internet" && (
                        <td>{c.internet_up == null ? "-" : c.internet_up ? "Online" : "Offline"}</td>
                      )}
                      {overloadFocus === "internet" && (
                        <td className="text-right font-mono">{c.latency_ms != null ? `${c.latency_ms} ms` : "-"}</td>
                      )}
                      {overloadFocus === "internet" && (
                        <td className="text-right font-mono">{c.download_mbps != null ? `${c.download_mbps} Mbps` : "-"}</td>
                      )}
                      {overloadFocus === "internet" && (
                        <td className="text-right font-mono">{c.upload_mbps != null ? `${c.upload_mbps} Mbps` : "-"}</td>
                      )}
                      <td><StatusBadge status={c.status} /></td>
                    </tr>
                  ))}
                  {overloadRows.length === 0 ? (
                    <tr>
                      <td colSpan={overloadColCount} className="py-8 text-center text-muted2">Tidak ada PC pada kategori ini.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <div className="mt-5 flex justify-end">
              <button className="btn" onClick={() => setOverloadModal(null)}>Tutup</button>
            </div>
          </div>
        </div>
      ) : null}

      {selectedComputer ? (
        <div
          className="dialog-overlay"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedComputer(null);
              setPresenceError(null);
              presenceCheck.reset();
            }
          }}
        >
          <div
            className="dialog-card max-h-[90vh] max-w-3xl overflow-y-auto"
            role="dialog"
            aria-modal="true"
            aria-label={`Informasi ${selectedComputer.name}`}
          >
            <div className="flex items-start justify-between gap-4 border-b border-line pb-3.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base font-bold text-white">{selectedComputer.name}</span>
                  <StatusBadge status={selectedComputer.status} />
                </div>
                <div className="mt-1 text-xs text-muted2">
                  {selectedComputer.hostname || "Hostname tidak tersedia"} · IP: {selectedComputer.ip || "—"} · Group: {selectedComputer.group_name || "Tanpa grup"}
                </div>
              </div>
              <button
                className="action-btn shrink-0"
                onClick={() => {
                  setSelectedComputer(null);
                  setPresenceError(null);
                  presenceCheck.reset();
                }}
                title="Tutup detail komputer"
                aria-label="Tutup detail komputer"
              >
                <X size={16} />
              </button>
            </div>

            {/* Performance Gauges Section */}
            <div className="mt-4">
              <div className="mb-2.5 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted2">
                  Live Performance & Telemetry
                </span>
                {selectedComputer.speed_test_at && (
                  <span className="text-[10px] text-muted">
                    Speedtest: {selectedComputer.speed_test_at}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
                <ComputerMetricGauge
                  type="cpu"
                  value={selectedComputer.cpu}
                  subtext={selectedComputer.cpu != null ? `${Math.round(selectedComputer.cpu)}% load` : "Belum ada data"}
                />
                <ComputerMetricGauge
                  type="mem"
                  value={selectedComputer.mem}
                  subtext={selectedComputer.mem != null ? `${Math.round(selectedComputer.mem)}% used` : "Belum ada data"}
                />
                <ComputerMetricGauge
                  type="latency"
                  value={selectedComputer.latency_ms}
                  secondaryValue={selectedComputer.latency_srv_ms}
                  subtext={
                    selectedComputer.latency_ms != null
                      ? `${selectedComputer.latency_ms} ms ping`
                      : "No ping data"
                  }
                />
                <ComputerMetricGauge
                  type="download"
                  value={selectedComputer.download_mbps}
                  subtext={
                    selectedComputer.download_mbps != null
                      ? `${selectedComputer.download_mbps} Mbps`
                      : "Belum dites"
                  }
                />
                <ComputerMetricGauge
                  type="upload"
                  value={selectedComputer.upload_mbps}
                  subtext={
                    selectedComputer.upload_mbps != null
                      ? `${selectedComputer.upload_mbps} Mbps`
                      : "Belum dites"
                  }
                />
              </div>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase text-muted2">Identitas & Status</div>
                <dl className="space-y-1.5 text-xs">
                  <DetailRow label="Group" value={selectedComputer.group_name || "Tanpa grup"} />
                  <DetailRow label="IP utama" value={selectedComputer.ip} mono />
                  <DetailRow label="MAC address" value={selectedComputer.mac} mono />
                  <DetailRow label="OS" value={selectedComputer.os_info} />
                  <DetailRow label="Agent" value={selectedComputer.agent_version} />
                  <DetailRow
                    label="Auto-start"
                    value={
                      selectedComputer.autostart_mode === "task-scheduler"
                        ? "SYSTEM (boot, semua user)"
                        : selectedComputer.autostart_mode === "hkcu-run"
                          ? "Per-user (login only)"
                          : selectedComputer.autostart_mode || "-"
                    }
                  />
                  <DetailRow label="Terakhir heartbeat" value={selectedComputer.last_seen} />
                  <DetailRow label="Perintah tertunda" value={selectedComputer.pending_cmd ? `${selectedComputer.pending_cmd} @ ${selectedComputer.cmd_issued_at}` : null} mono />
                  <DetailRow label="Hasil perintah" value={selectedComputer.last_cmd_result || null} mono />
                  <DetailRow label="Terdaftar" value={selectedComputer.created_at} />
                </dl>
              </div>
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase text-muted2">Jaringan & Topologi</div>
                <dl className="space-y-1.5 text-xs">
                  <DetailRow label="Koneksi" value={selectedComputer.conn_type} />
                  <DetailRow label="Interface" value={selectedComputer.iface_name} />
                  <DetailRow label="Jalur server" value={selectedComputer.server_reach} />
                  <DetailRow label="Internet" value={selectedComputer.internet_up == null ? null : selectedComputer.internet_up ? "Online" : "Offline"} />
                  <DetailRow label="SSID" value={selectedComputer.ssid} />
                  <DetailRow label="WiFi IP" value={selectedComputer.wifi_ip} mono />
                  <DetailRow label="AP IP" value={selectedComputer.ap_ip} mono />
                  <DetailRow label="BSSID" value={selectedComputer.ap_mac} mono />
                  <DetailRow label="Latency PC → server" value={selectedComputer.latency_ms != null ? `${selectedComputer.latency_ms} ms` : "-"} />
                  <DetailRow label="Latency server → PC" value={selectedComputer.latency_srv_ms != null ? `${selectedComputer.latency_srv_ms} ms` : "-"} />
                  <DetailRow label="Speed test" value={selectedComputer.speed_test_at || "-"} />
                </dl>
              </div>
            </div>

            <div className="mt-5">
              <div className="mb-2 text-[11px] font-semibold uppercase text-muted2">Semua interface</div>
              <div className="overflow-auto rounded border border-line bg-black/20">
                <table className="text-xs">
                  <thead>
                    <tr><th>Nama</th><th>IP</th><th>MAC</th></tr>
                  </thead>
                  <tbody>
                    {selectedComputer.interfaces.length ? selectedComputer.interfaces.map((item) => (
                      <tr key={`${item.name}-${item.mac}-${item.ip}`}>
                        <td>{item.name || "-"}</td>
                        <td className="font-mono">{item.ip || "-"}</td>
                        <td className="font-mono">{item.mac || "-"}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={3} className="text-muted2">Tidak ada data interface</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-5 rounded border border-line bg-black/20 p-3">
              <div className="text-xs font-semibold text-white">Aksi PC ini</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  className="btn btn-sm"
                  disabled={command.isPending || selectedComputer.status !== "online"}
                  onClick={() => sendCommand(selectedComputer, "update")}
                  title="Update agent di PC ini"
                >
                  <RefreshCw size={13} /> Update
                </button>
                <button
                  className="btn btn-sm"
                  disabled={installSoftware.isPending || selectedComputer.status !== "online"}
                  onClick={() => installAppOn(selectedComputer)}
                  title="Install software dari katalog di PC ini"
                >
                  Install App
                </button>
                {selectedComputer.status !== "online" ? (
                  <button
                    className="btn btn-sm"
                    disabled={presenceCheck.isPending}
                    onClick={() => {
                      setPresenceError(null);
                      presenceCheck.mutate(selectedComputer.id);
                    }}
                    title="Cek kehadiran jaringan — PC hidup (agent mati) atau benar-benar offline?"
                  >
                    <Network size={13} className={presenceCheck.isPending ? "animate-spin" : undefined} />
                    {presenceCheck.isPending ? "Mengecek…" : "Check"}
                  </button>
                ) : null}
                {selectedComputer.pending_cmd ? (
                  <button
                    className="btn btn-sm"
                    disabled={cancelCommand.isPending}
                    onClick={() => cancelPendingOn(selectedComputer)}
                    title="Batalkan perintah yang tertunda"
                  >
                    <X size={13} /> Batalkan ({selectedComputer.pending_cmd})
                  </button>
                ) : null}
                <button
                  className="btn btn-sm"
                  onClick={() => renameComputer(selectedComputer)}
                  title="Ganti nama / group komputer"
                >
                  ✎ Rename
                </button>
                {isSuperadmin ? (
                  <>
                    <button
                      className="btn btn-sm"
                      disabled={command.isPending}
                      onClick={() => sendCommand(selectedComputer, "restart")}
                      title="Restart komputer dari jarak jauh"
                    >
                      Restart
                    </button>
                    <button
                      className="btn btn-sm"
                      disabled={command.isPending}
                      onClick={() => sendCommand(selectedComputer, "shutdown")}
                      title="Matikan komputer dari jarak jauh"
                    >
                      Shutdown
                    </button>
                    <button
                      className="btn btn-sm flex items-center gap-1.5"
                      disabled={command.isPending}
                      onClick={() => sendCommand(selectedComputer, "cleanup-nodelete")}
                      title="Bersihkan sisa C:\nodelete (offline ikut antre ≤24 jam)"
                    >
                      <Unlink size={13} /> Cleanup
                    </button>
                  </>
                ) : null}
                <button
                  className="btn btn-sm text-bad"
                  disabled={remove.isPending}
                  onClick={() => deleteComputer(selectedComputer, true)}
                  title="Hapus dari panel"
                >
                  Hapus
                </button>
              </div>
              {presenceError && presenceError.computer.id === selectedComputer.id ? (
                <div className="mt-2 rounded border border-red-500/40 bg-red-500/10 p-2 text-[11px] text-red-300">
                  <span className="font-semibold">Cek kehadiran gagal:</span> {presenceError.message}
                  <button
                    className="ml-2 underline hover:text-white"
                    disabled={presenceCheck.isPending}
                    onClick={() => presenceCheck.mutate(selectedComputer.id)}
                  >
                    {presenceCheck.isPending ? "Mengecek…" : "Coba lagi"}
                  </button>
                </div>
              ) : null}
              {selectedComputer.status !== "online" && !selectedComputer.pending_cmd ? (
                <div className="mt-1 text-[10px] text-muted2">PC harus online agar menerima perintah update/install/restart.</div>
              ) : null}
            </div>

            <div className="mt-5 rounded border border-accent/30 bg-accent/5 p-3">
              <div className="text-xs font-semibold text-white">Update App Agent</div>
              <button
                className="btn btn-primary btn-sm mt-2"
                disabled={command.isPending || selectedComputer.status !== "online"}
                onClick={() => sendCommand(selectedComputer, "update")}
              >
                Update otomatis di PC ini
              </button>
              {selectedComputer.status !== "online" ? (
                <div className="mt-1 text-[10px] text-muted2">PC harus online agar menerima perintah.</div>
              ) : null}
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded bg-black/40 p-2 text-[11px] text-green-300">
                  python3 panel_agent.py --update
                </code>
                <button className="btn btn-sm shrink-0" onClick={() => copy("python3 panel_agent.py --update")}>
                  <Copy size={13} /> Salin
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded bg-black/40 p-2 text-[11px] text-green-300">
                  python panel_agent.py --update
                </code>
                <button className="btn btn-sm shrink-0" onClick={() => copy("python panel_agent.py --update")}>
                  <Copy size={13} /> Windows
                </button>
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                className="btn"
                onClick={() => {
                  setSelectedComputer(null);
                  setPresenceError(null);
                  presenceCheck.reset();
                }}
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {presenceResult ? (
        <div
          className="dialog-overlay"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              setPresenceResult(null);
              presenceCheck.reset();
            }
          }}
        >
          <div className="dialog-card max-h-[90vh] max-w-lg overflow-y-auto">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-bold">Cek kehadiran: {presenceResult.computer.name}</div>
                <div className="text-[10px] text-muted2">
                  heartbeat: {presenceResult.computer.last_seen || "-"} · MAC DB:{" "}
                  {presenceResult.result.mac_db || "-"}
                </div>
              </div>
              <button className="btn btn-sm" onClick={() => { setPresenceResult(null); presenceCheck.reset(); }}>
                <X size={13} />
              </button>
            </div>

            <div
              className={`mb-3 rounded border p-3 text-xs ${
                presenceResult.result.verdict === "alive"
                  ? "border-green-500/40 bg-green-500/10 text-green-300"
                  : presenceResult.result.verdict === "dead"
                    ? "border-red-500/40 bg-red-500/10 text-red-300"
                    : "border-yellow-500/40 bg-yellow-500/10 text-yellow-300"
              }`}
            >
              <div className="font-bold">
                {presenceResult.result.verdict === "alive"
                  ? "✅ PC HIDUP di jaringan — agent-nya yang mati"
                  : presenceResult.result.verdict === "dead"
                    ? "🟥 Tidak terdeteksi — PC kemungkinan mati / off / kabel lepas"
                    : presenceResult.result.verdict === "unknown"
                      ? "⚠️ Tidak pasti — tidak ada balasan ICMP"
                      : "ℹ️ Tidak ada IP valid untuk dites"}
              </div>
              <div className="mt-1 text-muted2">{presenceResult.result.summary}</div>
            </div>

            <div className="mb-1 text-[11px] font-semibold uppercase text-muted2">Hasil probe server → PC</div>
            {presenceResult.result.checks.length ? (
              <div className="overflow-auto rounded border border-line bg-black/20">
                <table className="text-xs">
                  <thead>
                    <tr>
                      <th>IP</th>
                      <th>Ping</th>
                      <th>State ARP</th>
                      <th>MAC di L2</th>
                    </tr>
                  </thead>
                  <tbody>
                    {presenceResult.result.checks.map((chk) => (
                      <tr key={chk.ip}>
                        <td className="font-mono">{chk.ip}</td>
                        <td className={chk.ping_ms != null ? "text-green-400" : "text-red-400"}>
                          {chk.ping_ms != null ? `${chk.ping_ms} ms` : "gagal"}
                        </td>
                        <td className="font-mono">{chk.neigh_state || "-"}</td>
                        <td className="font-mono">{chk.neigh_mac || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded border border-line bg-black/20 p-3 text-[11px] text-muted2">
                Tidak ada alamat IP yang bisa dicoba.
              </div>
            )}

            {presenceResult.result.ap_matches.length ? (
              <div className="mt-3">
                <div className="mb-1 text-[11px] font-semibold uppercase text-muted2">
                  MAC cocok di scan access point
                </div>
                {presenceResult.result.ap_matches.map((ap, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded border border-line bg-black/20 px-3 py-2 text-[11px]">
                    <span className="font-mono">{ap.mac} · {ap.ip || "-"}</span>
                    <span className={ap.status === "ONLINE" ? "text-green-400" : "text-muted2"}>
                      {ap.status}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="mt-4 flex justify-end">
              <button
                className="btn"
                onClick={() => { setPresenceResult(null); presenceCheck.reset(); }}
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      ) : null}

    </>
  );
}

function BulkMenuItem({
  disabled,
  reason,
  onSelect,
  icon,
  title,
  desc,
}: {
  disabled?: boolean;
  reason?: string;
  onSelect: () => void;
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <button
      role="menuitem"
      className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
      disabled={disabled}
      title={reason ?? title}
      onClick={onSelect}
    >
      <span className="shrink-0 text-muted">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-white">{title}</span>
        <span className="block truncate text-[10px] text-muted2">{reason ?? desc}</span>
      </span>
    </button>
  );
}

function DetailRow({ label, value, mono = false }: { label: string; value: string | null; mono?: boolean }) {
  return (
    <div className="flex gap-3">
      <dt className="w-36 shrink-0 text-muted2">{label}</dt>
      <dd className={mono ? "break-all font-mono text-white" : "break-words text-white"}>{value || "-"}</dd>
    </div>
  );
}

function ComputerHint({
  c,
  currentVersion,
}: {
  c: ManagedComputer;
  currentVersion?: string;
}) {
  let dot = "bg-slate-400";
  let text: string;
  if (c.pending_cmd) {
    dot = "bg-orange-400";
    text = c.pending_cmd.toUpperCase();
  } else if (c.status === "online") {
    dot = "bg-green-400";
    text = "OK";
  } else if (c.status === "waiting") {
    text = "belum pernah terhubung";
  } else {
    dot = "bg-yellow-400";
    text = `offline · ${c.heartbeat_age != null ? `${Math.round(c.heartbeat_age)}s lalu` : "lama"}`;
  }

  const pending = c.pending_cmd ? `⏳ ${c.pending_cmd.toUpperCase()}${c.status !== "online" ? " menunggu PC online" : ""}` : null;
  const failed = /gagal|failed|error/i.test(c.last_cmd_result || "")
    ? c.last_cmd_result!.slice(0, 60)
    : null;
  // Update sudah "OK" tapi versi yang berjalan masih lama → file baru sudah
  // terpasang; agent akan restart otomatis (re-exec in-place) pada detik berikutnya.
  const needsRestart =
    /update:\s*OK/i.test(c.last_cmd_result || "") &&
    !!c.agent_version &&
    !!currentVersion &&
    c.agent_version !== currentVersion
      ? `⬤ file v${currentVersion} terpasang — menunggu agent restart otomatis (masih v${c.agent_version})`
      : null;

  return (
    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[9px] leading-tight">
      <span className="inline-flex min-w-0 items-center gap-1">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        <span
          className="max-w-[150px] truncate text-muted2"
          title={c.pending_cmd ? `${c.pending_cmd} · ${c.last_cmd_result || ""}` : text}
        >
          {text}
        </span>
      </span>
      {pending ? <span className="max-w-[180px] truncate text-orange-400" title={pending}>{pending}</span> : null}
      {failed ? <span className="max-w-[150px] truncate text-red-400" title={c.last_cmd_result}>{failed}</span> : null}
      {needsRestart ? <span className="max-w-[200px] truncate text-sky-400" title={needsRestart}>⚡ menunggu restart otomatis v{currentVersion}</span> : null}
    </div>
  );
}
