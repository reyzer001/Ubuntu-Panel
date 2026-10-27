from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    # superadmin | admin | viewer
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    full_name: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # terakhir kali user logout eksplisit; ""/None = belum pernah logout (masih
    # terbuka / sesi lama). Dipakai untuk menampilkan "kapan di-off".
    logout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    computer_access: Mapped[list["UserComputerAccess"]] = relationship(
        "UserComputerAccess",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserComputerAccess(Base):
    __tablename__ = "user_computer_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    computer_id: Mapped[int] = mapped_column(
        ForeignKey("managed_computers.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="computer_access")
    computer: Mapped["ManagedComputer"] = relationship("ManagedComputer", back_populates="user_access")

    __table_args__ = ({"sqlite_autoincrement": True},)


class UserPageAccess(Base):
    """Izin akses halaman tertentu per user panel (mis. page="cctv").

    Hanya berlaku untuk role selain superadmin; superadmin selalu boleh.
    """

    __tablename__ = "user_page_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    __table_args__ = ({"sqlite_autoincrement": True},)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    username: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    target: Mapped[str] = mapped_column(String(256), default="")
    result: Mapped[str] = mapped_column(String(32), default="SUCCESS")


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # panel | directory | config | mysql | postgres
    type: Mapped[str] = mapped_column(String(16))
    # path sumber (directory/config), nama database (mysql/postgres),
    # diabaikan untuk type=panel
    source: Mapped[str] = mapped_column(String(512), default="")
    destination: Mapped[str] = mapped_column(String(512))
    # ekspresi cron 5 field; kosong = hanya manual
    schedule: Mapped[str] = mapped_column(String(64), default="")
    retention_days: Mapped[int] = mapped_column(default=7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("backup_jobs.id", ondelete="CASCADE"), nullable=True
    )
    job_name: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # RUNNING | SUCCESS | FAILED
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    size_bytes: Mapped[int] = mapped_column(default=0)
    file_path: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")


class APScanTarget(Base):
    """Subnet LAN yang dipindai pencari Akses Point."""

    __tablename__ = "ap_scan_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    cidr: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class APGroup(Base):
    """Grup Akses Point (mis. per lantai / per segmen)."""

    __tablename__ = "ap_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class AccessPoint(Base):
    """Inventory perangkat jaringan; MAC menjadi kunci identitas.

    Perangkat yang offline TETAP tersimpan — status hanya indikasi
    apakah dia terlihat di scan terakhir.
    """

    __tablename__ = "access_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    ip: Mapped[str] = mapped_column(String(45), default="")
    vendor: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    ssid: Mapped[str] = mapped_column(String(256), default="")
    # legacy kolom teks; digantikan group_id (tetap ada agar DB lama aman)
    group_name: Mapped[str] = mapped_column(String(64), default="")
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("ap_groups.id", ondelete="SET NULL"), nullable=True
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    # true bila terdeteksi/marked sebagai access point
    is_ap: Mapped[bool] = mapped_column(Boolean, default=False)
    # segment jaringan (otomatis dari subnet label: CCTV, Phone, Internet, dll.)
    segment: Mapped[str] = mapped_column(String(64), default="")
    # ONLINE | OFFLINE
    status: Mapped[str] = mapped_column(String(16), default="OFFLINE")
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class APEvent(Base):
    """Log kejadian perangkat: discovered / online / offline."""

    __tablename__ = "ap_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ap_id: Mapped[int | None] = mapped_column(
        ForeignKey("access_points.id", ondelete="CASCADE"), nullable=True
    )
    mac: Mapped[str] = mapped_column(String(17))
    ip: Mapped[str] = mapped_column(String(45), default="")
    # DISCOVERED | ONLINE | OFFLINE
    event: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class ManagedComputer(Base):
    """PC yang dimonitor lewat Panel Agent (heartbeat berkala).

    Agent berjalan di PC klien, mengirim data perangkat + latency ke
    server; status ONLINE/OFFLINE dihitung dari usia last_seen.
    """

    __tablename__ = "managed_computers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    group_name: Mapped[str] = mapped_column(String(64), default="")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(128), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    mac: Mapped[str] = mapped_column(String(128), default="")
    os_info: Mapped[str] = mapped_column(String(256), default="")
    # JSON ringkas: daftar interface tambahan {name, ip, mac}
    interfaces: Mapped[str] = mapped_column(Text, default="")
    cpu: Mapped[float | None] = mapped_column(nullable=True)
    mem: Mapped[float | None] = mapped_column(nullable=True)
    internet_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    download_mbps: Mapped[float | None] = mapped_column(nullable=True)
    upload_mbps: Mapped[float | None] = mapped_column(nullable=True)
    speed_test_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # akumulasi byte jaringan sejak sampel metrik terakhir disimpan
    net_rx_pending: Mapped[float] = mapped_column(default=0.0)
    net_tx_pending: Mapped[float] = mapped_column(default=0.0)
    agent_version: Mapped[str] = mapped_column(String(32), default="")
    # mode autostart Windows: task-scheduler (boot, semua user) |
    # hkcu-run (login-only) | system (non-Windows)
    autostart_mode: Mapped[str] = mapped_column(String(64), default="")
    # true bila SMB/file-sharing terbuka di PC (untuk share printer guest)
    smb_open: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # jalur koneksi utama: LAN | WIFI | ""
    conn_type: Mapped[str] = mapped_column(String(16), default="")
    ssid: Mapped[str] = mapped_column(String(64), default="")
    iface_name: Mapped[str] = mapped_column(String(32), default="")
    wifi_ip: Mapped[str] = mapped_column(String(45), default="")
    ap_ip: Mapped[str] = mapped_column(String(45), default="")
    ap_mac: Mapped[str] = mapped_column(String(128), default="")
    latency_srv_ms: Mapped[float | None] = mapped_column(nullable=True)
    # deteksi jalur koneksi PC→server: LAN | INTERNET | ""
    server_reach: Mapped[str] = mapped_column(String(16), default="")
    # perintah remote: restart | shutdown | update | install:<pkg> |
    # share-printer:<key> | unshare-printer:<key> | NULL; hasil eksekusi dari agent
    pending_cmd: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cmd_issued_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_cmd_result: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    # Terakhir kali IP komputer cocok dengan perangkat ONLINE di inventori
    # Access Point (hasil topologi auto-check). Status online digabung dengan
    # heartbeat: online = heartbeat AKTIF ATAU ap_seen_at masih segar.
    ap_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    user_access: Mapped[list["UserComputerAccess"]] = relationship(
        "UserComputerAccess",
        back_populates="computer",
        cascade="all, delete-orphan",
    )
    printers: Mapped[list["SharedPrinter"]] = relationship(
        "SharedPrinter",
        back_populates="computer",
        cascade="all, delete-orphan",
    )


class SharedPrinter(Base):
    """Printer yang di-share oleh sebuah PC (lewat Panel Agent).

    Identitas printer tetap terikat ke `computer_id` (bukan IP) sehingga
    tetap valid walau PC berpindah IP karena DHCP. IP terkini pemilik
    diambil dari ManagedComputer saat resolusi dilakukan.
    """

    __tablename__ = "shared_printers"

    id: Mapped[int] = mapped_column(primary_key=True)
    computer_id: Mapped[int] = mapped_column(
        ForeignKey("managed_computers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    # nama share SMB (Windows) / nama queue CUPS (Linux); kosong = belum di-share
    share_name: Mapped[str] = mapped_column(String(128), default="")
    # windows | linux | mac
    platform: Mapped[str] = mapped_column(String(16), default="")
    driver: Mapped[str] = mapped_column(String(160), default="")
    port: Mapped[str] = mapped_column(String(160), default="")
    # true bila printer sedang di-share (share_name terisi)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    computer: Mapped["ManagedComputer"] = relationship(
        "ManagedComputer", back_populates="printers"
    )

    __table_args__ = ({"sqlite_autoincrement": True},)


class CameraGroup(Base):
    """Grup kamera CCTV (mis. per gedung / per lokasi)."""

    __tablename__ = "camera_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class Camera(Base):
    """Kamera CCTV yang dikelola panel.

    Panel login sendiri ke kamera memakai daftar ``CameraCredential`` lalu
    mem-proxy snapshot/stream ke browser (browser tidak perlu login kamera).
    ``active_credential_id`` menyimpan kredensial terakhir yang berhasil.
    """

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    ip: Mapped[str] = mapped_column(String(45), default="", index=True)
    # port web (http/https) + port RTSP terpisah
    port: Mapped[int] = mapped_column(default=80)
    rtsp_port: Mapped[int] = mapped_column(default=554)
    # http | https — skema untuk URL snapshot / halaman login
    scheme: Mapped[str] = mapped_column(String(8), default="http")
    channel: Mapped[int] = mapped_column(default=1)
    # http | rtsp | onvif
    protocol: Mapped[str] = mapped_column(String(16), default="http")
    vendor: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    mac: Mapped[str] = mapped_column(String(17), default="")
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("camera_groups.id", ondelete="SET NULL"), nullable=True
    )
    # path relatif utk ambil JPEG & stream; kosong = pakai default per vendor
    snapshot_path: Mapped[str] = mapped_column(Text, default="")
    stream_path: Mapped[str] = mapped_column(Text, default="")
    # manual | auto
    source: Mapped[str] = mapped_column(String(16), default="manual")
    ap_id: Mapped[int | None] = mapped_column(
        ForeignKey("access_points.id", ondelete="SET NULL"), nullable=True
    )
    # kredensial terakhir yang berhasil (id CameraCredential)
    active_credential_id: Mapped[int | None] = mapped_column(nullable=True)
    # ONLINE | OFFLINE
    status: Mapped[str] = mapped_column(String(16), default="OFFLINE")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )

    credentials: Mapped[list["CameraCredential"]] = relationship(
        "CameraCredential",
        back_populates="camera",
        cascade="all, delete-orphan",
    )


class CameraCredential(Base):
    """Pasangan username+password untuk login ke kamera.

    Beberapa entri berurutan dicoba otomatis: mulai dari yang terakhir
    berhasil (``Camera.active_credential_id``), lalu sisanya sesuai
    ``order_index``. Password disimpan terenkripsi (Fernet).
    """

    __tablename__ = "camera_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    username: Mapped[str] = mapped_column(String(128), default="")
    password_enc: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(default=0)
    last_ok_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    camera: Mapped["Camera"] = relationship(
        "Camera", back_populates="credentials"
    )

    __table_args__ = ({"sqlite_autoincrement": True},)


class AppSetting(Base):
    """Pengaturan aplikasi global (terenkripsi bila bernilai sensitif)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    value_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class WebApp(Base):
    """Website lokal yang dijalankan lewat panel.

    Satu WebApp = satu entri di list; bisa berisi satu service saja
    atau beberapa (mis. folder backend + frontend) yang berjalan
    sebagai satu kesatuan.
    """

    __tablename__ = "web_apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    # native | docker | docker-compose
    runtime: Mapped[str] = mapped_column(String(16), default="native")
    php_version: Mapped[str] = mapped_column(String(16), default="")
    docker_image: Mapped[str] = mapped_column(String(256), default="")
    dockerfile: Mapped[str] = mapped_column(String(1024), default="")
    docker_container: Mapped[str] = mapped_column(String(128), default="")
    docker_status: Mapped[str] = mapped_column(String(32), default="")
    compose_file: Mapped[str] = mapped_column(Text, default="")   # path docker-compose.yml
    compose_project: Mapped[str] = mapped_column(String(128), default="")  # -p nama project
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class WebService(Base):
    """Satu proses dev-server di dalam WebApp (per folder + command)."""

    __tablename__ = "web_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("web_apps.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(64), default="")
    dir: Mapped[str] = mapped_column(Text, default="")
    command: Mapped[str] = mapped_column(Text, default="")
    # 0 = otomatis (ikut framework / cari port bebas)
    port: Mapped[int] = mapped_column(default=0)
    resolved_port: Mapped[int] = mapped_column(default=0)
    pid: Mapped[int | None] = mapped_column(nullable=True)
    # ONLINE | OFFLINE — diperbarui monitor loop
    status: Mapped[str] = mapped_column(String(16), default="OFFLINE")
    log_path: Mapped[str] = mapped_column(Text, default="")
    # Cloudflare Quick Tunnel — expose service ke internet
    tunnel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tunnel_pid: Mapped[int | None] = mapped_column(nullable=True)
    # auto re-expose saat tunnel mati / server restart → URL baru tiap kali
    tunnel_auto: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class MetricSample(Base):
    __tablename__ = "metric_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )
    cpu: Mapped[float] = mapped_column(default=0.0)
    ram: Mapped[float] = mapped_column(default=0.0)
    disk: Mapped[float] = mapped_column(default=0.0)
    load1: Mapped[float] = mapped_column(default=0.0)
    net_rx_rate: Mapped[float] = mapped_column(default=0.0)
    net_tx_rate: Mapped[float] = mapped_column(default=0.0)
    temp: Mapped[float | None] = mapped_column(nullable=True)


class CameraEvent(Base):
    __tablename__ = "camera_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    ip: Mapped[str] = mapped_column(String(45), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    event: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class ComputerMetricSample(Base):
    """Sampel CPU/RAM/trafik mentah dari heartbeat agent (sementara)."""

    __tablename__ = "computer_metric_samples"
    __table_args__ = (
        Index(
            "ix_computer_metric_samples_computer_ts",
            "computer_id",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    computer_id: Mapped[int] = mapped_column(
        ForeignKey("managed_computers.id", ondelete="CASCADE"),
        index=True,
    )
    cpu: Mapped[float] = mapped_column(default=0.0)
    mem: Mapped[float] = mapped_column(default=0.0)
    net_rx_bytes: Mapped[float] = mapped_column(default=0.0)
    net_tx_bytes: Mapped[float] = mapped_column(default=0.0)
    net_seconds: Mapped[float] = mapped_column(default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class ComputerMetricHourly(Base):
    """Rekap per jam CPU/RAM/trafik komputer; pengganti sampel mentah."""

    __tablename__ = "computer_metric_hourly"
    __table_args__ = (
        UniqueConstraint(
            "computer_id",
            "bucket",
            name="uq_computer_metric_hourly_computer_bucket",
        ),
        Index("ix_computer_metric_hourly_bucket", "bucket"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    computer_id: Mapped[int] = mapped_column(
        ForeignKey("managed_computers.id", ondelete="CASCADE"),
        index=True,
    )
    bucket: Mapped[datetime] = mapped_column(DateTime)
    cpu_avg: Mapped[float] = mapped_column(default=0.0)
    cpu_min: Mapped[float] = mapped_column(default=0.0)
    cpu_max: Mapped[float] = mapped_column(default=0.0)
    mem_avg: Mapped[float] = mapped_column(default=0.0)
    mem_min: Mapped[float] = mapped_column(default=0.0)
    mem_max: Mapped[float] = mapped_column(default=0.0)
    net_rx_bytes: Mapped[float] = mapped_column(default=0.0)
    net_tx_bytes: Mapped[float] = mapped_column(default=0.0)
    net_seconds: Mapped[float] = mapped_column(default=0.0)
    samples: Mapped[int] = mapped_column(default=0)


class ComputerSpeedSample(Base):
    """Hasil speed test agent untuk laporan internet.

    ``source`` membedakan tes PC -> internet publik (dipakai report) dari
    tes lama PC -> server panel. Data lama tetap disimpan, tetapi tidak
    dihitung sebagai kecepatan internet.
    """

    __tablename__ = "computer_speed_samples"
    __table_args__ = (
        UniqueConstraint(
            "computer_id",
            "tested_at",
            name="uq_computer_speed_samples_computer_tested",
        ),
        Index(
            "ix_computer_speed_samples_computer_received",
            "computer_id",
            "received_at",
        ),
        Index("ix_computer_speed_samples_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    computer_id: Mapped[int] = mapped_column(
        ForeignKey("managed_computers.id", ondelete="CASCADE"),
        index=True,
    )
    # Waktu tes menurut agent (dipakai untuk dedup heartbeat berulang).
    tested_at: Mapped[datetime] = mapped_column(DateTime)
    # Waktu server menerima hasil tes (dipakai untuk filter periode report).
    received_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    download_mbps: Mapped[float] = mapped_column(default=0.0)
    upload_mbps: Mapped[float] = mapped_column(default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="server")
