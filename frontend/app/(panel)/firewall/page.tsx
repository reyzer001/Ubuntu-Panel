"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { useConfirm, useToast } from "@/components/providers";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { SortTh, useTableSort } from "@/components/ui/table-sort";
import { api, ApiError } from "@/lib/api";
import type { FirewallRule, FirewallStatus } from "@/lib/types";

export default function FirewallPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm } = useConfirm();
  const [port, setPort] = useState("");
  const [protocol, setProtocol] = useState("tcp");
  const [ruleAction, setRuleAction] = useState("allow");
  const [source, setSource] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["firewall"],
    queryFn: () => api<FirewallStatus>("/firewall"),
  });

  const addRule = useMutation({
    mutationFn: (body: {
      port: string;
      protocol: string;
      action: string;
      source?: string;
    }) =>
      api("/firewall/rules", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      toast.success("Firewall rule added");
      setPort("");
      setSource("");
      queryClient.invalidateQueries({ queryKey: ["firewall"] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.message : "Failed to add rule"),
  });

  const deleteRule = useMutation({
    mutationFn: (vars: { port: string; protocol: string; source?: string }) => {
      const q = vars.source ? `?source=${encodeURIComponent(vars.source)}` : "";
      return api(
        `/firewall/rules/${encodeURIComponent(vars.port)}/${vars.protocol}${q}`,
        { method: "DELETE" }
      );
    },
    onSuccess: () => {
      toast.success("Firewall rule deleted");
      queryClient.invalidateQueries({ queryKey: ["firewall"] });
    },
    onError: (err) =>
      toast.error(
        err instanceof ApiError ? err.message : "Failed to delete rule"
      ),
  });

  const rules = data?.rules ?? [];
  const allowed = rules.filter((r) => r.action === "ALLOW").length;
  const blocked = rules.filter((r) => r.action !== "ALLOW").length;

  const rulesSort = useTableSort(
    rules,
    {
      port: (r) => r.port,
      protocol: (r) => r.protocol,
      action: (r) => r.action,
      from: (r) => r.from,
    },
    "port"
  );

  return (
    <>
      <PageHeader
        title="Firewall"
        subtitle="UFW firewall management"
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ["firewall"] })}
        refreshing={isLoading}
      />

      {!data?.available ? (
        <div className="card mb-4 border-[#6b5620] bg-[#241b09] text-[11px] text-[#ffd58a]">
          {data?.error || "ufw is not available"}
        </div>
      ) : null}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Firewall"
          icon={<span className="text-sm">◈</span>}
          value={data?.enabled ? "ON" : "OFF"}
          valueTone={data?.enabled ? "positive" : "negative"}
          bottomLeft="UFW status"
          bottomRight={
            <span className={data?.enabled ? "text-ok" : "text-bad"}>
              {data?.enabled ? "Protected" : "Disabled"}
            </span>
          }
        />
        <StatCard
          label="Allowed Rules"
          icon={<span className="text-sm">✓</span>}
          value={allowed}
          bottomLeft="Inbound"
        />
        <StatCard
          label="Blocked Rules"
          icon={<span className="text-sm">✕</span>}
          value={blocked}
          bottomLeft="Inbound"
        />
      </section>

      <div className="h-4" />

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Firewall Rules</div>
            <div className="card-subtitle">UFW inbound rules</div>
          </div>
        </div>

        <form
          className="mb-4 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!port.trim()) return;
            addRule.mutate({
              port: port.trim(),
              protocol,
              action: ruleAction,
              source: source.trim(),
            });
          }}
        >
          <input
            className="input w-32"
            placeholder="Port (e.g. 8080)"
            value={port}
            onChange={(e) => setPort(e.target.value)}
          />
          <select
            className="input"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value)}
          >
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
          <select
            className="input"
            value={ruleAction}
            onChange={(e) => setRuleAction(e.target.value)}
          >
            <option value="allow">Allow</option>
            <option value="deny">Deny</option>
          </select>
          <input
            className="input w-48"
            placeholder="Source IP/CIDR (kosong = Anywhere)"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={addRule.isPending || !data?.available}
          >
            + Add Rule
          </button>
        </form>

        <div className="table-wrap overflow-auto">
          <table>
            <thead>
              <tr>
                <SortTh label="Port" k="port" active={rulesSort.key === "port"} dir={rulesSort.dir} onToggle={rulesSort.toggle} />
                <SortTh label="Protocol" k="protocol" active={rulesSort.key === "protocol"} dir={rulesSort.dir} onToggle={rulesSort.toggle} />
                <SortTh label="Action" k="action" active={rulesSort.key === "action"} dir={rulesSort.dir} onToggle={rulesSort.toggle} />
                <SortTh label="Source" k="from" active={rulesSort.key === "from"} dir={rulesSort.dir} onToggle={rulesSort.toggle} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rulesSort.sorted.map((r: FirewallRule, i) => (
                <tr key={`${r.port}-${r.protocol}-${r.from}-${i}`}>
                  <td>
                    <strong>{r.port}</strong>
                  </td>
                  <td>{r.protocol}</td>
                  <td>
                    <StatusBadge
                      status={r.action === "ALLOW" ? "allow" : "deny"}
                    />
                  </td>
                  <td>{r.from}</td>
                  <td>
                    <button
                      className="action-btn"
                      disabled={
                        deleteRule.isPending ||
                        !data?.available ||
                        !/^\d{1,5}$/.test(r.port)
                      }
                      onClick={async () => {
                        if (
                          await confirm({
                            message: `Delete rule ${r.port}/${r.protocol.toLowerCase()}${r.from && r.from !== "Anywhere" ? ` from ${r.from}` : ""}?`,
                            confirmText: "Ya, hapus",
                          })
                        ) {
                          deleteRule.mutate({
                            port: r.port,
                            protocol: r.protocol.toLowerCase(),
                            source:
                              r.from && r.from !== "Anywhere" ? r.from : "",
                          });
                        }
                      }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {rules.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-muted2">
                    No firewall rules
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
