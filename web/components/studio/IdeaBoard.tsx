"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { CloseIcon } from "@/components/Icons";
import { call, del, patch, post } from "@/lib/client";
import type { IdeaOut } from "@/lib/types";

const COLUMNS = ["inbox", "researching", "drafting", "scheduled", "published"] as const;

/** An empty column should say what to do, not describe its own emptiness. */
const EMPTY = {
  inbox: "inboxEmpty",
  researching: "researchingEmpty",
  drafting: "draftingEmpty",
  scheduled: "scheduledEmpty",
  published: "publishedEmpty",
} as const;

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function IdeaBoard({ initial }: { initial: IdeaOut[] }) {
  const t = useTranslations("studio.ideas");
  const router = useRouter();
  const [ideas, setIdeas] = useState(initial);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setIdeas(await call<IdeaOut[]>("/api/studio/ideas"));
  }

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      // A move is applied optimistically; if the server refused it, put the board back.
      await refresh().catch(() => undefined);
    }
  }

  async function move(id: number, status: IdeaOut["status"]) {
    // Optimistic: the card follows the cursor immediately, the server catches up.
    setIdeas((prev) => prev.map((i) => (i.id === id ? { ...i, status } : i)));
    await run(() => patch(`/api/studio/ideas/${id}`, { status }));
  }

  async function draftFrom(idea: IdeaOut) {
    setError(null);
    try {
      const draft = await post<{ id: number }>("/api/studio/drafts", {
        title: idea.title,
        // The body is plain text; it must not be read as markup.
        html: idea.body ? escapeHtml(idea.body).replace(/\n/g, "<br>") : "",
        idea_id: idea.id,
      });
      await patch(`/api/studio/ideas/${idea.id}`, { status: "drafting" });
      router.push(`/studio/drafts/${draft.id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          void run(async () => {
            await post("/api/studio/ideas", { title: title.trim() });
            setTitle("");
          });
        }}
        className="flex gap-2"
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("placeholder")}
          className="input-field"
        />
        <button className="btn-primary px-4">{t("add")}</button>
      </form>

      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}

      <div className="mt-6 grid gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-5">
        {COLUMNS.map((column) => {
          const items = ideas.filter((i) => i.status === column);
          const over = dragging !== null;
          return (
            <section
              key={column}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragging !== null) void move(dragging, column);
                setDragging(null);
              }}
              className={`rounded-lg border border-dashed p-1 transition-colors ${
                over ? "border-border-strong bg-surface-2" : "border-transparent"
              }`}
            >
              <h2 className="mb-2 flex items-baseline justify-between gap-2 border-b pb-1.5 text-[0.8125rem]">
                <span className="font-medium">{t(column)}</span>
                <span className="tnum text-xs text-muted-foreground">{items.length}</span>
              </h2>
              <ul className="space-y-1.5">
                {items.map((idea) => (
                  <li
                    key={idea.id}
                    draggable
                    onDragStart={() => setDragging(idea.id)}
                    onDragEnd={() => setDragging(null)}
                    className="panel group cursor-grab p-2.5 active:cursor-grabbing"
                  >
                    <div className="flex items-start gap-2">
                      <p className="min-w-0 flex-1 text-sm">{idea.title}</p>
                      {idea.status !== "published" ? (
                        <button
                          onClick={() => void move(idea.id, "dropped")}
                          className="text-xs text-muted-foreground opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                          title={t("drop")}
                        >
                          {t("drop")}
                        </button>
                      ) : null}
                      <button
                        onClick={() => void run(() => del(`/api/studio/ideas/${idea.id}`))}
                        className="text-muted-foreground opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                        aria-label={t("delete", { title: idea.title })}
                      >
                        <CloseIcon size={13} />
                      </button>
                    </div>
                    {idea.body ? (
                      <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{idea.body}</p>
                    ) : null}
                    {idea.status !== "published" ? (
                      <button
                        onClick={() => void draftFrom(idea)}
                        className="mt-2 text-xs text-primary opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                      >
                        {t("writeDraft")}
                      </button>
                    ) : null}
                  </li>
                ))}
                {items.length === 0 ? (
                  <li className="px-1 py-5 text-xs text-muted-foreground">{t(EMPTY[column])}</li>
                ) : null}
              </ul>
            </section>
          );
        })}
      </div>

      {ideas.some((i) => i.status === "dropped") ? (
        <section className="mt-8 border-t pt-4">
          <h2 className="mb-2 text-[0.8125rem] font-medium text-muted-foreground">{t("dropped")}</h2>
          <ul className="flex flex-wrap gap-2">
            {ideas
              .filter((i) => i.status === "dropped")
              .map((idea) => (
                <li key={idea.id} className="chip flex items-center gap-2">
                  <span className="max-w-[16rem] truncate">{idea.title}</span>
                  <button onClick={() => void move(idea.id, "inbox")} className="text-primary">
                    {t("restore")}
                  </button>
                </li>
              ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
