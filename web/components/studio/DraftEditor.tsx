"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { ArrowLeftIcon, CloseIcon, ExternalIcon, SparkIcon } from "@/components/Icons";
import { TagChip } from "@/components/tags/TagChip";
import { del, patch, post } from "@/lib/client";
import { fullDate } from "@/lib/format";
import type { DraftOut } from "@/lib/types";

const TEXT_LIMIT = 4096;
const CAPTION_LIMIT = 1024;

/** Marks Telegram supports. `document.execCommand` is deprecated but is still the only way to get
 *  reliable rich-text editing in a contenteditable without shipping a full editor framework. */
const MARKS = [
  { cmd: "bold", label: "B", className: "font-bold" },
  { cmd: "italic", label: "I", className: "italic" },
  { cmd: "underline", label: "U", className: "underline" },
  { cmd: "strikeThrough", label: "S", className: "line-through" },
] as const;

export function DraftEditor({ initial, botUsername }: { initial: DraftOut; botUsername: string | null }) {
  const router = useRouter();
  const locale = useLocale();
  const editorRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState(initial);
  const [html, setHtml] = useState(initial.html);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  const [scheduleAt, setScheduleAt] = useState("");
  const [busy, setBusy] = useState(false);

  const published = draft.status === "published";
  const hasMedia = (draft.media ?? []).length > 0;
  const limit = hasMedia ? CAPTION_LIMIT : TEXT_LIMIT;
  const used = visibleLength(html);

  // Autosave a second after typing stops, so the blogger never loses work to a closed tab.
  // The "saving" flag is set where the edit happens; this effect only talks to the server.
  useEffect(() => {
    if (published || html === draft.html) return;
    const timer = setTimeout(async () => {
      try {
        const saved = await patch<DraftOut>(`/api/studio/drafts/${draft.id}`, { html });
        setDraft(saved);
        setSaving("saved");
      } catch (e) {
        setError((e as Error).message);
        setSaving("idle");
      }
    }, 900);
    return () => clearTimeout(timer);
  }, [html, draft.id, draft.html, published]);

  function applyMark(cmd: string) {
    editorRef.current?.focus();
    document.execCommand(cmd);
    setHtml(editorRef.current?.innerHTML ?? "");
    setSaving("saving");
  }

  function addLink() {
    const url = window.prompt("Link URL");
    if (!url) return;
    editorRef.current?.focus();
    document.execCommand("createLink", false, url);
    setHtml(editorRef.current?.innerHTML ?? "");
    setSaving("saving");
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/studio/uploads", { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "upload failed");
      const media = [...(draft.media ?? []), { upload_id: body.upload_id, kind: body.kind, url: body.url }];
      setDraft(await patch<DraftOut>(`/api/studio/drafts/${draft.id}`, { media }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeMedia(index: number) {
    const media = (draft.media ?? []).filter((_, i) => i !== index);
    setDraft(await patch<DraftOut>(`/api/studio/drafts/${draft.id}`, { media }));
  }

  async function publish(when?: string) {
    setBusy(true);
    setError(null);
    try {
      await post(`/api/studio/drafts/${draft.id}/publish`, {
        scheduled_at: when ? new Date(when).toISOString() : null,
      });
      router.refresh();
      router.push("/studio/drafts");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/studio/drafts" className="link-quiet flex items-center gap-1.5 text-sm">
          <ArrowLeftIcon size={14} /> drafts
        </Link>
        <span className="chip">{draft.status}</span>
        {draft.ai_generated ? <span className="chip">AI draft</span> : null}
        <span className="ml-auto text-xs text-muted-foreground">
          {saving === "saving" ? "Saving…" : saving === "saved" ? "Saved" : ""}
        </span>
      </div>

      {published ? (
        <div className="border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--success)" }}>
          <span suppressHydrationWarning>
            Published{draft.published_at ? ` on ${fullDate(draft.published_at, locale)}` : ""}.
          </span>
          {botUsername ? ` Sent by @${botUsername}.` : ""}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-2">
          <div className="flex flex-wrap items-center gap-1">
            {MARKS.map((m) => (
              <button
                key={m.cmd}
                type="button"
                onClick={() => applyMark(m.cmd)}
                disabled={published}
                className={`h-8 w-8 rounded-md border text-sm hover:bg-surface-2 ${m.className}`}
                title={m.cmd}
              >
                {m.label}
              </button>
            ))}
            <button type="button" onClick={addLink} disabled={published} className="btn-ghost h-8 px-2 text-xs">
              link
            </button>
            <label className="btn-ghost h-8 cursor-pointer px-2 text-xs">
              media
              <input
                type="file"
                className="hidden"
                accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
                disabled={published || busy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                  e.target.value = "";
                }}
              />
            </label>
            <span className={`ml-auto text-xs tabular-nums ${used > limit ? "text-destructive" : "text-muted-foreground"}`}>
              {used} / {limit}
            </span>
          </div>

          <div
            ref={editorRef}
            contentEditable={!published}
            suppressContentEditableWarning
            onInput={(e) => {
              setHtml((e.target as HTMLDivElement).innerHTML);
              setSaving("saving");
            }}
            dangerouslySetInnerHTML={{ __html: initial.html }}
            className="tg-body min-h-56 rounded-xl border bg-surface p-4 outline-none focus:border-ring"
            data-placeholder="Write your post…"
          />

          {(draft.media ?? []).length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {(draft.media ?? []).map((m, i) => (
                <li key={i} className="relative">
                  {m.kind === "photo" && m.url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- presigned MinIO preview
                    <img src={m.url} alt="" className="h-16 w-16 rounded-lg object-cover" />
                  ) : (
                    <span className="grid h-16 w-16 place-items-center rounded-lg bg-surface-2 text-xs">
                      {m.kind}
                    </span>
                  )}
                  {!published ? (
                    <button
                      onClick={() => void removeMedia(i)}
                      className="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-foreground text-background"
                      aria-label="Remove"
                    >
                      <CloseIcon size={10} />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="space-y-2">
          <div className="text-xs text-muted-foreground">Preview</div>
          <div className="rounded-xl bg-surface-2 p-4">
            <div className="max-w-md rounded-2xl rounded-bl-sm bg-surface p-3 shadow-sm">
              {(draft.media ?? []).length > 0 ? (
                <div className="mb-2 grid grid-cols-2 gap-1">
                  {(draft.media ?? []).slice(0, 4).map((m, i) =>
                    m.kind === "photo" && m.url ? (
                      // eslint-disable-next-line @next/next/no-img-element -- presigned MinIO preview
                      <img key={i} src={m.url} alt="" className="aspect-square w-full rounded-lg object-cover" />
                    ) : (
                      <span key={i} className="grid aspect-square place-items-center rounded-lg bg-surface-2 text-xs">
                        {m.kind}
                      </span>
                    ),
                  )}
                </div>
              ) : null}
              <div className="tg-body text-[0.95rem]" dangerouslySetInnerHTML={{ __html: html || "<span class='text-muted-foreground'>…</span>" }} />
            </div>
          </div>

          {draft.suggested_tags.length > 0 ? (
            <div className="space-y-1.5">
              <div className="text-xs text-muted-foreground">Will be filed under</div>
              <div className="flex flex-wrap gap-1.5">
                {draft.suggested_tags.map((t) => (
                  <TagChip key={t.slug} tag={t} locale={locale} />
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>

      {error ? (
        <p className="rounded-md border p-2.5 text-sm" style={{ color: "var(--destructive)", borderColor: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}

      {!published ? (
        <div className="card-surface flex flex-wrap items-center gap-2 p-4">
          <button onClick={() => void publish()} disabled={busy || used > limit} className="btn-primary">
            Publish now
          </button>
          <span className="text-xs text-muted-foreground">or</span>
          <input
            type="datetime-local"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
            className="input-field w-auto"
          />
          <button
            onClick={() => void publish(scheduleAt)}
            disabled={busy || !scheduleAt || used > limit}
            className="btn-ghost"
          >
            Schedule
          </button>
          <button
            onClick={async () => {
              setDraft(await post<DraftOut>(`/api/studio/drafts/${draft.id}/suggest-tags`, {}));
              router.refresh();
            }}
            className="btn-ghost"
          >
            <SparkIcon size={13} /> Suggest tags
          </button>
          <button
            onClick={async () => {
              if (!window.confirm("Delete this draft?")) return;
              await del(`/api/studio/drafts/${draft.id}`);
              router.push("/studio/drafts");
            }}
            className="link-quiet ml-auto text-xs"
          >
            Delete draft
          </button>
        </div>
      ) : draft.published_tg_message_id ? (
        <a
          href={`https://t.me/${botUsername ?? ""}`}
          className="link-quiet flex items-center gap-1 text-sm"
          target="_blank"
          rel="noreferrer"
        >
          Open in Telegram <ExternalIcon size={12} />
        </a>
      ) : null}
    </div>
  );
}

function visibleLength(html: string): number {
  const text = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
  // Telegram counts UTF-16 code units, which is what String#length already is in JS.
  return text.length;
}
