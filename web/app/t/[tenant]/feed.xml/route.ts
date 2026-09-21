import { apiFetch } from "@/lib/api";
import type { PostPage, TenantPublic } from "@/lib/types";

function esc(s: string) {
  return s.replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[c]!);
}

export async function GET() {
  const [tenant, page] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<PostPage>("/api/posts?limit=50"),
  ]);
  const base = `https://${tenant.domain}`;
  const items = page.items
    .map((p) => {
      const title = p.title ?? (p.text || "post").replace(/\s+/g, " ").slice(0, 80);
      return `<item><title>${esc(title)}</title><link>${base}/post/${p.id}</link><guid isPermaLink="true">${base}/post/${p.id}</guid><pubDate>${new Date(p.date).toUTCString()}</pubDate><description>${esc(p.html ?? p.text)}</description></item>`;
    })
    .join("");
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>${esc(tenant.title)}</title><link>${base}</link><description>${esc(tenant.about ?? tenant.title)}</description><language>${tenant.primary_lang}</language>${items}</channel></rss>`;
  return new Response(xml, {
    headers: { "content-type": "application/rss+xml; charset=utf-8", "cache-control": "public, max-age=600" },
  });
}
