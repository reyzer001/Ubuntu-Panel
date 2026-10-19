"use client";

import { useMemo, useState } from "react";

export type SortDir = "asc" | "desc";

export type SortAccessors<T> = Record<string, (row: T) => string | number>;

/** Hook sort tabel: klik header untuk ganti kolom, klik lagi ubah arah. */
export function useTableSort<T>(
  rows: T[],
  accessors: SortAccessors<T>,
  defaultKey?: string,
  defaultDir: SortDir = "asc",
) {
  const [key, setKey] = useState<string | null>(defaultKey ?? null);
  const [dir, setDir] = useState<SortDir>(defaultDir);

  const sorted = useMemo(() => {
    const get = key ? accessors[key] : undefined;
    if (!key || !get) return rows;
    return [...rows].sort((a, b) => {
      const va = get(a);
      const vb = get(b);
      let c: number;
      if (typeof va === "number" && typeof vb === "number") {
        c = va - vb;
      } else {
        c = String(va)
          .toLowerCase()
          .localeCompare(String(vb).toLowerCase(), undefined, { numeric: true });
      }
      return dir === "asc" ? c : -c;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, key, dir]);

  const toggle = (k: string) => {
    if (k === key) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setKey(k);
      setDir("asc");
    }
  };

  return { sorted, key, dir, toggle };
}

/** <th> yang bisa diklik untuk mengurutkan kolom. */
export function SortTh({
  label,
  k,
  active,
  dir,
  onToggle,
  className = "",
}: {
  label: React.ReactNode;
  k: string;
  active: boolean;
  dir: SortDir;
  onToggle: (k: string) => void;
  className?: string;
}) {
  return (
    <th className={className}>
      <button
        type="button"
        className="inline-flex cursor-pointer items-center gap-1 select-none hover:text-ok"
        onClick={() => onToggle(k)}
        title="Click to sort"
      >
        {label}
        <span className="text-[9px] opacity-70">
          {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}
