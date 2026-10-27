"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Cpu,
  Flame,
  HardDrive,
  MemoryStick,
  SlidersHorizontal,
  Thermometer,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/page-header";
import { useToast } from "@/components/providers";
import { ConcentricPerformanceMeter } from "@/components/ui/concentric-performance-meter";
import { GaugeCard } from "@/components/ui/gauge-card";
import { MetricDetailModal, type MetricType } from "@/components/ui/metric-detail-modal";
import { MyzrokToggle } from "@/components/myzrok-toggle";
import { MiniNetworkGauge } from "@/components/ui/mini-network-gauge";
import { StatusBadge } from "@/components/ui/status-badge";
import { ThermalThresholdModal } from "@/components/ui/thermal-threshold-modal";
import { useMetricsStream } from "@/hooks/use-metrics-stream";
import { ApiError, api } from "@/lib/api";
import {
  DEFAULT_THERMAL_THRESHOLDS,
  pickPrimarySensor,
  sensorRank,
  tempTone,
  type ThermalThresholds,
} from "@/lib/thermal";
import type {
  FilesystemInfo,
  LogEntry,
  Metrics,
  ServiceInfo,
  SystemInfo,
} from "@/lib/types";
import { useAuth } from "@/store/auth";
import clsx from "clsx";

const CRITICAL = ["nginx", "postgresql", "postgres", "docker", "redis", "ssh"];

type Range = "1m" | "5m" | "all";

const RANGE_POINTS: Record<Range, number> = { "1m": 30, "5m": 150, all: Infinity };

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const user = useAuth((state) => state.user);
  const canEditThermal = user?.role === "superadmin";
  const [range, setRange] = useState<Range>("5m");
  const [selectedMetric, setSelectedMetric] = useState<MetricType | null>(null);
  const [thresholdOpen, setThresholdOpen] = useState(false);

  const { data: info } = useQuery({
    queryKey: ["system-info"],
    queryFn: () => api<SystemInfo>("/system/info"),
  });
  const { data: metricsRest } = useQuery({
    queryKey: ["metrics"],
    queryFn: () => api<Metrics>("/system/metrics"),
    refetchInterval: 15_000,
  });
  const { data: servicesData } = useQuery({
    queryKey: ["services"],
    queryFn: () => api<{ services: ServiceInfo[] }>("/services"),
  });
  const { data: logsData } = useQuery({
    queryKey: ["logs", "dashboard"],
    queryFn: () => api<{ entries: LogEntry[] }>("/logs?lines=50"),
  });
  const { data: fsData } = useQuery({
    queryKey: ["filesystems"],
    queryFn: () =>
      api<{ filesystems: FilesystemInfo[] }>("/storage/filesystems"),
  });
  const { data: thermalSettings } = useQuery({
    queryKey: ["thermal-settings"],
    queryFn: () => api<ThermalThresholds>("/settings/thermal"),
    staleTime: 60_000,
  });
  const thresholds = thermalSettings ?? DEFAULT_THERMAL_THRESHOLDS;

  const saveThermal = useMutation({
    mutationFn: (values: ThermalThresholds) =>
      api<ThermalThresholds>("/settings/thermal", {
        method: "PUT",
        body: JSON.stringify(values),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["thermal-settings"], data);
      setThresholdOpen(false);
      toast.success("Thermal thresholds disimpan");
    },
    onError: (error) => {
      toast.error(
        "Gagal menyimpan threshold",
        {
          description:
            error instanceof ApiError ? error.message : "Terjadi kesalahan",
        }
      );
    },
  });

  const { metrics: live, history, transport } = useMetricsStream();
  const m = live ?? metricsRest ?? null;

  const tempChartData = useMemo(() => {
    const points = history.slice(-RANGE_POINTS[range]);
    return points.flatMap((point) =>
      typeof point.temp === "number"
        ? [{ t: point.t.slice(11, 16), temp: Number(point.temp.toFixed(1)) }]
        : []
    );
  }, [history, range]);

  const criticalServices = (servicesData?.services ?? [])
    .filter((s) => CRITICAL.some((k) => s.name.includes(k)))
    .slice(0, 5);

  const sensors = m?.temperatures ?? [];
  const orderedSensors = [...sensors].sort(
    (a, b) => sensorRank(a) - sensorRank(b)
  );
  const primarySensor = pickPrimarySensor(sensors);
  const currentTemp = m?.cpu_temperature ?? primarySensor?.current ?? null;
  const maxTemp = sensors.reduce((max, sensor) => Math.max(max, sensor.current), 0);
  const tempStatus = tempTone(currentTemp ?? 0, thresholds);
  const maxTempStatus = tempTone(maxTemp, thresholds);

  return (
    <>
      <PageHeader
        title="Server Overview"
        subtitle={`Monitoring ${info?.hostname ?? "server"} · ${
          transport === "ws" ? "live" : transport === "polling" ? "polling" : "offline"
        }`}
        onRefresh={() => queryClient.invalidateQueries()}
        right={<MyzrokToggle />}
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <GaugeCard
          variant="cpu"
          label="CPU Usage"
          icon={<Cpu size={15} className="text-muted" />}
          gaugeValue={m ? m.cpu : 0}
          kernel={m?.cpu_kernel ?? 0.2}
          format={(v) => `${v.toFixed(0)}%`}
          subtext={`${m?.cpu_cores ?? "—"} vCPU`}
          onClick={() => setSelectedMetric("cpu")}
          statusText={
            (m?.cpu ?? 0) >= 90
              ? "High"
              : (m?.cpu ?? 0) >= 75
                ? "Elevated"
                : "Normal"
          }
        />
        <GaugeCard
          variant="memory"
          label="Memory"
          icon={<MemoryStick size={15} className="text-muted" />}
          gaugeValue={m ? m.ram_used / 1024 ** 3 : 0}
          gaugeMax={m ? m.ram_total / 1024 ** 3 : 100}
          active={m ? m.mem_active / 1024 ** 3 : 0}
          inactive={m ? m.mem_inactive / 1024 ** 3 : 0}
          cached={m ? m.mem_cached / 1024 ** 3 : 0}
          swap={m?.swap ?? 0}
          subtext={m ? `${m.ram.toFixed(0)}% terpakai` : "—"}
          onClick={() => setSelectedMetric("memory")}
          statusText={
            (m?.ram ?? 0) >= 90
              ? "High"
              : (m?.ram ?? 0) >= 75
                ? "Elevated"
                : "Normal"
          }
        />
        <GaugeCard
          variant="storage"
          label="Storage"
          icon={<HardDrive size={15} className="text-muted" />}
          gaugeValue={m ? m.disk_used / 1024 ** 3 : 0}
          gaugeMax={m ? m.disk_total / 1024 ** 3 : 100}
          subtext={m ? `${m.disk.toFixed(0)}% terpakai` : "—"}
          onClick={() => setSelectedMetric("storage")}
          statusText={
            (m?.disk ?? 0) >= 90
              ? "High"
              : (m?.disk ?? 0) >= 75
                ? "Watch"
                : "Normal"
          }
        />
        <GaugeCard
          variant="load"
          label="Load Average"
          icon={<Activity size={15} className="text-muted" />}
          gaugeValue={(() => {
            const cores = m?.cpu_cores ?? 1;
            const load = m?.load1 ?? 0;
            return Math.min((load / cores) * 100, 100);
          })()}
          gaugeMax={100}
          gaugeText={`of ${m?.cpu_cores ?? "—"} cores`}
          format={(v) => ((v / 100) * (m?.cpu_cores ?? 1)).toFixed(2)}
          subtext={`1 min · ${m?.cpu_cores ?? "—"} core`}
          onClick={() => setSelectedMetric("load")}
          statusText={(() => {
            const cores = m?.cpu_cores ?? 1;
            const load = m?.load1 ?? 0;
            const pct = (load / cores) * 100;
            if (pct >= 90) return "High";
            if (pct >= 75) return "Elevated";
            return "Normal";
          })()}
        />
      </section>

      <div className="h-4" />

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ConcentricPerformanceMeter
          metrics={m}
          range={range}
          onRangeChange={setRange}
          onSelectMetric={(met) => setSelectedMetric(met)}
          transport={transport}
        />

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Critical Services</div>
              <div className="card-subtitle">systemd services</div>
            </div>
            <a href="/services" className="btn">
              View all
            </a>
          </div>
          <div>
            {criticalServices.map((s) => (
              <div
                key={s.unit}
                className="flex items-center justify-between border-b border-line py-2.5 last:border-b-0"
              >
                <div>
                  <div className="text-[11px] font-bold">{s.name}</div>
                  <div className="mt-0.5 text-[9px] text-muted">
                    {s.description}
                  </div>
                </div>
                <StatusBadge status={s.status} />
              </div>
            ))}
            {criticalServices.length === 0 ? (
              <div className="py-6 text-center text-xs text-muted2">
                No well-known services detected
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <div className="h-4" />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <div className="card sm:col-span-2 lg:col-span-2 xl:col-span-2">
          <div className="card-header">
            <div>
              <div className="card-title">CPU Temperature</div>
              <div className="card-subtitle">
                Live trend · {range === "all" ? "semua buffer" : `terakhir ${range}`}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              {canEditThermal ? (
                <button
                  type="button"
                  onClick={() => setThresholdOpen(true)}
                  className="grid h-[30px] w-[30px] place-items-center rounded-lg border border-line bg-panel2 text-muted transition hover:text-fg"
                  aria-label="Atur thermal thresholds"
                  title="Atur thermal thresholds"
                >
                  <SlidersHorizontal size={14} />
                </button>
              ) : null}
              <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2">
                <Flame size={15} style={{ color: tempStatus.color }} />
              </div>
            </div>
          </div>
          {currentTemp != null ? (
            <>
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-end gap-1">
                    <span
                      className="font-mono text-4xl font-bold leading-none"
                      style={{ color: tempStatus.color }}
                    >
                      {currentTemp.toFixed(1)}
                    </span>
                    <span className="mb-1 text-sm text-muted">°C</span>
                  </div>
                  <div className="mt-1 truncate text-[10px] text-muted">
                    {primarySensor
                      ? `${primarySensor.chip} · ${primarySensor.label}`
                      : "CPU package"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="rounded-full px-2 py-1 text-[10px] font-bold"
                    style={{
                      color: tempStatus.color,
                      backgroundColor: `${tempStatus.color}1a`,
                    }}
                  >
                    {tempStatus.label}
                  </span>
                  <span className="text-[10px] text-muted">
                    Max {maxTemp.toFixed(1)}°C
                  </span>
                </div>
              </div>

              <div className="mt-3 h-[156px] w-full">
                {tempChartData.length > 1 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={tempChartData}
                      margin={{ top: 6, right: 6, bottom: 0, left: -20 }}
                    >
                      <defs>
                        <linearGradient id="tempFill" x1="0" y1="0" x2="0" y2="1">
                          <stop
                            offset="0%"
                            stopColor={tempStatus.color}
                            stopOpacity={0.32}
                          />
                          <stop
                            offset="100%"
                            stopColor={tempStatus.color}
                            stopOpacity={0.02}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="var(--line, #263244)"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="t"
                        tick={{ fontSize: 9, fill: "#8b98a9" }}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={28}
                      />
                      <YAxis
                        domain={[
                          0,
                          Math.max(
                            100,
                            Math.ceil(thresholds.hot + 10),
                            Math.ceil(
                              Math.max(...tempChartData.map((p) => p.temp)) + 5
                            )
                          ),
                        ]}
                        tick={{ fontSize: 9, fill: "#8b98a9" }}
                        tickLine={false}
                        axisLine={false}
                        width={36}
                        tickFormatter={(value) => `${value}°`}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#131a24",
                          border: "1px solid #263244",
                          borderRadius: 10,
                          fontSize: 11,
                        }}
                        labelStyle={{ color: "#8b98a9" }}
                        formatter={(value) => [
                          `${Number(value).toFixed(1)}°C`,
                          "CPU",
                        ]}
                      />
                      <ReferenceLine
                        y={thresholds.warm}
                        stroke="#f59e0b"
                        strokeDasharray="4 4"
                        label={{
                          value: `Warm ${thresholds.warm}°`,
                          fill: "#f59e0b",
                          fontSize: 9,
                          position: "insideTopRight",
                        }}
                      />
                      <ReferenceLine
                        y={thresholds.hot}
                        stroke="#ef4444"
                        strokeDasharray="4 4"
                        label={{
                          value: `Hot ${thresholds.hot}°`,
                          fill: "#ef4444",
                          fontSize: 9,
                          position: "insideBottomRight",
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="temp"
                        stroke={tempStatus.color}
                        strokeWidth={2}
                        fill="url(#tempFill)"
                        dot={false}
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="grid h-full place-items-center rounded-lg border border-dashed border-line text-[10px] text-muted">
                    Menunggu data suhu live…
                  </div>
                )}
              </div>

              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted">
                <span>
                  Sensors {sensors.length} · Max{" "}
                  <span style={{ color: maxTempStatus.color }}>
                    {maxTemp.toFixed(1)}°C
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-warn">Warm ≥ {thresholds.warm}°C</span>
                  <span className="text-bad">Hot ≥ {thresholds.hot}°C</span>
                </span>
              </div>
            </>
          ) : (
            <div className="py-10 text-center text-xs text-muted2">
              No temperature sensors detected
              <div className="mt-1 text-[10px] text-muted">
                VM atau driver sensor tidak tersedia
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Thermal Sensors</div>
              <div className="card-subtitle">Server temperature sources</div>
            </div>
            <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-panel2">
              <Thermometer size={15} className="text-muted" />
            </div>
          </div>
          {orderedSensors.length > 0 ? (
            <>
              <div className="space-y-2.5">
                {orderedSensors.slice(0, 5).map((sensor, index) => {
                  const tone = tempTone(sensor.current, thresholds);
                  const limit = sensor.critical ?? sensor.high ?? 100;
                  return (
                    <div key={`${sensor.chip}-${sensor.label}-${index}`}>
                      <div className="mb-1 flex items-center justify-between gap-2 text-[10px]">
                        <span className="truncate">
                          <span className="font-semibold text-fg">
                            {sensor.label}
                          </span>{" "}
                          <span className="text-muted2">· {sensor.chip}</span>
                        </span>
                        <span
                          className="shrink-0 font-mono font-bold"
                          style={{ color: tone.color }}
                        >
                          {sensor.current.toFixed(1)}°C
                        </span>
                      </div>
                      <div className="progress">
                        <div
                          className={`progress-bar ${tone.bar}`}
                          style={{
                            width: `${Math.min(
                              100,
                              Math.max(0, (sensor.current / limit) * 100)
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              {orderedSensors.length > 5 ? (
                <div className="mt-2 text-[9px] text-muted">
                  +{orderedSensors.length - 5} sensor lainnya
                </div>
              ) : null}
            </>
          ) : (
            <div className="py-10 text-center text-xs text-muted2">
              Tidak ada sensor thermal
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Network</div>
              <div className="card-subtitle">Current traffic</div>
            </div>
            <a href="/network" className="btn">
              Details
            </a>
          </div>
          <div className="grid grid-cols-2 gap-2.5 mb-2.5">
            <div className="info-item">
              <div className="info-label">Interface IP</div>
              <div className="info-value">{info?.primary_ip || "—"}</div>
            </div>
            <div className="info-item">
              <div className="info-label">Hostname</div>
              <div className="info-value truncate">{info?.hostname ?? "—"}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <MiniNetworkGauge variant="download" rate={live?.net_rx_rate ?? 0} />
            <MiniNetworkGauge variant="upload" rate={live?.net_tx_rate ?? 0} />
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Recent Activity</div>
              <div className="card-subtitle">Latest server events</div>
            </div>
            <a href="/logs" className="btn">
              Logs
            </a>
          </div>
          {(logsData?.entries ?? []).slice(0, 4).map((log, i) => (
            <div key={`${log.time}-${i}`} className="mb-3 flex gap-2.5 last:mb-0">
              <div
                className={clsx(
                  "mt-1 h-[7px] w-[7px] shrink-0 rounded-full",
                  log.level === "ERROR" && "bg-bad",
                  log.level === "WARN" && "bg-warn",
                  log.level === "INFO" && "bg-ok"
                )}
              />
              <div>
                <div className="text-[10px] leading-snug">{log.message}</div>
                <div className="mt-0.5 text-[9px] text-muted">
                  {log.time} · {log.source}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <MetricDetailModal
        type={selectedMetric}
        metrics={m}
        systemInfo={info}
        filesystems={fsData?.filesystems}
        onClose={() => setSelectedMetric(null)}
      />

      <ThermalThresholdModal
        open={thresholdOpen}
        initial={thresholds}
        saving={saveThermal.isPending}
        onClose={() => setThresholdOpen(false)}
        onSave={(values) => saveThermal.mutate(values)}
      />
    </>
  );
}
