import { apiFetch } from "@/lib/api";
import type { PostPage, TenantPublic } from "@/lib/types";

export async function GET() {
  const tenant = await apiFetch<TenantPublic>("/api/tenant");
  const base = `https://${tenant.domain}`;
  const urls: string[] = [`<url><loc>${base}/</loc></url>`, `<url><loc>${base}/top</loc></url>`];
  let cursor: string | null = null;
  for (let i = 0; i < 40; i++) {
    const page: PostPage = await apiFetch<PostPage>(
      `/api/posts?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    for (const p of page.items) {
      urls.push(`<url><loc>${base}/post/${p.id}</loc><lastmod>${new Date(p.edit_date ?? p.date).toISOString()}</lastmod></url>`);
    }
    cursor = page.next_cursor;
    if (!cursor) break;
  }
  const xml = `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join("")}</urlset>`;
  return new Response(xml, { headers: { "content-type": "application/xml", "cache-control": "public, max-age=3600" } });
}
