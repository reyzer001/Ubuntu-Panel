export interface Metrics {
  time: string;
  cpu: number;
  cpu_kernel: number;
  cpu_cores: number;
  ram: number;
  ram_used: number;
  ram_total: number;
  mem_active: number;
  mem_inactive: number;
  mem_cached: number;
  swap: number;
  disk: number;
  disk_used: number;
  disk_total: number;
  load1: number;
  load5: number;
  load15: number;
  uptime: number;
  process_count: number;
  net_rx_rate: number;
  net_tx_rate: number;
  disk_read_rate: number;
  disk_write_rate: number;
  net_interfaces?: IfaceRate[];
}

export interface SystemInfo {
  hostname: string;
  os: string;
  kernel: string;
  arch: string;
  cpu_model: string;
  cpu_cores: number;
  ram_total: number;
  boot_time: string;
  primary_ip: string;
}

export interface ServiceInfo {
  name: string;
  unit: string;
  description: string;
  status: string;
  enabled: string;
}

export interface ProcessInfo {
  pid: number;
  user: string;
  name: string;
  cpu: number;
  memory: number;
  memory_percent: number;
}

export interface FilesystemInfo {
  device: string;
  mountpoint: string;
  fstype: string;
  total: number;
  used: number;
  free: number;
  percent: number;
  inodes_percent: number | null;
}

export interface InterfaceInfo {
  interface: string;
  up: boolean;
  ip: string;
  mac: string;
  speed_mbps: number;
  rx_bytes: number;
  tx_bytes: number;
  rx_rate?: number;
  tx_rate?: number;
}

export interface IfaceRate {
  interface: string;
  rx_rate: number;
  tx_rate: number;
}

export interface NetHistoryPoint {
  t: string;
  rates: Record<string, IfaceRate>;
}

export interface PortInfo {
  port: number;
  protocol: string;
  address: string;
  process: string;
}

export interface PanelUser {
  id: number;
  username: string;
  role: "superadmin" | "admin" | "viewer";
  full_name: string;
  email: string;
  phone: string;
  created_at: string;
  last_login_at?: string | null;
  last_seen_at?: string | null;
  logout_at?: string | null;
  online?: boolean;
}

export interface ManagedComputer {
  id: number;
  name: string;
  group_name: string;
  hostname: string;
  ip: string;
  mac: string;
  merk: string;
  os_info: string;
  interfaces: { name: string; ip: string; mac: string }[];
  cpu: number | null;
  mem: number | null;
  internet_up: boolean | null;
  latency_ms: number | null;
  download_mbps: number | null;
  upload_mbps: number | null;
  speed_test_at: string | null;
  agent_version: string;
  autostart_mode: string;
  conn_type: string;
  ssid: string;
  iface_name: string;
  wifi_ip: string;
  ap_ip: string;
  ap_mac: string;
  latency_srv_ms: number | null;
  server_reach: string;
  pending_cmd: string | null;
  cmd_issued_at: string | null;
  last_cmd_result: string;
  status: "online" | "offline" | "waiting";
  online_source: "heartbeat" | "ap" | "both" | "none";
  ap_seen_at: string | null;
  heartbeat_age: number | null;
  last_seen: string | null;
  created_at: string;
}

export interface PresenceCheck {
  ip: string;
  ping_ms: number | null;
  neigh_state: string | null;
  neigh_mac: string | null;
  same_lan: boolean;
}

export interface APPresenceMatch {
  mac: string;
  ip: string;
  model: string;
  is_ap: boolean;
  status: string;
  last_seen: string | null;
}

export interface PresenceResult {
  verdict: "alive" | "dead" | "unknown" | "no_ip";
  summary: string;
  mac_db: string;
  checks: PresenceCheck[];
  ap_matches: APPresenceMatch[];
}

export interface BulkPresenceComputer {
  id: number;
  name: string;
  status_agent: "online" | "offline" | "waiting";
  verdict: "alive" | "dead" | "unknown" | "no_ip";
  summary: string;
  color: "green" | "yellow" | "red";
  ping: PresenceCheck[];
}

export interface BulkPresenceResult {
  overall: "green" | "yellow" | "red";
  label: string;
  counts: { total: number; green: number; yellow: number; red: number };
  computers: BulkPresenceComputer[];
}

export interface TopologyStatus {
  interval: number;
  ap_ttl: number;
  running: boolean;
  last_run: string | null;
  last_result: string;
}

export interface TopologyUpdated {
  id: number;
  name: string;
  matched: string;
  ip_from: string;
  ip_to: string;
  ap_ip: string;
  ap_status: string;
}

export interface TopologyResult {
  checked: number;
  online_ap: number;
  updated_ip: number;
  updated: TopologyUpdated[];
  last_run: string;
  /** Hint tambahan, mis. inventory AP kosong sehingga 0 online belum tentu PC mati. */
  note?: string;
}

export interface ContainerInfo {
  name: string;
  image: string;
  status: string;
  cpu: string;
  memory: string;
  ports: string;
  host_ports: number[];
}

export interface ContainerPortMap {
  container: string;
  host_ip: string | null;
  host_port: number | null;
}

export interface ContainerDetail {
  name: string;
  image: string;
  status: string;
  health: string | null;
  command: string;
  entrypoint: string;
  created: string;
  started_at: string | null;
  uptime: string | null;
  restart_policy: string;
  ports: string;
  host_ports: number[];
  port_map: ContainerPortMap[];
  processes: { titles: string[]; rows: string[][] };
  networks: string[];
  mounts: { source: string; destination: string }[];
  env_keys: string[];
}

export interface FirewallRule {
  port: string;
  protocol: string;
  action: string;
  from: string;
}

export interface FirewallStatus {
  available: boolean;
  enabled: boolean;
  rules: FirewallRule[];
  error: string;
}

export interface UserAccount {
  username: string;
  uid: number;
  group: string;
  home: string;
  shell: string;
  status: string;
}

export interface LogEntry {
  time: string;
  level: string;
  source: string;
  message: string;
}

export interface HistoryPoint {
  t: string;
  cpu: number;
  ram: number;
  rx: number;
  tx: number;
}

export interface BackupRun {
  id: number;
  job_id: number | null;
  job_name: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  size_bytes: number;
  file_path: string;
  message: string;
}

export interface BackupJob {
  id: number;
  name: string;
  type: string;
  source: string;
  destination: string;
  schedule: string;
  retention_days: number;
  enabled: boolean;
  last_run: BackupRun | null;
  next_run: string | null;
}

export interface MaintenanceStatus {
  root_disk: { total: number; used: number; percent: number };
  journal_usage: string;
  journal_bytes: number | null;
  apt_cache_bytes: number;
  upgradable: number | null;
  is_root: boolean;
  os_user?: string;
  sudo_nopasswd?: boolean;
}

export interface MaintenanceTask {
  id: string;
  kind: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  returncode: number | null;
  output: string[];
  errors?: string[];
  warnings?: string[];
}

export interface DbCleanupStatus {
  retention_days: {
    audit_logs: number;
    ap_events: number;
    backup_runs: number;
  };
  interval_seconds: number;
  rows: {
    audit_logs: number;
    ap_events: number;
    backup_runs: number;
  };
}

export interface DbCleanupResult {
  deleted: {
    audit_logs: number;
    ap_events: number;
    backup_runs: number;
  };
  retention_days: number;
}

export interface AccessPoint {
  id: number;
  mac: string;
  ip: string;
  vendor: string;
  model: string;
  ssid: string;
  group_id: number | null;
  group_name: string;
  pinned: boolean;
  notes: string;
  is_ap: boolean;
  segment: string;
  status: string;
  first_seen: string;
  last_seen: string;
}

export interface APGroup {
  id: number;
  name: string;
  count: number;
}

export interface APScanProgress {
  running: boolean;
  cidr?: string;
  target_index?: number;
  targets_total?: number;
  done?: number;
  total?: number;
  found?: number;
  phase?: "sweep" | "arp" | "probe" | "write";
}

export interface APSummary {
  total: number;
  online: number;
  offline: number;
  aps: number;
  pinned: number;
  scanning: boolean;
  scan_progress?: APScanProgress;
  last_scan: string | null;
  last_result: string;
  wifi_iface: string;
  ping_interval?: number;
  offline_after?: number;
}

export interface APEvent {
  id: number;
  mac: string;
  ip: string;
  event: string;
  timestamp: string;
}

export interface APScanTarget {
  id: number;
  cidr: string;
  label: string;
}

export interface WebService {
  id: number;
  label: string;
  dir: string;
  command: string;
  port: number;
  resolved_port: number;
  pid: number | null;
  status: "ONLINE" | "OFFLINE";
  tunnel_url: string | null;
  tunnel_pid: number | null;
  tunnel_auto?: boolean;
  dir_exists?: boolean;
  dir_size?: number;
}

export interface ServiceTunnelCheck {
  running: boolean;
  running_pid: number | null;
  url: string | null;
  reachable: boolean | null;
  status_code: number | null;
  error: string | null;
  log_tail: string[];
}

export interface ServiceCheckResult {
  service: {
    pid: number | null;
    pid_alive: boolean;
    status: "ONLINE" | "OFFLINE";
    resolved_port: number;
    port_listening: boolean;
    log_tail: string[];
  };
  tunnel: ServiceTunnelCheck;
}

export interface ComposeService {
  name: string;
  status: "ONLINE" | "OFFLINE";
  ports: string[];
  health: string;
}

export interface ComposeStatus {
  online: number;
  total: number;
  /** Alasan compose tidak bisa dibaca; kosong bila sehat. */
  error?: string;
  services: ComposeService[];
}

export interface WebApp {
  id: number;
  name: string;
  runtime: "native" | "docker" | "docker-compose";
  php_version: string;
  docker_image: string;
  dockerfile: string;
  docker_container: string;
  docker_status: string;
  compose_file: string;
  compose_project: string;
  created_at: string;
  services: WebService[];
  online: number;
  total: number;
  compose_status?: ComposeStatus;
  /** Error compose yang dulu ditelan backend jadi OFFLINE tanpa alasan. */
  compose_error?: string;
}

export interface WebsiteDetail extends WebApp {
  container_detail?: ContainerDetail | null;
}

/** Project docker-compose yang jalan tapi belum terdaftar di panel. */
export interface UnmanagedProject {
  kind: "docker-compose";
  project: string;
  project_dir: string;
  compose_file: string;
  running_services: string[];
  ports: string[];
  container_count: number;
  name_suggest: string;
}

export interface ReconcileResult {
  unmanaged: UnmanagedProject[];
  registered_count: number;
  running_count: number;
}

export interface AdoptResult {
  ok: boolean;
  id: number;
  name: string;
  compose_status?: ComposeStatus;
}

export interface SyncResult {
  label: string;
  error: string | null;
  success?: boolean;
  files_synced?: number;
  target?: string;
  output?: string;
}

export interface DeployJob {
  id: string;
  app_id: number;
  service_id: number;
  service_label: string;
  dir: string;
  status: "running" | "done" | "failed";
  stage: string;
  progress: number;
  log: string[];
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: string[];
}

export interface PhpDepInfo {
  version: string;
  extensions: string[];
  packages: string[];
}

export interface NodeDepInfo {
  version: string | null;
  package_manager: string;
  manager_version: string | null;
}

export interface PythonDepInfo {
  version: string | null;
  packages: string[];
}

export interface DependencyInfo {
  label: string;
  dir: string;
  error?: string;
  language: string;
  php: PhpDepInfo | null;
  node: NodeDepInfo | null;
  python: PythonDepInfo | null;
  frameworks: string[];
  services: string[];
  env_files: string[];
  dockerfile: boolean;
}

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  is_symlink: boolean;
  size: number;
  mode: string;
  mtime: number;
}

export interface DirListing {
  path: string;
  parent: string | null;
  entries: FileEntry[];
  free: number | null;
}

export interface AgentArtifactInfo {
  available: boolean;
  filename?: string | null;
  size?: number | null;
  mtime?: string | null;
}

export interface AgentArtifacts {
  version: string;
  windows: AgentArtifactInfo;
  linux: AgentArtifactInfo;
}

export interface PrinterConnectCommand {
  share_path: string;
  powershell?: string;
  cmd?: string;
  shell?: string;
}

export interface SharedPrinter {
  id: number;
  computer_id: number;
  owner_name: string;
  owner_ip: string;
  owner_mac: string;
  owner_online: boolean;
  owner_status: "online" | "offline" | "waiting";
  name: string;
  share_name: string;
  share_path: string;
  platform: string;
  driver: string;
  port: string;
  is_shared: boolean;
  online: boolean;
  updated_at: string;
  connect?: PrinterConnectCommand;
}

export interface PrinterListResult {
  printers: SharedPrinter[];
  total: number;
  shared: number;
}

export interface CameraCredential {
  id: number;
  username: string;
  order_index: number;
  active: boolean;
  last_ok_at: string | null;
}

export interface Camera {
  id: number;
  name: string;
  ip: string;
  port: number;
  rtsp_port: number;
  scheme: string;
  channel: number;
  protocol: string;
  vendor: string;
  model: string;
  mac: string;
  group_id: number | null;
  group_name: string;
  snapshot_path: string;
  stream_path: string;
  source: "manual" | "auto";
  ap_id: number | null;
  active_credential_id: number | null;
  status: "ONLINE" | "OFFLINE";
  notes: string;
  web_url: string;
  last_seen: string | null;
  credentials: CameraCredential[];
}

export interface CameraSummary {
  total: number;
  online: number;
  offline: number;
  ping_interval: number;
  offline_after: number;
}

export interface CameraGroup {
  id: number;
  name: string;
  count: number;
}

export interface DiscoverableCamera {
  ap_id: number;
  ip: string;
  mac: string;
  vendor: string;
  model: string;
  segment: string;
  status: string;
}

export interface PageAccessUser {
  username: string;
  role: string;
  page_access: string[];
}

export interface PrinterResolveResult {
  owner: {
    id: number;
    name: string;
    ip: string;
    hostname: string;
    online: boolean;
    status: string;
  };
  printers: SharedPrinter[];
  total: number;
}
