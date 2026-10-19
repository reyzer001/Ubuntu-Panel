"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError } from "@/lib/api";
import type {
  APEvent,
  APGroup,
  APScanProgress,
  APScanTarget,
  APSummary,
  AccessPoint,
} from "@/lib/types";

function fmtTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString();
}

function isMatchingSegment(seg: string | undefined, target: string): boolean {
  if (!seg) return false;
  const s = seg.trim().toUpperCase();
  const t = target.trim().toUpperCase();
  if (t === "PHONE" || t === "TELEPON") {
    return s === "PHONE" || s === "TELEPON" || s === "TELP" || s === "VOIP";
  }
  if (t === "CCTV") {
    return s === "CCTV" || s === "KAMERA" || s === "CAMERA";
  }
  if (t === "INTERNET") {
    return s === "INTERNET" || s === "LAN" || s === "OFFICE" || s === "KANTOR";
  }
  return s === t;
}

const PHASE_LABEL: Record<string, string> = {
  sweep: "pinging every host .1 – .254 …",
  arp: "reading ARP / MAC table …",
  probe: "probing admin pages for models …",
  write: "saving to inventory …",
};

/** Panel animasi progres scan: melacak host .1 → .254 secara live. */
function ScanProgress({ p }: { p: APScanProgress }) {
  const [anim, setAnim] = useState(0);
  const target = p.done ?? 0;
  const total = p.total || 256;

  useEffect(() => {
    const iv = setInterval(() => {
      setAnim((v) => {
        if (target <= v) return target;
        return Math.min(target, v + Math.max(1, Math.round((target - v) * 0.18)));
      });
    }, 50);
    return () => clearInterval(iv);
  }, [target]);

  const pct = Math.min(100, (anim / total) * 100);
  const prefix = (p.cidr ?? "").split(".").slice(0, 3).join(".");
  const octet = Math.min(anim, 255);

  return (
    <div className="mb-5 rounded-xl border border-line bg-panel2 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="flex items-center gap-2 font-semibold text-ok">
          <span className="inline-block h-2 w-2 animate-ping rounded-full bg-ok" />
          Scanning {p.cidr ?? ""}
        </span>
        {(p.targets_total ?? 0) > 1 ? (
          <span className="text-muted">
            target {p.target_index}/{p.targets_total}
          </span>
        ) : null}
        <span className="font-mono text-[13px]">
          {prefix ? `${prefix}.${octet}` : `${anim}/${total}`}
        </span>
        <span className="text-muted">{PHASE_LABEL[p.phase ?? "sweep"] ?? p.phase}</span>
        <span className="ml-auto rounded-md border border-line px-2 py-0.5 font-mono text-[11px] text-muted">
          {pct.toFixed(0)}% · {anim}/{total} hosts · {p.found ?? 0} found
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-panel">
        <div
          className="h-full rounded-full bg-ok"
          style={{ width: `${pct}%`, transition: "width 80ms linear" }}
        />
      </div>
    </div>
  );
}

const EMPTY_EDIT = {
  ssid: "",
  model: "",
  group_id: null as number | null,
  notes: "",
  is_ap: false,
  pinned: false,
};

type Filter = "AP" | "CCTV" | "PHONE" | "INTERNET" | "PIN" | "ONLINE" | "OFFLINE" | "ALL";

export default function AccessPointsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();

  const [filter, setFilter] = useState<Filter>("AP");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const [showTargets, setShowTargets] = useState(false);
  const [targetForm, setTargetForm] = useState({ cidr: "", label: "" });
  const [targetError, setTargetError] = useState("");
  const [showGroups, setShowGroups] = useState(false);
  const [groupForm, setGroupForm] = useState("");
  const [groupError, setGroupError] = useState("");
  const [renameId, setRenameId] = useState<number | null>(null);
  const [renameForm, setRenameForm] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ ...EMPTY_EDIT });

  useEffect(() => {
    setPage(1);
  }, [filter, search]);

  const listQuery = useQuery({
    queryKey: ["ap-list"],
    queryFn: () =>
      api<{ aps: AccessPoint[]; summary: APSummary }>("/access-points"),
    refetchInterval: (q) => (q.state.data?.summary.scanning ? 1500 : 20_000),
  });
  const targetsQuery = useQuery({
    queryKey: ["ap-targets"],
    queryFn: () => api<{ targets: APScanTarget[] }>("/access-points/targets"),
  });
  const suggestQuery = useQuery({
    queryKey: ["ap-suggest"],
    queryFn: () =>
      api<{ suggestions: { cidr: string; iface: string }[] }>(
        "/access-points/suggest-targets",
      ),
    enabled: showTargets,
  });
  const groupsQuery = useQuery({
    queryKey: ["ap-groups"],
    queryFn: () => api<{ groups: APGroup[] }>("/access-points/groups"),
  });
  const eventsQuery = useQuery({
    queryKey: ["ap-events"],
    queryFn: () => api<{ events: APEvent[] }>("/access-points/events?limit=60"),
    refetchInterval: 20_000,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["ap-list"] });
    queryClient.invalidateQueries({ queryKey: ["ap-events"] });
    queryClient.invalidateQueries({ queryKey: ["ap-groups"] });
  };
  const onErr = (err: unknown, fallback: string) =>
    toast.error(err instanceof ApiError ? err.message : fallback);

  // ----------------------------------------------------------- mutations
  const scanNow = useMutation({
    mutationFn: () => api("/access-points/scan-now", { method: "POST" }),
    onSuccess: () => {
      toast.info("Scan started — results will appear in a few seconds");
      setTimeout(invalidateAll, 1500);
    },
    onError: (err) => onErr(err, "Failed to start scan"),
  });

  const cleanupStale = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; deleted: number }>("/access-points/cleanup-stale?days=3", {
        method: "DELETE",
      }),
    onSuccess: (res) => {
      toast.success(`${res.deleted} perangkat offline usang berhasil dibersihkan`);
      invalidateAll();
    },
    onError: (err) => onErr(err, "Gagal membersihkan data usang"),
  });

  const addTarget = useMutation({
    mutationFn: (body: { cidr: string; label: string }) =>
      api("/access-points/targets", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (_res, vars) => {
      toast.success(`Subnet ${vars.cidr} added`);
      setTargetForm({ cidr: "", label: "" });
      setTargetError("");
      queryClient.invalidateQueries({ queryKey: ["ap-targets"] });
    },
    onError: (err) =>
      setTargetError(err instanceof ApiError ? err.message : "Failed to add subnet"),
  });

  const deleteTarget = useMutation({
    mutationFn: (id: number) =>
      api(`/access-points/targets/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ap-targets"] }),
    onError: (err) => onErr(err, "Failed to delete subnet"),
  });

  const addGroup = useMutation({
    mutationFn: (name: string) =>
      api("/access-points/groups", { method: "POST", body: JSON.stringify({ name }) }),
    onSuccess: () => {
      toast.success("Group created");
      setGroupForm("");
      setGroupError("");
      invalidateAll();
    },
    onError: (err) =>
      setGroupError(err instanceof ApiError ? err.message : "Failed to create group"),
  });

  const renameGroup = useMutation({
    mutationFn: (vars: { id: number; name: string }) =>
      api(`/access-points/groups/${vars.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: vars.name }),
      }),
    onSuccess: () => {
      toast.success("Group renamed");
      setRenameId(null);
      invalidateAll();
    },
    onError: (err) => onErr(err, "Failed to rename group"),
  });

  const deleteGroup = useMutation({
    mutationFn: (id: number) =>
      api(`/access-points/groups/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Group deleted — devices are kept");
      invalidateAll();
    },
    onError: (err) => onErr(err, "Failed to delete group"),
  });

  const saveEdit = useMutation({
    mutationFn: (vars: { id: number; body: typeof editForm }) =>
      api(`/access-points/${vars.id}`, {
        method: "PUT",
        body: JSON.stringify(vars.body),
      }),
    onSuccess: () => {
      toast.success("Device updated");
      setEditId(null);
      invalidateAll();
    },
    onError: (err) => onErr(err, "Failed to save device"),
  });

  const pinAp = useMutation({
    mutationFn: (vars: { id: number; pinned: boolean }) =>
      api(`/access-points/${vars.id}/pin?pinned=${vars.pinned}`, { method: "POST" }),
    onSuccess: invalidateAll,
    onError: (err) => onErr(err, "Failed to toggle pin"),
  });

  const moveGroup = useMutation({
    mutationFn: (vars: {
      id: number;
      group_id: number | null;
      ssid: string;
      model: string;
      notes: string;
      is_ap: boolean;
      pinned: boolean;
    }) =>
      api(`/access-points/${vars.id}`, {
        method: "PUT",
        body: JSON.stringify({
          ssid: vars.ssid,
          model: vars.model,
          notes: vars.notes,
          is_ap: vars.is_ap,
          pinned: vars.pinned,
          group_id: vars.group_id,
        }),
      }),
    onSuccess: invalidateAll,
    onError: (err) => onErr(err, "Failed to move device to group"),
  });

  const deleteAp = useMutation({
    mutationFn: (id: number) => api(`/access-points/${id}`, { method: "DELETE" }),
    onSuccess: invalidateAll,
    onError: (err) => onErr(err, "Failed to delete device"),
  });

  const clearEvents = useMutation({
    mutationFn: () => api("/access-points/events", { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Events cleared — pinned devices kept");
      queryClient.invalidateQueries({ queryKey: ["ap-events"] });
    },
    onError: (err) => onErr(err, "Failed to clear events"),
  });

  // ------------------------------------------------------------- derived
  const aps = listQuery.data?.aps ?? [];
  const summary = listQuery.data?.summary;
  const targets = targetsQuery.data?.targets ?? [];
  const groups = groupsQuery.data?.groups ?? [];
  const events = eventsQuery.data?.events ?? [];
  const suggestions = suggestQuery.data?.suggestions ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return aps.filter((a) => {
      if (filter === "PIN" && !a.pinned && a.group_id == null) return false;
      if (filter === "ONLINE" && a.status !== "ONLINE") return false;
      if (filter === "OFFLINE" && a.status !== "OFFLINE") return false;
      if (
        filter === "AP" &&
        !a.is_ap &&
        !a.ssid &&
        !a.group_name?.toLowerCase().includes("access point")
      )
        return false;
      if (filter === "CCTV" && !isMatchingSegment(a.segment, "CCTV")) return false;
      if (filter === "PHONE" && !isMatchingSegment(a.segment, "PHONE")) return false;
      if (filter === "INTERNET" && !isMatchingSegment(a.segment, "INTERNET")) return false;
      if (!q) return true;
      return [a.mac, a.ip, a.vendor, a.model, a.ssid, a.group_name, a.segment, a.notes]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [aps, filter, search]);

  const deviceSort = useTableSort<AccessPoint>(
    filtered,
    {
      status: (ap) => ap.status,
      segment: (ap) => ap.segment,
      ssid: (ap) => ap.ssid,
      ip: (ap) => ap.ip,
      mac: (ap) => ap.mac,
      vendor: (ap) => ap.vendor,
      group: (ap) => ap.group_name,
      last_seen: (ap) => ap.last_seen,
    },
    "ip",
  );

  const totalPages = Math.max(1, Math.ceil(deviceSort.sorted.length / pageSize));
  const paginatedDevices = useMemo(() => {
    const start = (page - 1) * pageSize;
    return deviceSort.sorted.slice(start, start + pageSize);
  }, [deviceSort.sorted, page, pageSize]);

  const eventSort = useTableSort<APEvent>(
    events,
    {
      timestamp: (ev) => ev.timestamp,
      event: (ev) => ev.event,
      mac: (ev) => ev.mac,
      ip: (ev) => ev.ip,
    },
    "timestamp",
    "desc",
  );

  const startEdit = (ap: AccessPoint) => {
    setEditId(ap.id);
    setEditForm({
      ssid: ap.ssid,
      model: ap.model,
      group_id: ap.group_id,
      notes: ap.notes,
      is_ap: ap.is_ap,
      pinned: ap.pinned,
    });
  };

  const submitEdit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (editId == null) return;
    saveEdit.mutate({
      id: editId,
      body: {
        ...editForm,
        ssid: editForm.ssid.trim(),
        model: editForm.model.trim(),
        notes: editForm.notes.trim(),
      },
    });
  };

  const cctvCount = useMemo(
    () => aps.filter((a) => isMatchingSegment(a.segment, "CCTV")).length,
    [aps],
  );
  const phoneCount = useMemo(
    () => aps.filter((a) => isMatchingSegment(a.segment, "PHONE")).length,
    [aps],
  );
  const internetCount = useMemo(
    () => aps.filter((a) => isMatchingSegment(a.segment, "INTERNET")).length,
    [aps],
  );

  const FILTERS: { key: Filter; label: string }[] = [
    { key: "AP", label: `Access Points (${summary?.aps ?? 0})` },
    { key: "CCTV", label: `CCTV (${cctvCount})` },
    { key: "PHONE", label: `Telepon (${phoneCount})` },
    { key: "INTERNET", label: `Internet (${internetCount})` },
    { key: "PIN", label: `Pins & Groups (${summary?.pinned ?? 0} pins)` },
    { key: "ONLINE", label: `Online (${summary?.online ?? 0})` },
    { key: "OFFLINE", label: `Offline (${summary?.offline ?? 0})` },
    { key: "ALL", label: `Semua (${summary?.total ?? 0})` },
  ];

  return (
    <>
      <PageHeader
        title="Network Devices"
        subtitle="LAN inventory — Access Points, CCTV, IP Phones, auto-detected by subnet segment"
        onRefresh={invalidateAll}
        refreshing={listQuery.isLoading}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Devices"
          icon={<span className="text-sm">▤</span>}
          value={summary?.total ?? "-"}
          bottomLeft={`${summary?.aps ?? 0} AP · ${groups.length} groups`}
        />
        <StatCard
          label="Online"
          icon={<span className="text-sm">◉</span>}
          value={summary?.online ?? "-"}
          valueTone={(summary?.online ?? 0) > 0 ? "positive" : undefined}
          bottomLeft={`pinged every ${summary?.ping_interval ?? 15}s`}
        />
        <StatCard
          label="Offline"
          icon={<span className="text-sm">◌</span>}
          value={summary?.offline ?? "-"}
          valueTone={(summary?.offline ?? 0) > 0 ? "negative" : undefined}
          bottomLeft={`after ${summary?.offline_after ?? 4} missed replies · data kept`}
        />
        <StatCard
          label="Auto SSID"
          icon={<span className="text-sm">📶</span>}
          value={summary?.wifi_iface ? "ACTIVE" : "MANUAL"}
          valueTone={summary?.wifi_iface ? "positive" : undefined}
          bottomLeft={
            summary?.wifi_iface
              ? `adapter ${summary.wifi_iface} — scanned every cycle`
              : "server has no WiFi adapter — set manually via Edit"
          }
          bottomRight={`scan ${summary?.last_scan ? fmtTime(summary.last_scan).split(",")[0] : "-"}`}
        />
      </section>

      <div className="h-4" />

      {/* --------------------------------------------------- device list */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Daftar Perangkat Jaringan</div>
            <div className="card-subtitle">
              Pilih tab segmen di bawah untuk melihat Access Point, CCTV, Telepon, atau seluruh perangkat LAN
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn" onClick={() => setShowGroups((v) => !v)}>
              Grup ({groups.length})
            </button>
            <button className="btn" onClick={() => setShowTargets((v) => !v)}>
              Subnet ({targets.length})
            </button>
            <button
              className="btn text-xs"
              disabled={cleanupStale.isPending}
              title="Hapus perangkat offline yang tidak di-pin dan tidak aktif > 3 hari"
              onClick={async () => {
                if (
                  await confirm({
                    title: "Bersihkan Data Usang",
                    message:
                      "Hapus perangkat offline yang tidak di-pin/tanpa grup yang sudah tidak aktif lebih dari 3 hari? (Perangkat AP, Pinned, dan Grup tetap aman).",
                    confirmText: "Ya, bersihkan",
                    tone: "warning",
                  })
                )
                  cleanupStale.mutate();
              }}
            >
              {cleanupStale.isPending ? "Membersihkan…" : "Bersihkan Usang"}
            </button>
            <button
              className="btn btn-primary"
              disabled={scanNow.isPending || !!summary?.scanning}
              onClick={() => scanNow.mutate()}
            >
              {summary?.scanning ? "Scanning…" : "Scan Sekarang"}
            </button>
          </div>
        </div>

        {/* ------------------------------------------- scan progress */}
        {summary?.scanning && summary.scan_progress ? (
          <ScanProgress p={summary.scan_progress} />
        ) : null}

        {/* ------------------------------------------------ groups panel */}
        {showGroups ? (
          <div className="mb-5 rounded-xl border border-line bg-panel2 p-3">
            <form
              className="mb-3 flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (groupForm.trim()) addGroup.mutate(groupForm.trim());
              }}
            >
              <label className="text-[11px] text-muted">
                New Group Name
                <input
                  className="input mt-1 w-56"
                  placeholder="Floor 1 / Warehouse / Meeting Room"
                  value={groupForm}
                  onChange={(e) => setGroupForm(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!groupForm.trim() || addGroup.isPending}
                onClick={() => groupForm.trim() && addGroup.mutate(groupForm.trim())}
              >
                Create Group
              </button>
              {groupError ? (
                <span className="text-[11px] text-bad">{groupError}</span>
              ) : null}
            </form>
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => (
                <div
                  key={g.id}
                  className="flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-xs"
                >
                  {renameId === g.id ? (
                    <>
                      <input
                        className="input w-40"
                        value={renameForm}
                        onChange={(e) => setRenameForm(e.target.value)}
                        autoFocus
                      />
                      <button
                        className="action-btn"
                        disabled={!renameForm.trim() || renameGroup.isPending}
                        onClick={() =>
                          renameForm.trim() &&
                          renameGroup.mutate({ id: g.id, name: renameForm.trim() })
                        }
                      >
                        Save
                      </button>
                      <button className="action-btn" onClick={() => setRenameId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <strong>{g.name}</strong>
                      <span className="text-muted2">{g.count} devices</span>
                      <button
                        className="action-btn"
                        onClick={() => {
                          setRenameId(g.id);
                          setRenameForm(g.name);
                        }}
                      >
                        Rename
                      </button>
                      <button
                        className="action-btn text-bad"
                        disabled={deleteGroup.isPending}
                        onClick={async () => {
                          if (
                            await confirm({
                              message: `Delete group "${g.name}"? Devices inside are not removed.`,
                              confirmText: "Yes, delete",
                            })
                          )
                            deleteGroup.mutate(g.id);
                        }}
                      >
                        Del
                      </button>
                    </>
                  )}
                </div>
              ))}
              {groups.length === 0 ? (
                <span className="py-2 text-[11px] text-muted2">
                  No groups yet — create one, then move devices using the dropdown in the table
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* ----------------------------------------------- subnets panel */}
        {showTargets ? (
          <div className="mb-5 rounded-xl border border-line bg-panel2 p-3">
            <form
              className="mb-3 flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (targetForm.cidr.trim())
                  addTarget.mutate({
                    cidr: targetForm.cidr.trim(),
                    label: targetForm.label.trim(),
                  });
              }}
            >
              <label className="text-[11px] text-muted">
                Subnet (CIDR)
                <input
                  className="input mt-1 w-48"
                  placeholder="192.168.11.0/24"
                  value={targetForm.cidr}
                  onChange={(e) => setTargetForm({ ...targetForm, cidr: e.target.value })}
                />
              </label>
              <label className="text-[11px] text-muted">
                Label (optional)
                <input
                  className="input mt-1 w-52"
                  placeholder="Floor 1 / Office Segment"
                  value={targetForm.label}
                  onChange={(e) => setTargetForm({ ...targetForm, label: e.target.value })}
                />
              </label>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!targetForm.cidr.trim() || addTarget.isPending}
                onClick={() =>
                  targetForm.cidr.trim() &&
                  addTarget.mutate({
                    cidr: targetForm.cidr.trim(),
                    label: targetForm.label.trim(),
                  })
                }
              >
                Add
              </button>
              {targetError ? (
                <span className="text-[11px] text-bad">{targetError}</span>
              ) : null}
            </form>
            {suggestions.length > 0 ? (
              <div className="mb-3 flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] text-muted">Server subnets:</span>
                {suggestions.map((s) => {
                  const exists = targets.some((t) => t.cidr === s.cidr);
                  return (
                    <button
                      key={`${s.cidr}-${s.iface}`}
                      disabled={exists || addTarget.isPending}
                      title={exists ? "Already added" : `Add ${s.cidr} (${s.iface})`}
                      className={`rounded-full border px-2.5 py-1 font-mono text-[11px] ${
                        exists
                          ? "border-line text-muted2"
                          : "border-line text-ok hover:bg-panel"
                      }`}
                      onClick={() =>
                        addTarget.mutate({
                          cidr: s.cidr,
                          label: `iface ${s.iface}`,
                        })
                      }
                    >
                      {exists ? "✓" : "+"} {s.cidr}
                    </button>
                  );
                })}
              </div>
            ) : null}
            <table>
              <thead>
                <tr>
                  <th>Subnet</th>
                  <th>Label</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {targets.map((t) => (
                  <tr key={t.id}>
                    <td><strong>{t.cidr}</strong></td>
                    <td>{t.label || <span className="text-muted2">-</span>}</td>
                    <td>
                      <button
                        className="action-btn text-bad"
                        disabled={deleteTarget.isPending}
                        onClick={() => deleteTarget.mutate(t.id)}
                      >
                        Del
                      </button>
                    </td>
                  </tr>
                ))}
                {targets.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-muted2">
                      No subnets yet — add a LAN range to start scanning
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}

        {/* ------------------------------------------------ filter bar */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              className={`btn ${filter === f.key ? "btn-primary" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
          <input
            className="input ml-auto w-full sm:w-64"
            placeholder="Search IP / MAC / SSID / vendor…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* -------------------------------------------------- form edit */}
        {editId != null ? (
          <form
            className="mb-5 grid grid-cols-1 gap-2 rounded-xl border border-line bg-panel2 p-3 sm:grid-cols-2 lg:grid-cols-3"
            onSubmit={submitEdit}
          >
            <label className="text-[11px] text-muted">
              WiFi Name (SSID)
              <input
                className="input mt-1 w-full"
                placeholder="OFFICE-FL1"
                value={editForm.ssid}
                onChange={(e) => setEditForm({ ...editForm, ssid: e.target.value })}
              />
            </label>
            <label className="text-[11px] text-muted">
              Model
              <input
                className="input mt-1 w-full"
                placeholder="RG-AP840"
                value={editForm.model}
                onChange={(e) => setEditForm({ ...editForm, model: e.target.value })}
              />
            </label>
            <label className="text-[11px] text-muted">
              Group
              <select
                className="input mt-1 w-full"
                value={editForm.group_id ?? ""}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    group_id: e.target.value ? Number(e.target.value) : null,
                  })
                }
              >
                <option value="">— no group —</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
            </label>
            <label className="text-[11px] text-muted sm:col-span-2">
              Notes
              <input
                className="input mt-1 w-full"
                placeholder="Meeting room AP"
                value={editForm.notes}
                onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
              />
            </label>
            <div className="flex items-end gap-4 text-[11px] text-muted">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={editForm.is_ap}
                  onChange={(e) => setEditForm({ ...editForm, is_ap: e.target.checked })}
                />
                Access Point
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={editForm.pinned}
                  onChange={(e) => setEditForm({ ...editForm, pinned: e.target.checked })}
                />
                Pin
              </label>
            </div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3">
              <button type="submit" className="btn btn-primary" disabled={saveEdit.isPending}>
                Save
              </button>
              <button type="button" className="btn" onClick={() => setEditId(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : null}

        {/* ------------------------------------------------------- table */}
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Status" k="status" active={deviceSort.key === "status"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="Segment" k="segment" active={deviceSort.key === "segment"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="SSID / WiFi Name" k="ssid" active={deviceSort.key === "ssid"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="IP" k="ip" active={deviceSort.key === "ip"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="MAC Address" k="mac" active={deviceSort.key === "mac"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="Vendor / Model" k="vendor" active={deviceSort.key === "vendor"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="Group" k="group" active={deviceSort.key === "group"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <SortTh label="Last Seen" k="last_seen" active={deviceSort.key === "last_seen"} dir={deviceSort.dir} onToggle={deviceSort.toggle} />
                <th>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {paginatedDevices.map((ap) => (
                <tr key={ap.id}>
                  <td>
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-[7px] w-[7px] rounded-full ${
                          ap.status === "ONLINE"
                            ? "bg-ok shadow-[0_0_8px_#22c55e]"
                            : "bg-bad"
                        }`}
                      />
                      <StatusBadge status={ap.status.toLowerCase()} />
                      {ap.pinned ? <span title="Terpin">📌</span> : null}
                    </div>
                  </td>
                  <td className="text-[11px]">
                    {ap.segment ? (
                      <span
                        className={`status ${
                          isMatchingSegment(ap.segment, "CCTV")
                            ? "status-info"
                            : isMatchingSegment(ap.segment, "PHONE")
                              ? "status-warning"
                              : isMatchingSegment(ap.segment, "INTERNET")
                                ? "status-running"
                                : ""
                        }`}
                      >
                        {ap.segment}
                      </span>
                    ) : (
                      <span className="text-muted2">-</span>
                    )}
                  </td>
                  <td>
                    <strong>{ap.ssid || <span className="text-muted2">—</span>}</strong>
                    {!ap.is_ap ? (
                      <span className="ml-2 text-[9px] uppercase tracking-wider text-muted2">
                        Bukan AP
                      </span>
                    ) : null}
                  </td>
                  <td className="font-mono">{ap.ip}</td>
                  <td className="font-mono text-[11px]">
                    {ap.mac.startsWith("ip-") ? (
                      <span title="MAC not readable (different segment) — tracked by IP">
                        {ap.ip}
                        <span className="ml-1 text-[9px] uppercase text-muted2">no mac</span>
                      </span>
                    ) : (
                      ap.mac
                    )}
                  </td>
                  <td>
                    {ap.vendor || <span className="text-muted2">?</span>}
                    {ap.model ? <span className="block text-[10px] text-muted">{ap.model}</span> : null}
                    {ap.notes ? (
                      <span className="block text-[10px] text-muted">📝 {ap.notes}</span>
                    ) : null}
                  </td>
                  <td>
                    <select
                      className="input w-36 py-1 text-[11px]"
                      value={ap.group_id ?? ""}
                      disabled={moveGroup.isPending}
                      onChange={(e) => {
                        const gid = e.target.value ? Number(e.target.value) : null;
                        moveGroup.mutate({
                          id: ap.id,
                          group_id: gid,
                          ssid: ap.ssid,
                          model: ap.model,
                          notes: ap.notes,
                          is_ap: ap.is_ap,
                          pinned: ap.pinned,
                        });
                      }}
                    >
                      <option value="">— no group —</option>
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>{g.name}</option>
                      ))}
                    </select>
                  </td>
                  <td
                    className="whitespace-nowrap text-[11px] text-muted"
                    title={`First seen ${fmtTime(ap.first_seen)}`}
                  >
                    {fmtTime(ap.last_seen)}
                  </td>
                  <td>
                    <div className="flex gap-1.5">
                      <button
                        className="action-btn"
                        disabled={pinAp.isPending}
                        onClick={() => pinAp.mutate({ id: ap.id, pinned: !ap.pinned })}
                      >
                        {ap.pinned ? "Unpin" : "Pin"}
                      </button>
                      <button className="action-btn" onClick={() => startEdit(ap)}>
                        Edit
                      </button>
                      <button
                        className="action-btn text-bad"
                        disabled={deleteAp.isPending}
                        onClick={async () => {
                          if (
                            await confirm({
                              message: `Remove ${ap.mac} from the inventory?`,
                              confirmText: "Yes, remove",
                            })
                          )
                            deleteAp.mutate(ap.id);
                        }}
                      >
                        Del
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && !listQuery.isLoading ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-muted2">
                    {filter === "PIN"
                      ? "No pinned or grouped devices yet — open the All tab, then pin/group the important ones"
                      : targets.length === 0
                        ? "Add a subnet target first via the “Subnets” button, then run a scan"
                        : "No devices match the filter"}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {/* --------------------------------------------------- pagination */}
        {totalPages > 1 ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-muted">
            <div>
              Menampilkan {(page - 1) * pageSize + 1} –{" "}
              {Math.min(page * pageSize, deviceSort.sorted.length)} dari{" "}
              {deviceSort.sorted.length} perangkat
            </div>
            <div className="flex items-center gap-1.5">
              <button
                className="btn btn-sm px-2.5 py-1 text-xs"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ← Sebelumnya
              </button>
              <span className="px-2 font-mono">
                {page} / {totalPages}
              </span>
              <button
                className="btn btn-sm px-2.5 py-1 text-xs"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Berikutnya →
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="h-4" />

      {/* ------------------------------------------------------- events */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Recent Events</div>
            <div className="card-subtitle">newly discovered, online &amp; offline transitions</div>
          </div>
          <button
            className="btn"
            disabled={clearEvents.isPending || events.length === 0}
            onClick={async () => {
              if (
                await confirm({
                  message: "Clear all events? Events of pinned devices are kept.",
                  confirmText: "Yes, clear",
                })
              )
                clearEvents.mutate();
            }}
          >
            Clear
          </button>
        </div>
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Time" k="timestamp" active={eventSort.key === "timestamp"} dir={eventSort.dir} onToggle={eventSort.toggle} />
                <SortTh label="Event" k="event" active={eventSort.key === "event"} dir={eventSort.dir} onToggle={eventSort.toggle} />
                <SortTh label="MAC" k="mac" active={eventSort.key === "mac"} dir={eventSort.dir} onToggle={eventSort.toggle} />
                <SortTh label="IP" k="ip" active={eventSort.key === "ip"} dir={eventSort.dir} onToggle={eventSort.toggle} />
              </tr>
            </thead>
            <tbody>
              {eventSort.sorted.map((ev) => (
                <tr key={ev.id}>
                  <td className="whitespace-nowrap text-[11px]">{fmtTime(ev.timestamp)}</td>
                  <td>
                    <StatusBadge
                      status={
                        ev.event === "DISCOVERED"
                          ? "info"
                          : ev.event === "ONLINE"
                            ? "online"
                            : "offline"
                      }
                    />
                  </td>
                  <td className="font-mono text-[11px]">{ev.mac}</td>
                  <td>{ev.ip}</td>
                </tr>
              ))}
              {events.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-muted2">
                    No events yet
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
