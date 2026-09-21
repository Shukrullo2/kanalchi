"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CloseIcon } from "@/components/Icons";
import { call, del, patch, post } from "@/lib/client";
import type { IdeaOut } from "@/lib/types";

const COLUMNS: { key: IdeaOut["status"]; label: string }[] = [
  { key: "inbox", label: "Caught" },
  { key: "researching", label: "Looking into it" },
  { key: "drafting", label: "Being written" },
  { key: "published", label: "Sent" },
];

/** An empty column should say what to do, not describe its own emptiness. */
const EMPTY: Record<string, string> = {
  inbox: "Anything you jot down lands here.",
  researching: "Drag an idea here while you dig into it.",
  drafting: "Ideas you have started writing show up here.",
  published: "Ideas that made it to the channel.",
};

export function IdeaBoard({ initial }: { initial: IdeaOut[] }) {
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
        html: idea.body ? idea.body.replace(/\n/g, "<br>") : "",
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
          placeholder="Jot down an idea…"
          className="input-field"
        />
        <button className="btn-primary px-4">Add</button>
      </form>

      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}

      <div className="mt-6 grid gap-x-5 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
        {COLUMNS.map((column) => {
          const items = ideas.filter((i) => i.status === column.key);
          const over = dragging !== null;
          return (
            <section
              key={column.key}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragging !== null) void move(dragging, column.key);
                setDragging(null);
              }}
              className={`rounded-lg border border-dashed p-1 transition-colors ${
                over ? "border-border-strong bg-surface-2" : "border-transparent"
              }`}
            >
              <h2 className="mb-2 flex items-baseline justify-between gap-2 border-b pb-1.5 text-[0.8125rem]">
                <span className="font-medium">{column.label}</span>
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
                      <button
                        onClick={() => void run(() => del(`/api/studio/ideas/${idea.id}`))}
                        className="text-muted-foreground opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
                        aria-label={`Delete "${idea.title}"`}
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
                        Write a draft
                      </button>
                    ) : null}
                  </li>
                ))}
                {items.length === 0 ? (
                  <li className="px-1 py-5 text-xs text-muted-foreground">{EMPTY[column.key]}</li>
                ) : null}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
