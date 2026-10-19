import clsx from "clsx";

export const ROLE_LABEL: Record<string, string> = {
  superadmin: "Superadmin",
  admin: "Admin",
  viewer: "Viewer",
};

export const ROLE_DESC: Record<string, string> = {
  superadmin: "akses penuh + kelola akun panel",
  admin: "operasional penuh (start/stop/deploy), tidak bisa kelola akun",
  viewer: "hanya melihat — semua aksi perubahan ditolak",
};

export const VALID_ROLES = ["superadmin", "admin", "viewer"] as const;

const ROLE_CLASS: Record<string, string> = {
  superadmin: "border-[#7c4dff]/50 bg-[#2a1e52] text-[#c9b3ff]",
  admin: "border-[#1d5a8f] bg-[#0d2436] text-[#8ec9ff]",
  viewer: "border-line bg-panel2 text-muted",
};

export function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
        ROLE_CLASS[role] ?? ROLE_CLASS.viewer
      }`}
    >
      {ROLE_LABEL[role] ?? role}
    </span>
  );
}

export function RoleSelect({
  value,
  onChange,
  disabled,
  className,
}: {
  value: string;
  onChange: (role: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <select
      className={clsx("input py-1 text-xs", className ?? "w-36")}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {VALID_ROLES.map((r) => (
        <option key={r} value={r}>
          {ROLE_LABEL[r]}
        </option>
      ))}
    </select>
  );
}
