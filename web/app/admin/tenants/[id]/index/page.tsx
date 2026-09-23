import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeftIcon } from "@/components/Icons";
import { TagManager } from "@/components/admin/TagManager";
import { TaxonomyVersions } from "@/components/admin/TaxonomyVersions";
import { apiFetchOrNull } from "@/lib/api";
import { dimensionLabel } from "@/lib/labels";
import type { AdminTenant, DimensionOut, PendingTag, TagOut, TaxonomyVersionOut } from "@/lib/types";

type Props = { params: Promise<{ id: string }> };

export const dynamic = "force-dynamic";

/** A channel's index: what is waiting to be filed, what is live, what a rebuild proposes. */
export default async function TenantIndexPage({ params }: Props) {
  const { id } = await params;
  const base = `/api/admin/tenants/${id}`;
  const [tenant, pending, tags, hidden, dimensions, versions] = await Promise.all([
    apiFetchOrNull<AdminTenant>(base, { admin: true }),
    apiFetchOrNull<PendingTag[]>(`${base}/tags/pending`, { admin: true }),
    apiFetchOrNull<TagOut[]>(`${base}/tags?limit=300`, { admin: true }),
    apiFetchOrNull<TagOut[]>(`${base}/tags/hidden`, { admin: true }),
    apiFetchOrNull<DimensionOut[]>(`${base}/dimensions`, { admin: true }),
    apiFetchOrNull<TaxonomyVersionOut[]>(`${base}/taxonomy`, { admin: true }),
  ]);
  if (!tenant) notFound();

  const locale = tenant.primary_lang;
  const groups = Object.fromEntries((dimensions ?? []).map((d) => [d.key, dimensionLabel(d, locale)]));
  const activeId = (versions ?? []).find((v) => v.status === "applied")?.id ?? null;

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/tenants/${tenant.id}`} className="link-quiet mb-2 inline-flex items-center gap-1.5 text-sm">
          <ArrowLeftIcon size={14} /> {tenant.domain}
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">Index</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The tags readers browse by. Labels are shown in the channel&apos;s language ({locale}).
        </p>
      </div>

      <TaxonomyVersions tenantId={tenant.id} versions={versions ?? []} activeId={activeId} />

      <TagManager
        tenantId={tenant.id}
        pending={pending ?? []}
        tags={tags ?? []}
        hidden={hidden ?? []}
        locale={locale}
        groups={groups}
      />
    </div>
  );
}
