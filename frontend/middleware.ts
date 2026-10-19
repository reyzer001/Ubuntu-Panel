import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// HTML pages harus selalu revalidate agar deploy baru langsung
// terasa di balik CDN (Cloudflare). Next.js secara bawaan
// mengirim s-maxage=31536000 pada halaman prerendered,
// sehingga user bisa melihat versi lama meski server sudah baru.
export function middleware(request: NextRequest) {
  const res = NextResponse.next();
  if (!request.nextUrl.pathname.startsWith("/_next/static")) {
    res.headers.set("Cache-Control", "no-cache");
  }
  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico).*)"],
};
