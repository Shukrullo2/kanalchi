import "server-only";
import { cookies, headers } from "next/headers";
import { ADMIN_HOST, API_INTERNAL_URL } from "./config";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Server-side call to FastAPI. Carries the tenant host (set by proxy.ts) and the viewer's cookies. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit & { admin?: boolean } = {},
): Promise<T> {
  const h = await headers();
  const c = await cookies();
  const tenantHost = init.admin
    ? ADMIN_HOST
    : (h.get("x-tenant-host") ?? h.get("host")?.split(":")[0] ?? "");
  const res = await fetch(`${API_INTERNAL_URL}${path}`, {
    ...init,
    headers: {
      accept: "application/json",
      "x-tenant-host": tenantHost,
      cookie: c.toString(),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function apiFetchOrNull<T>(
  path: string,
  init: RequestInit & { admin?: boolean } = {},
): Promise<T | null> {
  try {
    return await apiFetch<T>(path, init);
  } catch (e) {
    // 402: the plan does not include this (the studio's writing tools); the page shows the gate.
    if (e instanceof ApiError && [401, 402, 403, 404].includes(e.status))
      return null;
    throw e;
  }
}
