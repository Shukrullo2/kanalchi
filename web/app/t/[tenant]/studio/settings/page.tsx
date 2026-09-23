import { SettingsPanel } from "@/components/studio/SettingsPanel";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { MemberOut, StudioSettings } from "@/lib/types";

export default async function StudioSettingsPage() {
  const [settings, members, me] = await Promise.all([
    apiFetch<StudioSettings>("/api/studio/settings"),
    apiFetchOrNull<MemberOut[]>("/api/studio/members"),
    getMe(),
  ]);
  return <SettingsPanel initial={settings} members={members ?? []} meId={me.authenticated ? me.tg_user_id : null} />;
}
