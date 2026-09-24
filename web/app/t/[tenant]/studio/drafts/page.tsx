import { DraftList } from "@/components/studio/DraftList";
import { apiFetchOrNull } from "@/lib/api";
import type { DraftOut } from "@/lib/types";

export default async function DraftsPage() {
  // Null on a plan without the writing tools; the studio layout shows the gate instead.
  const drafts = (await apiFetchOrNull<DraftOut[]>("/api/studio/drafts")) ?? [];
  return <DraftList initial={drafts} />;
}
