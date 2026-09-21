import { DraftList } from "@/components/studio/DraftList";
import { apiFetch } from "@/lib/api";
import type { DraftOut } from "@/lib/types";

export default async function DraftsPage() {
  const drafts = await apiFetch<DraftOut[]>("/api/studio/drafts");
  return <DraftList initial={drafts} />;
}
