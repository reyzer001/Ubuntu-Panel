"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useToast } from "@/components/providers";
import { api } from "@/lib/api";
import type { LogEntry } from "@/lib/types";
import { useTableSort } from "@/components/ui/table-sort";
import clsx from "clsx";

type Level = "ALL" | "INFO" | "WARN" | "ERROR";

export default function LogsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [level, setLevel] = useState<Level>("ALL");
  const [search, setSearch] = useState("");

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["logs", level],
    queryFn: () =>
      api<{ entries: LogEntry[] }>(
        `/logs?lines=500&level=${encodeURIComponent(level)}`
      ),
    refetchInterval: 20_000,
  });

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return (data?.entries ?? []).filter(
      (e) =>
        !q ||
        e.message.toLowerCase().includes(q) ||
        e.source.toLowerCase().includes(q)
    );
  }, [data, search]);

  const logSort = useTableSort<LogEntry>(
    rows,
    {
      time: (log) => log.time,
      level: (log) => log.level,
      source: (log) => log.source,
    },
    "time",
    "desc"
  );

  function exportLogs() {
    const text = rows
      .map((e) => `${e.time} [${e.level}] ${e.source}: ${e.message}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `system-logs-${new Date().toISOString().slice(0, 19)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.info("Log viewer opened — file exported");
  }

  return (
    <>
      <PageHeader
        title="System Logs"
        subtitle="Journal and system events"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["logs"] })}
        refreshing={isFetching || isLoading}
      />

      <div className="card">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5">
          <input
            className="input min-w-[240px]"
            placeholder="Search logs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {(["ALL", "INFO", "WARN", "ERROR"] as Level[]).map((l) => (
              <button
                key={l}
                className={clsx("btn px-2.5 py-1.5", level === l && "btn-primary")}
                onClick={() => setLevel(l)}
              >
                {l}
              </button>
            ))}
            <button className="btn" onClick={exportLogs}>
              Export
            </button>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted">Sort:</span>
          {[
            { k: "time", label: "Newest/Oldest" },
            { k: "level", label: "Level" },
          ].map((c) => (
            <button
              key={c.k}
              className={`btn px-2 py-1 text-[11px] ${
                logSort.key === c.k ? "btn-primary" : ""
              }`}
              onClick={() => logSort.toggle(c.k)}
            >
              {c.label}{" "}
              {logSort.key === c.k ? (
                <span className="text-[9px]">{logSort.dir === "asc" ? "▲" : "▼"}</span>
              ) : null}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          {logSort.sorted.map((log, i) => (
            <div
              key={`${log.time}-${i}`}
              className="grid grid-cols-1 items-center gap-1 rounded-[9px] border border-line bg-[#131a22] px-3 py-2.5 text-[10px] md:grid-cols-[75px_70px_110px_1fr] md:gap-2.5"
            >
              <div className="text-muted2">{log.time}</div>
              <div
                className={clsx(
                  "font-bold",
                  log.level === "ERROR" && "text-[#ff8f8f]",
                  log.level === "WARN" && "text-[#ffd277]",
                  log.level === "INFO" && "text-[#7fb2ff]"
                )}
              >
                {log.level}
              </div>
              <div className="truncate text-[#9eabb9]">{log.source}</div>
              <div className="break-all text-[#d7dee6]">{log.message}</div>
            </div>
          ))}
          {rows.length === 0 ? (
            <div className="py-10 text-center text-xs text-muted2">
              No log entries found
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
