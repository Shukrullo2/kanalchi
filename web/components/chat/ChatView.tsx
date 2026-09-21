"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { SparkIcon } from "@/components/Icons";
import { parseCitations, streamTurn } from "@/lib/chat";
import { postDate } from "@/lib/format";
import type { ChatCitation, ChatSuggestions, ChatTurn } from "@/lib/types";

type Labels = {
  placeholder: string;
  intro: string;
  send: string;
  thinking: string;
  disabled: string;
  sources: string;
};

export function ChatView({
  suggestions,
  locale,
  labels,
  kind = "viewer",
}: {
  suggestions: ChatSuggestions;
  locale: string;
  labels: Labels;
  kind?: "viewer" | "research";
}) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState<string | null>(null);
  const sessionRef = useRef<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, tool]);

  async function ensureSession(): Promise<string | null> {
    if (sessionRef.current) return sessionRef.current;
    const res = await fetch("/api/chat/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind, locale }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { session_id: string };
    sessionRef.current = data.session_id;
    return data.session_id;
  }

  async function ask(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setDraft("");
    setBusy(true);
    setTurns((prev) => [
      ...prev,
      { role: "user", content: question, citations: [] },
      { role: "assistant", content: "", citations: [], pending: true },
    ]);

    const sessionId = await ensureSession();
    if (!sessionId) {
      setTurns((prev) => patchLast(prev, { pending: false, error: "Could not start a chat session." }));
      setBusy(false);
      return;
    }

    await streamTurn(sessionId, question, {
      onDelta: (chunk) => setTurns((prev) => patchLast(prev, { content: lastContent(prev) + chunk })),
      onTool: (name) => setTool(name),
      onCitations: (cards: ChatCitation[]) => setTurns((prev) => patchLast(prev, { cards })),
      onError: (message) => setTurns((prev) => patchLast(prev, { error: message })),
      onDone: () => {
        setTool(null);
        setBusy(false);
        setTurns((prev) => patchLast(prev, { pending: false }));
      },
    });
  }

  if (!suggestions.enabled) {
    return <div className="card-surface p-12 text-center text-sm text-muted-foreground">{labels.disabled}</div>;
  }

  return (
    <div className="flex min-h-[60vh] flex-col gap-5">
      {turns.length === 0 ? (
        <div className="card-surface flex flex-col items-center gap-4 p-8 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-accent text-accent-foreground">
            <SparkIcon size={20} />
          </span>
          <p className="max-w-sm text-pretty text-sm text-muted-foreground">{labels.intro}</p>
          <div className="flex flex-wrap justify-center gap-1.5">
            {suggestions.suggestions.map((s) => (
              <button key={s} onClick={() => ask(s)} className="btn-ghost text-xs">
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 space-y-4">
          {turns.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                  {turn.content}
                </p>
              </div>
            ) : (
              <div key={i} className="space-y-2.5">
                <div className="tg-body text-[0.95rem] leading-relaxed">
                  <Answer text={turn.content} cards={turn.cards ?? []} />
                  {turn.pending && !turn.content ? (
                    <span className="inline-flex gap-1 align-middle">
                      {[0, 1, 2].map((d) => (
                        <span
                          key={d}
                          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
                          style={{ animationDelay: `${d * 120}ms` }}
                        />
                      ))}
                    </span>
                  ) : null}
                </div>
                {turn.error ? (
                  <p className="text-sm" style={{ color: "var(--destructive)" }}>
                    {turn.error}
                  </p>
                ) : null}
                {turn.cards && turn.cards.length > 0 ? (
                  <div className="space-y-1.5">
                    <div className="text-xs text-muted-foreground">
                      {labels.sources}
                    </div>
                    <ul className="space-y-1">
                      {turn.cards.map((c) => (
                        <li key={c.id}>
                          <Link
                            href={c.url}
                            className="flex items-baseline gap-2 rounded-md px-2 py-1 text-sm transition-colors hover:bg-surface-2"
                          >
                            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">#{c.id}</span>
                            <span className="min-w-0 flex-1 truncate">{c.title}</span>
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {postDate(c.date, locale)}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ),
          )}
          {tool ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
              {labels.thinking} · {tool.replace(/_/g, " ")}
            </p>
          ) : null}
          <div ref={bottomRef} />
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(draft);
        }}
        className="sticky bottom-4 flex gap-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={labels.placeholder}
          disabled={busy}
          maxLength={2000}
          className="input-field py-3 shadow-sm"
        />
        <button disabled={busy || !draft.trim()} className="btn-primary px-4 shadow-sm">
          {labels.send}
        </button>
      </form>
    </div>
  );
}

function Answer({ text, cards }: { text: string; cards: ChatCitation[] }) {
  const known = new Map(cards.map((c) => [c.id, c]));
  return (
    <>
      {parseCitations(text).map((part, i) =>
        part.kind === "text" ? (
          <span key={i} className="whitespace-pre-wrap">
            {part.value}
          </span>
        ) : (
          <Link
            key={i}
            href={known.get(part.id)?.url ?? `/post/${part.id}`}
            title={known.get(part.id)?.title}
            className="mx-0.5 inline-flex items-center rounded bg-accent px-1 align-baseline text-[0.7rem] font-medium text-accent-foreground no-underline"
          >
            {part.id}
          </Link>
        ),
      )}
    </>
  );
}

function lastContent(turns: ChatTurn[]): string {
  return turns[turns.length - 1]?.content ?? "";
}

function patchLast(turns: ChatTurn[], patch: Partial<ChatTurn>): ChatTurn[] {
  if (turns.length === 0) return turns;
  const copy = [...turns];
  copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
  return copy;
}
