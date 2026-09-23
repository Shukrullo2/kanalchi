"use client";

import Link from "@/components/AppLink";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
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

export function DraftEditor({
  initial,
  botUsername,
  channelUsername,
}: {
  initial: DraftOut;
  botUsername: string | null;
  /** The channel's public @username, which is what a link to a sent post needs. */
  channelUsername: string | null;
}) {
  const t = useTranslations("studio.editor");
  const or = useTranslations("common")("or");
  const status = useTranslations("studio.status");
  const router = useRouter();
  const locale = useLocale();
  const editorRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState(initial);
  const [html, setHtml] = useState(initial.html);
  const [title, setTitle] = useState(initial.title);
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
    const url = window.prompt(t("linkPrompt"));
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
    try {
      setDraft(await patch<DraftOut>(`/api/studio/drafts/${draft.id}`, { media }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  /** Title and preview flag save straight away; they are not what the blogger is typing. */
  async function saveMeta(fields: { title?: string; disable_preview?: boolean }) {
    try {
      setDraft(await patch<DraftOut>(`/api/studio/drafts/${draft.id}`, fields));
      setSaving("saved");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  /** The queued send checks the row before it fires, so putting the row back to "draft" is enough. */
  async function cancelSchedule() {
    setBusy(true);
    setError(null);
    try {
      setDraft(await post<DraftOut>(`/api/studio/drafts/${draft.id}/cancel`, {}));
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
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
          <ArrowLeftIcon size={14} /> {t("back")}
        </Link>
        <span className="chip">{status.has(draft.status) ? status(draft.status) : draft.status}</span>
        {draft.ai_generated ? <span className="chip">{t("aiDraft")}</span> : null}
        <span className="ml-auto text-xs text-muted-foreground">
          {saving === "saving" ? t("saving") : saving === "saved" ? t("saved") : ""}
        </span>
      </div>

      {published ? (
        <div className="border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--success)" }}>
          <span suppressHydrationWarning>
            {draft.published_at
              ? t("publishedOn", { date: fullDate(draft.published_at, locale) })
              : t("published")}
          </span>
          {botUsername ? t("sentByBot", { bot: botUsername }) : ""}
        </div>
      ) : draft.status === "scheduled" && draft.scheduled_at ? (
        <div className="flex flex-wrap items-center gap-3 border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--primary)" }}>
          <span suppressHydrationWarning>{t("scheduledFor", { date: fullDate(draft.scheduled_at, locale) })}</span>
          <button onClick={() => void cancelSchedule()} disabled={busy} className="link-quiet text-xs">
            {t("cancelSchedule")}
          </button>
        </div>
      ) : draft.publish_error ? (
        <div className="border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--destructive)", color: "var(--destructive)" }}>
          {draft.publish_error}
        </div>
      ) : null}

      {!published ? (
        <input
          className="input-field"
          placeholder={t("titlePlaceholder")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => {
            if (title !== draft.title) void saveMeta({ title });
          }}
        />
      ) : draft.title ? (
        <h2 className="text-[0.9375rem] font-medium">{draft.title}</h2>
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
              {t("link")}
            </button>
            <label className="btn-ghost h-8 cursor-pointer px-2 text-xs">
              {t("media")}
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
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={draft.disable_preview}
                disabled={published}
                onChange={(e) => void saveMeta({ disable_preview: e.target.checked })}
              />
              {t("hidePreview")}
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
            data-placeholder={t("placeholder")}
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
                      aria-label={t("remove")}
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
          <div className="text-xs text-muted-foreground">{t("preview")}</div>
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
              <div className="text-xs text-muted-foreground">{t("willBeFiled")}</div>
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
          <button onClick={() => void publish()} disabled={busy || used > limit || !botUsername} className="btn-primary">
            {t("publishNow")}
          </button>
          <span className="text-xs text-muted-foreground">{or}</span>
          <input
            type="datetime-local"
            value={scheduleAt}
            onChange={(e) => setScheduleAt(e.target.value)}
            className="input-field w-auto"
          />
          <button
            onClick={() => void publish(scheduleAt)}
            disabled={busy || !scheduleAt || used > limit || !botUsername}
            className="btn-ghost"
          >
            {t("schedule")}
          </button>
          {!botUsername ? (
            <span className="basis-full text-xs" style={{ color: "var(--warning)" }}>
              {t("noBot")}
            </span>
          ) : null}
          <button
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                setDraft(await post<DraftOut>(`/api/studio/drafts/${draft.id}/suggest-tags`, {}));
                router.refresh();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="btn-ghost"
          >
            <SparkIcon size={13} /> {t("suggestTags")}
          </button>
          <button
            onClick={async () => {
              if (!window.confirm(t("confirmDelete"))) return;
              await del(`/api/studio/drafts/${draft.id}`);
              router.push("/studio/drafts");
            }}
            className="link-quiet ml-auto text-xs"
          >
            {t("deleteDraft")}
          </button>
        </div>
      ) : draft.published_tg_message_id && channelUsername ? (
        <a
          href={`https://t.me/${channelUsername}/${draft.published_tg_message_id}`}
          className="link-quiet flex items-center gap-1 text-sm"
          target="_blank"
          rel="noreferrer"
        >
          {t("openTelegram")} <ExternalIcon size={12} />
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
