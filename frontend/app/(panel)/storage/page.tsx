"use client";

import { useMemo, useRef, useState, type DragEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Download,
  File as FileIcon,
  Folder,
  FolderPlus,
  Link2,
  Loader2,
  Trash2,
  Upload,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import { api, apiDownload, apiUpload, ApiError } from "@/lib/api";
import {
  cx,
  formatBytes,
  formatRate,
  toneBarClass,
  usageTone,
} from "@/lib/format";
import type { DirListing, FileEntry, FilesystemInfo } from "@/lib/types";
import { useTableSort } from "@/components/ui/table-sort";

function fmtDate(t: number): string {
  if (!t) return "—";
  return new Date(t * 1000).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

async function readEntry(
  entry: FileSystemEntry,
  basePath: string
): Promise<{ relativePath: string; file: File }[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject)
    );
    return [{ relativePath: `${basePath}/${entry.name}`, file }];
  }
  if (entry.isDirectory) {
    const dir = entry as FileSystemDirectoryEntry;
    const reader = dir.createReader();
    const results: { relativePath: string; file: File }[] = [];
    const readBatch = () =>
      new Promise<FileSystemEntry[]>((resolve) =>
        reader.readEntries(resolve, () => resolve([]))
      );
    let batch: FileSystemEntry[];
    do {
      batch = await readBatch();
      for (const child of batch) {
        results.push(...(await readEntry(child, `${basePath}/${entry.name}`)));
      }
    } while (batch.length > 0);
    return results;
  }
  return [];
}

type SortKey = "name" | "size" | "mtime";

export default function StoragePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const { metrics: live } = useMetricsStream();

  const { data, isLoading } = useQuery({
    queryKey: ["filesystems"],
    queryFn: () =>
      api<{ filesystems: FilesystemInfo[] }>("/storage/filesystems"),
  });

  const fsSort = useTableSort<FilesystemInfo>(
    data?.filesystems ?? [],
    {
      mountpoint: (fs) => fs.mountpoint,
      fstype: (fs) => fs.fstype,
      percent: (fs) => fs.percent,
      total: (fs) => fs.total,
    },
    "mountpoint"
  );

  // ------------------------------------------------------- file manager
  const [cwd, setCwd] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);
  const [jump, setJump] = useState("");
  const [uploading, setUploading] = useState<{ name: string; pct: number } | null>(
    null
  );
  const [busyAction, setBusyAction] = useState(false);
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const filesQuery = useQuery({
    queryKey: ["files", cwd, showHidden],
    queryFn: () =>
      api<DirListing>(
        `/files/list?path=${encodeURIComponent(cwd)}&show_hidden=${showHidden}`
      ),
  });

  const listing = filesQuery.data;
  const curPath = listing?.path ?? "";

  const invalidateFiles = () => {
    queryClient.invalidateQueries({ queryKey: ["files"] });
    queryClient.invalidateQueries({ queryKey: ["filesystems"] });
  };
  const onErr = (err: unknown, fallback: string) =>
    toast.error(err instanceof ApiError ? err.message : fallback);

  const entries = useMemo(() => {
    const rows = listing?.entries ?? [];
    const dirFirst = [...rows].sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      const mul = sortAsc ? 1 : -1;
      if (sortKey === "size") return (a.size - b.size) * mul;
      if (sortKey === "mtime") return (a.mtime - b.mtime) * mul;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) * mul;
    });
    return dirFirst;
  }, [listing, sortKey, sortAsc]);

  const crumbs = useMemo(() => {
    if (!curPath) return [];
    const parts = curPath.split("/").filter(Boolean);
    const acc: { label: string; path: string }[] = [
      { label: "/", path: "/" },
    ];
    let run = "";
    for (const p of parts) {
      run += `/${p}`;
      acc.push({ label: p, path: run });
    }
    return acc;
  }, [curPath]);

  const openDir = (p: string) => {
    setCwd(p);
    setJump("");
  };

  const goUp = () => {
    if (listing?.parent != null) openDir(listing.parent);
  };

  const onPickFiles = async (flist: FileList | null) => {
    if (!flist?.length || !listing) return;
    let ok = 0;
    let fail = 0;
    for (const f of Array.from(flist)) {
      setUploading({ name: f.name, pct: 0 });
      const fd = new FormData();
      fd.append("path", listing.path);
      const relativePath = (f as File & { webkitRelativePath?: string }).webkitRelativePath;
      if (relativePath) fd.append("relative_path", relativePath);
      fd.append("file", f);
      try {
        await apiUpload("/files/upload", fd, (pct) =>
          setUploading({ name: f.name, pct })
        );
        ok += 1;
      } catch (err) {
        fail += 1;
        onErr(err, `Upload gagal: ${f.name}`);
      }
    }
    setUploading(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (ok > 0) {
      if (fail > 0)
        toast.warning(`Upload: ${ok} berhasil, ${fail} gagal`, {
          description: `${fail} file tidak terunggah, coba ulangi.`,
        });
      else toast.success("Upload selesai");
    }
    if (ok > 0) invalidateFiles();
  };

  const onDropHandler = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;
    if (!listing) return;
    const items = e.dataTransfer.items;
    if (!items?.length) return;
    const allFiles: { relativePath: string; file: File }[] = [];
    for (const item of Array.from(items)) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) {
        allFiles.push(...(await readEntry(entry, "")));
      }
    }
    if (allFiles.length === 0) return;
    const rootFolder = allFiles[0].relativePath.split("/")[1] || "dropped";
    let ok = 0;
    let fail = 0;
    for (const item of allFiles) {
      setUploading({ name: `drop: ${item.relativePath}`, pct: 0 });
      const fd = new FormData();
      fd.append("path", listing.path);
      fd.append("relative_path", item.relativePath);
      fd.append("file", item.file);
      try {
        await apiUpload("/files/upload", fd, (pct) =>
          setUploading((cur) => (cur ? { ...cur, pct } : null))
        );
        ok += 1;
      } catch (err) {
        fail += 1;
        onErr(err, `Upload gagal: ${item.relativePath}`);
      }
    }
    setUploading(null);
    if (ok > 0) {
      toast[fail > 0 ? "warning" : "success"](
        `Folder "${rootFolder}": ${ok} berhasil${fail ? `, ${fail} gagal` : ""}`
      );
      invalidateFiles();
    }
  };

  const newFolder = async () => {
    if (!listing) return;
    const name = window.prompt("Nama folder baru:");
    if (!name?.trim()) return;
    setBusyAction(true);
    try {
      await api("/files/mkdir", {
        method: "POST",
        body: JSON.stringify({ path: listing.path, name: name.trim() }),
      });
      toast.success("Folder dibuat");
      invalidateFiles();
    } catch (err) {
      onErr(err, "Gagal membuat folder");
    } finally {
      setBusyAction(false);
    }
  };

  const removeEntry = async (e: FileEntry) => {
    const what = e.is_dir
      ? `folder "${e.name}" BESERTA SELURUH ISINYA`
      : `file "${e.name}"`;
    if (
      !(await confirm({
        message: `Hapus ${what}?`,
        confirmText: "Ya, hapus",
      }))
    )
      return;
    setBusyAction(true);
    try {
      await api(`/files?path=${encodeURIComponent(e.path)}`, {
        method: "DELETE",
      });
      toast.success("Terhapus");
      invalidateFiles();
    } catch (err) {
      onErr(err, "Gagal menghapus");
    } finally {
      setBusyAction(false);
    }
  };

  const downloadFile = async (e: FileEntry) => {
    if (downloadingPath) return;
    if (e.is_dir)
      toast.info("Menyiapkan arsip…", {
        description: `Folder "${e.name}" sedang dikompres.`,
      });
    setDownloadingPath(e.path);
    try {
      await apiDownload(
        `/files/download?path=${encodeURIComponent(e.path)}`,
        e.is_dir ? `${e.name.trim() || "folder"}.zip` : e.name
      );
    } catch (err) {
      onErr(err, "Download gagal");
    } finally {
      setDownloadingPath(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Storage"
        subtitle="Disk, filesystem & file manager"
        onRefresh={() => {
          queryClient.invalidateQueries({ queryKey: ["filesystems"] });
          invalidateFiles();
        }}
        refreshing={isLoading || filesQuery.isLoading}
      />

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Filesystems</div>
              <div className="card-subtitle">Mounted filesystems</div>
            </div>
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted">Sort:</span>
            {[
              { k: "mountpoint", label: "Mount point" },
              { k: "fstype", label: "Type" },
              { k: "percent", label: "Use%" },
              { k: "total", label: "Total" },
            ].map((c) => (
              <button
                key={c.k}
                className={`btn px-2 py-1 text-[11px] ${
                  fsSort.key === c.k ? "btn-primary" : ""
                }`}
                onClick={() => fsSort.toggle(c.k)}
              >
                {c.label}{" "}
                {fsSort.key === c.k ? (
                  <span className="text-[9px]">{fsSort.dir === "asc" ? "▲" : "▼"}</span>
                ) : null}
              </button>
            ))}
          </div>

          {fsSort.sorted.map((fs) => (
            <div key={fs.mountpoint} className="mb-5 last:mb-0">
              <div className="mb-2 flex justify-between text-[11px]">
                <span>
                  <strong>{fs.mountpoint}</strong>
                  <span className="ml-2 text-muted2">{fs.device}</span>
                </span>
                <span>{fs.percent}%</span>
              </div>
              <div className="progress">
                <div
                  className={`progress-bar ${toneBarClass[usageTone(fs.percent)]}`}
                  style={{ width: `${Math.min(100, fs.percent)}%` }}
                />
              </div>
              <div className="mt-1.5 text-[9px] text-muted">
                {formatBytes(fs.used)} used of {formatBytes(fs.total)} ·{" "}
                {formatBytes(fs.free)} free · inodes{" "}
                {fs.inodes_percent != null ? `${fs.inodes_percent}%` : "—"}
              </div>
            </div>
          ))}
          {(data?.filesystems ?? []).length === 0 ? (
            <div className="py-8 text-center text-xs text-muted2">
              No filesystem data
            </div>
          ) : null}
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Disk I/O</div>
              <div className="card-subtitle">Current activity</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div className="info-item">
              <div className="info-label">Read</div>
              <div className="info-value">
                {formatRate(live?.disk_read_rate ?? 0)}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Write</div>
              <div className="info-value">
                {formatRate(live?.disk_write_rate ?? 0)}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Total Used</div>
              <div className="info-value">
                {live ? formatBytes(live.disk_used) : "—"}
              </div>
            </div>
            <div className="info-item">
              <div className="info-label">Total Capacity</div>
              <div className="info-value">
                {live ? formatBytes(live.disk_total) : "—"}
              </div>
            </div>
          </div>

          <p className="mt-4 text-[10px] leading-relaxed text-muted">
            Tip: gunakan <strong>File Manager</strong> di bawah untuk upload,
            download, dan mengelola file dari perangkat mana pun (localhost,
            IP LAN, atau IP Tailscale).
          </p>
        </div>
      </section>

      {/* --------------------------------------------------- file manager */}
      <div className="h-4" />
      <div
        className="card relative"
        onDragEnter={(e) => {
          e.preventDefault();
          e.stopPropagation();
          dragCounter.current++;
          if (e.dataTransfer.types.includes("Files")) setIsDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          e.stopPropagation();
          dragCounter.current--;
          if (dragCounter.current === 0) setIsDragging(false);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={onDropHandler}
      >
        {isDragging && (
          <div className="absolute inset-0 z-50 flex items-center justify-center rounded-xl border-2 border-dashed border-accent bg-accent/10 backdrop-blur-sm">
            <span className="text-sm font-medium text-accent">
              Drop files or folders here
            </span>
          </div>
        )}
        <div className="card-header">
          <div>
            <div className="card-title">File Manager</div>
            <div className="card-subtitle">
              {listing
                ? `${formatBytes(listing.free ?? 0)} free · ${
                    entries.length
                  } items`
                : "loading…"}
            </div>
          </div>
        </div>

        {/* toolbar */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            className="btn px-2 py-1.5"
            title="Ke folder atas"
            disabled={!listing || listing.parent == null}
            onClick={goUp}
          >
            <ArrowUp size={14} />
          </button>
          <input
            className="input w-full max-w-md font-mono text-xs"
            placeholder={curPath || "/path/ke/folder"}
            value={jump}
            onChange={(e) => setJump(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") openDir(jump.trim() || "");
            }}
          />
          <label className="flex items-center gap-1.5 text-[11px] text-muted">
            <input
              type="checkbox"
              checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)}
            />
            hidden
          </label>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button className="btn px-2 py-1.5 text-xs" onClick={newFolder} disabled={busyAction}>
              <FolderPlus size={14} /> New Folder
            </button>
            <button
              className="btn btn-primary px-2 py-1.5 text-xs"
              disabled={uploading != null}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={14} /> Upload
            </button>
            <button
              className="btn px-2 py-1.5 text-xs"
              disabled={uploading != null}
              onClick={() => folderInputRef.current?.click()}
            >
              <Folder size={14} /> Upload Folder
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => onPickFiles(e.target.files)}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
              className="hidden"
              onChange={(e) => onPickFiles(e.target.files)}
            />
          </div>
        </div>

        {/* breadcrumbs */}
        {crumbs.length > 0 ? (
          <div className="mb-3 flex flex-wrap items-center gap-0.5 font-mono text-[11px]">
            {crumbs.map((c, i) => (
              <span key={c.path} className="flex items-center">
                {i > 0 ? <span className="mx-0.5 text-muted2">/</span> : null}
                <button
                  className={cx(
                    "rounded px-1 py-0.5 hover:bg-panel2",
                    i === crumbs.length - 1 ? "font-bold text-accent" : "text-muted"
                  )}
                  onClick={() => openDir(c.path)}
                >
                  {c.label}
                </button>
              </span>
            ))}
          </div>
        ) : null}

        {/* upload progress */}
        {uploading ? (
          <div className="mb-3 rounded-lg border border-line bg-panel2 p-2.5">
            <div className="mb-1.5 flex justify-between text-[10px] text-muted">
              <span className="truncate font-mono">{uploading.name}</span>
              <span>{uploading.pct}%</span>
            </div>
            <div className="progress">
              <div
                className="progress-bar bg-info transition-all"
                style={{ width: `${uploading.pct}%` }}
              />
            </div>
          </div>
        ) : null}

        {/* sort */}
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted">Sort:</span>
          {([
            ["name", "Name"],
            ["size", "Size"],
            ["mtime", "Modified"],
          ] as const).map(([k, label]) => (
            <button
              key={k}
              className={`btn px-2 py-1 text-[11px] ${
                sortKey === k ? "btn-primary" : ""
              }`}
              onClick={() => {
                if (sortKey === k) setSortAsc((v) => !v);
                else {
                  setSortKey(k);
                  setSortAsc(true);
                }
              }}
            >
              {label}{" "}
              {sortKey === k ? (
                <span className="text-[9px]">{sortAsc ? "▲" : "▼"}</span>
              ) : null}
            </button>
          ))}
        </div>

        {/* entries */}
        {filesQuery.isLoading ? (
          <div className="py-8 text-center text-sm text-muted2">Loading…</div>
        ) : filesQuery.isError ? (
          <div className="py-6 text-center text-xs text-bad">
            Gagal membaca folder — cek path atau izin akses.
          </div>
        ) : entries.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted2">
            Folder kosong
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-line">
            {entries.map((e, i) => (
              <div
                key={e.path}
                className={cx(
                  "flex items-center gap-2 px-3 py-2 hover:bg-panel2/70",
                  i % 2 === 1 && "bg-panel2/30"
                )}
              >
                {e.is_dir ? (
                  <Folder size={15} className="shrink-0 text-info" />
                ) : e.is_symlink ? (
                  <Link2 size={14} className="shrink-0 text-muted2" />
                ) : (
                  <FileIcon size={15} className="shrink-0 text-muted" />
                )}
                {e.is_dir && !e.is_symlink ? (
                  <button
                    className="min-w-0 flex-1 truncate text-left text-xs hover:text-accent"
                    title={e.path}
                    onClick={() => openDir(e.path)}
                  >
                    {e.name}
                  </button>
                ) : (
                  <span className="min-w-0 flex-1 truncate text-xs" title={e.path}>
                    {e.name}
                  </span>
                )}
                <span className="hidden w-24 shrink-0 font-mono text-[10px] text-muted2 sm:block">
                  {e.mode}
                </span>
                <span className="hidden w-36 shrink-0 text-right text-[10px] text-muted2 md:block">
                  {fmtDate(e.mtime)}
                </span>
                <span className="w-16 shrink-0 text-right text-[10px] text-muted">
                  {e.is_dir ? "—" : formatBytes(e.size)}
                </span>
                <button
                  className="action-btn shrink-0 disabled:opacity-40"
                  title={e.is_dir ? "Download folder (ZIP)" : "Download"}
                  disabled={downloadingPath != null}
                  onClick={() => downloadFile(e)}
                >
                  {downloadingPath === e.path ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Download size={13} />
                  )}
                </button>
                <button
                  className="action-btn shrink-0 text-bad disabled:opacity-40"
                  title="Delete"
                  disabled={busyAction || (downloadingPath != null && downloadingPath === e.path)}
                  onClick={() => removeEntry(e)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
