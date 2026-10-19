import ipaddress
import os
import re
import shlex
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

UNIT_RE = re.compile(r"^[A-Za-z0-9@._\-\\x2d]+$")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

SERVICE_ACTIONS = {"start", "stop", "restart", "enable", "disable"}
CONTAINER_ACTIONS = {"start", "stop", "restart"}

_net_prev = {"ts": None, "io": None}
_disk_prev = {"ts": None, "io": None}
_rate_lock = threading.Lock()
# iface -> (ts, rx_bytes, tx_bytes); dipakai bersama WS metrics & REST
_iface_prev: dict[str, tuple[float, int, int]] = {}
_iface_lock = threading.Lock()
# cache hasil rate terakhir agar pembaca REST tidak ikut menggeser baseline
_iface_last: dict[str, dict] = {}
_iface_last_ts: float = 0.0
# seberapa lama cache dianggap segar (detik); WS menick tiap 2 detik
_IFACE_CACHE_TTL = 30.0


def _iface_rates() -> list[dict]:
    """RX/TX rate per interface (bytes/detik) sejak sampel sebelumnya.
    Satu snapshot global agar rate konsisten walau dipanggil dari
    beberapa tempat (WS 2 detik sekali + REST)."""
    with _iface_lock:
        counters = psutil.net_io_counters(pernic=True)
        now = time.time()
        result = []
        for iface, io in counters.items():
            prev = _iface_prev.get(iface)
            rx_rate = tx_rate = 0.0
            if prev and now > prev[0]:
                dt = now - prev[0]
                rx_rate = max(0.0, io.bytes_recv - prev[1]) / dt
                tx_rate = max(0.0, io.bytes_sent - prev[2]) / dt
            result.append(
                {
                    "interface": iface,
                    "rx_rate": round(rx_rate, 1),
                    "tx_rate": round(tx_rate, 1),
                }
            )
        # buang interface yang sudah hilang (mis. veth docker dihapus)
        alive = set(counters)
        for stale in list(_iface_prev):
            if stale not in alive:
                del _iface_prev[stale]
        for r in result:
            io = counters[r["interface"]]
            _iface_prev[r["interface"]] = (now, io.bytes_recv, io.bytes_sent)
        global _iface_last, _iface_last_ts
        _iface_last = {r["interface"]: dict(r) for r in result}
        _iface_last_ts = now
        return result


def peek_iface_rates() -> list[dict]:
    """Rate per interface TANPA menggeser baseline.

    list_interfaces() (REST, dipanggil saat user buka/refresh page)
    tidak boleh memakan baseline milik WS /system/metrics — kalau ikut
    memanggil _iface_rates(), sampelnya selalu berjarak milidetik dari
    tick WS sehingga rx_rate/tx_rate REST selalu ~0.0.
    """
    with _iface_lock:
        fresh = bool(_iface_last) and (time.time() - _iface_last_ts) < _IFACE_CACHE_TTL
        if fresh:
            return [dict(v) for v in _iface_last.values()]
    return _iface_rates()


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


# ---------------------------------------------------------------- metrics

def get_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = os.getloadavg()
    uptime = int(time.time() - psutil.boot_time())

    # kernel/system share of busy CPU time, for the user-vs-system stack
    times = psutil.cpu_times()
    busy_split = times.user + times.system
    cpu_kernel = times.system / busy_split if busy_split > 0 else 0.0

    net = psutil.net_io_counters()
    now = time.time()
    rx_rate = tx_rate = 0.0
    read_rate = write_rate = 0.0
    with _rate_lock:
        if _net_prev["ts"] and now > _net_prev["ts"]:
            dt = now - _net_prev["ts"]
            rx_rate = max(0.0, net.bytes_recv - _net_prev["io"].bytes_recv) / dt
            tx_rate = max(0.0, net.bytes_sent - _net_prev["io"].bytes_sent) / dt
        _net_prev["ts"] = now
        _net_prev["io"] = net

        try:
            dio = psutil.disk_io_counters()
            if dio:
                if _disk_prev["ts"] and now > _disk_prev["ts"]:
                    dt = now - _disk_prev["ts"]
                    read_rate = max(
                        0.0, dio.read_bytes - _disk_prev["io"].read_bytes
                    ) / dt
                    write_rate = max(
                        0.0, dio.write_bytes - _disk_prev["io"].write_bytes
                    ) / dt
                _disk_prev["ts"] = now
                _disk_prev["io"] = dio
        except Exception:
            pass

    procs = psutil.pids()

    return {
        "time": datetime.now().isoformat(timespec="seconds"),
        "cpu": cpu,
        "cpu_kernel": round(cpu_kernel, 4),
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "ram": mem.percent,
        "ram_used": mem.used,
        "ram_total": mem.total,
        "mem_active": mem.active,
        "mem_inactive": mem.inactive,
        "mem_cached": mem.cached + mem.buffers,
        "swap": psutil.swap_memory().percent,
        "disk": disk.percent,
        "disk_used": disk.used,
        "disk_total": disk.total,
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
        "uptime": uptime,
        "process_count": len(procs),
        "net_rx_rate": rx_rate,
        "net_tx_rate": tx_rate,
        "disk_read_rate": read_rate,
        "disk_write_rate": write_rate,
        "net_interfaces": _iface_rates(),
    }


# ---------------------------------------------------------------- system info

def get_system_info() -> dict:
    uname = os.uname()
    os_release = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_release[k] = v.strip('"')
    except OSError:
        pass

    cpu_model = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass

    primary_ip = ""
    try:
        addrs = psutil.net_if_addrs()
        for iface in ("eth0", "ens3", "enp0s3", "ens18"):
            if iface in addrs:
                for a in addrs[iface]:
                    if a.family == socket.AF_INET:
                        primary_ip = a.address
                        break
            if primary_ip:
                break
        if not primary_ip:
            for iface_addrs in addrs.values():
                for a in iface_addrs:
                    if a.family == socket.AF_INET and a.address != "127.0.0.1":
                        primary_ip = a.address
                        break
                if primary_ip:
                    break
    except Exception:
        pass

    return {
        "hostname": uname.nodename,
        "os": os_release.get("PRETTY_NAME", "Unknown"),
        "kernel": uname.release,
        "arch": uname.machine,
        "cpu_model": cpu_model or "Unknown",
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "ram_total": psutil.virtual_memory().total,
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(
            timespec="seconds"
        ),
        "primary_ip": primary_ip,
    }


# ---------------------------------------------------------------- services

def list_services() -> dict:
    units_out = _run(
        [
            "systemctl", "list-units", "--type=service", "--all",
            "--no-pager", "--plain", "--legend=false",
        ]
    )
    files_out = _run(
        [
            "systemctl", "list-unit-files", "--type=service",
            "--no-pager", "--plain", "--legend=false",
        ]
    )

    enabled_map: dict[str, str] = {}
    for line in files_out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(".service"):
            enabled_map[parts[0]] = parts[1]

    services = []
    for line in units_out.stdout.splitlines():
        parts = line.split(maxsplit=4)
        if len(parts) < 4 or not parts[0].endswith(".service"):
            continue
        unit, _load, active, sub = parts[0], parts[1], parts[2], parts[3]
        description = parts[4] if len(parts) == 5 else ""
        status = "running" if active == "active" else "stopped"
        if active == "active" and sub == "exited":
            status = "info"
        services.append(
            {
                "name": unit.removesuffix(".service"),
                "unit": unit,
                "description": description,
                "status": status,
                "enabled": enabled_map.get(unit, "unknown"),
            }
        )
    return {"services": services}


def service_action(name: str, action: str) -> dict:
    if action not in SERVICE_ACTIONS:
        raise ValueError(f"Invalid action '{action}'")
    unit = name if name.endswith(".service") else f"{name}.service"
    if not UNIT_RE.match(unit):
        raise ValueError("Invalid service name")
    proc = _run(["systemctl", action, unit], timeout=30)
    return {
        "success": proc.returncode == 0,
        "output": (proc.stdout or proc.stderr).strip()[:2000],
    }


# ---------------------------------------------------------------- processes

def list_processes(limit: int = 250) -> list[dict]:
    total_mem = psutil.virtual_memory().total
    procs = []
    for p in psutil.process_iter(
        ["pid", "name", "username", "cpu_percent", "memory_info"]
    ):
        try:
            info = p.info
            mem = info["memory_info"].rss if info["memory_info"] else 0
            procs.append(
                {
                    "pid": info["pid"],
                    "user": info["username"] or "?",
                    "name": info["name"] or "?",
                    "cpu": info["cpu_percent"] or 0.0,
                    "memory": mem,
                    "memory_percent": (mem / total_mem * 100) if total_mem else 0.0,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return procs[:limit]


def kill_process(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.kill()
        return {"success": True, "output": f"Killed {name} (PID {pid})"}
    except psutil.NoSuchProcess:
        return {"success": False, "output": f"No process with PID {pid}"}
    except psutil.AccessDenied:
        return {
            "success": False,
            "output": f"Permission denied killing PID {pid} (try running as root)",
        }


# ---------------------------------------------------------------- storage

def list_filesystems() -> list[dict]:
    result = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        inodes_pct = None
        try:
            st = os.statvfs(part.mountpoint)
            if st.f_files > 0:
                inodes_pct = round(
                    (st.f_files - st.f_ffree) / st.f_files * 100, 1
                )
        except OSError:
            pass
        result.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
                "inodes_percent": inodes_pct,
            }
        )
    return result


# ---------------------------------------------------------------- network

def list_interfaces() -> list[dict]:
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    rates = {r["interface"]: r for r in peek_iface_rates()}
    result = []
    for iface, addrs in psutil.net_if_addrs().items():
        ip = mac = ""
        for a in addrs:
            if a.family == socket.AF_INET:
                ip = a.address
            elif a.family == psutil.AF_LINK:
                mac = a.address
        st = stats.get(iface)
        io = counters.get(iface)
        rate = rates.get(iface, {})
        result.append(
            {
                "interface": iface,
                "up": bool(st.isup) if st else False,
                "ip": ip,
                "mac": mac,
                "speed_mbps": st.speed if st else 0,
                "rx_bytes": io.bytes_recv if io else 0,
                "tx_bytes": io.bytes_sent if io else 0,
                "rx_rate": rate.get("rx_rate", 0.0),
                "tx_rate": rate.get("tx_rate", 0.0),
            }
        )
    return result


def list_ports() -> dict:
    listening: dict[tuple, dict] = {}
    established = 0
    try:
        cons = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        cons = []

    pid_names: dict[int, str] = {}
    for c in cons:
        if c.status == psutil.CONN_ESTABLISHED:
            established += 1
        if c.status != psutil.CONN_LISTEN or c.laddr is None:
            continue
        proto = "UDP" if c.type == socket.SOCK_DGRAM else "TCP"
        key = (c.laddr.port, proto, c.laddr.ip)
        if key in listening:
            continue
        pname = "-"
        if c.pid:
            if c.pid not in pid_names:
                try:
                    pid_names[c.pid] = psutil.Process(c.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pid_names[c.pid] = "unknown"
            pname = pid_names[c.pid]
        listening[key] = {
            "port": c.laddr.port,
            "protocol": proto,
            "address": c.laddr.ip,
            "process": pname,
        }

    ports = sorted(listening.values(), key=lambda x: x["port"])
    return {"ports": ports, "established": established}


# ---------------------------------------------------------------- firewall

def ufw_status() -> dict:
    proc = _run(["ufw", "status"])
    if proc.returncode != 0:
        return {
            "available": False,
            "enabled": False,
            "rules": [],
            "error": (proc.stderr or proc.stdout).strip()
            or "ufw not available (run backend as root to manage firewall)",
        }
    enabled = "Status: active" in proc.stdout
    rules = []
    # parse table rows e.g. "22/tcp   ALLOW   Anywhere"
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("ALLOW", "DENY", "REJECT", "LIMIT"):
            port_proto = parts[0]
            port, _, proto = port_proto.partition("/")
            rules.append(
                {
                    "port": port,
                    "protocol": proto.upper() or "ANY",
                    "action": parts[1],
                    "from": parts[2],
                }
            )
    return {"available": True, "enabled": enabled, "rules": rules, "error": ""}


def _validate_firewall_args(port: str, protocol: str, action: str, source: str = "") -> None:
    if not re.match(r"^\d{1,5}(?:-\d{1,5})?$", port):
        raise ValueError("Invalid port")
    if protocol not in ("tcp", "udp"):
        raise ValueError("Protocol must be tcp or udp")
    if action not in ("allow", "deny"):
        raise ValueError("Action must be allow or deny")
    if source:
        try:
            if "/" in source:
                ipaddress.ip_network(source, strict=False)
            else:
                ipaddress.ip_address(source)
        except ValueError:
            raise ValueError(
                "Invalid source (gunakan IP atau CIDR, mis. 192.168.0.0/16)"
            )


def _ufw_argv(action: str, port: str, protocol: str, source: str = "") -> list[str]:
    spec = f"{port}/{protocol}"
    if source:
        return ["ufw", action, "from", source, "to", "any", "port", spec]
    return ["ufw", action, spec]


def ufw_add_rule(port: str, protocol: str, action: str, source: str = "") -> dict:
    _validate_firewall_args(port, protocol, action, source)
    proc = _run(_ufw_argv(action, port, protocol, source), timeout=30)
    return {
        "success": proc.returncode == 0,
        "output": (proc.stdout or proc.stderr).strip()[:2000],
    }


def ufw_delete_rule(port: str, protocol: str, source: str = "") -> dict:
    _validate_firewall_args(port, protocol, "allow", source)
    for action in ("allow", "deny"):
        proc = _run(["ufw", "delete", *_ufw_argv(action, port, protocol, source)], timeout=30)
        if proc.returncode == 0:
            break
    return {
        "success": proc.returncode == 0,
        "output": (proc.stdout or proc.stderr).strip()[:2000],
    }


# ---------------------------------------------------------------- users

def list_users() -> list[dict]:
    import grp

    group_map = {g.gr_gid: g.gr_name for g in grp.getgrall()}
    result = []
    for pw in pwd_all():
        shell = pw.pw_shell
        status = "Active"
        if shell.endswith("nologin") or shell.endswith("false"):
            status = "No login"
        result.append(
            {
                "username": pw.pw_name,
                "uid": pw.pw_uid,
                "group": group_map.get(pw.pw_gid, str(pw.pw_gid)),
                "home": pw.pw_dir,
                "shell": shell,
                "status": status,
            }
        )
    return result


def pwd_all():
    import pwd

    return pwd.getpwall()


def create_user(username: str) -> dict:
    if not USERNAME_RE.match(username):
        raise ValueError(
            "Invalid username (lowercase letters, digits, -, _ only)"
        )
    proc = _run(["useradd", "-m", "-s", "/bin/bash", username], timeout=30)
    return {
        "success": proc.returncode == 0,
        "output": (proc.stderr or proc.stdout).strip()[:2000]
        or f"User {username} created",
    }


def delete_user(username: str) -> dict:
    if not USERNAME_RE.match(username):
        raise ValueError("Invalid username")
    if username in ("root",):
        raise ValueError("Refusing to delete root")
    proc = _run(["userdel", "-r", username], timeout=30)
    return {
        "success": proc.returncode == 0,
        "output": (proc.stderr or proc.stdout).strip()[:2000]
        or f"User {username} deleted",
    }


# ---------------------------------------------------------------- docker

def docker_client():
    import docker

    return docker.from_env()


def list_containers() -> dict:
    try:
        client = docker_client()
    except Exception as exc:
        return {
            "available": False,
            "containers": [],
            "error": f"Docker unavailable: {exc}",
        }

    containers = []
    try:
        for c in client.containers.list(all=True):
            stats = {}
            try:
                stats = c.stats(stream=False)
            except Exception:
                pass
            cpu_pct = "-"
            mem_usage = "-"
            if stats:
                try:
                    cpu_delta = (
                        stats["cpu_stats"]["cpu_usage"]["total_usage"]
                        - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                    )
                    sys_delta = (
                        stats["cpu_stats"]["system_cpu_usage"]
                        - stats["precpu_stats"]["system_cpu_usage"]
                    )
                    online = stats["cpu_stats"].get("online_cpus") or 1
                    if sys_delta > 0:
                        cpu_pct = f"{round(cpu_delta / sys_delta * online * 100, 1)}%"
                    mu = stats["memory_stats"].get("usage", 0)
                    mem_usage = f"{round(mu / 1024 / 1024)} MB" if mu else "-"
                except (KeyError, TypeError, ZeroDivisionError):
                    pass
            ports, host_ports, _port_map = _container_ports(c.attrs)
            containers.append(
                {
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:19],
                    "status": c.status,
                    "cpu": cpu_pct,
                    "memory": mem_usage,
                    "ports": ports,
                    "host_ports": host_ports,
                }
            )
    except Exception as exc:
        return {
            "available": True,
            "containers": [],
            "error": f"Failed listing containers: {exc}",
        }
    return {"available": True, "containers": containers, "error": ""}


def container_action(name: str, action: str) -> dict:
    if action not in CONTAINER_ACTIONS:
        raise ValueError(f"Invalid action '{action}'")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", name):
        raise ValueError("Invalid container name")
    client = docker_client()
    container = client.containers.get(name)
    getattr(container, action)()
    return {"success": True, "output": f"Container {name} {action}ed"}


def parse_port_mappings(ports: str) -> dict:
    port_map = {}
    for part in ports.split(","):
        part = part.strip()
        if not part:
            continue
        proto = "tcp"
        if ":" in part:
            host, _, container = part.partition(":")
        else:
            host, container = "", part
        if "/" in container:
            container, _, proto = container.partition("/")
            if proto not in ("tcp", "udp"):
                raise ValueError(f"Invalid protocol in '{part}'")
        if not host.isdigit() or not container.isdigit():
            raise ValueError(f"Invalid port mapping '{part}' (use HOST:CONTAINER)")
        if not (0 < int(host) < 65536) or not (0 < int(container) < 65536):
            raise ValueError(f"Port out of range in '{part}'")
        port_map[f"{container}/{proto}"] = int(host)
    return port_map


def _container_ports(attrs: dict) -> tuple[str, list[int], list[dict]]:
    """Return (ports string HOST:CONTAINER, host_ports list, detail mapping)."""
    pairs, host_ports, detail = [], [], []
    ns_ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
    for cport in sorted(ns_ports):
        bindings = ns_ports[cport] or []
        cp = cport.replace("/tcp", "")
        if cport.endswith("/udp"):
            cp += "/udp"
        if not bindings:
            pairs.append(cp)
            detail.append({"container": cp, "host_ip": None, "host_port": None})
            continue
        for b in bindings:
            hp = str(b.get("HostPort") or "")
            if hp:
                pairs.append(f"{hp}:{cp}")
                try:
                    host_ports.append(int(hp))
                except ValueError:
                    pass
                detail.append(
                    {"container": cp, "host_ip": b.get("HostIp"), "host_port": int(hp)}
                )
    return ",".join(sorted(set(pairs))) or "-", sorted(set(host_ports)), detail


def container_detail(name: str) -> dict:
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", name):
        raise ValueError("Invalid container name")
    client = docker_client()
    c = client.containers.get(name)
    attrs = c.attrs
    state = attrs.get("State", {})
    ports_str, host_ports, port_map = _container_ports(attrs)

    processes = {"titles": [], "rows": []}
    try:
        top = c.top(ps_args="aux")
        titles = top.get("Titles", [])
        want = ["USER", "PID", "%CPU", "%MEM", "STAT", "START", "TIME", "COMMAND"]
        idx = [i for i, t in enumerate(titles) if t in want]
        sel_titles = [titles[i] for i in idx]
        rows = [
            [(r[i][:70] if i < len(r) else "") for i in idx]
            for r in top.get("Processes", [])[:20]
        ]
        processes = {"titles": sel_titles, "rows": rows}
    except Exception:
        pass

    health = (state.get("Health") or {}).get("Status")
    started_at = state.get("StartedAt") or None
    uptime = None
    if state.get("Running") and started_at:
        try:
            from datetime import timezone

            dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            secs = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins = rem // 60
            uptime = (
                f"{days}d {hours}h {mins}m" if days
                else f"{hours}h {mins}m" if hours
                else f"{mins}m"
            )
        except (ValueError, TypeError):
            pass

    networks = list((attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
    mounts = [
        {"source": m.get("Source", ""), "destination": m.get("Destination", "")}
        for m in attrs.get("Mounts", [])
    ]
    env_keys = [
        e.split("=", 1)[0] for e in (attrs.get("Config", {}).get("Env") or []) if "=" in e
    ]

    return {
        "name": c.name,
        "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:19],
        "status": c.status,
        "health": health,
        "command": " ".join(attrs.get("Config", {}).get("Cmd") or []),
        "entrypoint": " ".join(attrs.get("Config", {}).get("Entrypoint") or []),
        "created": (attrs.get("Created") or "")[:19].replace("T", " "),
        "started_at": (str(started_at)[:19].replace("T", " ")) if started_at else None,
        "uptime": uptime,
        "restart_policy": (attrs.get("HostConfig", {}).get("RestartPolicy") or {}).get(
            "Name", ""
        ),
        "ports": ports_str,
        "host_ports": host_ports,
        "port_map": port_map,
        "processes": processes,
        "networks": networks,
        "mounts": mounts,
        "env_keys": env_keys[:30],
    }


def deploy_container(image: str, name: str = "", ports: str = "") -> dict:
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9/_.:@-]*$", image):
        raise ValueError("Invalid image reference")
    name = name.strip()
    if name and not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", name):
        raise ValueError("Invalid container name")
    port_map = parse_port_mappings(ports) if ports.strip() else {}

    client = docker_client()
    try:
        client.images.pull(image)
    except Exception:
        pass
    kwargs = {"detach": True}
    if name:
        kwargs["name"] = name
    if port_map:
        kwargs["ports"] = port_map
    container = client.containers.run(image, **kwargs)
    return {
        "success": True,
        "output": f"Container {container.name} started from {image}",
    }


def remove_container(name: str, remove_image: bool = False) -> dict:
    """Stop, remove, and optionally delete the image of a container."""
    client = docker_client()
    msgs = []
    img_name = None
    try:
        c = client.containers.get(name)
        img_tags = c.image.tags
        img_name = img_tags[0] if img_tags else str(c.image.id)[:19]
        c.stop(timeout=5)
    except Exception:
        pass
    try:
        c = client.containers.get(name)
        c.remove(force=True)
        msgs.append(f"Container '{name}' removed")
    except Exception:
        msgs.append(f"Container '{name}' not found or already removed")
    if remove_image and img_name:
        try:
            client.images.remove(img_name, force=True)
            msgs.append(f"Image '{img_name}' removed")
        except Exception:
            msgs.append(f"Image '{img_name}' could not be removed (may be used by other containers)")
    return {"success": True, "output": " | ".join(msgs)}


def build_website_image(project_dir: str, dockerfile: str, tag: str) -> dict:
    """Build a website image from a Dockerfile inside its project directory."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+$", tag):
        raise ValueError("Invalid website image tag")
    project = os.path.realpath(project_dir)
    docker_path = os.path.realpath(os.path.join(project, dockerfile))
    if not docker_path.startswith(project + os.sep) or not os.path.isfile(docker_path):
        raise ValueError("Dockerfile tidak ditemukan di folder website")
    client = docker_client()
    client.images.build(
        path=project,
        dockerfile=os.path.relpath(docker_path, project),
        tag=tag,
    )
    return {"success": True, "image": tag, "output": f"Built {tag}"}


# Versi PHP yang disediakan dropdown build website dari 7.0 sampai versi
# terbaru stable yang tersedia di image Docker resmi `php:<versi>-cli`.
SUPPORTED_PHP_VERSIONS: list[str] = [
    "7.0",
    "7.1",
    "7.2",
    "7.3",
    "7.4",
    "8.0",
    "8.1",
    "8.2",
    "8.3",
    "8.4",
    "8.5",
]
LATEST_PHP_VERSION = "8.5"
_PHP_VERSION_RE = re.compile(r"^\d+\.\d+$")


def _php_version_candidates(value: str) -> list[str]:
    """Extract PHP versions like 7.0 or 8.4 from a Composer version constraint."""
    parts: list[str] = []
    if not value:
        return parts
    for m in re.finditer(r"(?:\^|~|>=|>|==|=|<=|<)?\s*(\d+)\.(\d+)", value):
        major, minor = m.groups()
        parts.append(f"{major}.{minor}")
    return parts


def normalize_php_version(version: str) -> str:
    """Validasi & normalisasi versi PHP yang diizinkan di Dockerfile."""
    v = (version or "").strip()
    if v in SUPPORTED_PHP_VERSIONS:
        return v
    if v and _PHP_VERSION_RE.match(v) and v not in SUPPORTED_PHP_VERSIONS:
        raise ValueError(
            f"Versi PHP '{v}' tidak didukung. Pilih dari: {', '.join(SUPPORTED_PHP_VERSIONS)}"
        )
    return ""


def _detect_php_version(project_dir: str) -> str:
    """Detect minimum PHP version from composer.lock or composer.json."""
    import json as _json
    project = os.path.realpath(project_dir)
    # 1) Try composer.lock — scan "require.php" of all packages for highest minimum
    lock = os.path.join(project, "composer.lock")
    if os.path.isfile(lock):
        try:
            data = _json.loads(Path(lock).read_text()[:2_000_000])
            highest = "7.0"
            for pkg in data.get("packages", []) + data.get("packages-dev", []):
                for candidate in _php_version_candidates((pkg.get("require") or {}).get("php", "")):
                    if candidate == "7.0":
                        highest = max(highest, candidate, key=lambda x: tuple(int(p) for p in x.split(".")))
                    elif candidate in SUPPORTED_PHP_VERSIONS:
                        highest = max(highest, candidate, key=lambda x: tuple(int(p) for p in x.split(".")))
            if highest != "7.0":
                return highest
        except Exception:
            pass
    # 2) Fallback to composer.json
    cjson = os.path.join(project, "composer.json")
    if os.path.isfile(cjson):
        try:
            data = _json.loads(Path(cjson).read_text()[:500_000])
            php_req = (data.get("require") or {}).get("php", "")
            candidates = _php_version_candidates(php_req)
            if candidates:
                return max(candidates, key=lambda x: tuple(int(p) for p in x.split(".")))
        except Exception:
            pass
    return LATEST_PHP_VERSION


def detect_project_dependencies(project_dir: str) -> dict:
    """Scan project folder and detect all dependency version requirements.

    Returns a dict with:
    - language: primary language (php, node, python, static)
    - php: { version, composer_version, extensions }
    - node: { version, package_manager, manager_version }
    - python: { version }
    - frameworks: list of detected frameworks
    - services: required services (mysql, postgres, redis, etc.)
    - env_files: list of env files found
    - dockerfile: whether a Dockerfile exists
    """
    import json as _json

    project = os.path.realpath(project_dir)
    result: dict = {
        "language": "static",
        "php": None,
        "node": None,
        "python": None,
        "frameworks": [],
        "services": [],
        "env_files": [],
        "dockerfile": False,
    }

    # check for Dockerfile
    if os.path.isfile(os.path.join(project, "Dockerfile")):
        result["dockerfile"] = True
    if os.path.isfile(os.path.join(project, ".ubuntu-panel.Dockerfile")):
        result["dockerfile"] = True

    # check for env files
    for env_name in [".env", ".env.local", ".env.example", ".env.production"]:
        if os.path.isfile(os.path.join(project, env_name)):
            result["env_files"].append(env_name)

    # ---- PHP / Composer ----
    composer_json = os.path.join(project, "composer.json")
    composer_lock = os.path.join(project, "composer.lock")
    if os.path.isfile(composer_json) or os.path.isfile(composer_lock):
        result["language"] = "php"
        php_info: dict = {"version": "8.1", "extensions": [], "packages": []}

        # detect PHP version from composer.lock
        if os.path.isfile(composer_lock):
            try:
                data = _json.loads(Path(composer_lock).read_text()[:2_000_000])
                highest = "8.1"
                for pkg in data.get("packages", []) + data.get("packages-dev", []):
                    req = (pkg.get("require") or {}).get("php", "")
                    m = re.search(r">=?\s*8\.(\d+)", req)
                    if m:
                        v = f"8.{m.group(1)}"
                        if v > highest:
                            highest = v
                    m2 = re.search(r"\^8\.(\d+)", req)
                    if m2:
                        v = f"8.{m2.group(1)}"
                        if v > highest:
                            highest = v
                php_info["version"] = highest
            except Exception:
                pass

        # fallback to composer.json
        if os.path.isfile(composer_json) and php_info["version"] == "8.1":
            try:
                data = _json.loads(Path(composer_json).read_text()[:500_000])
                php_req = (data.get("require") or {}).get("php", "")
                m = re.search(r"[>=\^]*8\.(\d+)", php_req)
                if m:
                    php_info["version"] = f"8.{m.group(1)}"
            except Exception:
                pass

        # detect extensions from composer.json
        if os.path.isfile(composer_json):
            try:
                data = _json.loads(Path(composer_json).read_text()[:500_000])
                ext_require = data.get("require", {})
                known_exts = [
                    "ext-pdo", "ext-mbstring", "ext-xml", "ext-curl", "ext-json",
                    "ext-gd", "ext-intl", "ext-zip", "ext-bcmath", "ext-tokenizer",
                    "ext-dom", "ext-fileinfo", "ext-openssl", "ext-mysqlnd",
                    "ext-pgsql", "ext-sqlite3", "ext-redis", "ext-memcached",
                ]
                for ext in known_exts:
                    if ext in ext_require:
                        php_info["extensions"].append(ext.replace("ext-", ""))

                # get key packages
                packages = data.get("require", {})
                skip = {"php", "ext-*"}
                for pkg_name in packages:
                    if any(pkg_name.startswith(s.replace("*", "")) for s in skip):
                        continue
                    if not pkg_name.startswith("ext-"):
                        php_info["packages"].append(pkg_name)
                php_info["packages"] = php_info["packages"][:20]  # limit
            except Exception:
                pass

        result["php"] = php_info

        # detect frameworks
        if os.path.isfile(composer_json):
            try:
                data = _json.loads(Path(composer_json).read_text()[:500_000])
                pkgs = {**data.get("require", {}), **data.get("require-dev", {})}
                if "laravel/framework" in pkgs:
                    result["frameworks"].append("Laravel")
                if "symfony/symfony" in pkgs or "symfony/framework-bundle" in pkgs:
                    result["frameworks"].append("Symfony")
                if "drupal/core" in pkgs:
                    result["frameworks"].append("Drupal")
                if "wordpress" in str(data.get("name", "")).lower():
                    result["frameworks"].append("WordPress")
                if "illuminate/support" in pkgs:
                    result["frameworks"].append("Laravel (illuminate)")
            except Exception:
                pass

    # ---- Node.js / npm / yarn / pnpm ----
    package_json = os.path.join(project, "package.json")
    nvmrc = os.path.join(project, ".nvmrc")
    node_version_file = os.path.join(project, ".node-version")
    if os.path.isfile(package_json):
        result["language"] = "node" if result["language"] == "static" else result["language"]
        node_info: dict = {"version": None, "package_manager": "npm", "manager_version": None}

        # detect node version from .nvmrc / .node-version
        for vf in [nvmrc, node_version_file]:
            if os.path.isfile(vf):
                try:
                    v = Path(vf).read_text().strip().lstrip("v")
                    if v:
                        node_info["version"] = v
                        break
                except Exception:
                    pass

        # detect package manager
        if os.path.isfile(os.path.join(project, "yarn.lock")):
            node_info["package_manager"] = "yarn"
        elif os.path.isfile(os.path.join(project, "pnpm-lock.yaml")):
            node_info["package_manager"] = "pnpm"
        elif os.path.isfile(os.path.join(project, "bun.lockb")):
            node_info["package_manager"] = "bun"

        # detect node engine from package.json
        try:
            data = _json.loads(Path(package_json).read_text()[:2_000_000])
            engines = data.get("engines", {})
            if "node" in engines:
                node_info["version"] = engines["node"]
            if node_info["package_manager"] == "npm" and "npm" in engines:
                node_info["manager_version"] = engines["npm"]

            # detect frameworks
            all_deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            if "next" in all_deps:
                result["frameworks"].append(f"Next.js {all_deps['next']}")
            if "nuxt" in all_deps or "@nuxt/kit" in all_deps:
                result["frameworks"].append(f"Nuxt {all_deps.get('nuxt', '')}")
            if "react" in all_deps:
                result["frameworks"].append(f"React {all_deps['react']}")
            if "vue" in all_deps:
                result["frameworks"].append(f"Vue {all_deps['vue']}")
            if "@angular/core" in all_deps:
                result["frameworks"].append(f"Angular {all_deps['@angular/core']}")
            if "svelte" in all_deps:
                result["frameworks"].append(f"Svelte {all_deps['svelte']}")
            if "vite" in all_deps:
                result["frameworks"].append(f"Vite {all_deps['vite']}")
            if "typescript" in all_deps:
                result["frameworks"].append(f"TypeScript {all_deps['typescript']}")
            if "express" in all_deps:
                result["frameworks"].append(f"Express {all_deps['express']}")
            if "nestjs/core" in all_deps:
                result["frameworks"].append(f"NestJS {all_deps['nestjs/core']}")
            if "laravel-vite-plugin" in all_deps:
                result["frameworks"].append("Laravel Vite")
            if "tailwindcss" in all_deps:
                result["frameworks"].append(f"Tailwind CSS {all_deps['tailwindcss']}")
        except Exception:
            pass

        result["node"] = node_info

    # ---- Python ----
    requirements_txt = os.path.join(project, "requirements.txt")
    pyproject_toml = os.path.join(project, "pyproject.toml")
    python_version_file = os.path.join(project, ".python-version")
    setup_py = os.path.join(project, "setup.py")
    if any(os.path.isfile(f) for f in [requirements_txt, pyproject_toml, setup_py]):
        result["language"] = "python" if result["language"] == "static" else result["language"]
        python_info: dict = {"version": None, "packages": []}

        # detect python version from .python-version
        if os.path.isfile(python_version_file):
            try:
                v = Path(python_version_file).read_text().strip()
                if v:
                    python_info["version"] = v
            except Exception:
                pass

        # detect from pyproject.toml
        if os.path.isfile(pyproject_toml):
            try:
                content = Path(pyproject_toml).read_text()[:500_000]
                # python version
                m = re.search(r'requires-python\s*=\s*"[>=<>*]([^"]+)"', content)
                if m:
                    python_info["version"] = m.group(1)
                # frameworks
                if "django" in content.lower():
                    result["frameworks"].append("Django")
                if "flask" in content.lower():
                    result["frameworks"].append("Flask")
                if "fastapi" in content.lower():
                    result["frameworks"].append("FastAPI")
            except Exception:
                pass

        # read requirements.txt for packages
        if os.path.isfile(requirements_txt):
            try:
                lines = Path(requirements_txt).read_text()[:100_000].splitlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        pkg = re.split(r"[>=<~!]", line)[0].strip()
                        if pkg:
                            python_info["packages"].append(pkg)
                python_info["packages"] = python_info["packages"][:30]
            except Exception:
                pass

        # detect frameworks from requirements
        pkgs_lower = " ".join(python_info["packages"]).lower()
        if "django" in pkgs_lower:
            result["frameworks"].append("Django")
        if "flask" in pkgs_lower:
            result["frameworks"].append("Flask")
        if "fastapi" in pkgs_lower:
            result["frameworks"].append("FastAPI")
        if "uvicorn" in pkgs_lower:
            result["frameworks"].append("Uvicorn")

        result["python"] = python_info

    # ---- Detect services from env/config ----
    # scan .env files for database/redis/etc
    env_content = ""
    for env_name in [".env", ".env.example", ".env.local"]:
        env_path = os.path.join(project, env_name)
        if os.path.isfile(env_path):
            try:
                env_content += Path(env_path).read_text()[:50_000] + "\n"
            except Exception:
                pass

    env_upper = env_content.upper()
    if "MYSQL" in env_upper or "DB_CONNECTION=mysql" in env_upper:
        result["services"].append("MySQL")
    if "POSTGRES" in env_upper or "DB_CONNECTION=pgsql" in env_upper:
        result["services"].append("PostgreSQL")
    if "REDIS" in env_upper:
        result["services"].append("Redis")
    if "MEMCACHED" in env_upper:
        result["services"].append("Memcached")
    if "MONGO" in env_upper:
        result["services"].append("MongoDB")
    if "MAIL_HOST" in env_upper or "SMTP" in env_upper:
        result["services"].append("SMTP/Mail")

    # detect from docker-compose
    for dc_name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
        dc_path = os.path.join(project, dc_name)
        if os.path.isfile(dc_path):
            try:
                dc_content = Path(dc_path).read_text()[:100_000].lower()
                if "mysql" in dc_content:
                    result["services"].append("MySQL")
                if "postgres" in dc_content:
                    result["services"].append("PostgreSQL")
                if "redis" in dc_content:
                    result["services"].append("Redis")
                if "mongo" in dc_content:
                    result["services"].append("MongoDB")
                if "memcached" in dc_content:
                    result["services"].append("Memcached")
            except Exception:
                pass

    # deduplicate services
    result["services"] = list(dict.fromkeys(result["services"]))

    return result


def ensure_website_dockerfile(project_dir: str, php_version: str = "") -> str:
    """Create a conservative template only when a project has no Dockerfile."""
    project = os.path.realpath(project_dir)
    target = os.path.join(project, ".ubuntu-panel.Dockerfile")
    if os.path.isfile(os.path.join(project, "Dockerfile")):
        return "Dockerfile"
    if os.path.isfile(os.path.join(project, "composer.json")):
        # hanya pakai versi yang di daftar SUPPORTED_PHP_VERSIONS (tag docker
        # resmi ada) agar build tak gagal; selain itu detect lalu fallback aman.
        try:
            version = normalize_php_version(php_version) or _detect_php_version(
                project_dir
            )
        except ValueError:
            version = _detect_php_version(project_dir)
        if version not in SUPPORTED_PHP_VERSIONS:
            version = LATEST_PHP_VERSION
        content = (
            f"FROM php:{version}-cli\n"
            "COPY --from=composer:2 /usr/bin/composer /usr/bin/composer\n"
            "WORKDIR /app\nCOPY . .\n"
            "RUN composer install --no-interaction --no-dev\n"
            "EXPOSE 8000\n"
            'CMD ["php", "artisan", "serve", "--host=0.0.0.0", "--port=8000"]\n'
        )
    elif os.path.isfile(os.path.join(project, "package.json")):
        content = (
            "FROM node:22-alpine\nWORKDIR /app\nCOPY package*.json ./\n"
            "RUN npm install\nCOPY . .\nEXPOSE 3000\n"
            'CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]\n'
        )
    elif os.path.isfile(os.path.join(project, "requirements.txt")):
        content = (
            "FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt ./\n"
            "RUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\n"
            "EXPOSE 8000\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n"
        )
    else:
        content = "FROM nginx:alpine\nCOPY . /usr/share/nginx/html\nEXPOSE 80\n"
    Path(target).write_text(content, encoding="utf-8")
    return ".ubuntu-panel.Dockerfile"


def run_website_image(image: str, name: str, host_port: int, container_port: int = 8000) -> dict:
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9_.-]+$", image):
        raise ValueError("Invalid website image")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", name):
        raise ValueError("Invalid website container name")
    if not (1 <= host_port <= 65535 and 1 <= container_port <= 65535):
        raise ValueError("Invalid website port")
    client = docker_client()
    try:
        old = client.containers.get(name)
        old.remove(force=True)
    except Exception:
        pass
    container = client.containers.run(
        image,
        name=name,
        detach=True,
        ports={f"{container_port}/tcp": host_port},
    )
    container.reload()
    return {
        "success": True,
        "container": container.name,
        "pid": (container.attrs.get("State") or {}).get("Pid"),
        "host_port": host_port,
    }


def sync_folder_to_container(
    folder_path: str, container_name: str, label: str = ""
) -> dict:
    """Copy all files from a host folder into a running Docker container.

    Uses docker cp to sync the folder contents to /app/<label> inside the container.
    If label is empty, files go to /app/ directly.
    """
    folder = os.path.realpath(folder_path)
    if not os.path.isdir(folder):
        raise ValueError(f"Folder tidak ada: {folder}")

    label = label.strip()
    if label and not re.match(r"^[A-Za-z0-9._-]+$", label):
        raise ValueError(
            "Invalid label (hanya huruf, angka, titik, strip, underscore)"
        )

    client = docker_client()
    try:
        container = client.containers.get(container_name)
    except Exception:
        raise ValueError(f"Container '{container_name}' tidak ditemukan")

    if container.status != "running":
        raise ValueError(f"Container '{container_name}' tidak berjalan")

    # tentukan target di dalam container
    target = f"/app/{label}" if label else "/app"

    # pastikan target path ada di dalam container
    try:
        container.exec_run(["mkdir", "-p", target])
    except Exception:
        pass

    # copy folder contents ke container
    # docker cp tidak bisa langsung copy directory contents ke path yang sudah ada
    # jadi kita copy ke temporary lalu mv
    tmp = f"/tmp/_sync_{label or 'app'}"
    try:
        container.exec_run(["rm", "-rf", tmp])
    except Exception:
        pass

    # copy ke target menggunakan docker cp
    try:
        # docker cp lebih reliable daripada tar stream
        result = subprocess.run(
            ["docker", "cp", f"{folder}/.", f"{container_name}:{target}"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0 and result.stderr.strip():
            raise RuntimeError(result.stderr.strip())

        file_count = sum(1 for _ in Path(folder).rglob("*") if _.is_file())
        return {
            "success": True,
            "files_synced": file_count,
            "target": target,
            "output": f"Synced {file_count} files to {target}",
        }
    except Exception as exc:
        raise RuntimeError(f"Sync gagal: {exc}")


# ---------------------------------------------------------------- logs

_PRIORITY = {0: "ERROR", 1: "ERROR", 2: "ERROR", 3: "ERROR", 4: "WARN"}


def read_logs(lines: int = 200, level: str = "ALL") -> list[dict]:
    lines = max(20, min(lines, 2000))
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "-o", "json"]
    if level == "ERROR":
        cmd += ["-p", "err"]
    elif level == "WARN":
        cmd += ["-p", "warning"]

    proc = _run(cmd, timeout=25)
    entries = []
    for raw in proc.stdout.splitlines():
        try:
            import json

            item = json.loads(raw)
        except (ValueError, ImportError):
            continue
        ts = int(item.get("__REALTIME_TIMESTAMP", 0)) / 1_000_000
        priority = int(item.get("PRIORITY", 6))
        lvl = _PRIORITY.get(priority, "INFO")
        source = item.get("SYSLOG_IDENTIFIER") or item.get("_COMM") or "kernel"
        message = item.get("MESSAGE", "")
        if isinstance(message, list):
            message = bytes(message).decode(errors="replace")
        entries.append(
            {
                "time": datetime.fromtimestamp(ts).strftime("%H:%M:%S"),
                "level": lvl,
                "source": source,
                "message": str(message)[:500],
            }
        )
    entries.reverse()
    return entries


# ---------------------------------------------------------------- terminal

_VIRTUAL_IFACE_RE = re.compile(
    r"^(lo$|docker|br-|veth|virbr|tailscale|ts\d|wg\d|tun\d|tap\d|zt|nordlynx|ppp)"
)
_PING_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def lan_interface() -> str:
    """Interface LAN fisik (bukan lo/tailscale/docker) — dipakai untuk ping."""
    try:
        proc = _run(["ip", "route", "show", "default"], timeout=5)
        m = re.search(r"\bdev\s+(\S+)", proc.stdout)
        if m and not _VIRTUAL_IFACE_RE.match(m.group(1)):
            return m.group(1)
    except Exception:
        pass
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    for name in sorted(addrs):
        if _VIRTUAL_IFACE_RE.match(name):
            continue
        st = stats.get(name)
        if not st or not st.isup:
            continue
        if any(a.family == socket.AF_INET for a in addrs[name]):
            return name
    return "eth0"


def _terminal_ping(cmd: str) -> dict:
    args = cmd.split()[1:]
    target = ""
    count = 4
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-c":
            try:
                count = int(args[i + 1])
            except (IndexError, ValueError):
                raise ValueError("Invalid -c value")
            i += 2
            continue
        if arg.startswith("-"):
            raise ValueError(f"Unknown option '{arg}'")
        if not target:
            target = arg
        else:
            try:
                count = int(arg)
            except ValueError:
                raise ValueError("Usage: ping <host/ip> [count]")
        i += 1
    if not target:
        raise ValueError("Usage: ping <host/ip> [count]")
    if not _PING_HOST_RE.match(target):
        raise ValueError("Invalid ping target")
    count = max(1, min(count, 10))

    iface = lan_interface()
    try:
        proc = _run(["ping", "-c", str(count), "-I", iface, target], timeout=count * 3 + 5)
    except subprocess.TimeoutExpired:
        proc = None
    out = ((proc.stdout if proc else "") + "\n" + (proc.stderr if proc else "")).strip()
    header = f"via {iface} ({next((a.address for n, i in psutil.net_if_addrs().items() if n == iface for a in i if a.family == socket.AF_INET), '?')})"
    return {"output": f"{header}\n{out}"}


def terminal_exec(command: str) -> dict:
    cmd = command.strip()
    if not cmd:
        raise ValueError("Empty command")

    if cmd == "help":
        return {
            "output": "\n".join(
                [
                    "Allowed commands:",
                    "  uptime           server uptime",
                    "  free -h          memory usage",
                    "  df -h            disk usage",
                    "  ping <host> [n]  ping via interface LAN (bukan Tailscale/docker)",
                    "  docker ps        running containers",
                    "  systemctl status critical services",
                    "  ps               top processes by CPU",
                ]
            )
        }

    if cmd == "uptime":
        m = get_metrics()
        days, rem = divmod(m["uptime"], 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        return {
            "output": (
                f" up {days} days, {hours}:{minutes:02d}, "
                f"load average: {m['load1']}, {m['load5']}, {m['load15']}"
            )
        }

    if cmd == "free -h":
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        h = lambda b: f"{b / 1024**3:.1f}G"
        return {
            "output": (
                f"Mem: {h(mem.total)} total / {h(mem.used)} used / {h(mem.available)} free\n"
                f"Swap: {h(swap.total)} total / {h(swap.used)} used"
            )
        }

    if cmd == "df -h":
        rows = ["Filesystem      Size  Used  Use%  Mounted"]
        for fs in list_filesystems():
            size = fs["total"] / 1024**3
            used = fs["used"] / 1024**3
            unit = "T" if size >= 1024 else "G"
            scale = 1024 if size >= 1024 else 1
            rows.append(
                f"{fs['device']:<15} {size / scale:.0f}{unit}   "
                f"{used / scale:.0f}{unit}   {fs['percent']}%   {fs['mountpoint']}"
            )
        return {"output": "\n".join(rows)}

    if cmd == "docker ps":
        data = list_containers()
        if not data["available"]:
            return {"output": data["error"]}
        if not data["containers"]:
            return {"output": "No running containers"}
        return {
            "output": "\n".join(
                f"{c['name']:<20} {c['image']:<30} {c['status']}"
                for c in data["containers"]
            )
        }

    if cmd == "systemctl status":
        data = list_services()
        critical = [
            s
            for s in data["services"]
            if any(k in s["name"] for k in ("nginx", "ssh", "docker", "postgres", "mysql", "redis"))
        ]
        if not critical:
            return {"output": "No well-known services found"}
        return {
            "output": "\n".join(
                f"{s['unit']:<28} {s['status']}" for s in critical
            )
        }

    if cmd == "ps":
        rows = ["  PID USER      CPU%  MEM  NAME"]
        for p in list_processes(limit=10):
            rows.append(
                f"{p['pid']:>5} {p['user']:<9} {p['cpu']:>4.1f}  "
                f"{round(p['memory'] / 1024**2):>4}M  {p['name']}"
            )
        return {"output": "\n".join(rows)}

    if cmd == "ping" or cmd.startswith("ping "):
        return _terminal_ping(cmd)

    raise ValueError(
        f"Command not allowed: '{cmd}'. Type 'help' for allowed commands."
    )


def website_terminal_exec(command: str, cwd: str) -> dict:
    """Run approved project commands without invoking a shell."""
    project = os.path.realpath(cwd)
    if not os.path.isdir(project):
        raise ValueError("Folder website tidak ditemukan")
    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise ValueError("Command tidak valid") from exc
    if not args or len(args) > 10:
        raise ValueError("Command tidak valid")
    allowed = {"pwd", "ls", "php", "composer", "node", "npm", "python", "docker"}
    if args[0] not in allowed:
        raise ValueError(f"Command tidak diizinkan: {args[0]}")
    subargs = args[1:]
    if args[0] == "ls" and any(arg not in ("-la", "-l", ".") for arg in subargs):
        raise ValueError("ls hanya boleh membaca folder website")
    if args[0] in {"php", "python"} and subargs and subargs[0] not in (
        "--version", "-v", "-V", "artisan", "manage.py",
    ):
        raise ValueError("Gunakan php artisan atau python manage.py")
    if args[0] == "composer" and subargs and subargs[0] not in (
        "--version", "-v", "install", "update", "dump-autoload",
    ):
        raise ValueError("Composer command tidak diizinkan")
    if args[0] == "npm" and subargs and subargs[0] not in (
        "--version", "-v", "install", "ci", "run",
    ):
        raise ValueError("NPM command tidak diizinkan")
    if args[0] == "node" and subargs not in (["--version"], ["-v"]):
        raise ValueError("Node hanya boleh memeriksa versi")
    if args[0] == "docker" and subargs[:1] not in (["--version"], ["-v"], ["ps"], ["compose"]):
        raise ValueError("Docker command tidak diizinkan")
    if any(arg in {";", "&&", "||", "|", ">", ">>"} for arg in args):
        raise ValueError("Shell operator tidak diizinkan")
    proc = subprocess.run(args, cwd=project, capture_output=True, text=True, timeout=15)
    output = (proc.stdout + proc.stderr).strip()
    return {"output": output or f"exit code {proc.returncode}", "returncode": proc.returncode}
