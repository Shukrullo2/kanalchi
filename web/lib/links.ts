/**
 * How an outbound link is labelled.
 *
 * A channel that cites fifty other channels should not present fifty links that
 * all read "t.me". Telegram URLs carry the channel in their path, so they are
 * labelled by it; everything else keeps its domain.
 */
export function linkLabel(url: string, domain?: string | null): string {
  const handle = telegramHandle(url);
  return handle ?? domain ?? hostOf(url);
}

/** `https://t.me/tengenomika/608` → `@tengenomika`. Null for invite and private links. */
export function telegramHandle(url: string): string | null {
  const match = /^https?:\/\/(?:www\.)?t\.me\/([A-Za-z0-9_]{3,})(?:\/|$|\?)/.exec(url);
  if (!match) return null;
  const name = match[1];
  // `joinchat` and `c` are invite and private-channel paths, not channel names.
  if (name === "joinchat" || name === "c") return null;
  return `@${name}`;
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
