"use client";

/** Browser-side call to the same-origin API (Caddy routes /api/* to FastAPI). */
export async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body as { detail?: string }).detail ?? res.statusText);
  return body as T;
}

export const post = <T,>(path: string, data?: unknown) =>
  call<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
export const patch = <T,>(path: string, data: unknown) => call<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const del = <T,>(path: string) => call<T>(path, { method: "DELETE" });
