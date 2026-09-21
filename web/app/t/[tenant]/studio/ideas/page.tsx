import { IdeaBoard } from "@/components/studio/IdeaBoard";
import { apiFetch } from "@/lib/api";
import type { IdeaOut } from "@/lib/types";

export default async function IdeasPage() {
  const ideas = await apiFetch<IdeaOut[]>("/api/studio/ideas");
  return <IdeaBoard initial={ideas} />;
}
