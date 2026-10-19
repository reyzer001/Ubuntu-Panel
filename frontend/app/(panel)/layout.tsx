import type { ReactNode } from "react";
import { PanelInner } from "./panel-inner";

// Render dinamis agar HTML tidak di-cache CDN (Cloudflare).
// Bawaan Next.js untuk halaman prerendered adalah
// s-maxage=31536000 — membuat user tetap melihat versi
// lama meski server sudah di-deploy ulang.
export const dynamic = "force-dynamic";

export default function PanelLayout({ children }: { children: ReactNode }) {
  return <PanelInner>{children}</PanelInner>;
}
