"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusDot } from "@/components/admin/StatusDot";
import { ProposalPreview } from "@/components/taxonomy/ProposalPreview";
import { call, post } from "@/lib/client";
import type { TaxonomyPreview, TaxonomyVersionOut } from "@/lib/types";

const WORDS = {
  newTags: (n: number) => `${n} new`,
  keptTags: (n: number) => `${n} kept`,
  droppedTags: (n: number) => `${n} dropped`,
};

/** Index versions: the live one, proposals waiting for a decision, and what each would change. */
export function TaxonomyVersions({
  tenantId,
  versions,
  activeId,
}: {
  tenantId: number;
  versions: TaxonomyVersionOut[];
  activeId: number | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<number | null>(null);
  const [preview, setPreview] = useState<Record<number, TaxonomyPreview>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const base = `/api/admin/tenants/${tenantId}/taxonomy`;

  async function show(id: number) {
    if (open === id) return setOpen(null);
    setOpen(id);
    if (!preview[id]) {
      try {
        setPreview((p) => ({ ...p }));
        const data = await call<TaxonomyPreview>(`${base}/${id}`);
        setPreview((p) => ({ ...p, [id]: data }));
      } catch (e) {
        setNote((e as Error).message);
      }
    }
  }

  async function apply(id: number) {
    setBusy(true);
    setNote(null);
    try {
      await post(`${base}/${id}/apply`);
      setNote("Applying in the background; the version turns live when the re-filing finishes.");
      router.refresh();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-surface overflow-hidden">
      <h2 className="border-b px-4 py-3 text-sm font-medium">Index versions</h2>
      {versions.length === 0 ? (
        <p className="p-6 text-sm text-muted-foreground">No index built yet; it follows the first extraction.</p>
      ) : (
        <ul className="divide-y text-sm">
          {versions.map((v) => {
            const stats = Object.values(v.stats);
            const tags = stats.reduce((n, s) => n + (s.tags ?? 0), 0);
            return (
              <li key={v.id} className="px-4 py-2.5">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusDot status={v.status === "applied" ? "active" : v.status === "proposed" ? "queued" : v.status === "building" || v.status === "applying" ? "running" : "archived"} />
                  <span className="font-medium">version {v.version_no}</span>
                  <span className="text-xs text-muted-foreground">
                    {v.status}
                    {v.id === activeId ? " · live" : ""}
                    {tags ? ` · ${tags} tags` : ""} · ${v.cost_usd.toFixed(2)}
                    {v.built_at ? ` · ${v.built_at.slice(0, 10)}` : ""}
                  </span>
                  <span className="ml-auto flex items-center gap-2">
                    {v.status === "proposed" || v.status === "applied" ? (
                      <button onClick={() => void show(v.id)} className="link-quiet text-xs">
                        {open === v.id ? "Hide" : "What changes"}
                      </button>
                    ) : null}
                    {v.status === "proposed" ? (
                      <button disabled={busy} onClick={() => void apply(v.id)} className="btn-primary py-1 text-xs">
                        Apply
                      </button>
                    ) : null}
                  </span>
                </div>
                {open === v.id ? (
                  preview[v.id] ? (
                    <div className="mt-2">
                      <ProposalPreview preview={preview[v.id]} locale="en" words={WORDS} />
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-muted-foreground">Loading…</p>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {note ? <p className="border-t px-4 py-2 text-xs text-muted-foreground">{note}</p> : null}
    </section>
  );
}
