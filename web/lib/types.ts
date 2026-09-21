export type TenantPublic = {
  id: number;
  slug: string;
  domain: string;
  status: string;
  title: string;
  about?: string | null;
  username?: string | null;
  photo_key?: string | null;
  primary_lang: string;
  locales: string[];
  bot_username: string | null;
  post_count?: number;
  theme: Record<string, unknown>;
};

export type Me =
  | { authenticated: false }
  | { authenticated: true; role: "admin" | "owner" | "editor"; name: string; username?: string | null; photo_url?: string | null; tg_user_id: number };

export type AdminTenant = {
  id: number;
  slug: string;
  domain: string;
  status: string;
  title: string;
  primary_lang: string;
  locales: string[];
  bot_username: string | null;
  has_bot_token: boolean;
  domain_verified_at: string | null;
  daily_chat_budget_usd: number;
  daily_studio_budget_usd: number;
  created_at: string;
  channel: null | {
    id: number;
    tg_channel_id: number;
    username: string | null;
    title: string;
    backfill_status: string;
    backfill_checkpoint: number;
    backfill_total_estimate: number | null;
    participants_count: number | null;
  };
};

export type AdminOverview = {
  tenants: AdminTenant[];
  accounts: number;
  running_jobs: number;
  spend_today_usd: number;
};
