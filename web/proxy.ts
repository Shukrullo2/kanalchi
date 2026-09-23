import { NextRequest, NextResponse } from "next/server";
import { ADMIN_HOST, API_INTERNAL_URL, PLATFORM_DOMAIN } from "@/lib/config";

type TenantLite = { slug: string; primary_lang: string; status: string };
const cache = new Map<string, { at: number; value: TenantLite | null }>();
const TTL_MS = 60_000;

async function resolveTenant(host: string): Promise<TenantLite | null> {
  const hit = cache.get(host);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value;
  let value: TenantLite | null = null;
  try {
    const res = await fetch(`${API_INTERNAL_URL}/internal/tenants/by-host?host=${encodeURIComponent(host)}`, {
      cache: "no-store",
    });
    if (res.ok) value = (await res.json()) as TenantLite;
  } catch {
    // API down: fall through to the cached value if any, else unknown host
    if (hit) return hit.value;
  }
  cache.set(host, { at: Date.now(), value });
  return value;
}

export async function proxy(req: NextRequest) {
  const host = (req.headers.get("host") ?? "").split(":")[0].toLowerCase();
  const url = req.nextUrl;
  const reqHeaders = new Headers(req.headers);
  // Never trust tenant headers from the client.
  reqHeaders.delete("x-tenant-host");
  reqHeaders.delete("x-tenant-slug");
  reqHeaders.delete("x-tenant-lang");

  // Reached only when Next runs without Caddy (local dev): next.config.ts forwards /api/* to
  // FastAPI, but that proxy replaces the Host header, so the tenant host travels explicitly.
  if (url.pathname.startsWith("/api/")) {
    reqHeaders.set("x-tenant-host", host);
    return NextResponse.next({ request: { headers: reqHeaders } });
  }

  if (host === ADMIN_HOST) {
    if (url.pathname.startsWith("/admin")) return NextResponse.next({ request: { headers: reqHeaders } });
    const u = url.clone();
    u.pathname = url.pathname === "/" ? "/admin" : `/admin${url.pathname}`;
    return NextResponse.rewrite(u, { request: { headers: reqHeaders } });
  }

  const tenant = await resolveTenant(host);
  // The platform's own domain (and its www.) is the public landing page. A registered channel
  // domain always wins, so a mis-set PLATFORM_DOMAIN can never hide a channel behind it.
  // `osor.localhost` stands in for the platform domain when developing.
  const landing =
    (PLATFORM_DOMAIN && (host === PLATFORM_DOMAIN || host === `www.${PLATFORM_DOMAIN}`)) ||
    (process.env.NODE_ENV === "development" && host === "osor.localhost");
  if (!tenant && landing) {
    const u = url.clone();
    u.pathname = url.pathname === "/" ? "/landing" : `/landing${url.pathname}`;
    return NextResponse.rewrite(u, { request: { headers: reqHeaders } });
  }
  if (!tenant) {
    const u = url.clone();
    u.pathname = "/unknown-host";
    return NextResponse.rewrite(u, { request: { headers: reqHeaders } });
  }
  reqHeaders.set("x-tenant-host", host);
  reqHeaders.set("x-tenant-slug", tenant.slug);
  reqHeaders.set("x-tenant-lang", tenant.primary_lang);
  const u = url.clone();
  u.pathname = `/t/${tenant.slug}${url.pathname === "/" ? "" : url.pathname}`;
  return NextResponse.rewrite(u, { request: { headers: reqHeaders } });
}

export const config = {
  // Everything except Next internals, static files and paths Caddy routes elsewhere.
  // robots.txt / sitemap.xml / feed.xml are tenant-specific, so they must be rewritten too.
  // /api/ stays in so the dev fallback above can stamp the tenant host on it.
  matcher: ["/((?!_next/|tg/|media/|uploads/|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|webp|ico|css|js|map)$).*)"],
};
