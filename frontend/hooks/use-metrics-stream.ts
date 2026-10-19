"use client";

import { useEffect, useRef, useState } from "react";
import { api, directWsUrl, USE_PROXY, wsUrl } from "@/lib/api";
import type { HistoryPoint, Metrics } from "@/lib/types";
import { useAuth } from "@/store/auth";

const MAX_POINTS = 150;
const POLL_MS = 2000;
const WS_OPEN_TIMEOUT_MS = 5000;
const WS_RETRY_MS = 3000;
const WS_REPROBE_MS = 30000;

export type MetricsTransport = "ws" | "polling" | "offline";

export function useMetricsStream() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [connected, setConnected] = useState(false);
  const [transport, setTransport] = useState<MetricsTransport>("offline");
  const token = useAuth((s) => s.token);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!token) return;
    let closed = false;
    let ws: WebSocket | null = null;
    let openTimer: ReturnType<typeof setTimeout> | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let reprobeTimer: ReturnType<typeof setTimeout> | null = null;
    // indeks kandidat URL berikutnya; bertambah tiap gagal tanpa frame
    let urlIdx = 0;
    // jumlah kandidat yang gagal beruntun tanpa satu frame pun
    let framelessFails = 0;

    const candidates = () => {
      const list = [wsUrl("/ws/metrics")];
      // Next.js rewrites tidak meneruskan upgrade WebSocket, jadi
      // kandidat same-origin selalu gagal saat USE_PROXY=1.
      if (USE_PROXY) list.push(directWsUrl("/ws/metrics"));
      // buang duplikat (abaikan query token saat bandingkan)
      return list.filter(
        (u, i) =>
          list.findIndex((v) => v.split("?")[0] === u.split("?")[0]) === i
      );
    };

    const handleFrame = (data: Metrics) => {
      if (closed) return;
      setMetrics(data);
      setHistory((prev) =>
        [
          ...prev,
          {
            t: data.time,
            cpu: data.cpu,
            ram: data.ram,
            rx: data.net_rx_rate,
            tx: data.net_tx_rate,
          },
        ].slice(-MAX_POINTS)
      );
      setConnected(true);
    };

    const clearTimers = () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      if (openTimer) clearTimeout(openTimer);
      if (reprobeTimer) clearTimeout(reprobeTimer);
      retryRef.current = openTimer = reprobeTimer = null;
    };

    const stopPolling = () => {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
    };

    const schedule = (fn: () => void, ms: number) => {
      if (closed) return;
      retryRef.current = setTimeout(fn, ms);
    };

    // Fallback HTTP polling bila WS tidak bisa dipakai sama sekali
    // (mis. port backend tak terjangkau browser). REST /system/metrics
    // lewat proxy HTTP Next.js yang memang berfungsi.
    const startPolling = () => {
      if (closed) return;
      setTransport("polling");
      if (!pollTimer) {
        const tick = async () => {
          if (closed) return;
          try {
            const data = await api<Metrics>("/system/metrics");
            setTransport("polling");
            handleFrame(data);
          } catch {
            // biarkan polling jalan; api() sudah menangani 401 (logout)
          }
        };
        tick();
        pollTimer = setInterval(tick, POLL_MS);
      }
      // sesekali coba naik kelas lagi ke WS
      if (!reprobeTimer) {
        reprobeTimer = setTimeout(() => {
          reprobeTimer = null;
          if (!closed) connect();
        }, WS_REPROBE_MS);
      }
    };

    const connect = () => {
      if (closed) return;
      const urls = candidates();
      // token bisa refresh — bangun ulang URL tiap percobaan
      const url = urls[urlIdx % urls.length];
      let gotFrame = false;

      const onFramelessFail = () => {
        if (gotFrame || closed) return;
        framelessFails += 1;
        urlIdx += 1;
        const total = candidates().length;
        if (framelessFails >= total && total > 0) {
          // semua kandidat WS mati — turun ke polling, coba WS lagi nanti
          framelessFails = 0;
          startPolling();
        } else {
          schedule(connect, WS_RETRY_MS);
        }
      };

      try {
        ws = new WebSocket(url);
      } catch {
        onFramelessFail();
        return;
      }

      openTimer = setTimeout(() => {
        // server tak menjawab — anggap kandidat ini mati
        try {
          ws?.close();
        } catch {
          // abaikan
        }
      }, WS_OPEN_TIMEOUT_MS);

      ws.onopen = () => {
        if (closed) {
          ws?.close();
          return;
        }
        // jangan klaim connected sebelum frame pertama tiba
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string) as Metrics;
          if (!gotFrame) {
            gotFrame = true;
            framelessFails = 0;
            urlIdx = 0;
            stopPolling();
            setTransport("ws");
            if (openTimer) clearTimeout(openTimer);
          }
          handleFrame(data);
        } catch {
          // ignore malformed frame
        }
      };

      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          // abaikan
        }
      };

      ws.onclose = () => {
        if (openTimer) clearTimeout(openTimer);
        setConnected(false);
        if (closed) return;
        if (gotFrame) {
          // WS sempat hidup — coba sambung lagi dari kandidat pertama
          urlIdx = 0;
          framelessFails = 0;
          schedule(connect, WS_RETRY_MS);
        } else {
          onFramelessFail();
        }
      };
    };

    connect();

    return () => {
      closed = true;
      clearTimers();
      stopPolling();
      try {
        ws?.close();
      } catch {
        // abaikan
      }
      ws = null;
    };
  }, [token]);

  return { metrics, history, connected, transport };
}
