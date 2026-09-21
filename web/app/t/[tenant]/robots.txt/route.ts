import { apiFetch } from "@/lib/api";
import type { TenantPublic } from "@/lib/types";

export async function GET() {
  const tenant = await apiFetch<TenantPublic>("/api/tenant");
  const body = [
    "User-agent: *",
    "Disallow: /studio",
    "Disallow: /chat",
    "Allow: /",
    "",
    `Sitemap: https://${tenant.domain}/sitemap.xml`,
  ].join("\n");
  return new Response(body, { headers: { "content-type": "text/plain" } });
}
