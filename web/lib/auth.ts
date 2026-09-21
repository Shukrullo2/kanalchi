import "server-only";
import { apiFetchOrNull } from "./api";
import type { Me } from "./types";

export async function getMe(admin = false): Promise<Me> {
  const me = await apiFetchOrNull<Me>("/api/auth/me", { admin });
  return me ?? { authenticated: false };
}
