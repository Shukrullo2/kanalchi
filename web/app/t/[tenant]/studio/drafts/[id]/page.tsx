import { notFound } from "next/navigation";
import { DraftEditor } from "@/components/studio/DraftEditor";
import { apiFetchOrNull } from "@/lib/api";
import type { DraftOut, StudioSettings } from "@/lib/types";

type Props = { params: Promise<{ id: string }> };

export default async function DraftPage({ params }: Props) {
  const { id } = await params;
  const [draft, settings] = await Promise.all([
    apiFetchOrNull<DraftOut>(`/api/studio/drafts/${id}`),
    apiFetchOrNull<StudioSettings>("/api/studio/settings"),
  ]);
  if (!draft) notFound();
  return <DraftEditor initial={draft} botUsername={settings?.bot_username ?? null} />;
}
