"use client";

import { useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Cctv,
  Container,
  DatabaseBackup,
  Globe,
  HardDrive,
  LayoutDashboard,
  Layers,
  LogOut,
  MonitorSmartphone,
  Network,
  ScrollText,
  Shield,
  SquareTerminal,
  UserCog,
  Users,
  Wifi,
  Wrench,
} from "lucide-react";
import { api } from "@/lib/api";
import type { PageAccessUser, SystemInfo } from "@/lib/types";
import { useAuth } from "@/store/auth";
import clsx from "clsx";

const NAV = [
  {
    section: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    section: "System",
    items: [
      { href: "/services", label: "Services", icon: Layers },
      { href: "/processes", label: "Processes", icon: Activity },
      { href: "/logs", label: "Logs", icon: ScrollText },
    ],
  },
  {
    section: "Infrastructure",
    items: [
      { href: "/storage", label: "Storage", icon: HardDrive },
      { href: "/network", label: "Network", icon: Network },
      { href: "/access-points", label: "Access Points", icon: Wifi },
      { href: "/websites", label: "Management Website", icon: Globe },
      { href: "/docker", label: "Management Docker", icon: Container },
    ],
  },
  {
    section: "Security",
    items: [
      { href: "/firewall", label: "Firewall", icon: Shield },
      { href: "/users", label: "Users", icon: Users },
      { href: "/terminal", label: "Terminal", icon: SquareTerminal },
    ],
  },
  {
    section: "Operations",
    items: [
      { href: "/backup", label: "Backup", icon: DatabaseBackup },
      { href: "/maintenance", label: "Maintenance", icon: Wrench },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const logout = useAuth((s) => s.logout);
  const user = useAuth((s) => s.user);

  const { data: info } = useQuery({
    queryKey: ["system-info"],
    queryFn: () => api<SystemInfo>("/system/info"),
    staleTime: 60_000,
  });

  const { data: me } = useQuery({
    queryKey: ["auth-me"],
    queryFn: () => api<PageAccessUser>("/auth/me"),
    staleTime: 60_000,
  });

  const hasCctv =
    me?.role === "superadmin" || (me?.page_access ?? []).includes("cctv");

  const nav = useMemo(
    () =>
      NAV.map((group) =>
        group.section === "Infrastructure" && hasCctv
          ? {
              ...group,
              items: [
                ...group.items,
                { href: "/cctv", label: "Management CCTV", icon: Cctv },
              ],
            }
          : group
      ),
    [hasCctv]
  );

  return (
    <aside className="fixed bottom-0 left-0 top-0 z-50 w-[70px] overflow-y-auto border-r border-line bg-sidebar p-3 lg:w-[250px] lg:p-5">
      <div className="flex items-center gap-3 px-1 pb-5 pt-1">
        <div className="grid h-[38px] w-[38px] shrink-0 place-items-center rounded-[10px] bg-accent font-black text-white">
          U
        </div>
        <span className="hidden text-[17px] font-bold lg:inline">
          Server Manager
        </span>
      </div>

      <div className="mb-5 hidden rounded-xl border border-line bg-panel p-3 lg:block">
        <div className="text-[9px] font-bold uppercase tracking-widest text-muted2">
          Active Server
        </div>
        <select
          className="mt-2 w-full rounded-lg border border-line bg-panel2 px-2 py-2 text-xs outline-none"
          value={info?.hostname ?? ""}
          disabled
        >
          <option>{info?.hostname ?? "connecting…"}</option>
        </select>
        <div className="mt-2.5 flex items-center gap-2 text-[11px] text-ok">
          <span className="h-[7px] w-[7px] rounded-full bg-ok shadow-[0_0_8px_#22c55e]" />
          Online
        </div>
      </div>

      <nav>
        {nav.map((group) => (
          <div key={group.section} className="mt-4">
            <div className="hidden px-2.5 pb-2 text-[9px] font-extrabold uppercase tracking-widest text-muted2 lg:block">
              {group.section}
            </div>
            {group.items.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={clsx("nav-item justify-center lg:justify-start", {
                  active: pathname === href,
                })}
                title={label}
              >
                <Icon size={17} strokeWidth={2} />
                <span className="hidden lg:inline">{label}</span>
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <Link
        href="/computer-management"
        className={clsx("nav-item justify-center lg:justify-start", {
          active: pathname === "/computer-management",
        })}
        title="Management Computer"
      >
        <MonitorSmartphone size={17} strokeWidth={2} />
        <span className="hidden lg:inline">Management Computer</span>
      </Link>

      <Link
        href="/user-management"
        className={clsx("nav-item mt-6 justify-center lg:justify-start", {
          active: pathname === "/user-management",
        })}
        title="User Management"
      >
        <UserCog size={17} strokeWidth={2} />
        <span className="hidden lg:inline">User Management</span>
      </Link>

      <button
        onClick={async () => {
          try {
            await api("/auth/logout", { method: "POST" });
          } catch {
            // token lokal tetap dibersihkan walau server gagal dicapai
          }
          logout();
          window.location.href = "/login";
        }}
        className="nav-item justify-center lg:justify-start"
        title={`Logout ${user?.username ?? ""}`}
      >
        <LogOut size={17} />
        <span className="hidden lg:inline">Logout</span>
      </button>
    </aside>
  );
}
