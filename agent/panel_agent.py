#!/usr/bin/env python3
"""
Panel Agent — Ubuntu Server Manager
====================================
App pendukung "Menagement Computer". Dijalankan di PC klien (Windows/
Linux/macOS), mengirim heartbeat berkala ke server panel berisi:

  - nama perangkat (hostname)
  - IP address tiap interface + MAC address
  - OS / versi agent
  - CPU & RAM usage (opsional, jika psutil tersedia)
  - status internet (uji ICMP ke 1.1.1.1) + latency HTTP ke server

Hanya butuh Python 3.8+ TANPA dependensi tambahan (psutil opsional).
Dapat dibuild jadi 1 file exe/binary (PyInstaller) agar PC klien tanpa Python.

Konfigurasi (pilih salah satu):
  a. argumen : python panel_agent.py --server http://IP-SERVER:8000 --token pca_xxx
  b. file    : letakkan agent.ini di SEBELAH program (lihat agent.ini.example):
                 [agent]
                 server   = http://IP-SERVER:8000
                 token    = pca_xxxxxxxx
                 interval = 10

Fitur:
  - heartbeat tiap 10s (ping PC→server, server juga membalas ping ke PC)
  - deteksi jalur koneksi: LAN atau WIFI (+ nama SSID & IP wifi)
    - menerima perintah remote restart / shutdown / update dari panel

Sekali klik + hidup lagi setiap boot:
   Cukup dobel-klik — tanpa flag apa pun. Agent mendaftar otomatis (MAC
   address), memasang autostart TANPA hak admin, lalu berjalan di background:

     Windows : dobel-klik panel_agent.py / panel-agent.exe
               → console menutup sendiri, proses lanjut via pythonw
                 registry HKCU\\...\\Run → jalan otomatis tiap login
               → MODE ADMIN: jalankan sekali "sebagai administrator"
                 lalu --setup — autostart pindah ke Task Scheduler
                 (/RL HIGHEST) sehingga agent berjalan dengan hak admin
                 otomatis tiap boot, dan siap untuk perintah berhak tinggi.
     Linux   : ./panel-agent
               → systemd --user + linger (jalan saat boot),
                 fallback ~/.config/autostart (jalan saat login)

   Flag opsional: --setup (pasang ulang manual), --visible (Windows:
   tetap tampilkan console), --uninstall (cabut total).

  Build exe tunggal:
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name panel-agent agent/panel_agent.py

Bersih total:
  <program> --uninstall  → hapus autostart + salinan program;
  hapus file aslinya = tidak ada sisa apa pun.
"""

import argparse
import configparser
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
import threading
from typing import List, Optional, Set, Tuple
import urllib.error
import urllib.request
import uuid

AGENT_VERSION = "1.5.1"
SERVICE_NAME = "panel-agent"
OFFICE_SERVER = "http://192.168.11.126:8000"
DISCOVERY_PORT = 8001
DISCOVERY_MAGIC = b"PANEL_DISCOVERY"
DISCOVERY_RESPONSE_PREFIX = b"PANEL_SERVER|"

# Alamat server yang ditanam OTOMATIS (tidak perlu diketik manual):
#  - PANEL_SERVER_INJECTED diisi saat script diunduh dari panel
#  - PANEL_SERVER_EMBEDDED dibuat oleh build-exe saat compile exe/binary
PANEL_SERVER_INJECTED = OFFICE_SERVER
try:
    import _build_config as _bc

    PANEL_SERVER_EMBEDDED = str(getattr(_bc, "SERVER", "") or "")
except ImportError:
    PANEL_SERVER_EMBEDDED = ""

# latency pengukuran loop sebelumnya (dikirim ulang di heartbeat berikutnya,
# karena latency baru diketahui SETELAH server membalas)
_last_latency: Optional[float] = None
# kode HTTP heartbeat terakhir (401 → token invalid → auto re-register)
_last_hb_status: Optional[int] = None
_speed_lock = threading.Lock()
_speed_result = {"download_mbps": None, "upload_mbps": None, "speed_test_at": ""}
_speed_started = False
_printer_cache: dict = {"at": 0.0, "data": []}


# --------------------------------------------------------------- lokasi & config

CONFIG_NAME = "agent.ini"
LOG_NAME = "panel-agent.log"


def is_frozen() -> bool:
    """True bila berjalan sebagai exe/binary hasil build PyInstaller."""
    return getattr(sys, "frozen", False)


def app_base_dir() -> str:
    """Folder tempat program ini berada (bukan folder ekstraksi sementara)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(".")


def program_path() -> str:
    if is_frozen():
        return os.path.abspath(sys.executable)
    if "__file__" in globals():
        return os.path.abspath(__file__)
    if hasattr(sys, "argv") and sys.argv and sys.argv[0] not in ("-", "-c", ""):
        return os.path.abspath(sys.argv[0])
    return ""


def config_path() -> str:
    return os.path.join(app_base_dir(), CONFIG_NAME)


def load_config() -> dict:
    """Baca agent.ini di samping program → {server, token, interval} (string)."""
    vals = {"server": "", "token": "", "interval": ""}
    cp = configparser.ConfigParser()
    try:
        cp.read(config_path(), encoding="utf-8")
    except configparser.Error:
        return vals
    if not cp.has_section("agent"):
        return vals
    for key in vals:
        vals[key] = str(cp.get("agent", key, fallback="")).strip()
    return vals


def save_config(server: str, token: str, interval: int) -> None:
    """Simpan agent.ini di samping program (gagal diam bila folder read-only)."""
    cp = configparser.ConfigParser()
    cp["agent"] = {
        "server": server,
        "token": token,
        "interval": str(interval),
    }
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            cp.write(f)
    except OSError as exc:
        print(f"[warn] tidak bisa menulis {config_path()} ({exc}) — "
              "config hanya berlaku untuk sesi ini")


def pause_exit(message: str, code: int) -> int:
    """Tampilkan pesan fatal + tahan jendela agar tidak tertutup sendiri."""
    print(f"\n{message}")
    try:
        input("Tekan Enter untuk keluar…")
    except Exception:
        pass          # tanpa konsol (--noconsole) — pesan sudah ke file log
    return code


def ensure_output() -> None:
    """exe --noconsole tidak punya stdout/stderr — arahkan ke file log di
    sebelah program agar status heartbeat tetap bisa diperiksa."""
    if sys.stdout is None or sys.stderr is None:
        try:
            f = open(os.path.join(app_base_dir(), LOG_NAME), "a", buffering=1)
            sys.stdout = sys.stderr = f
        except OSError:
            pass


# ------------------------------------------------------------ pengumpulan data

_last_cpu_times: Optional[Tuple[float, float]] = None


def primary_ip() -> str:
    """Fallback IP lokal dari interface yang dipakai menuju internet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def public_ip() -> str:
    """Ambil IP publik IPv4 yang terlihat dari internet.

    Nilai ini sengaja dipisahkan dari daftar interface lokal. Jika semua
    layanan gagal, kembalikan kosong dan jangan memakai IP lokal sebagai
    pengganti.
    """
    services = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    )
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Ubuntu-Panel-Agent"})
            with urllib.request.urlopen(req, timeout=5) as res:
                candidate = res.read().decode("ascii", errors="ignore").strip()
            address = ipaddress.ip_address(candidate)
            if address.version == 4 and address.is_global:
                return str(address)
        except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError):
            continue
    return ""


def get_cpu_percent() -> Optional[float]:
    """CPU usage percentage (0-100%). Zero-dependency fallback untuk Linux & Windows."""
    global _last_cpu_times
    try:
        import psutil  # type: ignore
        return psutil.cpu_percent(interval=None)
    except ImportError:
        pass

    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = [float(x) for x in line.split()[1:]]
            idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)
            total = sum(parts)
            if _last_cpu_times is not None:
                last_idle, last_total = _last_cpu_times
                idle_delta = idle - last_idle
                total_delta = total - last_total
                _last_cpu_times = (idle, total)
                if total_delta > 0:
                    pct = round(100.0 * (1.0 - (idle_delta / total_delta)), 1)
                    return max(0.0, min(100.0, pct))
            _last_cpu_times = (idle, total)
            try:
                with open("/proc/loadavg", "r") as f:
                    load = float(f.read().split()[0])
                cpu_count = os.cpu_count() or 1
                return round(min(100.0, (load / cpu_count) * 100.0), 1)
            except Exception:
                return None
        except Exception:
            return None
    elif system == "Windows":
        try:
            import ctypes
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]
            def _to_i(ft):
                return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            idle_ft, kern_ft, user_ft = FILETIME(), FILETIME(), FILETIME()
            if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle_ft), ctypes.byref(kern_ft), ctypes.byref(user_ft)):
                idle, kern, user = _to_i(idle_ft), _to_i(kern_ft), _to_i(user_ft)
                total = kern + user
                if _last_cpu_times is not None:
                    last_idle, last_total = _last_cpu_times
                    idle_delta = idle - last_idle
                    total_delta = total - last_total
                    _last_cpu_times = (idle, total)
                    if total_delta > 0:
                        pct = round(100.0 * (1.0 - (idle_delta / total_delta)), 1)
                        return max(0.0, min(100.0, pct))
                _last_cpu_times = (idle, total)
        except Exception:
            pass
    return None


def get_mem_percent() -> Optional[float]:
    """RAM usage percentage (0-100%). Zero-dependency fallback untuk Linux & Windows."""
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().percent
    except ImportError:
        pass

    system = platform.system()
    if system == "Linux":
        try:
            with open("/proc/meminfo", "r") as f:
                content = f.read()
            total = avail = 0
            for line in content.splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1])
            if total > 0:
                if avail == 0:
                    for line in content.splitlines():
                        if line.startswith("MemFree:"):
                            avail = int(line.split()[1])
                return round((1.0 - (avail / total)) * 100.0, 1)
        except Exception:
            pass
    elif system == "Windows":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("sullAvailExtendedVirtual", ctypes.c_uint64),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return float(stat.dwMemoryLoad)
        except Exception:
            pass
    return None


def collect_interfaces() -> List[dict]:
    """Daftar interface: {name, ip, mac}. Menggunakan psutil jika ada, atau fallback OS native."""
    out: List[dict] = []
    try:
        import psutil  # type: ignore

        af_link = getattr(psutil, "AF_LINK", -1)
        for name, addrs in psutil.net_if_addrs().items():
            mac = next(
                (a.address for a in addrs if a.family == af_link and a.address), ""
            )
            ip = next(
                (
                    a.address
                    for a in addrs
                    if a.family == socket.AF_INET and not a.address.startswith("127.")
                ),
                "",
            )
            if name == "lo":
                continue
            out.append({"name": name, "ip": ip, "mac": mac})
        if out:
            return out
    except ImportError:
        pass

    # fallback Linux native (/sys/class/net)
    system = platform.system()
    if system == "Linux":
        net_dir = "/sys/class/net"
        if os.path.exists(net_dir):
            for iface in sorted(os.listdir(net_dir)):
                if iface == "lo":
                    continue
                mac = ""
                mac_path = os.path.join(net_dir, iface, "address")
                if os.path.exists(mac_path):
                    try:
                        with open(mac_path) as f:
                            mac = f.read().strip()
                    except Exception:
                        pass
                ip = ""
                try:
                    out_ip = subprocess.check_output(
                        ["ip", "-4", "addr", "show", iface],
                        text=True, timeout=2,
                    )
                    m = re.search(r"inet\s+([0-9.]+)", out_ip)
                    if m:
                        ip = m.group(1)
                except Exception:
                    pass
                out.append({"name": iface, "ip": ip, "mac": mac})
            if out:
                return out

    # fallback Windows native (ipconfig)
    if system == "Windows":
        try:
            r = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True, text=True, timeout=8,
                creationflags=0x08000000,
            )
            current_adapter = current_mac = current_ip = ""
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.endswith(":") and not line.startswith("Physical") and not line.startswith("IPv4") and not line.startswith("Description"):
                    if current_adapter and (current_ip or current_mac):
                        out.append({"name": current_adapter, "ip": current_ip, "mac": current_mac})
                    current_adapter = line.rstrip(":")
                    current_mac = current_ip = ""
                elif "Physical Address" in line or "Alamat Fisik" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        current_mac = parts[1].strip().replace("-", ":").lower()
                elif "IPv4 Address" in line or "Alamat IPv4" in line:
                    m = re.search(r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", line)
                    if m:
                        current_ip = m.group(1)
            if current_adapter and (current_ip or current_mac):
                out.append({"name": current_adapter, "ip": current_ip, "mac": current_mac})
            if out:
                return out
        except Exception:
            pass

    # fallback stdlib: satu MAC global dari uuid
    node = uuid.getnode()
    mac = ":".join(f"{(node >> i) & 0xFF:02x}" for i in range(40, -1, -8))
    if mac == "00:00:00:00:00:00":  # random MAC sementara
        mac = ""
    out.append({"name": "default", "ip": primary_ip(), "mac": mac})
    return out


def check_internet() -> Optional[bool]:
    """Uji internet lewat koneksi TCP — andal di semua OS.

    CATATAN BUG LAMA: versi lama mencoba `ping -c ...` (format Linux)
    lebih dulu; di Windows ping tetap ADA tapi menolak opsi `-c`, dan
    fungsi langsung `return False` tanpa mencoba format Windows —
    akibatnya status internet selalu OFFLINE padahal browsing lancar.
    Kini memakai TCP connect ke DNS publik (jalur yang sama seperti
    browsing), ping OS-native hanya sebagai cadangan.
    """
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 53)):
        try:
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            return True
        except OSError:
            continue
    win = platform.system() == "Windows"
    cmd = ["ping", "-n", "1", "-w", "2000", "1.1.1.1"] if win else \
          ["ping", "-c", "1", "-W", "2", "1.1.1.1"]
    try:
        return subprocess.run(
            cmd, capture_output=True, timeout=5,
            creationflags=(0x08000000 if win else 0),
        ).returncode == 0
    except Exception:
        return None


def is_service_mode() -> bool:
    """True bila berjalan sebagai service/boot (bukan dobel-klik interaktif).

    Service = exe frozen, background pythonw (PANEL_AGENT_HIDDEN), atau
    dipanggil Task Scheduler / systemd. Mode ini TIDAK BOLEH exit sendiri
    (pause_exit) — harus retry selamanya sampai network/server online.
    """
    if is_frozen():
        return True
    if os.environ.get("PANEL_AGENT_HIDDEN") == "1":
        return True
    if os.environ.get("PANEL_AGENT_SERVICE") == "1":
        return True
    return False


def wait_for_network_online(max_wait: int = 300, step: int = 5) -> bool:
    """Tunggu sampai internet/network online (untuk boot yang network telat).

    Dipakai sebelum register/discover pertama + saat fail beruntun di
    run_loop. Return True bila online, False bila timeout. Tidak pernah
    raise — aman dipanggil dari service.
    """
    deadline = time.monotonic() + max(5, max_wait)
    waited = 0
    while time.monotonic() < deadline:
        try:
            if check_internet():
                if waited > 0:
                    print(f"[net] online setelah ~{waited}s — lanjut")
                return True
        except Exception:
            pass
        time.sleep(step)
        waited += step
        if waited % 30 == 0:
            print(f"[net] menunggu jaringan… ({waited}s)")
    return False


def _speed_test_worker(server: str, token: str) -> None:
    """Ukur throughput ke server tanpa menahan heartbeat berikutnya."""
    global _speed_result
    try:
        started = time.monotonic()
        req = urllib.request.Request(
            server.rstrip("/") + "/api/computers/speed-test?bytes=262144",
            headers={"X-Agent-Token": token},
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            res.read()
        elapsed = max(time.monotonic() - started, 0.001)
        download = round((262144 * 8 / elapsed) / 1_000_000, 2)
        started = time.monotonic()
        upload_request = urllib.request.Request(
            server.rstrip("/") + "/api/computers/speed-test",
            data=b"0" * 262144,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Agent-Token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(upload_request, timeout=8) as res:
            res.read()
        elapsed = max(time.monotonic() - started, 0.001)
        upload = round((262144 * 8 / elapsed) / 1_000_000, 2)
        with _speed_lock:
            _speed_result = {
                "download_mbps": download,
                "upload_mbps": upload,
                "speed_test_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        pass


def get_speed_result(server: str, token: str) -> dict:
    global _speed_started
    with _speed_lock:
        result = dict(_speed_result)
        should_start = not _speed_started
        if result["speed_test_at"]:
            try:
                should_start = time.time() - time.mktime(time.strptime(result["speed_test_at"], "%Y-%m-%dT%H:%M:%S")) > 900
            except ValueError:
                should_start = True
        if should_start:
            _speed_started = True
            threading.Thread(target=_speed_test_worker, args=(server, token), daemon=True).start()
    return result


# ------------------------------------------------------- deteksi LAN / WIFI

def _default_iface_linux() -> str:
    """Interface dengan default route (dari /proc/net/route)."""
    try:
        with open("/proc/net/route", encoding="ascii") as f:
            for line in f.read().splitlines()[1:]:
                parts = line.split()
                if len(parts) > 3 and parts[1] == "00000000":
                    flags = int(parts[3], 16)
                    if flags & 0x2:          # RTF_GATEWAY
                        return parts[0]
    except OSError:
        pass
    return ""


def _is_wireless_linux(iface: str) -> bool:
    if not iface:
        return False
    if os.path.isdir(f"/sys/class/net/{iface}/wireless"):
        return True
    try:
        with open("/proc/net/wireless", encoding="ascii") as f:
            return any(line.startswith(iface + ":") for line in f.read().splitlines()[2:])
    except OSError:
        return False


def _ssid_linux(iface: str) -> str:
    """SSID via iwgetid, fallback `iw dev <iface> link`."""
    try:
        r = subprocess.run(["iwgetid", iface, "-r"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:64]
    except Exception:
        pass
    try:
        r = subprocess.run(["iw", "dev", iface, "link"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("ssid:"):
                return line.split(":", 1)[1].strip()[:64]
    except Exception:
        pass
    return ""

def _default_gateway(iface: str = "") -> str:
    """Ambil gateway default, yaitu kandidat IP access point WiFi."""
    system = platform.system()
    if system == "Windows":
        try:
            r = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=8,
                creationflags=0x08000000,
            )
            for line in r.stdout.splitlines():
                if "Default Gateway" not in line and "Gateway Default" not in line:
                    continue
                value = line.split(":", 1)[-1].strip()
                if value and "." in value:
                    return value
        except Exception:
            pass
        return ""

    commands = [["ip", "route", "show", "default"]]
    if system == "Darwin":
        commands = [["route", "-n", "get", "default"]]
    for command in commands:
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                parts = line.split()
                if system == "Darwin" and len(parts) >= 2 and parts[0] == "gateway:":
                    return parts[1]
                if len(parts) >= 3 and parts[0] == "default" and parts[1] == "via":
                    if not iface or ("dev" in parts and parts[parts.index("dev") + 1] == iface):
                        return parts[2]
        except Exception:
            pass
    return ""


def _wifi_bssid(iface: str = "") -> str:
    """Ambil BSSID radio AP yang sedang dipakai, bukan gateway jaringan."""
    system = platform.system()
    if system == "Windows":
        command = ["netsh", "wlan", "show", "interfaces"]
    elif system == "Darwin":
        command = ["/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport", "-I"]
    else:
        command = ["iw", "dev", iface, "link"] if iface else []
    if not command:
        return ""
    try:
        r = subprocess.run(
            command, capture_output=True, text=True, timeout=8,
            creationflags=(0x08000000 if system == "Windows" else 0),
        )
        match = re.search(
            r"(?im)^\s*(?:BSSID|Access\s+Point)\s*:\s*"
            r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b|"
            r"^\s*Connected\s+to\s+"
            r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})\b",
            r.stdout,
        )
        return next((group.lower() for group in match.groups() if group), "") if match else ""
    except Exception:
        return ""


def _detect_windows_wifi() -> Tuple[bool, str]:
    """(connected?, ssid) dari netsh wlan show interfaces."""
    try:
        r = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000,
        )
        state = ssid = ""
        for raw in r.stdout.splitlines():
            if ":" not in raw:
                continue
            key, val = raw.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "state":
                state = val.lower()
            elif key == "ssid" and "bssid" not in key:
                ssid = val
        if state in ("connected", "terhubung") and ssid:
            return True, ssid[:64]
    except Exception:
        pass
    return False, ""


def collect_local_arp() -> List[dict]:
    """Kumpulkan tabel ARP lokal (IP -> MAC) dari sistem operasi klien."""
    arp_entries: List[dict] = []
    seen: Set[str] = set()
    system = platform.system()

    if system == "Linux":
        try:
            with open("/proc/net/arp", "r", encoding="ascii") as f:
                for line in f.read().splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip = parts[0]
                        mac = parts[3].lower()
                        if mac != "00:00:00:00:00:00" and re.fullmatch(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", mac):
                            if ip not in seen:
                                seen.add(ip)
                                arp_entries.append({"ip": ip, "mac": mac.replace("-", ":")})
        except Exception:
            pass
        if not arp_entries:
            try:
                out = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=3).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and "lladdr" in parts:
                        i = parts.index("lladdr")
                        if i + 1 < len(parts):
                            ip, mac = parts[0], parts[i + 1].lower()
                            if ip not in seen and mac != "00:00:00:00:00:00":
                                seen.add(ip)
                                arp_entries.append({"ip": ip, "mac": mac.replace("-", ":")})
            except Exception:
                pass

    elif system == "Windows":
        try:
            r = subprocess.run(
                ["arp", "-a"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000,
            )
            for line in r.stdout.splitlines():
                m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})", line)
                if m:
                    ip = m.group(1)
                    mac = m.group(2).lower().replace("-", ":")
                    if mac not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") and not ip.endswith(".255"):
                        if ip not in seen:
                            seen.add(ip)
                            arp_entries.append({"ip": ip, "mac": mac})
        except Exception:
            pass

    elif system == "Darwin":
        try:
            r = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                m = re.search(r"\((\d{1,3}(?:\.\d{1,3}){3})\)\s+at\s+([0-9a-fA-F:]{17})", line)
                if m:
                    ip = m.group(1)
                    mac = m.group(2).lower()
                    if mac != "ff:ff:ff:ff:ff:ff" and ip not in seen:
                        seen.add(ip)
                        arp_entries.append({"ip": ip, "mac": mac})
        except Exception:
            pass

    return arp_entries[:64]


# --------------------------------------------------------------- printer (share)

def _parse_printers_json(out: str) -> List[dict]:
    """Normalisasi output Get-Printer | ConvertTo-Json (objek atau array)."""
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    printers: List[dict] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name", "") or "").strip()
        if not name:
            continue
        share = str(item.get("ShareName", "") or "").strip()
        shared = bool(item.get("Shared")) and bool(share)
        printers.append({
            "name": name[:128],
            "share_name": share[:128],
            "shared": shared,
            "driver": str(item.get("DriverName", "") or "")[:160],
            "port": str(item.get("PortName", "") or "")[:160],
            "platform": "windows",
        })
    return printers


def _collect_printers_windows() -> List[dict]:
    script = (
        "Get-Printer | Select-Object Name,ShareName,Shared,DriverName,PortName "
        "| ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=20,
            creationflags=0x08000000,
        )
        return _parse_printers_json(r.stdout.strip())
    except Exception:
        return []


def _collect_printers_unix() -> List[dict]:
    printers: List[dict] = []
    seen: Set[str] = set()
    try:
        r = subprocess.run(["lpstat", "-v"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            m = re.match(r"device for (.+?):\s*(.*)", line)
            if not m:
                continue
            name = m.group(1).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            printers.append({
                "name": name[:128],
                "share_name": name[:128],
                "shared": True,
                "driver": "",
                "port": m.group(2).strip()[:160],
                "platform": platform.system().lower(),
            })
    except Exception:
        pass
    return printers


def collect_printers(force: bool = False) -> List[dict]:
    """Daftar printer lokal + status share (untuk dilaporkan ke panel).

    Hasil di-cache ~60s: enumerasi printer (PowerShell di Windows) terlalu
    berat untuk dijalankan tiap heartbeat 10s.
    """
    now = time.monotonic()
    if not force and _printer_cache["data"] and now - _printer_cache["at"] < 60:
        return _printer_cache["data"]
    system = platform.system()
    if system == "Windows":
        data = _collect_printers_windows()
    elif system in ("Linux", "Darwin"):
        data = _collect_printers_unix()
    else:
        data = []
    _printer_cache["at"] = now
    _printer_cache["data"] = data
    return data


def _sanitize_share_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", (name or "").strip()).strip("_")
    return s[:80] or "printer"


def _run_capture(cmd: List[str], timeout: int = 30) -> Tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip() + (
            ("\n" + r.stderr.strip()) if r.stderr and r.stderr.strip() else ""
        )
    except Exception as exc:      # noqa: BLE001
        return 1, str(exc)[:200]


LEGACY_CLEANUP_DIRS_WINDOWS = (
    r"C:\nodelete",
    "%LOCALAPPDATA%\\PanelAgent",
    "%LOCALAPPDATA%\\panel-agent",
)


def do_cleanup_nodelete() -> str:
    """Hapus sisa rollout lama (C:\\nodelete + varian user-mode legacy).

    Whitelist absolut — tidak ada parameter path dari server. Tidak pernah
    menyentuh %ProgramData%\\PanelAgent yang aktif. Bila proses ini sendiri
    masih jalan dari C:\\nodelete, di-SKIP aman (update agent dulu).
    Kembalikan string pendek untuk ACK (muat last_cmd_result 160 char).
    """
    if platform.system() != "Windows":
        return "SKIP: bukan Windows"
    try:
        running = (program_path() or "").lower()
    except Exception:
        running = ""
    norm_running = running.replace("/", "\\")
    if norm_running.startswith("c:\\nodelete"):
        return "SKIP: masih jalan dari C:\\nodelete — update agent dulu"
    removed_dirs = 0
    removed_files = 0
    locked: List[str] = []
    targets: List[str] = [r"C:\nodelete"]
    for raw in ("%LOCALAPPDATA%\\PanelAgent", "%LOCALAPPDATA%\\panel-agent"):
        expanded = os.path.expandvars(raw)
        if "%" not in expanded:
            targets.append(expanded)
    # Jangan hapus folder instalasi aktif walau namanya mirip.
    try:
        active = os.path.abspath(install_dir()).lower()
    except Exception:
        active = ""
    for path in targets:
        try:
            apath = os.path.abspath(path)
        except Exception:
            continue
        if not apath or apath.lower() == active:
            continue
        if not os.path.exists(apath):
            continue
        # Hitung file dulu untuk laporan.
        try:
            for _root, _dirs, files in os.walk(apath):
                removed_files += len(files)
        except OSError:
            pass
        ok = True
        for _i in range(3):
            try:
                attrib = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                      "System32", "attrib.exe")
                subprocess.run([attrib, "-h", "-s", "-r", apath, "/s", "/d"],
                               capture_output=True, timeout=30,
                               creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
            try:
                shutil.rmtree(apath, ignore_errors=False)
                break
            except OSError:
                ok = False
                time.sleep(2)
        if os.path.exists(apath):
            locked.append(apath)
        elif ok:
            removed_dirs += 1
    try:
        win_common_startup_clear()
    except Exception:
        pass
    if locked:
        return f"GAGAL: terkunci {locked[0][:60]} — reboot lalu ulangi"[:160]
    if removed_dirs == 0:
        return "OK: tidak ada sisa C:\\nodelete (sudah bersih)"
    return f"OK: {removed_dirs} folder, ~{removed_files} file legacy terhapus"[:160]


def set_printer_shared(name: str, shared: bool) -> Tuple[bool, str]:
    """Aktif/nonaktifkan share printer lokal. Windows butuh hak admin."""
    name = (name or "").strip()
    if not name:
        return False, "nama printer kosong"
    _printer_cache["at"] = 0.0        # paksa enumerasi ulang di heartbeat berikutnya
    system = platform.system()
    if system == "Windows":
        if not shared:
            script = (
                f"$p = Get-Printer -Name '{name}' -ErrorAction Stop; "
                "Set-Printer -Name $p.Name -Shared $false; "
                "Write-Output 'OK'"
            )
        else:
            share = _sanitize_share_name(name)
            # guest/no-password access: aktifkan akun Guest, beri Everyone
            # full access pada share, dan matikan password-protected sharing
            # agar PC lain di LAN bisa menambah printer tanpa kredensial.
            script = (
                f"$p = Get-Printer -Name '{name}' -ErrorAction Stop; "
                f"Set-Printer -Name $p.Name -Shared $true -ShareName '{share}'; "
                "Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' "
                "-ErrorAction SilentlyContinue "
                "| Set-NetFirewallRule -Enabled True -Profile Any "
                "-ErrorAction SilentlyContinue; "
                "net user guest /active:yes; "
                f"Grant-SmbShareAccess -Name '{share}' -AccountName Everyone "
                "-AccessRight Full -Force -ErrorAction SilentlyContinue; "
                "New-ItemProperty -Path "
                "'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters' "
                "-Name 'restrictnullsessaccess' -Value 0 -PropertyType DWord "
                "-Force -ErrorAction SilentlyContinue; "
                "New-ItemProperty -Path "
                "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa' "
                "-Name 'EveryoneIncludesAnonymous' -Value 1 -PropertyType DWord "
                "-Force -ErrorAction SilentlyContinue; "
                f"Write-Output 'OK::{share}'"
            )
        code, out = _run_capture(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", script], timeout=60,
        )
        if code == 0 and "OK" in out:
            share = out.split("::", 1)[1].strip() if "::" in out else ""
            label = "share aktif" + (f" sebagai '{share}'" if share else "")
            return True, label
        return False, out or "gagal mengubah share printer"
    # Linux/CUPS: aktifkan queue + bagikan via CUPS
    if not shared:
        code, out = _run_capture(["lpadmin", "-p", name, "-o", "printer-is-shared=false"])
        return (code == 0), (out or "share dinonaktifkan")
    code, out = _run_capture(["lpadmin", "-p", name, "-E", "-o", "printer-is-shared=true"])
    return (code == 0), (out or "share diaktifkan")


def check_smb_open() -> Optional[bool]:
    """Cek cepat apakah SMB/file-sharing terbuka (untuk badge panel).

    Windows: firewall 'File and Printer Sharing' enabled ATAU port 445
    listen. Linux: cups aktif. None bila tidak dapat ditentukan.
    """
    system = platform.system()
    if system == "Windows":
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' "
                 "-ErrorAction SilentlyContinue | "
                 "Where-Object { $_.Enabled -eq 'True' } | "
                 "Select-Object -First 1 | ForEach-Object { $_.Enabled }"],
                capture_output=True, text=True, timeout=15,
                creationflags=CREATE_NO_WINDOW,
            )
            if "True" in (r.stdout or ""):
                return True
        except Exception:
            pass
        try:
            s = socket.create_connection(("127.0.0.1", 445), timeout=2)
            s.close()
            return True
        except OSError:
            pass
        return False
    if system == "Linux":
        try:
            r = subprocess.run(["systemctl", "is-active", "cups"],
                               capture_output=True, text=True, timeout=5)
            if r.stdout.strip() == "active":
                return True
        except Exception:
            pass
        return False
    return None


def ensure_smb_open() -> Tuple[bool, str]:
    """Buka SMB/file-sharing otomatis agar \\\\IP\\printer bisa diakses guest.

    Idempotent + silent: aman dipanggil tiap boot / tiap jam dari
    ensure_autostart. Windows butuh hak admin/SYSTEM — user biasa di-skip
    diam (return False). Linux best-effort (CUPS share + port 631).
    """
    system = platform.system()
    if system == "Windows":
        if not is_elevated_windows():
            return False, "butuh admin (skip, coba lagi saat SYSTEM)"
        script = (
            "Set-Service LanmanServer -StartupType Automatic "
            "-ErrorAction SilentlyContinue; "
            "Start-Service LanmanServer -ErrorAction SilentlyContinue; "
            "Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' "
            "-ErrorAction SilentlyContinue "
            "| Set-NetFirewallRule -Enabled True -Profile Any "
            "-ErrorAction SilentlyContinue; "
            "net user guest /active:yes; "
            "New-ItemProperty -Path "
            "'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\LanmanServer\\Parameters' "
            "-Name 'restrictnullsessaccess' -Value 0 -PropertyType DWord "
            "-Force -ErrorAction SilentlyContinue; "
            "New-ItemProperty -Path "
            "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa' "
            "-Name 'EveryoneIncludesAnonymous' -Value 1 -PropertyType DWord "
            "-Force -ErrorAction SilentlyContinue; "
            "Set-SmbServerConfiguration -AutoShareServer $true "
            "-Force -ErrorAction SilentlyContinue; "
            "Write-Output 'OK'"
        )
        code, out = _run_capture(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", script], timeout=60,
        )
        if code == 0 and "OK" in out:
            # Re-apply Everyone Full ke share printer yang pernah ada agar
            # tahan reboot / update Windows.
            try:
                for p in collect_printers(force=True):
                    if p.get("shared") and p.get("share_name"):
                        _run_capture(
                            ["powershell", "-NoProfile", "-ExecutionPolicy",
                             "Bypass", "-Command",
                             f"Grant-SmbShareAccess -Name '{p['share_name']}' "
                             "-AccountName Everyone -AccessRight Full -Force "
                             "-ErrorAction SilentlyContinue"],
                            timeout=30,
                        )
            except Exception:
                pass
            return True, "SMB terbuka (firewall+guest+LanmanServer)"
        return False, (out or "gagal membuka SMB")[:120]
    if system == "Linux":
        ok_any = False
        for cmd in (
            ["cupsctl", "--share-printers"],
            ["ufw", "allow", "631/tcp"],
        ):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=15)
                if r.returncode == 0:
                    ok_any = True
            except Exception:
                pass
        try:
            r = subprocess.run(["systemctl", "enable", "--now", "cups-browsed"],
                               capture_output=True, timeout=20)
            if r.returncode == 0:
                ok_any = True
        except Exception:
            pass
        return ok_any, "CUPS share diaktifkan" if ok_any else "gagal (butuh root?)"
    return False, "platform tidak didukung"


def detect_connection(interfaces: List[dict], arp_table: Optional[List[dict]] = None) -> dict:
    """Jalur koneksi utama → {conn_type, ssid, iface_name, wifi_ip, ap_ip, ap_mac}.

    WIFI  : default route lewat interface wireless — kirim SSID + BSSID radio.
    LAN   : kabel / lainnya.
    """
    system = platform.system()
    arp = arp_table or []

    def _find_ap_ip_from_bssid(bssid: str) -> str:
        if not bssid:
            return ""
        # 1. Exact match
        for entry in arp:
            if entry.get("mac", "").lower() == bssid.lower():
                return entry.get("ip", "")
        # 2. Prefix 5 octet match (radio vs ethernet MAC pada vendor AP yang sama)
        if len(bssid) >= 14:
            prefix = bssid[:14].lower()
            for entry in arp:
                if entry.get("mac", "").lower()[:14] == prefix:
                    return entry.get("ip", "")
        return ""

    if system == "Windows":
        connected, ssid = _detect_windows_wifi()
        if connected:
            wifi_ip = ""
            for i in interfaces:
                if i["ip"] and i["name"].lower() not in ("lo", "loopback"):
                    wifi_ip = wifi_ip or i["ip"]
            bssid = _wifi_bssid()
            ap_ip = _find_ap_ip_from_bssid(bssid)
            return {"conn_type": "WIFI", "ssid": ssid,
                    "iface_name": "Wi-Fi", "wifi_ip": wifi_ip,
                    "ap_ip": ap_ip, "ap_mac": bssid}
        main = next((i for i in interfaces if i["ip"]), {})
        return {"conn_type": "LAN", "ssid": "",
                "iface_name": main.get("name", ""), "wifi_ip": "", "ap_ip": "", "ap_mac": ""}

    if system == "Linux":
        iface = _default_iface_linux()
        if _is_wireless_linux(iface):
            ip = next((i["ip"] for i in interfaces if i["name"] == iface), "")
            bssid = _wifi_bssid(iface)
            ap_ip = _find_ap_ip_from_bssid(bssid)
            return {"conn_type": "WIFI", "ssid": _ssid_linux(iface),
                    "iface_name": iface, "wifi_ip": ip,
                    "ap_ip": ap_ip, "ap_mac": bssid}
        return {"conn_type": "LAN", "ssid": "",
            "iface_name": iface, "wifi_ip": "", "ap_ip": "", "ap_mac": ""}

    # macOS — coba en0 sebagai wifi standar
    try:
        r = subprocess.run(
            ["networksetup", "-getairportnetwork", "en0"],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout.strip()
        if "Current Wi-Fi Network" in out or "Jaringan Wi-Fi Saat Ini" in out:
            ssid = out.split(":", 1)[1].strip()[:64]
            ip = next((i["ip"] for i in interfaces if i["name"] == "en0"), "")
            bssid = _wifi_bssid("en0")
            ap_ip = _find_ap_ip_from_bssid(bssid)
            return {"conn_type": "WIFI", "ssid": ssid,
                    "iface_name": "en0", "wifi_ip": ip,
                    "ap_ip": ap_ip, "ap_mac": bssid}
    except Exception:
        pass
    return {"conn_type": "LAN", "ssid": "", "iface_name": "", "wifi_ip": "", "ap_ip": "", "ap_mac": ""}


def gather(token_ok_note: str = "") -> dict:
    interfaces = collect_interfaces()
    local_arp = collect_local_arp()
    conn = detect_connection(interfaces, local_arp)
    # IP dan MAC utama harus berasal dari interface koneksi aktif (WiFi/LAN),
    # bukan adapter virtual atau interface lain yang kebetulan terdaftar duluan.
    main = next(
        (
            item for item in interfaces
            if item.get("name") == conn.get("iface_name")
            and item.get("ip")
        ),
        None,
    )
    if not main:
        main = next(
            (
                item for item in interfaces
                if item.get("ip")
                and item.get("mac")
                and not item.get("name", "").lower().startswith(("docker", "veth"))
            ),
            next((item for item in interfaces if item.get("ip")), {}),
        )
    return {
        "hostname": socket.gethostname(),
        "ip": main.get("ip", ""),
        "mac": main.get("mac", ""),
        "os_info": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "interfaces": interfaces,
        "local_arp": local_arp,
        "printers": collect_printers(),
        "cpu": get_cpu_percent(),
        "mem": get_mem_percent(),
        "internet_up": check_internet(),
        "latency_ms": _last_latency,
        "agent_version": AGENT_VERSION,
        "autostart_mode": _autostart_mode(),
        "smb_open": check_smb_open(),
        **conn,
    }


# ------------------------------------------------------- auto register

def register_to_server(server: str) -> Tuple[bool, dict]:
    """Zero-config: daftar otomatis pakai MAC address → server balas token.

    PC yang sudah pernah mendaftar langsung dikenali (re-bind), jadi
    instalasi ulang agent pun tanpa isi apa pun.
    """
    g = gather()
    payload = {
        "hostname": g["hostname"],
        "mac": g["mac"],
        "ip": g["ip"],
        "os_info": g["os_info"],
        "agent_version": AGENT_VERSION,
    }
    req = urllib.request.Request(
        server.rstrip("/") + "/api/computers/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return True, json.loads(res.read().decode() or "{}")
    except Exception as exc:
        return False, {"error": str(exc)[:200]}


# ------------------------------------------------------- auto-discover server

def discover_server(timeout: float = 3.0) -> str:
    """Kirim UDP broadcast ke semua device di subnet → server balas IP:port.

    Balik URL server (mis. http://192.168.11.126:8000) atau "" bila gagal.

    Strategi:
      1. Global broadcast 255.255.255.255
      2. Broadcast ke tiap subnet adapter aktif (x.x.x.255)
      3. Langsung ke 127.0.0.1 (server di mesin yang sama)
      4. Langsung ke IP lokal
    """
    try:
        targets: Set[str] = {"255.255.255.255", "127.0.0.1"}

        # Kumpulkan broadcast address dari semua interface yang punya IP
        try:
            for iface in collect_interfaces():
                ip = iface.get("ip", "")
                if ip and "." in ip and not ip.startswith("127."):
                    targets.add(ip)
                    parts = ip.split(".")
                    if len(parts) == 4:
                        parts[3] = "255"
                        targets.add(".".join(parts))
        except Exception:
            pass

        # Fallback stdlib route
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            targets.add(local_ip)
            parts = local_ip.split(".")
            parts[3] = "255"
            targets.add(".".join(parts))
        except OSError:
            pass

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(max(0.5, timeout / 3))

        for t_addr in targets:
            try:
                sock.sendto(DISCOVERY_MAGIC, (t_addr, DISCOVERY_PORT))
            except OSError:
                pass

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
                if data.startswith(DISCOVERY_RESPONSE_PREFIX):
                    payload = data[len(DISCOVERY_RESPONSE_PREFIX):].decode()
                    ip_port = payload.split("|")
                    if len(ip_port) == 2:
                        ip, port = ip_port
                        sock.close()
                        return f"http://{ip}:{port}"
            except socket.timeout:
                for t_addr in targets:
                    try:
                        sock.sendto(DISCOVERY_MAGIC, (t_addr, DISCOVERY_PORT))
                    except OSError:
                        pass
        sock.close()
    except OSError:
        pass
    return ""


# ------------------------------------------------------------------ heartbeat

def send_heartbeat(server: str, token: str) -> Tuple[bool, Optional[float], dict]:
    global _last_latency, _last_hb_status
    payload = gather()
    payload.update(get_speed_result(server, token))
    t0 = time.monotonic()
    req = urllib.request.Request(
        server.rstrip("/") + "/api/computers/heartbeat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Agent-Token": token},
        method="POST",
    )
    data: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            try:
                data = json.loads(res.read().decode() or "{}")
            except ValueError:
                data = {}
        latency = round((time.monotonic() - t0) * 1000, 1)
        _last_latency = latency
        return True, latency, data
    except urllib.error.HTTPError as exc:
        _last_hb_status = exc.code          # 401 = token ditolak server
        _last_latency = None
        return False, None, {}
    except (urllib.error.URLError, OSError):
        _last_latency = None
        return False, None, {}


# --------------------------------------------------------- perintah remote

def run_remote_command(action: str) -> str:
    """restart / shutdown di PC lokal. Butuh hak cukup (root/admin)."""
    win = platform.system() == "Windows"
    if action == "restart":
        args = ["shutdown", "/r", "/t", "5"] if win else ["shutdown", "-r", "now"]
    elif action == "shutdown":
        args = ["shutdown", "/s", "/t", "5"] if win else ["shutdown", "-h", "now"]
    else:
        return "perintah tidak dikenal"

    def _try(cmds: List[List[str]]) -> Optional[str]:
        nonlocal last_err
        for cmd in cmds:
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=20,
                    creationflags=(0x08000000 if win else 0),
                )
                if r.returncode == 0:
                    return "executed"
                last_err = (r.stderr or r.stdout or "").strip()
            except FileNotFoundError:
                continue
            except Exception as exc:
                last_err = str(exc)
        return None

    last_err = ""
    result = _try([args])
    if result is None and not win:          # butuh sudo tanpa password
        result = _try([["sudo", "-n", *args]])
    if result:
        return result
    return f"gagal ({last_err[:100] or 'permission denied'}) — jalankan agent sebagai root/admin"


SOFTWARE_PACKAGES = {
    "7zip": {"windows": "7zip.7zip", "linux": "p7zip-full"},
    "vlc": {"windows": "VideoLAN.VLC", "linux": "vlc"},
    "notepad-plus-plus": {"windows": "Notepad++.Notepad++", "linux": "notepadqq"},
    "google-chrome": {"windows": "Google.Chrome", "linux": "google-chrome-stable"},
}


def install_software(package_id: str) -> str:
    """Install hanya paket yang terdaftar di katalog lokal agent."""
    package = SOFTWARE_PACKAGES.get(package_id.strip().lower())
    if not package:
        return "GAGAL: software tidak dikenal"
    win = platform.system() == "Windows"
    if win:
        command = ["winget", "install", "--id", package["windows"],
                   "--exact", "--silent", "--accept-package-agreements",
                   "--accept-source-agreements"]
    elif platform.system() == "Linux":
        command = ["sudo", "-n", "apt-get", "install", "-y", package["linux"]]
    else:
        return "GAGAL: platform tidak didukung"
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=900,
            creationflags=(CREATE_NO_WINDOW if win else 0),
        )
        if result.returncode == 0:
            return "OK: software terpasang"
        detail = (result.stderr or result.stdout or "install gagal").strip()
        return f"GAGAL: {detail[:130]}"
    except Exception as exc:
        return f"GAGAL: {str(exc)[:130]}"


# ------------------------------------------------------- setup / uninstall

INSTALL_DIR_NAME = "PanelAgent"
WIN_RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
WIN_RUN_KEY_HKLM = r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run"
WIN_RUN_VALUE = SERVICE_NAME
WIN_TASK_NAME = SERVICE_NAME              # Task Scheduler (mode elevated)
CREATE_NO_WINDOW = 0x08000000

# Launcher VBS di Common Startup (semua user): tunggu network online
# maks ~5 menit lalu jalankan salinan ProgramData secara hidden.
COMMON_STARTUP_VBS = """Set ws = CreateObject("WScript.Shell")
For i = 1 To 60
  Set ex = ws.Exec("ping -n 1 -w 1000 1.1.1.1")
  Do While ex.Status = 0
    WScript.Sleep 100
  Loop
  If ex.ExitCode = 0 Then Exit For
  WScript.Sleep 5000
Next
ws.Run {exe_cmd}, 0, False
"""

USER_UNIT = """[Unit]
Description=Ubuntu Panel Agent (heartbeat PC)
After=network-online.target
Wants=network-online.target
# Tanpa batas start-limit: walau sempat gagal di awal boot (mis. net belum
# up), sistemd akan terus mencoba — agent wajib hidup sampai PC mati.
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={exec}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""

SYSTEM_UNIT_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"
SYSTEM_UNIT = """[Unit]
Description=Ubuntu Panel Agent (heartbeat PC)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={exec}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Ubuntu Panel Agent
Exec={exec}
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
"""


def install_dir() -> str:
    """Folder instalasi permanen agent — selalu machine-wide di Windows.

    Windows : %ProgramData%\\PanelAgent (berlaku SEMUA user, new user ikut).
    Mode per-user lama (LOCALAPPDATA via PANEL_AGENT_USERMODE) hanya dipakai
    bila installer eksplisit memintanya; default selalu machine-wide agar
    agent 'nempel di mesin, bukan di profil'.
    """
    system = platform.system()
    if system == "Windows":
        if os.environ.get("PANEL_AGENT_USERMODE") == "1":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            return os.path.join(base, INSTALL_DIR_NAME)
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
        return os.path.join(base, INSTALL_DIR_NAME)
    try:
        if os.geteuid() == 0:
            return os.path.join("/opt", INSTALL_DIR_NAME)
    except AttributeError:
        pass
    return os.path.join(os.path.expanduser("~"), ".local", "share", INSTALL_DIR_NAME)


def _python_launcher() -> str:
    """Path interpreter untuk autostart.

    Di Windows pakai path ABSOLUT pythonw.exe (saudara sys.executable) agar
    Task Scheduler SYSTEM — yang PATH-nya tidak memuat Python — tetap bisa
    menjalankan agent saat boot tanpa login.

    Tidak pernah mengembalikan shim `py.exe` / nama-telanjang bila ada
    alternatif absolut: nama-telanjang membuat Task SYSTEM gagal diam-diam
    saat boot (kasus: hanya C:\\WINDOWS\\py.exe tanpa runtime -> exit 112
    "No installed Python found!").
    """
    if platform.system() == "Windows":
        exe_dir = os.path.dirname(sys.executable or "")
        for name in ("pythonw.exe", "python.exe"):
            cand = os.path.join(exe_dir, name) if exe_dir else name
            if os.path.isabs(cand) and os.path.exists(cand):
                return cand
        # sys.executable sendiri (sudah absolut saat dijalankan via py launcher)
        if sys.executable and os.path.isabs(sys.executable) and os.path.exists(sys.executable):
            base = os.path.basename(sys.executable).lower()
            if base not in ("py.exe", "pyw.exe"):
                return sys.executable
            # shim py.exe: cari interpreter asli di PATH / lokasi umum
            try:
                out = subprocess.run(
                    [sys.executable, "-3", "-c", "import sys; print(sys.executable)"],
                    capture_output=True, text=True, timeout=10,
                )
                real = (out.stdout or "").strip().strip('"').strip("'")
                if real and os.path.isabs(real) and os.path.exists(real):
                    return real
            except Exception:
                pass
        for which_name in ("pythonw.exe", "python.exe"):
            found = shutil.which(which_name)
            if found and os.path.isabs(found) and os.path.exists(found):
                return found
        for common in (
            r"C:\Python314\pythonw.exe",
            r"C:\Python313\pythonw.exe",
            r"C:\Python312\pythonw.exe",
            r"C:\Python314\python.exe",
            r"C:\Python313\python.exe",
            r"C:\Python312\python.exe",
        ):
            if os.path.exists(common):
                return common
        # terakhir: apa pun yang menjalankan proses ini (lebih baik daripada
        # nama-telanjang "pythonw" yang pasti gagal di konteks SYSTEM)
        if sys.executable:
            return sys.executable
        return "pythonw"
    return "python3"


def exec_command(target: str) -> str:
    """Perintah lengkap untuk menjalankan program yang sudah terpasang."""
    if is_frozen():
        return f'"{target}"'
    return f'"{_python_launcher()}" "{target}"'


def _user_env() -> dict:
    env = dict(os.environ)
    if platform.system() != "Windows":
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def win_autostart_set(exe_cmd: str) -> bool:
    try:
        r = subprocess.run(
            ["reg", "add", WIN_RUN_KEY, "/v", WIN_RUN_VALUE,
             "/t", "REG_SZ", "/d", exe_cmd, "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def win_autostart_clear() -> bool:
    try:
        r = subprocess.run(
            ["reg", "delete", WIN_RUN_KEY, "/v", WIN_RUN_VALUE, "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def win_hklm_run_set(exe_cmd: str) -> bool:
    """Autostart machine-wide via HKLM Run — berlaku SEMUA user (butuh admin)."""
    try:
        r = subprocess.run(
            ["reg", "add", WIN_RUN_KEY_HKLM, "/v", WIN_RUN_VALUE,
             "/t", "REG_SZ", "/d", exe_cmd, "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def win_hklm_run_clear() -> bool:
    try:
        r = subprocess.run(
            ["reg", "delete", WIN_RUN_KEY_HKLM, "/v", WIN_RUN_VALUE, "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def win_hklm_run_exists() -> bool:
    try:
        r = subprocess.run(
            ["reg", "query", WIN_RUN_KEY_HKLM, "/v", WIN_RUN_VALUE],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def win_common_startup_path() -> str:
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return os.path.join(
        base, r"Microsoft\Windows\Start Menu\Programs\StartUp",
        f"{SERVICE_NAME}.vbs",
    )


def win_common_startup_install(exe_cmd: str) -> bool:
    """Launcher VBS di Common Startup (semua user): tunggu network lalu start.

    Jaring pengaman ketiga bila Task Scheduler dihapus AV/kebijakan.
    Butuh admin untuk menulis ke Common Startup.
    """
    try:
        os.makedirs(os.path.dirname(win_common_startup_path()), exist_ok=True)
        with open(win_common_startup_path(), "w", encoding="utf-8") as f:
            f.write(COMMON_STARTUP_VBS.format(exe_cmd=f'"{exe_cmd}"' if not exe_cmd.startswith('"') else exe_cmd))
        return True
    except OSError:
        return False


def win_common_startup_clear() -> bool:
    try:
        os.remove(win_common_startup_path())
        return True
    except OSError:
        return False


def win_common_startup_exists() -> bool:
    return os.path.exists(win_common_startup_path())


def is_elevated_windows() -> bool:
    """True bila proses ini punya hak Administrator penuh (UAC elevate)."""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def win_task_exists() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/tn", WIN_TASK_NAME],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=15,
        )
        return r.returncode == 0
    except Exception:
        return False


def _autostart_mode() -> str:
    """Mode autostart: task-scheduler (boot, semua user, machine-wide),
    hklm-run / common-startup (cadangan all-users), atau hkcu-run
    (login-only, user tsb saja). Non-Windows → "system"."""
    if platform.system() != "Windows":
        return "system"
    try:
        modes = []
        if win_task_exists():
            modes.append("task-scheduler")
        if win_hklm_run_exists():
            modes.append("hklm-run")
        if win_common_startup_exists():
            modes.append("common-startup")
        if modes:
            return "+".join(modes)
        return "hkcu-run"
    except Exception:  # noqa: BLE001
        return "hkcu-run"


def _split_exe_cmd(exe_cmd: str) -> Tuple[str, str]:
    """Pecah exe_cmd jadi (execute, arguments) dengan sadar-kutip Windows.

    exe_cmd berbentuk '"C:\\...\\pythonw.exe" "C:\\...\\panel_agent.py"'
    (atau '"C:\\...\\panel-agent.exe"'). partition(" ") biasa HANCUR bila
    path mengandung spasi (mis. C:\\Users\\POLIKLINIK 07\\...), sehingga
    Task Scheduler gagal dibuat. Fungsi ini menghormati tanda kutip ganda.
    """
    parts: List[str] = []
    cur: List[str] = []
    in_q = False
    for ch in exe_cmd.strip():
        if ch == '"':
            in_q = not in_q
            cur.append(ch)
        elif ch in (" ", "\t") and not in_q:
            if cur:
                parts.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    if not parts:
        return exe_cmd, ""
    execute = parts[0]
    # New-ScheduledTaskAction -Execute TIDAK boleh memakai kutip pembungkus
    if len(execute) >= 2 and execute.startswith('"') and execute.endswith('"'):
        execute = execute[1:-1]
    return execute, " ".join(parts[1:])


def win_task_install(exe_cmd: str) -> bool:
    """Autostart via Task Scheduler sebagai SYSTEM + restart-on-failure.

    Task berjalan dengan hak SYSTEM (setara root) **saat PC boot** tanpa
    menunggu login, dan otomatis dijalankan ulang bila proses agent mati.
    Trigger: AtStartup + AtLogon (jaring pengaman).

    exe_cmd bisa '"C:\\...\\panel-agent.exe"' (frozen) atau
    '"pythonw" "C:\\...\\panel_agent.py"' (script); dipecah jadi
    Execute + Argument agar benar untuk New-ScheduledTaskAction.
    """
    execute, arguments = _split_exe_cmd(exe_cmd)
    # Escape kutip tunggal untuk string single-quoted PowerShell (' -> '')
    execute_ps = execute.replace("'", "''")
    arguments_ps = arguments.replace("'", "''")

    if is_elevated_windows():
        try:
            script = PS_TASK_TEMPLATE.format(
                execute=execute_ps,
                arguments=arguments_ps,
                name=WIN_TASK_NAME,
            )
            r2 = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile",
                 "-Command", script],
                capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=60,
            )
            if r2.returncode == 0:
                return True
        except Exception:
            pass

    # Fallback: schtasks /ru SYSTEM (boot-time, hak tinggi)
    try:
        r = subprocess.run(
            ["schtasks", "/create", "/tn", WIN_TASK_NAME, "/tr", exe_cmd,
             "/sc", "onstart", "/ru", "SYSTEM", "/rl", "highest", "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


PS_TASK_TEMPLATE = (
    "$a = New-ScheduledTaskAction -Execute '{execute}' -Argument '{arguments}'; "
    "$t1 = New-ScheduledTaskTrigger -AtStartup; "
    "$t1.Delay = 'PT30S'; "
    "$t2 = New-ScheduledTaskTrigger -AtLogOn; "
    "$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' "
    "-LogonType ServiceAccount -RunLevel Highest; "
    "$s = New-ScheduledTaskSettingsSet -RestartCount 999 "
    "-RestartInterval (New-TimeSpan -Minutes 1) "
    "-ExecutionTimeLimit ([TimeSpan]::Zero) "
    "-MultipleInstances IgnoreNew -StartWhenAvailable "
    "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
    "-WakeToRun -DisallowStartIfOnBatteries:$false; "
    "Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger $t1,$t2 "
    "-Principal $p -Settings $s -Force | Out-Null"
)


def win_task_remove() -> bool:
    try:
        r = subprocess.run(
            ["schtasks", "/delete", "/tn", WIN_TASK_NAME, "/f"],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def linux_system_service_enable(exe_cmd: str, use_sudo: bool = False) -> Optional[str]:
    """systemd system-wide (root) → hidup saat boot sebelum login.

    Balik None bila sukses, pesan galat bila gagal. use_sudo=True memakai
    `sudo -n` (tanpa password) — gagal bila sudo butuh password.
    """
    prefix = ["sudo", "-n"] if use_sudo else []
    if not use_sudo and os.geteuid() != 0:
        return "butuh root"
    try:
        p = subprocess.run(
            [*prefix, "tee", SYSTEM_UNIT_PATH],
            input=SYSTEM_UNIT.replace("{exec}", exe_cmd),
            capture_output=True, text=True, timeout=30,
        )
        if p.returncode != 0:
            return (p.stderr or "").strip() or "gagal menulis unit"
        for cmd in (
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", "--now", SERVICE_NAME],
        ):
            r = subprocess.run([*prefix, *cmd], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return (r.stderr or "").strip() or "gagal mengaktifkan service"
        return None
    except Exception as exc:      # noqa: BLE001
        return str(exc)[:200]


def linux_system_service_active() -> bool:
    try:
        if not os.path.exists(SYSTEM_UNIT_PATH):
            return False
        r = subprocess.run(
            ["systemctl", "is-enabled", SERVICE_NAME],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() == "enabled"
    except Exception:
        return False


def linux_user_service_enable(exe_cmd: str) -> Optional[str]:
    """systemd --user + linger → hidup saat boot walau belum login.
    Balik None bila sukses, pesan galat bila gagal (tanpa sudo)."""
    unit_dir = os.path.join(os.path.expanduser("~"), ".config", "systemd", "user")
    unit_path = os.path.join(unit_dir, f"{SERVICE_NAME}.service")
    try:
        os.makedirs(unit_dir, exist_ok=True)
        with open(unit_path, "w", encoding="utf-8") as f:
            f.write(USER_UNIT.replace("{exec}", exe_cmd))
        for cmd in (
            ["systemctl", "--user", "daemon-reload"],
            ["loginctl", "enable-linger"],
            ["systemctl", "--user", "enable", SERVICE_NAME],
        ):
            subprocess.run(cmd, check=True, capture_output=True,
                           timeout=20, env=_user_env())
        return None
    except Exception as exc:
        try:
            os.remove(unit_path)
        except OSError:
            pass
        return str(exc)


def linux_desktop_autostart(exe_cmd: str) -> None:
    d = os.path.join(os.path.expanduser("~"), ".config", "autostart")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{SERVICE_NAME}.desktop")
    with open(path, "w", encoding="utf-8") as f:
        f.write(DESKTOP_ENTRY.replace("{exec}", exe_cmd))


def linux_autostart_clear() -> None:
    home = os.path.expanduser("~")
    subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME],
                   capture_output=True, timeout=20, env=_user_env())
    subprocess.run(["loginctl", "disable-linger"],
                   capture_output=True, timeout=20, env=_user_env())
    for p in (
        os.path.join(home, ".config", "systemd", "user", f"{SERVICE_NAME}.service"),
        os.path.join(home, ".config", "autostart", f"{SERVICE_NAME}.desktop"),
    ):
        try:
            os.remove(p)
        except OSError:
            pass
    subprocess.run(["systemctl", "--user", "daemon-reload"],
                   capture_output=True, timeout=20, env=_user_env())


def _same_file(a: str, b: str) -> bool:
    """True bila dua path menunjuk file yang sama (aman untuk self-copy)."""
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except Exception:
        return False


def _copy_if_different(src: str, dst: str) -> None:
    """Salin src->dst kecuali file yang sama; toleran WinError 32.

    Di Windows agent.ini sering sedang dibuka proses agent lain saat
    --setup-autostart berjalan. Bila src==dst (sudah di lokasi permanen)
    tidak ada yang perlu disalin. Bila salin gagal karena file terkunci
    padahal isi identik/tujuan sudah ada, abaikan diam-diam.
    """
    if not src or not dst or _same_file(src, dst):
        return
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        # WinError 32: file dipakai proses lain. Bila dst sudah ada (mis.
        # token lama), itu bukan fatal untuk instalasi.
        if os.path.exists(dst):
            return
        raise exc


def copy_self_and_config(server: str = "") -> str:
    """Salin program (+ agent.ini) ke folder instalasi permanen.
    Balik path target terpasang."""
    src = program_path()
    dst_dir = install_dir()
    os.makedirs(dst_dir, exist_ok=True)
    filename = os.path.basename(src) if src else ("panel-agent" if is_frozen() else "panel_agent.py")
    dst = os.path.join(dst_dir, filename)

    if src and os.path.isfile(src):
        if not _same_file(src, dst):
            shutil.copy2(src, dst)
    else:
        # Jika dijalankan via stdin (curl | python3), unduh atau salin script langsung
        if server:
            try:
                req = urllib.request.Request(server.rstrip("/") + "/api/computers/agent-script")
                with urllib.request.urlopen(req, timeout=10) as res:
                    content = res.read()
                with open(dst, "wb") as f:
                    f.write(content)
            except Exception:
                pass

    if os.path.exists(config_path()):
        _copy_if_different(config_path(), os.path.join(dst_dir, CONFIG_NAME))
    return dst


def current_exe_cmd() -> str:
    """Perintah untuk menjalankan salinan terpasang (atau file saat ini)."""
    src = program_path()
    if src and os.path.isfile(src):
        return exec_command(src)
    filename = "panel-agent" if is_frozen() else "panel_agent.py"
    return exec_command(os.path.join(install_dir(), filename))


def _write_setup_marker(dst: str = "") -> None:
    try:
        os.makedirs(install_dir(), exist_ok=True)
        with open(setup_marker_path(), "w", encoding="utf-8") as f:
            f.write(dst or "")
    except OSError:
        pass


def win_run_elevated(extra_args: List[str]) -> bool:
    """Jalankan program ini SEKALI sebagai Administrator (UAC), lalu tunggu.

    Dipakai agar installer cukup **sekali minta elevate**: proses admin
    memasang task boot-time, proses asli (non-admin) tetap berjalan.
    """
    if platform.system() != "Windows":
        return False
    exe = sys.executable
    arg_list = list(extra_args) if is_frozen() else [os.path.abspath(__file__), *extra_args]
    quoted = "','".join(a.replace("'", "''") for a in arg_list)
    ps = (
        f"Start-Process -FilePath '{exe}' -Verb RunAs "
        f"-ArgumentList '{quoted}' -Wait"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps],
            capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=300,
        )
        return r.returncode == 0
    except Exception:
        return False


def do_ensure_smb() -> int:
    """Flag --ensure-smb: buka SMB sekali lalu keluar (dipakai installer)."""
    ok, msg = ensure_smb_open()
    print(f"[{'ok' if ok else 'info'}] SMB: {msg}")
    return 0 if ok else 1


def do_setup_autostart(server: str = "") -> int:
    """Dipanggil SEKALI sebagai admin: pasang salinan + triple autostart.

    Machine-wide: Task SYSTEM (utama) + HKLM Run + Common Startup VBS
    (cadangan all-users) + buka SMB untuk printer.
    """
    # paksa ProgramData walau pemanggil berasal dari LOCALAPPDATA
    saved_mode = os.environ.pop("PANEL_AGENT_USERMODE", None)
    try:
        dst = copy_self_and_config(server)
    finally:
        if saved_mode is not None:
            os.environ["PANEL_AGENT_USERMODE"] = saved_mode
    # hitung ulang exe_cmd dari lokasi ProgramData (bukan src pemanggil)
    filename = os.path.basename(dst)
    exe_cmd = exec_command(dst)
    _ = filename
    if platform.system() == "Windows":
        if not is_frozen():
            launcher = _python_launcher()
            # exe_cmd = '"<launcher>" "<dst>"' -> ambil launcher untuk validasi
            if not (os.path.isabs(launcher) and os.path.exists(launcher)):
                print(f"[gagal] interpreter Python tidak valid untuk Task SYSTEM: {launcher}")
                print("[gagal] install Python machine-wide ke C:\\Python314 (centang Add to PATH + for all users),")
                print("[gagal] lalu jalankan installer bootstrap sekali lagi. Jangan pakai shim py.exe saja.")
                return 1
        ok_task = win_task_install(exe_cmd)
        ok_hklm = win_hklm_run_set(exe_cmd)
        ok_vbs = win_common_startup_install(exe_cmd)
        win_autostart_clear()
        ok_smb, msg_smb = ensure_smb_open()
        print(f"[ok] terpasang di : {dst}")
        print(f"[{'ok' if ok_task else 'gagal'}] autostart 1/3 : Task Scheduler SYSTEM — jalan saat boot")
        print(f"[{'ok' if ok_hklm else 'gagal'}] autostart 2/3 : HKLM Run (semua user)")
        print(f"[{'ok' if ok_vbs else 'gagal'}] autostart 3/3 : Common Startup VBS (cadangan)")
        print(f"[{'ok' if ok_smb else 'info'}] SMB           : {msg_smb}")
        if ok_task or ok_hklm or ok_vbs:
            _write_setup_marker(dst)
            return 0
        print("[gagal] semua autostart boot-time gagal dibuat")
        return 1
    err = linux_system_service_enable(exe_cmd)
    print(f"[ok] terpasang di : {dst}")
    if err is None:
        print("[ok] autostart    : systemd system service — jalan saat boot")
        _write_setup_marker(dst)
        return 0
    print(f"[gagal] system service: {err}")
    return 1


def ensure_autostart(force: bool = False) -> None:
    """Self-heal triple autostart machine-wide + SMB.

    Hanya bertindak bila punya hak cukup (SYSTEM/root/sudo -n). Memastikan:
    1/3 Task SYSTEM, 2/3 HKLM Run, 3/3 Common Startup VBS — semuanya
    menunjuk ke salinan %ProgramData%\\PanelAgent. HKCU Run lama dibersihkan
    (migrasi per-user → machine-wide). SMB dibuka ulang bila tertutup.
    """
    if platform.system() == "Windows":
        if not is_elevated_windows():
            return
        saved_mode = os.environ.pop("PANEL_AGENT_USERMODE", None)
        try:
            dst = copy_self_and_config("")
            exe_cmd = exec_command(dst)
            if force or not win_task_exists():
                if win_task_install(exe_cmd):
                    win_autostart_clear()
                else:
                    print("[warn] Task Scheduler SYSTEM gagal dibuat ulang")
            if force or not win_hklm_run_exists():
                win_hklm_run_set(exe_cmd)
            if force or not win_common_startup_exists():
                win_common_startup_install(exe_cmd)
            try:
                ensure_smb_open()
            except Exception:
                pass
        except OSError as exc:
            print(f"[peringatan] self-heal autostart gagal: {exc}")
        finally:
            if saved_mode is not None:
                os.environ["PANEL_AGENT_USERMODE"] = saved_mode
        return
    exe_cmd = current_exe_cmd()
    if os.geteuid() == 0:
        if force or not linux_system_service_active():
            linux_system_service_enable(exe_cmd)
        return
    try:
        subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5, check=True)
    except Exception:
        return
    if force or not linux_system_service_active():
        linux_system_service_enable(exe_cmd, use_sudo=True)


def do_setup(server: str, token: str, interval: int) -> int:
    print(f"[setup] memasang agent v{AGENT_VERSION} …")

    # Windows non-admin: cukup MINTA ELEVATE SEKALI — proses admin memasang
    # salinan + task boot-time, proses ini tetap berjalan untuk sesi ini.
    if platform.system() == "Windows" and not is_elevated_windows():
        print("[elevate] minta hak Administrator SEKALI untuk autostart boot-time …")
        if win_run_elevated(["--setup-autostart", "--server", server]):
            print("[ok] terpasang sebagai Administrator (Task Scheduler SYSTEM)")
            _write_setup_marker()
            return 0
        print("[info] elevate dibatalkan — pakai instalasi per-user (login-only)")
        os.environ["PANEL_AGENT_USERMODE"] = "1"

    dst = copy_self_and_config(server)
    exe_cmd = exec_command(dst)

    if platform.system() == "Windows":
        if is_elevated_windows():
            ok_task = win_task_install(exe_cmd)
            ok_hklm = win_hklm_run_set(exe_cmd)
            ok_vbs = win_common_startup_install(exe_cmd)
            win_autostart_clear()
            ok_smb, msg_smb = ensure_smb_open()
            print(f"[ok] terpasang di : {dst}")
            print(f"[{'ok' if ok_task else 'gagal'}] autostart 1/3 : Task Scheduler SYSTEM — jalan saat boot")
            print(f"[{'ok' if ok_hklm else 'gagal'}] autostart 2/3 : HKLM Run (semua user)")
            print(f"[{'ok' if ok_vbs else 'gagal'}] autostart 3/3 : Common Startup VBS (cadangan)")
            print(f"[{'ok' if ok_smb else 'info'}] SMB           : {msg_smb}")
            if not (ok_task or ok_hklm or ok_vbs):
                print("[info] Task Scheduler gagal — fallback registry Run")
                if not win_autostart_set(exe_cmd):
                    print("[gagal] tidak bisa menulis registry Run — jalankan sekali lagi.")
                    return 1
                print(f"[ok] terpasang di : {dst}")
                print("[ok] autostart    : registry HKCU\\...\\Run — jalan tiap login")
        else:
            if not win_autostart_set(exe_cmd):
                print("[gagal] tidak bisa menulis registry Run — jalankan sekali lagi.")
                return 1
            print(f"[ok] terpasang di : {dst}")
            print("[ok] autostart    : registry HKCU\\...\\Run — jalan tiap login")
    else:
        err: Optional[str] = None
        if os.geteuid() == 0:
            err = linux_system_service_enable(exe_cmd)
        else:
            try:
                subprocess.run(["sudo", "-n", "true"], capture_output=True,
                               timeout=5, check=True)
                err = linux_system_service_enable(exe_cmd, use_sudo=True)
            except Exception:
                err = "tanpa sudo NOPASSWD"
        print(f"[ok] terpasang di : {dst}")
        if err is None:
            print("[ok] autostart    : systemd system service — jalan saat boot")
        else:
            uerr = linux_user_service_enable(exe_cmd)
            if uerr is None:
                print("[ok] autostart    : systemd --user + linger — jalan saat boot")
            else:
                linux_desktop_autostart(exe_cmd)
                print(f"[info] systemd tidak tersedia ({str(err)[:60]}…)")
                print("[ok] autostart    : ~/.config/autostart — jalan saat login")

    print(f"[ok] server       : {server}")
    print(f"[ok] token        : {token[:6]}••••••")
    print(f"[ok] interval     : {interval}s")
    print("[ok] agent berjalan sekarang — reboot pun akan hidup sendiri")
    name = "panel-agent" if is_frozen() else "python panel_agent.py"
    print(f"[info] cabut kapan saja: {name} --uninstall")
    print("-" * 60)
    _write_setup_marker(dst)
    return 0


def do_uninstall() -> int:
    removed: List[str] = []
    if platform.system() == "Windows":
        if win_autostart_clear():
            removed.append("autostart (registry HKCU Run)")
        if win_hklm_run_clear():
            removed.append("autostart (registry HKLM Run, semua user)")
        if win_common_startup_clear():
            removed.append("autostart (Common Startup VBS)")
        if win_task_remove():
            removed.append("autostart (Task Scheduler elevated)")
    else:
        linux_autostart_clear()
        removed.append("autostart (systemd user / desktop)")
        try:
            if os.geteuid() == 0:
                subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME],
                               capture_output=True, timeout=20)
                if os.path.exists(SYSTEM_UNIT_PATH):
                    os.remove(SYSTEM_UNIT_PATH)
                    subprocess.run(["systemctl", "daemon-reload"],
                                   capture_output=True, timeout=20)
                    removed.append("autostart (systemd system service)")
        except OSError:
            pass

    d = install_dir()
    shutil.rmtree(d, ignore_errors=True)
    if os.path.exists(d):
        removed.append(f"sebagian isi {d} (program sedang berjalan — hapus manual setelah keluar)")
    else:
        removed.append(f"salinan program ({d})")

    for r in removed:
        print(f"[ok] dihapus: {r}")
    print("[ok] bersih — file asli yang kamu klik tidak disentuh.")
    return 0


# ------------------------------------------------- jendela & instans tunggal

def _pid_alive(pid: int) -> bool:
    """Cek apakah proses dengan PID ini masih hidup (lintas-OS)."""
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFO
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            k.CloseHandle(h)
            return bool(ok) and code.value == 259    # STILL_ACTIVE
        except Exception:
            return True     # ragu → anggap hidup, jangan dobel jalan
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_single_instance() -> bool:
    """False bila agent lain masih hidup — cegah dua agent berjalan.

    Lock disimpan di folder instalasi (bukan folder program asli) agar
    semua salinan — yang diklik langsung maupun hasil --setup — berebut
    kunci yang sama.
    """
    try:
        os.makedirs(install_dir(), exist_ok=True)
        lock = os.path.join(install_dir(), "agent.lock")
        if os.path.exists(lock):
            with open(lock) as f:
                old = f.read().strip()
            if old.isdigit() and _pid_alive(int(old)):
                return False
            os.remove(lock)
        with open(lock, "w") as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        return True         # gagal tulis lock → tetap jalan saja


def relaunch_hidden_windows(server_known: bool) -> bool:
    """Dobel-klik panel_agent.py di Windows membuka console yang menetap.

    Solusi: lempar proses ke pythonw.exe (tanpa jendela sama sekali),
    console asli menutup sendiri. exe hasil build --noconsole tidak
    perlu semua ini karena sudah hidden sejak awal.

    Balik True bila proses background sudah dilempar (pemanggil harus
    segera keluar TANPA mengunci single-instance — proses anak yang
    akan memegang lock, bukan parent).
    """
    if platform.system() != "Windows" or is_frozen():
        return False                # Linux/exe: tidak ada masalah jendela
    if os.environ.get("PANEL_AGENT_HIDDEN") == "1":
        return False                # sudah di background — jangan lempar lagi
    skip = ("--help", "-h", "--uninstall", "--setup", "--visible",
            "--once-loop", "--ensure-smb")
    if any(a in sys.argv for a in skip):
        return False
    if not server_known:
        return False                # wizard butuh console — biarkan tampil
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        return False
    env = {**os.environ, "PANEL_AGENT_HIDDEN": "1"}
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    subprocess.Popen([pyw, os.path.abspath(__file__), *sys.argv[1:]],
                     creationflags=flags, close_fds=True, env=env)
    return True


def setup_marker_path() -> str:
    return os.path.join(install_dir(), ".installed")


def already_installed() -> bool:
    """True bila --setup pernah sukses DAN salinan program masih ada."""
    marker = setup_marker_path()
    if not os.path.exists(marker):
        return False
    try:
        with open(marker, encoding="utf-8") as f:
            recorded = f.read().strip()
    except OSError:
        recorded = ""
    if recorded and os.path.exists(recorded):
        return True
    src = program_path()
    filename = os.path.basename(src) if src else ("panel-agent" if is_frozen() else "panel_agent.py")
    dst = os.path.join(install_dir(), filename)
    return os.path.exists(dst)


def refresh_installed_copy() -> None:
    """Salinan di folder instalasi kadaluarsa (agent lama) → perbarui
    diam-diam, sehingga cukup menjalankan file terbaru sekali dan semua
    salinan ikut versi baru tanpa --setup ulang."""
    if is_frozen():
        return              # exe tunggal — tidak ada konsep salinan skrip
    src = program_path()
    if not src or not os.path.isfile(src):
        return
    dst = os.path.join(install_dir(), os.path.basename(src))
    try:
        if os.path.abspath(src) == os.path.abspath(dst):
            return          # kita MEMANG salinan terpasang — selesai
        if os.path.exists(dst) and \
                os.path.getmtime(src) <= os.path.getmtime(dst):
            return          # salinan sudah yang terbaru
        os.makedirs(install_dir(), exist_ok=True)
        shutil.copy2(src, dst)
        print("[ok] salinan terpasang diperbarui ke versi terbaru")
    except OSError as exc:
        print(f"[peringatan] gagal memperbarui salinan: {exc}")


def do_update(server: str) -> int:
    """Unduh versi terbaru dari panel dan restart agent terpasang."""
    if is_frozen():
        print("[gagal] update otomatis belum didukung untuk executable.")
        return 1
    if not server:
        print("[gagal] alamat server belum tersedia.")
        return 1

    dst = os.path.join(install_dir(), "panel_agent.py")
    tmp = dst + ".update"
    try:
        os.makedirs(install_dir(), exist_ok=True)
        req = urllib.request.Request(server.rstrip("/") + "/api/computers/agent-script")
        with urllib.request.urlopen(req, timeout=15) as res:
            content = res.read()
        if b"def run_loop(" not in content or b"AGENT_VERSION" not in content:
            print("[gagal] respons server bukan script agent yang valid.")
            return 1
        with open(tmp, "wb") as f:
            f.write(content)
        if os.path.exists(dst):
            shutil.copymode(dst, tmp)
        os.replace(tmp, dst)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print(f"[gagal] update agent: {exc}")
        return 1

    print(f"[ok] agent diperbarui: {dst}")
    cfg = load_config()
    token = cfg.get("token", "")
    interval = int(cfg.get("interval", "10")) if cfg.get("interval", "").isdigit() else 10
    restart_self_after_update(server, token, interval)
    print("[ok] service agent direstart")
    return 0


def update_from_remote(server: str) -> str:
    """Update agent dari command heartbeat dan kembalikan hasil singkat."""
    if is_frozen():
        return "GAGAL: update executable harus dilakukan manual"
    if not server:
        return "GAGAL: alamat server kosong"

    dst = os.path.join(install_dir(), "panel_agent.py")
    tmp = dst + ".update"
    try:
        os.makedirs(install_dir(), exist_ok=True)
        req = urllib.request.Request(server.rstrip("/") + "/api/computers/agent-script")
        with urllib.request.urlopen(req, timeout=15) as res:
            content = res.read()
        if b"def run_loop(" not in content or b"AGENT_VERSION" not in content:
            return "GAGAL: respons server bukan script agent yang valid"
        with open(tmp, "wb") as f:
            f.write(content)
        if os.path.exists(dst):
            shutil.copymode(dst, tmp)
        os.replace(tmp, dst)
        return f"OK: agent diperbarui ke {AGENT_VERSION}"
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return f"GAGAL: update agent ({exc})"[:160]


def _execv_new_version(dst: str, server: str, token: str, interval: int) -> None:
    """Ganti proses berjalan dengan versi terpasang secara in-place.

    PID tidak berubah -> Task Scheduler SYSTEM / systemd menganggap proses
    masih hidup, sehingga versi baru LANGSUNG aktif tanpa reboot / re-login.
    Tidak kembali normal; bila gagal melempar OSError.
    """
    if platform.system() == "Windows":
        os.environ["PANEL_AGENT_HIDDEN"] = "1"
    args = [
        sys.executable, dst,
        "--server", server, "--token", token, "--interval", str(interval),
    ]
    os.execv(sys.executable, args)


def restart_self_after_update(server: str, token: str, interval: int) -> None:
    """Aktifkan versi baru yang sudah diunduh.

    Script agent: in-place re-exec (PID sama, tanpa reboot). Bila re-exec
    gagal, fallback ke spawn proses baru / systemctl restart seperti lama.
    """
    try:
        lock = os.path.join(install_dir(), "agent.lock")
        if os.path.exists(lock):
            os.remove(lock)
    except OSError:
        pass

    frozen = is_frozen()
    dst = os.path.join(
        install_dir(), "panel-agent" if frozen else "panel_agent.py"
    )
    if not frozen:
        try:
            _execv_new_version(dst, server, token, interval)
        except OSError as exc:
            print(f"[warn] re-exec update gagal ({exc}) — pakai relaunch fallback")

    system = platform.system()
    if system == "Windows":
        pyw = _python_launcher()
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        env = {**os.environ, "PANEL_AGENT_HIDDEN": "1"}
        subprocess.Popen(
            [pyw, dst, "--server", server, "--token", token, "--interval", str(interval)],
            creationflags=flags, close_fds=True, env=env,
        )
    elif system == "Linux":
        res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True, text=True, env=_user_env(),
        )
        if res.stdout.strip() == "active":
            subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME],
                           capture_output=True, env=_user_env())
        else:
            subprocess.Popen(
                [sys.executable, dst, "--server", server, "--token", token,
                 "--interval", str(interval)],
                start_new_session=True,
            )


# ------------------------------------------------------------------------ main

def ack_command(server: str, token: str, action: str, status: str) -> None:
    req = urllib.request.Request(
        server.rstrip("/") + "/api/computers/ack",
        data=json.dumps({"action": action, "status": status}).encode(),
        headers={"Content-Type": "application/json", "X-Agent-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass


def run_loop(server: str, token: str, interval: int, once_loop: bool = False) -> int:
    print(f"Panel Agent v{AGENT_VERSION} -> {server} (interval {interval}s)")
    fail_streak = 0
    last_register_attempt = 0.0
    # self-heal autostart boot-time + SMB: cek saat start, lalu tiap ~1 jam
    try:
        ensure_autostart()
    except Exception:      # noqa: BLE001
        pass
    if not once_loop and not check_internet():
        print("[net] belum online saat start — tunggu maks 5 menit…")
        wait_for_network_online(max_wait=300)
    try:
        ensure_smb_open()
    except Exception:      # noqa: BLE001
        pass
    heal_at = time.monotonic() + 3600
    while True:
        global _last_hb_status
        _last_hb_status = None
        ok, latency, data = send_heartbeat(server, token)
        stamp = time.strftime("%H:%M:%S")
        # Agent yang dibawa ke ruangan/subnet lain bisa masih menyimpan URL
        # lama. Pulihkan koneksi ke IP server kantor tanpa setup manual.
        if not ok and server.rstrip("/") != OFFICE_SERVER and fail_streak >= 2:
            fallback_ok, fallback_latency, fallback_data = send_heartbeat(
                OFFICE_SERVER, token
            )
            if fallback_ok:
                server = OFFICE_SERVER
                ok, latency, data = fallback_ok, fallback_latency, fallback_data
                save_config(server, token, interval)
                print(f"[{stamp}] [ok] server dipulihkan ke {server}")
        if ok:
            fail_streak = 0
            print(f"[{stamp}] heartbeat OK ({latency} ms)")
            # simpan token baru dari server (rotasi token)
            resp_token = data.get("token")
            if resp_token and resp_token != token:
                token = resp_token
                save_config(server, token, interval)
                print(f"[{stamp}] token diperbarui oleh server")
            cmd = data.get("command")
            if cmd and cmd.startswith("install:"):
                package_id = cmd.split(":", 1)[1]
                status = install_software(package_id)
                print(f"[{stamp}] hasil INSTALL {package_id}: {status}")
                ack_command(server, token, cmd, status)
            elif cmd and cmd.startswith("share-printer:"):
                printer_name = cmd.split(":", 1)[1]
                okp, info = set_printer_shared(printer_name, True)
                status = f"{'OK' if okp else 'GAGAL'}: share '{printer_name}' — {info}"
                print(f"[{stamp}] {status}")
                ack_command(server, token, cmd, status)
            elif cmd and cmd.startswith("unshare-printer:"):
                printer_name = cmd.split(":", 1)[1]
                okp, info = set_printer_shared(printer_name, False)
                status = f"{'OK' if okp else 'GAGAL'}: unshare '{printer_name}' — {info}"
                print(f"[{stamp}] {status}")
                ack_command(server, token, cmd, status)
            elif cmd == "update":
                status = update_from_remote(server)
                print(f"[{stamp}] hasil UPDATE: {status}")
                ack_command(server, token, cmd, status)
                if status.startswith("OK:"):
                    restart_self_after_update(server, token, interval)
                    return 0
            elif cmd == "cleanup-nodelete":
                status = do_cleanup_nodelete()
                print(f"[{stamp}] hasil CLEANUP: {status}")
                ack_command(server, token, cmd, status)
            elif cmd in ("restart", "shutdown"):
                label = "RESTART" if cmd == "restart" else "SHUTDOWN"
                print(f"[{stamp}] >>> PERINTAH {label} diterima dari server!")
                status = run_remote_command(cmd)
                print(f"[{stamp}] hasil {label}: {status}")
                ack_command(server, token, cmd, status)
                return 0   # PC akan mati/restart — akhiri loop rapi
        else:
            fail_streak += 1
            # token ditolak server (entri komputer dihapus / diganti) →
            # jangan menyerah: daftar ulang otomatis pakai MAC address
            if _last_hb_status == 401:
                # batasi retry register: sekali tiap 30 detik
                now = time.monotonic()
                if now - last_register_attempt >= 30:
                    last_register_attempt = now
                    print(
                        f"[{stamp}] token ditolak server (401) — "
                        "mendaftar ulang otomatis…"
                    )
                    ok2, reg = register_to_server(server)
                    new_token = str(reg.get("token") or "")
                    if ok2 and new_token:
                        token = new_token
                        comp = reg.get("computer") or {}
                        print(
                            f"[{stamp}] [ok] dikenali lagi sebagai "
                            f"'{comp.get('name', '?')}' — lanjut heartbeat"
                        )
                        save_config(server, token, interval)
                        fail_streak = 0
                        continue
                    else:
                        err = reg.get("error", "server tidak merespons")
                        print(
                            f"[{stamp}] [warn] re-register gagal: {err} — "
                            "akan retry 30s lagi"
                        )
                # else: sudah coba tadi, tunggu interval berikutnya
            else:
                reason = "koneksi gagal" if fail_streak <= 3 else "server tidak merespons"
                if _last_hb_status:
                    reason = f"HTTP {_last_hb_status}"
                print(
                    f"[{stamp}] heartbeat GAGAL ({reason}, "
                    f"percobaan ke-{fail_streak})"
                )
        if once_loop:
            return 0 if ok else 1
        # Gagal beruntun 10x (~100s): network mungkin putus lama — tunggu
        # online lagi sebelum membanjiri log/server. Tidak pernah exit.
        if not ok and fail_streak > 0 and fail_streak % 10 == 0 and not once_loop:
            print(f"[{stamp}] gagal {fail_streak}x beruntun — tunggu network online…")
            wait_for_network_online(max_wait=300)
        if time.monotonic() >= heal_at:
            heal_at = time.monotonic() + 3600
            try:
                ensure_autostart()
            except Exception:      # noqa: BLE001
                pass
            try:
                ensure_smb_open()
            except Exception:      # noqa: BLE001
                pass
        time.sleep(interval)


def do_test(server: str, token: str) -> int:
    """Diagnosa lengkap: cetak data yang dikumpulkan dan tes komunikasi ke server."""
    print(f"=== DIAGNOSTIK PANEL AGENT v{AGENT_VERSION} ===")
    g = gather()
    print(f"Hostname   : {g.get('hostname')}")
    print(f"IP Utama   : {g.get('ip')}")
    print(f"MAC        : {g.get('mac')}")
    print(f"OS         : {g.get('os_info')}")
    ssid_str = f" (SSID: {g.get('ssid')})" if g.get('ssid') else ""
    print(f"Koneksi    : {g.get('conn_type')}{ssid_str}")
    print(f"CPU        : {g.get('cpu')}%" if g.get('cpu') is not None else "CPU        : -")
    print(f"RAM        : {g.get('mem')}%" if g.get('mem') is not None else "RAM        : -")
    print(f"Internet   : {'ONLINE' if g.get('internet_up') else 'OFFLINE'}")
    smb = g.get("smb_open")
    print(f"SMB        : {'TERBUKA' if smb else ('TERTUTUP' if smb is False else '-')}")
    print(f"Autostart  : {g.get('autostart_mode')}")
    print("\nInterfaces:")
    for iface in g.get("interfaces", []):
        print(f"  - {iface.get('name')}: IP={iface.get('ip') or '-'}, MAC={iface.get('mac') or '-'}")

    print("\nServer Target:")
    print(f"  URL   : {server or '(belum ditentukan)'}")
    print(f"  Token : {token or '(belum ada — akan auto-register)'}")

    if not server:
        print("[discover] mencari server di LAN via UDP broadcast…")
        server = discover_server(timeout=3.0)
        if server:
            print(f"[ok] server ditemukan: {server}")
        else:
            print("[gagal] server tidak ditemukan di LAN")
            return 1

    if token:
        print(f"\nMengirim tes heartbeat ke {server} (token: {token[:8]}...) …")
        ok, latency, data = send_heartbeat(server, token)
        if ok:
            print(f"[SUKSES] Heartbeat diterima server! Latensi: {latency} ms")
            print(f"Respon server: {data}")
            return 0
        else:
            print("[GAGAL] Server menolak heartbeat atau tidak dapat dihubungi.")
            return 1
    else:
        print(f"\nMenguji auto-register ke {server} …")
        ok, reg = register_to_server(server)
        if ok and reg.get("token"):
            print(f"[SUKSES] Terdaftar ke server! Token: {reg.get('token')}")
            print(f"Detail komputer: {reg.get('computer')}")
            return 0
        else:
            print(f"[GAGAL] Register gagal: {reg.get('error', 'server tidak merespons')}")
            return 1


def main() -> int:
    ensure_output()
    cfg = load_config()

    p = argparse.ArgumentParser(description="Ubuntu Panel Agent")
    p.add_argument("--server", default="",
                   help=f"URL server panel (default: dari {CONFIG_NAME})")
    p.add_argument("--token", default="",
                   help=f"Token komputer dari halaman Menagement Computer (default: dari {CONFIG_NAME})")
    p.add_argument("--interval", type=int, default=None,
                   help="detik antar heartbeat (default 10 / dari agent.ini)")
    p.add_argument("--setup", action="store_true",
                   help="sekali klik: pasang autostart + langsung jalan di background")
    p.add_argument("--uninstall", action="store_true",
                   help="cabut autostart + hapus salinan program (bersih total)")
    p.add_argument("--test", action="store_true",
                   help="uji diagnostik pengumpulan data & tes kirim ke server tanpa background/lock")
    p.add_argument("--update", action="store_true",
                   help="unduh versi terbaru agent dari server dan restart service")
    p.add_argument("--once-loop", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--setup-autostart", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--ensure-smb", action="store_true",
                   help="buka SMB/file-sharing sekali lalu keluar (butuh admin)")
    args = p.parse_args()

    # salinan yang berjalan dari LOCALAPPDATA (fallback user-mode) → pakai
    # folder yang sama agar marker/lock konsisten antar-run
    if platform.system() == "Windows" and os.environ.get("PANEL_AGENT_USERMODE") != "1":
        pp = (program_path() or "").lower()
        local = (os.environ.get("LOCALAPPDATA") or "").lower()
        if local and pp.startswith(local) and INSTALL_DIR_NAME.lower() in pp:
            os.environ["PANEL_AGENT_USERMODE"] = "1"

    if args.uninstall:
        return do_uninstall()

    # proses admin sekali-pakai dari elevate: pasang salinan + autostart, keluar
    if args.setup_autostart:
        server = args.server or cfg["server"] or PANEL_SERVER_INJECTED or PANEL_SERVER_EMBEDDED
        return do_setup_autostart(server)

    # urutan sumber alamat server: argumen > agent.ini > injected (download)
    # > embedded (hasil build exe) > auto-discover (UDP broadcast di LAN)
    # Saat setup dari link curl, URL yang ditanam pada script harus
    # mengalahkan URL lama di agent.ini; token lama tetap dipertahankan.
    if args.setup and not args.server and PANEL_SERVER_INJECTED:
        server = PANEL_SERVER_INJECTED
    else:
        server = (
            args.server or cfg["server"]
            or PANEL_SERVER_INJECTED or PANEL_SERVER_EMBEDDED
        )
    token = args.token or cfg["token"]
    interval = args.interval or (
        int(cfg["interval"]) if cfg["interval"].isdigit() else 10
    )
    interval = max(5, min(interval, 300))

    if args.update:
        return do_update(server)

    if args.ensure_smb:
        return do_ensure_smb()

    if args.test:
        return do_test(server, token)

    # fallback jika server localhost tidak dapat dihubungi dari PC klien
    if server and (server.startswith("http://localhost") or server.startswith("http://127.0.0.1")):
        # uji cepat apakah localhost memang aktif
        try:
            req = urllib.request.Request(server.rstrip("/") + "/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception:
            print(f"[info] server lokal ({server}) tidak merespons, mencari di LAN…")
            server = ""

    # alamat server masih kosong → auto-discover via UDP broadcast di LAN.
    # Service/boot: tunggu network online dulu, lalu retry SELAMANYA
    # (jangan pause_exit — WiFi/DHCP sering telat ~1-2 menit saat boot).
    if not server:
        if is_service_mode() or args.once_loop is False and not sys.stdin.isatty():
            print("[discover] server kosong — tunggu network online dulu…")
            wait_for_network_online(max_wait=300)
        print("[discover] mencari server panel di jaringan lokal…")
        attempt = 0
        while not server:
            attempt += 1
            found = discover_server(timeout=3.0)
            if found:
                server = found
                print(f"[ok] server ditemukan: {server}")
                save_config(server, token, interval)
                break
            print(f"[discover] percobaan {attempt} gagal, retry…")
            # service: jeda pendek lalu backoff; interaktif: 3x lalu wizard
            if not is_service_mode() and attempt >= 3:
                break
            time.sleep(5 if attempt < 6 else 30)
            if attempt % 6 == 0 and not is_service_mode():
                break
        if not server:
            # fallback: wizard interaktif (untuk non-LAN / headless).
            # Service TIDAK boleh sampai sini tanpa server — tunggu lagi
            # daripada exit agar Task Scheduler tidak perlu restart.
            if is_service_mode():
                print("[discover] belum ketemu — tunggu 60s lalu coba lagi…")
                time.sleep(60)
                return main() if not args.once_loop else 2
            if sys.stdin is not None:
                try:
                    interactive = sys.stdin.isatty()
                except Exception:
                    interactive = False
                if interactive:
                    print("Server tidak ditemukan di jaringan lokal.")
                    print("Masukkan alamat server manual:\n")
                    server = input("URL server  (mis. http://192.168.11.126:8000): ").strip()
                    if not interval and not cfg["interval"]:
                        raw = input("Interval detik [10]: ").strip()
                        interval = int(raw) if raw.isdigit() else 10
                        interval = max(5, min(interval, 300))
                    save_config(server, token, interval)
            if not server:
                return pause_exit(
                    "GAGAL: server panel tidak ditemukan.\n"
                    "  Pastikan server panel berjalan di jaringan yang sama.\n"
                    "  Atau buat file agent.ini manual:\n"
                    f"    {config_path()}\n"
                    "    [agent]\n"
                    "    server = http://IP-SERVER:8000",
                    code=2,
                )

    # dobel-klik .py di Windows → pindah ke background (tanpa jendela),
    # proses anak melanjutkan registrasi + heartbeat sendiri
    if relaunch_hidden_windows(server_known=True):
        print("[ok] agent berjalan di background — jendela ini boleh ditutup.")
        time.sleep(1.2)
        return 0

    # satu agent per PC — cek SEBELUM registrasi/wizard agar dobel-klik
    # cepat keluar dan tidak membuat entri/proses ganda
    if not acquire_single_instance():
        print("[stop] agent lain sudah berjalan di PC ini — keluar.")
        print("[info] untuk menguji status dan data agent, gunakan: python panel_agent.py --test")
        return 0

    # file yang dijalankan lebih baru dari salinan terpasang? perbarui
    refresh_installed_copy()

    # tanpa token → daftar otomatis pakai MAC address (zero-config).
    # Service/boot: retry SELAMANYA dengan backoff (network/server bisa
    # telat). Interaktif: 5x lalu pause_exit agar user bisa baca error.
    if not token:
        reg_attempt = 0
        while not token:
            reg_attempt += 1
            ok, reg = register_to_server(server)
            token = str(reg.get("token") or "")
            if ok and token:
                comp = reg.get("computer") or {}
                print(
                    f"[ok] terdaftar otomatis sebagai '{comp.get('name', '?')}' "
                    "(identitas MAC address)"
                )
                save_config(server, token, interval)
                break
            wait = min(5 * reg_attempt, 30)
            print(
                f"[warn] register gagal (percobaan {reg_attempt}): "
                f"{reg.get('error', 'server tidak merespons')} — "
                f"retry {wait}s..."
            )
            if not is_service_mode() and reg_attempt >= 5:
                return pause_exit(
                    f"GAGAL mendaftar ke {server} setelah 5 percobaan.\n"
                    "  Pastikan server panel hidup dan bisa dijangkau dari PC ini\n"
                    "  (cek kabel/WiFi, lalu firewall server untuk port 8000).",
                    code=2,
                )
            time.sleep(wait)

    if args.setup and do_setup(server, token, interval):
        return pause_exit(
            "Setup autostart gagal — agent tetap berjalan untuk sesi ini saja.", code=1,
        )

    # klik pertama apa pun (--setup tidak wajib): pasang autostart sekali,
    # klik/reboot berikutnya agent sudah terpasang permanen
    if not args.setup and not already_installed():
        try:
            do_setup(server, token, interval)
        except Exception as exc:
            print(f"[peringatan] autostart gagal dipasang: {exc}")

    try:
        return run_loop(server, token, interval, args.once_loop)
    except KeyboardInterrupt:
        print("\n[stop] agent dihentikan oleh pengguna")
        return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        ensure_output()
        traceback.print_exc()
        exit_code = 1
    sys.exit(exit_code)
