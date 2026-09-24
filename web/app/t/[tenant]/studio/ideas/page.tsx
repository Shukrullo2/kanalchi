import { IdeaBoard } from "@/components/studio/IdeaBoard";
import { apiFetchOrNull } from "@/lib/api";
import type { IdeaOut } from "@/lib/types";

export default async function IdeasPage() {
  // Null on a plan without the writing tools; the studio layout shows the gate instead.
  const ideas = (await apiFetchOrNull<IdeaOut[]>("/api/studio/ideas")) ?? [];
  return <IdeaBoard initial={ideas} />;
}
