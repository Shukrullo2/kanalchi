import { apiFetch } from "@/lib/api";
import type { TenantPublic } from "@/lib/types";

export async function GET() {
  const tenant = await apiFetch<TenantPublic>("/api/tenant");
  const body = [
    "User-agent: *",
    "Disallow: /studio",
    "Disallow: /chat",
    // Every tag combination is a distinct search or graph URL: an endless, expensive crawl.
    // Tag and post pages carry the same content and are what the sitemap lists.
    "Disallow: /search",
    "Disallow: /graph",
    "Disallow: /api/",
    "Allow: /",
    "",
    `Sitemap: https://${tenant.domain}/sitemap.xml`,
  ].join("\n");
  return new Response(body, { headers: { "content-type": "text/plain" } });
}
