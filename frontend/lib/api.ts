import { useAuth } from "@/store/auth";

const BACKEND_PORT = process.env.NEXT_PUBLIC_API_PORT ?? "8000";

// Jika NEXT_PUBLIC_API_URL diset eksplisit, pakai itu.
// Jika NEXT_PUBLIC_USE_PROXY="1", gunakan same-origin (lewat Next.js rewrites).
// Selain itu, URL API mengikuti hostname browser + port backend langsung.
function resolveApiUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (process.env.NEXT_PUBLIC_USE_PROXY === "1") {
    if (typeof window !== "undefined") {
      return window.location.origin;
    }
    return "";
  }
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`;
  }
  return `http://localhost:${BACKEND_PORT}`;
}

export const API_URL = resolveApiUrl();
export const USE_PROXY = !process.env.NEXT_PUBLIC_API_URL &&
  process.env.NEXT_PUBLIC_USE_PROXY === "1";

export function wsUrl(path: string): string {
  const token = useAuth.getState().token ?? "";
  if (USE_PROXY) {
    const proto = typeof window !== "undefined"
      ? (window.location.protocol === "https:" ? "wss:" : "ws:")
      : "ws:";
    return `${proto}//${typeof window !== "undefined" ? window.location.host : "localhost"}/api${path}?token=${encodeURIComponent(token)}`;
  }
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/api${path}?token=${encodeURIComponent(token)}`;
}

// URL WS langsung ke backend (hostname browser + port backend).
// WAJIB dipakai sebagai fallback karena Next.js `rewrites` tidak
// meneruskan upgrade WebSocket, sehingga WS same-origin (/api/…)
// selalu gagal (close 1006) saat USE_PROXY=1 dan stream metrics
// mati total (gauge network 00 terus).
export function directWsUrl(path: string): string {
  const token = useAuth.getState().token ?? "";
  const proto =
    typeof window !== "undefined" && window.location.protocol === "https:"
      ? "wss:"
      : "ws:";
  const host =
    typeof window !== "undefined" ? window.location.hostname : "localhost";
  return `${proto}//${host}:${BACKEND_PORT}/api${path}?token=${encodeURIComponent(token)}`;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  options: RequestInit & { elevated?: string } = {}
): Promise<T> {
  const { elevated, ...rest } = options;
  const token = useAuth.getState().token;
  const headers: Record<string, string> = {
    ...((rest.headers as Record<string, string>) ?? {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (rest.body) headers["Content-Type"] = "application/json";
  if (elevated) {
    const et = useAuth.getState().getElevated(elevated);
    if (et) headers["X-Elevated-Token"] = et;
  }

  const res = await fetch(`${API_URL}/api${path}`, {
    ...rest,
    headers,
    cache: "no-store",
  });

  if (res.status === 401) {
    useAuth.getState().logout();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // keep default message
    }
    throw new ApiError(res.status, detail);
  }

  return (res.status === 204 ? (undefined as T) : (await res.json()) as T);
}

// URL media (snapshot/stream) untuk <img>: token sesi + token step-up
// dikirim lewat query karena <img> tidak bisa mengirim header.
export function mediaUrl(path: string, scope: string): string {
  const token = useAuth.getState().token ?? "";
  const et = useAuth.getState().getElevated(scope) ?? "";
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (et) params.set("et", et);
  const q = params.toString();
  return `${API_URL}/api${path}${q ? `?${q}` : ""}`;
}

// Unduh file (mis. arsip backup) dengan header auth, lalu simpan via <a download>.
export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const token = useAuth.getState().token;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}/api${path}`, { headers });
  if (res.status === 401) {
    useAuth.getState().logout();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status})`);

  const blob = await res.blob();
  const match = res.headers
    .get("content-disposition")
    ?.match(/filename="?([^";]+)"?/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? fallbackName;
  a.click();
  URL.revokeObjectURL(url);
}

// Upload multipart — bypass Next.js proxy, kirim langsung ke backend.
// Next.js rewrite proxy sering timeout/ERROR pada multipart besar.
function uploadBaseUrl(): string {
  if (USE_PROXY) {
    return typeof window !== "undefined" ? window.location.origin : "";
  }
  if (typeof window === "undefined") return `http://localhost:${BACKEND_PORT}`;
  return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`;
}

export function apiUpload<T>(
  path: string,
  form: FormData,
  onProgress?: (pct: number) => void
): Promise<T> {
  const token = useAuth.getState().token;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${uploadBaseUrl()}/api${path}`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress)
        onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status === 401) {
        useAuth.getState().logout();
        if (typeof window !== "undefined") window.location.href = "/login";
        reject(new ApiError(401, "Session expired"));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch {
          resolve(undefined as T);
        }
        return;
      }
      let msg = `Upload failed (${xhr.status})`;
      try {
        const detail = JSON.parse(xhr.responseText)?.detail;
        if (detail) msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      } catch {
        // keep default message
      }
      reject(new ApiError(xhr.status, msg));
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error saat upload"));
    xhr.send(form);
  });
}
