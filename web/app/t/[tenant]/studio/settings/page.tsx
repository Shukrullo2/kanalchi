import { SettingsPanel } from "@/components/studio/SettingsPanel";
import { apiFetch } from "@/lib/api";
import type { StudioSettings } from "@/lib/types";

export default async function StudioSettingsPage() {
  const settings = await apiFetch<StudioSettings>("/api/studio/settings");
  return <SettingsPanel initial={settings} />;
}
