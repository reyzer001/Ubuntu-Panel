"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import { ArrowDown, ArrowUp, Network as NetworkIcon } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { NetworkGaugeCard } from "@/components/ui/network-gauge-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import { api } from "@/lib/api";
import { formatBytes, formatRate } from "@/lib/format";
import type {
  InterfaceInfo,
  NetHistoryPoint,
  PortInfo,
} from "@/lib/types";

const MAX_POINTS = 150;

export default function NetworkPage() {
  const queryClient = useQueryClient();
  const { metrics: live, connected, transport } = useMetricsStream();
  const [selectedIface, setSelectedIface] = useState<string>("");

  const { data: ifaces, isLoading } = useQuery({
    queryKey: ["interfaces"],
    queryFn: () =>
      api<{ interfaces: InterfaceInfo[] }>("/network/interfaces"),
  });

  const { data: portsData } = useQuery({
    queryKey: ["ports"],
    queryFn: () =>
      api<{ ports: PortInfo[]; established: number }>("/network/ports"),
  });

  // buffer riwayat rate per interface dari stream WS (2 detik per titik)
  const [netHist, setNetHist] = useState<NetHistoryPoint[]>([]);
  useEffect(() => {
    if (!live?.net_interfaces) return;
    setNetHist((prev) => {
      const rates: NetHistoryPoint["rates"] = {};
      for (const r of live.net_interfaces ?? []) rates[r.interface] = r;
      return [...prev, { t: live.time, rates }].slice(-MAX_POINTS);
    });
  }, [live]);

  // kandidat interface: buang loopback; pilihan default = trafik terbesar
  const ifaceOptions = useMemo(() => {
    const list = (ifaces?.interfaces ?? []).filter(
      (i) => i.interface !== "lo"
    );
    if (!list.length) return [];
    const totals = new Map<string, number>();
    for (const i of list)
      totals.set(i.interface, (i.rx_bytes ?? 0) + (i.tx_bytes ?? 0));
    return [...list].sort(
      (a, b) => (totals.get(b.interface) ?? 0) - (totals.get(a.interface) ?? 0)
    );
  }, [ifaces]);

  const activeIface =
    selectedIface || ifaceOptions[0]?.interface || "";

  const chartData = useMemo(
    () =>
      netHist
        .filter((p) => p.rates[activeIface])
        .map((p) => ({
          t: p.t.slice(11, 16),
          rx: Number(((p.rates[activeIface]?.rx_rate ?? 0) / 1024).toFixed(1)),
          tx: Number(((p.rates[activeIface]?.tx_rate ?? 0) / 1024).toFixed(1)),
        })),
    [netHist, activeIface]
  );

  const liveRate = live?.net_interfaces?.find(
    (r) => r.interface === activeIface
  );

  const ifacesList = ifaces?.interfaces ?? [];
  const ifacesSort = useTableSort(
    ifacesList,
    {
      interface: (i) => i.interface,
      status: (i) => (i.up ? 1 : 0),
      ip: (i) => i.ip,
      mac: (i) => i.mac,
      rx_rate: (i) =>
        live?.net_interfaces?.find((x) => x.interface === i.interface)
          ?.rx_rate ??
        i.rx_rate ??
        0,
      tx_rate: (i) =>
        live?.net_interfaces?.find((x) => x.interface === i.interface)
          ?.tx_rate ??
        i.tx_rate ??
        0,
      rx_bytes: (i) => i.rx_bytes,
      tx_bytes: (i) => i.tx_bytes,
    },
    "interface"
  );

  const portsList = portsData?.ports ?? [];
  const portsSort = useTableSort(
    portsList,
    {
      port: (p) => p.port,
      protocol: (p) => p.protocol,
      process: (p) => p.process,
      address: (p) => p.address,
    },
    "port"
  );

  return (
    <>
      <PageHeader
        title="Network"
        subtitle="Network interfaces and connections"
        onRefresh={() => {
          queryClient.invalidateQueries({ queryKey: ["interfaces"] });
          queryClient.invalidateQueries({ queryKey: ["ports"] });
        }}
        refreshing={isLoading}
        right={<StatusBadge status={connected ? "online" : "down"} />}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <NetworkGaugeCard
          variant="download"
          value={live?.net_rx_rate ?? 0}
          subtext={
            connected
              ? transport === "polling"
                ? "Polling 2 dtk (WS tak terjangkau)"
                : "Realtime rate"
              : "Stream terputus"
          }
          statusText={connected ? "Live" : "Offline"}
        />
        <NetworkGaugeCard
          variant="upload"
          value={live?.net_tx_rate ?? 0}
          subtext={
            connected
              ? transport === "polling"
                ? "Polling 2 dtk (WS tak terjangkau)"
                : "Realtime rate"
              : "Stream terputus"
          }
          statusText={connected ? "Live" : "Offline"}
        />
        <NetworkGaugeCard
          variant="connections"
          value={portsData?.established ?? 0}
          listeningCount={portsData?.ports?.length}
        />
      </section>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Traffic</div>
            <div className="card-subtitle">
              Realtime RX/TX · {activeIface || "—"} ·{" "}
              {liveRate
                ? `↓ ${formatRate(liveRate.rx_rate)} · ↑ ${formatRate(liveRate.tx_rate)}`
                : connected
                  ? "menunggu data…"
                  : "stream terputus — periksa koneksi ke backend"}
            </div>
          </div>
          <select
            className="input w-44"
            value={activeIface}
            onChange={(e) => setSelectedIface(e.target.value)}
          >
            {ifaceOptions.map((i) => (
              <option key={i.interface} value={i.interface}>
                {i.interface}
              </option>
            ))}
          </select>
        </div>
        <div className="h-[230px]">
          {chartData.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                <defs>
                  <linearGradient id="netRx" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="netTx" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#24303d" vertical={false} />
                <YAxis
                  width={55}
                  tick={{ fill: "#5f6c7c", fontSize: 10 }}
                  unit=" KB/s"
                />
                <Tooltip
                  contentStyle={{
                    background: "#151e28",
                    border: "1px solid #24303d",
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                  labelStyle={{ color: "#8794a4" }}
                />
                <Area type="monotone" dataKey="rx" name="RX" stroke="#3b82f6" strokeWidth={2} fill="url(#netRx)" isAnimationActive={false} />
                <Area type="monotone" dataKey="tx" name="TX" stroke="#8b5cf6" strokeWidth={2} fill="url(#netTx)" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="grid h-full place-items-center text-[11px] text-muted2">
              mengumpulkan sampel trafik… (±{Math.max(0, 5 - chartData.length) * 2} detik)
            </div>
          )}
        </div>
      </div>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Network Interfaces</div>
            <div className="card-subtitle">Interface configuration</div>
          </div>
        </div>
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Interface" k="interface" active={ifacesSort.key === "interface"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="Status" k="status" active={ifacesSort.key === "status"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="IP Address" k="ip" active={ifacesSort.key === "ip"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="MAC" k="mac" active={ifacesSort.key === "mac"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="RX Rate" k="rx_rate" active={ifacesSort.key === "rx_rate"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="TX Rate" k="tx_rate" active={ifacesSort.key === "tx_rate"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="RX Total" k="rx_bytes" active={ifacesSort.key === "rx_bytes"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
                <SortTh label="TX Total" k="tx_bytes" active={ifacesSort.key === "tx_bytes"} dir={ifacesSort.dir} onToggle={ifacesSort.toggle} />
              </tr>
            </thead>
            <tbody>
              {ifacesSort.sorted.map((i) => {
                const r = live?.net_interfaces?.find(
                  (x) => x.interface === i.interface
                );
                return (
                  <tr key={i.interface}>
                    <td>
                      <strong>{i.interface}</strong>
                    </td>
                    <td>
                      <StatusBadge status={i.up ? "online" : "down"} />
                    </td>
                    <td>{i.ip || "—"}</td>
                    <td>{i.mac || "—"}</td>
                    <td className="text-info">{formatRate(r?.rx_rate ?? i.rx_rate ?? 0)}</td>
                    <td className="text-warn">{formatRate(r?.tx_rate ?? i.tx_rate ?? 0)}</td>
                    <td>{formatBytes(i.rx_bytes)}</td>
                    <td>{formatBytes(i.tx_bytes)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Listening Ports</div>
            <div className="card-subtitle">
              Services accepting connections
            </div>
          </div>
        </div>
        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Port" k="port" active={portsSort.key === "port"} dir={portsSort.dir} onToggle={portsSort.toggle} />
                <SortTh label="Protocol" k="protocol" active={portsSort.key === "protocol"} dir={portsSort.dir} onToggle={portsSort.toggle} />
                <SortTh label="Process" k="process" active={portsSort.key === "process"} dir={portsSort.dir} onToggle={portsSort.toggle} />
                <SortTh label="Address" k="address" active={portsSort.key === "address"} dir={portsSort.dir} onToggle={portsSort.toggle} />
              </tr>
            </thead>
            <tbody>
              {portsSort.sorted.map((p, idx) => (
                <tr key={`${p.port}-${p.protocol}-${p.address}-${idx}`}>
                  <td>{p.port}</td>
                  <td>{p.protocol}</td>
                  <td>{p.process}</td>
                  <td>{p.address}</td>
                </tr>
              ))}
              {(portsData?.ports ?? []).length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-muted2">
                    No listening ports detected (run backend as root to see all)
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
