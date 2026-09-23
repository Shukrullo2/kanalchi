"use client";

import { useCallback, useState, useSyncExternalStore } from "react";

const EVENT = "kanalchi:panel";
const NARROW = "(max-width: 40rem)";

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener(EVENT, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(EVENT, cb);
  };
}
function subscribeNarrow(cb: () => void) {
  const mq = window.matchMedia(NARROW);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

/** A phone-sized viewport, where a floating panel would cover most of the canvas. */
export function isNarrow(): boolean {
  return window.matchMedia(NARROW).matches;
}

/**
 * Whether a floating control panel is open.
 *
 * It is a per-browser convenience: put away once, it stays away, and a phone
 * starts with it away because the canvas is the point. Read as an external
 * store so the first client render can disagree with the server's without a
 * hydration error, and so two panels sharing a key stay in step.
 */
export function usePanel(key: string) {
  const read = useCallback(() => {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }, [key]);
  const saved = useSyncExternalStore(subscribe, read, () => null);
  const narrow = useSyncExternalStore(subscribeNarrow, isNarrow, () => false);
  const [forced, setForced] = useState<boolean | null>(null);
  const open = forced ?? (saved !== null ? saved === "1" : !narrow);

  const toggle = useCallback(
    (next: boolean) => {
      setForced(next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {}
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  /** Put it away for now without remembering that. */
  const dismiss = useCallback(() => setForced(false), []);
  return { open, toggle, dismiss };
}
