export type TenantPublic = {
  id: number;
  slug: string;
  domain: string;
  status: string;
  title: string;
  about?: string | null;
  username?: string | null;
  photo_url?: string | null;
  participants_count?: number | null;
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

export type MediaOut = {
  id: number;
  kind: string;
  mime: string | null;
  width: number | null;
  height: number | null;
  duration_s: number | null;
  size_bytes: number | null;
  file_name: string | null;
  status: string;
  url: string | null;
  thumb_url: string | null;
  external_url: string | null;
};

export type LinkOut = { url: string; domain: string; title: string | null; kind: string | null };

export type PostOut = {
  id: number;
  date: string;
  edit_date: string | null;
  html: string | null;
  text: string;
  truncated: boolean;
  views: number;
  forwards: number;
  reactions_total: number;
  reactions: { emoji?: string; custom_emoji_id?: number; count: number }[];
  media_kind: string;
  media: MediaOut[];
  links: LinkOut[];
  poll: { question: string; answers: { text: string; voters: number | null }[]; total_voters: number | null } | null;
  forward_from: { title?: string; username?: string; channel_post?: number } | null;
  reply_to: number | null;
  title: string | null;
  summary: string | null;
  language: string | null;
  is_deleted: boolean;
  url: string;
  prev_id?: number | null;
  next_id?: number | null;
};

export type PostPage = { items: PostOut[]; next_cursor: string | null };

export type Checklist = {
  tenant_id: number;
  domain: string;
  status: string;
  steps: {
    channel: { done: boolean; title: string | null; username: string | null; total: number | null; account_id: number | null; noforwards: boolean | null };
    bot: { done: boolean; username: string | null };
    domain: { done: boolean; detail: string; resolves: boolean };
    backfill: { done: boolean; status: string | null; checkpoint: number; total: number | null };
  };
};

export type TgAccount = {
  id: number;
  phone: string;
  display_name: string | null;
  tg_user_id: number | null;
  status: string;
  health: Record<string, unknown>;
  flood_wait_until: string | null;
  last_seen_at: string | null;
};

export type JobRunOut = {
  id: number;
  tenant_id: number | null;
  type: string;
  status: string;
  progress: { stage?: string; done?: number; total?: number; checkpoint?: number; message?: string };
  cost_usd: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type DimensionOut = {
  key: string;
  labels: Record<string, string>;
  description: string | null;
  kind: string;
  tag_count: number;
};

export type TagOut = {
  slug: string;
  name: string;
  labels: Record<string, string>;
  description: string | null;
  dimension: string | null;
  post_count: number;
  engagement_score: number;
  parent_id: number | null;
  confidence?: number;
};

export type TagDetail = TagOut & {
  redirect_to?: string;
  first_post_at: string | null;
  last_post_at: string | null;
  histogram: { month: string; count: number }[];
  co_tags: { slug: string; name: string; labels: Record<string, string>; count: number }[];
  children: TagOut[];
  parent: TagOut | null;
};

export type SearchResult = {
  items: PostOut[];
  count: number;
  offset: number;
  has_more: boolean;
  facets?: Record<string, { slug: string; name: string; labels: Record<string, string>; count: number }[]>;
};

export type ChannelStats = {
  posts: number;
  total_views: number;
  mean_views: number;
  first_post_at: string | null;
  last_post_at: string | null;
  by_month: { month: string; posts: number; mean_views: number }[];
  top_tags: TagOut[];
};

export type ChatCitation = { id: number; date: string; title: string; url: string };

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations: number[];
  cards?: ChatCitation[];
  pending?: boolean;
  error?: string | null;
};

export type ChatSuggestions = { suggestions: string[]; enabled: boolean };
