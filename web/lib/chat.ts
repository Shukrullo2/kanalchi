"use client";

import type { ChatCitation } from "./types";

export type StreamHandlers = {
  onDelta: (text: string) => void;
  onTool: (name: string) => void;
  onCitations: (cards: ChatCitation[]) => void;
  onError: (message: string) => void;
  onDone: () => void;
};

/**
 * Reads the SSE turn stream.
 *
 * `fetch` rather than `EventSource`, because the turn is a POST with a body and has to carry
 * cookies; the framing is parsed by hand, which is a few lines and avoids a dependency.
 */
export async function streamTurn(sessionId: string, text: string, handlers: StreamHandlers): Promise<void> {
  const res = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!res.ok || !res.body) {
    const detail = await res.json().catch(() => ({}));
    handlers.onError((detail as { detail?: string }).detail ?? "The assistant is unavailable.");
    handlers.onDone();
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        dispatch(frame, handlers);
        split = buffer.indexOf("\n\n");
      }
    }
  } finally {
    handlers.onDone();
  }
}

function dispatch(frame: string, h: StreamHandlers) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }

  switch (event) {
    case "delta":
      h.onDelta(String(payload.text ?? ""));
      break;
    case "tool_call":
      h.onTool(String(payload.name ?? ""));
      break;
    case "citations":
      h.onCitations((payload.posts as ChatCitation[]) ?? []);
      break;
    case "error":
      h.onError(String(payload.message ?? "Something went wrong."));
      break;
    default:
      break;
  }
}

/** Splits an answer into text and [[post:ID]] markers so the UI can render inline citation chips. */
export function parseCitations(text: string): ({ kind: "text"; value: string } | { kind: "cite"; id: number })[] {
  const parts: ({ kind: "text"; value: string } | { kind: "cite"; id: number })[] = [];
  const re = /\[\[post:(\d+)\]\]/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push({ kind: "text", value: text.slice(last, match.index) });
    parts.push({ kind: "cite", id: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", value: text.slice(last) });
  return parts;
}
