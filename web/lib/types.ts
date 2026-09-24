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
  /** archive | basic | premium; null for a channel connected before plans existed. */
  plan?: string | null;
  /** Whether the studio's ideas, drafts, research and publishing are switched on. */
  writing_tools?: boolean;
  post_count?: number;
  first_post_at?: string | null;
  last_post_at?: string | null;
  theme: Record<string, unknown>;
};

export type Me =
  | { authenticated: false }
  | {
      authenticated: true;
      /** `user` is someone signed in on the platform domain to register a channel. */
      role: "admin" | "owner" | "editor" | "user";
      name: string;
      username?: string | null;
      photo_url?: string | null;
      tg_user_id: number;
    };

export type PlanId = "archive" | "basic" | "premium";
export type SubscriptionStatus = "none" | "pending" | "active" | "past_due" | "cancelled";

export type Plan = { id: PlanId; monthly_uzs: number; live_updates: boolean; writing_tools: boolean };

export type OnboardingQuote = {
  posts: number;
  /** The one-off import price in soums, whole thousands. */
  price_uzs: number;
  /** telegram (measured) | manual (typed in by the blogger) | sample */
  source: string;
  computed_at: string;
  /** Admin only: the estimated AI cost the price was made from. */
  ai_usd?: number;
  avg_post_tokens?: number | null;
};

export type PlanCatalogue = {
  currency: string;
  plans: Plan[];
  onboarding: { sample: OnboardingQuote };
};

/** A channel as its owner sees it on the sign-up pages. */
export type SignupChannel = {
  id: number;
  slug: string;
  domain: string;
  url: string;
  title: string;
  status: string;
  plan: PlanId | null;
  plan_monthly_uzs: number | null;
  subscription_status: SubscriptionStatus;
  subscription_paid_until: string | null;
  onboarding_paid_at: string | null;
  quote: OnboardingQuote | null;
  /** pending: Telegram is being asked for the size; failed: the blogger is asked instead. */
  preview_status: "pending" | "done" | "failed";
  requested_at: string | null;
  verified: boolean;
  /** The blogger chose not to prove ownership through the bot; the admin checks by hand. */
  verify_skipped: boolean;
  channel: {
    username: string | null;
    title: string | null;
    participants_count: number | null;
    posts_estimate: number | null;
    resolved: boolean;
  };
  progress: { imported: number; total: number | null; backfill_status: string | null };
  created_at: string;
};

export type AdminSignup = {
  user_id: number;
  tg_user_id: number;
  name: string;
  username: string | null;
  photo_url: string | null;
  signed_up_at: string;
  last_login_at: string | null;
  tenants: AdminTenant[];
};

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
  /** Given a placeholder under the platform domain rather than a domain of its own. */
  auto_domain: boolean;
  daily_chat_budget_usd: number;
  daily_studio_budget_usd: number;
  created_at: string;
  /** admin (connected by hand) | self (registered on the platform domain). */
  source: "admin" | "self";
  owner_user_id: number | null;
  plan: PlanId | null;
  subscription_status: SubscriptionStatus;
  subscription_paid_until: string | null;
  onboarding_quote: OnboardingQuote | null;
  onboarding_paid_at: string | null;
  requested_at: string | null;
  verify_skipped: boolean;
  channel: null | {
    id: number;
    tg_channel_id: number;
    username: string | null;
    title: string;
    backfill_status: string;
    backfill_checkpoint: number;
    backfill_total_estimate: number | null;
    /** Posts actually stored. The checkpoint is a Telegram message id, not a count. */
    imported: number;
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
  tags: PostTagOut[];
  prev_id?: number | null;
  next_id?: number | null;
};

export type PostTagOut = {
  slug: string;
  name: string;
  labels: Record<string, string>;
  dimension: string | null;
  post_count: number;
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
    backfill: { done: boolean; status: string | null; checkpoint: number; imported: number; total: number | null };
  };
  /** The most recent job for this tenant, if it failed. */
  last_error: { type: string; error: string | null; at: string | null } | null;
  pipeline: PipelineStatus;
};

export type PipelineStage = "import" | "profile" | "embed" | "extract" | "taxonomy" | "done";

/** Where a channel's indexing stands, computed from the database rather than from any one job. */
export type PipelineStatus = {
  stage: PipelineStage;
  tenant_status: string;
  stages: {
    import: { done: boolean; status: string | null; imported: number; total: number | null };
    profile: { done: boolean; possible: boolean };
    embed: { done: boolean; embedded: number; skipped: number; pending: number; total: number };
    extract: {
      done: boolean;
      succeeded: number;
      in_flight: number;
      failed: number;
      pending: number;
      total: number;
      batches: { id: number; status: string; requests: number; submitted_at: string | null; stale: boolean }[];
    };
    taxonomy: { done: boolean; version_no: number | null; status: string | null; version_id: number | null };
  };
  running: { type: string; progress: Record<string, unknown> }[];
  attention: string[];
  workers: { telegram: boolean | null; index: boolean | null };
  checked_at: string;
};

export type PipelineEstimate = {
  posts_total: number;
  posts_imported: number;
  avg_post_tokens: number;
  measured_from_channel: boolean;
  lines: Record<string, number>;
  total_usd: number;
  models: Record<string, string>;
  extraction_measured_usd?: number;
};

export type MemberOut = {
  tg_user_id: number;
  name: string;
  username: string | null;
  role: "owner" | "editor";
  invited: boolean;
  verified_admin_at: string | null;
  notifications_linked: boolean;
  last_login_at: string | null;
};

export type TaxonomyVersionOut = {
  id: number;
  version_no: number;
  status: string;
  is_active?: boolean;
  stats: Record<string, { candidates: number; tags: number; dropped: number }>;
  diff?: Record<string, number>;
  cost_usd: number;
  built_at: string | null;
  applied_at: string | null;
};

export type TaxonomyPreview = {
  id: number;
  version_no: number;
  status: string;
  built_at: string | null;
  applied_at: string | null;
  cost_usd: number;
  model: string;
  dimensions: {
    key: string;
    labels: Record<string, string>;
    new: string[];
    new_count: number;
    kept_count: number;
    dropped_count: number;
  }[];
  diff: Record<string, unknown>;
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
  tenant_domain: string | null;
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
  /** One entry per locale, like `labels`; empty when nobody has written one. */
  descriptions: Record<string, string>;
  kind: string;
  tag_count: number;
};

export type TagOut = {
  slug: string;
  name: string;
  labels: Record<string, string>;
  /** One entry per locale, like `labels`; empty for about half the tags. */
  descriptions: Record<string, string>;
  dimension: string | null;
  post_count: number;
  engagement_score: number;
  parent_id: number | null;
  /** The subject's own picture when it has one, else a post it appeared in. */
  thumb_url?: string | null;
  image_source?: "logo" | "logo_light" | "wikidata" | null;
  confidence?: number;
  /** The span of the tag's posts. On the list endpoint only; absent on nested tags. */
  first_post_at?: string | null;
  last_post_at?: string | null;
};

export type TagDetail = TagOut & {
  redirect_to?: string;
  first_post_at: string | null;
  last_post_at: string | null;
  histogram: { month: string; count: number }[];
  co_tags: { slug: string; name: string; labels: Record<string, string>; dimension: string | null; count: number }[];
  children: TagOut[];
  parent: TagOut | null;
};

export type SearchResult = {
  items: PostOut[];
  count: number;
  offset: number;
  has_more: boolean;
  /** How many posts matched, up to the search pool; with `total_capped`, "at least this many". */
  total?: number | null;
  total_capped?: boolean;
  facets?: Record<string, { slug: string; name: string; labels: Record<string, string>; count: number }[]>;
};

export type StatTag = { slug: string; name: string; labels: Record<string, string>; posts: number };

export type ChannelStats = {
  posts: number;
  total_views: number;
  mean_views: number;
  total_forwards: number;
  total_reactions: number;
  mean_length: number;
  first_post_at: string | null;
  last_post_at: string | null;
  timezone: string;
  by_month: { month: string; posts: number; mean_views: number }[];
  by_weekday: { dow: number; posts: number; mean_views: number }[];
  by_hour: { hour: number; posts: number; mean_views: number }[];
  by_day: { day: string; posts: number }[];
  by_year: { year: number; posts: number; mean_views: number; total_views: number }[];
  media_mix: { kind: string; posts: number }[];
  by_length: { bucket: "short" | "medium" | "long" | "essay"; posts: number; mean_views: number }[];
  by_language: { language: string; posts: number }[];
  by_weekday_hour: { dow: number; hour: number; posts: number }[];
  by_domain: { domain: string; links: number; posts: number; telegram: boolean }[];
  indexed_posts: number;
  top_themes: StatTag[];
  top_people: StatTag[];
  top_gov_orgs: StatTag[];
  by_format: StatTag[];
  by_stance: StatTag[];
  themes_over_time: { quarter: string; slug: string; name: string; labels: Record<string, string>; posts: number }[];
  longest_streak_days: number;
  busiest_day: { day: string; posts: number } | null;
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

export type IdeaOut = {
  id: number;
  title: string;
  body: string;
  status: "inbox" | "researching" | "drafting" | "scheduled" | "published" | "dropped";
  position: number;
  related_post_ids: number[];
  created_at: string;
};

export type DraftOut = {
  id: number;
  idea_id: number | null;
  title: string;
  html: string;
  media: { upload_id?: number; object_key?: string; kind?: string; url?: string }[];
  status: "draft" | "scheduled" | "publishing" | "published" | "failed" | "canceled";
  scheduled_at: string | null;
  published_tg_message_id: number | null;
  published_at: string | null;
  publish_error: string | null;
  disable_preview: boolean;
  suggested_tags: TagOut[];
  ai_generated: boolean;
  length: number;
  updated_at: string;
};

export type StudioOverview = {
  posts: number;
  subscribers: number | null;
  drafts: Record<string, number>;
  ideas: Record<string, number>;
  pending_tags: number;
  spend_today_usd: number;
  studio_budget_usd: number;
  studio_spent_usd: number;
  has_voice_profile: boolean;
  bot_username: string | null;
  plan: PlanId | null;
  writing_tools: boolean;
};

export type PendingTag = {
  id: number;
  name: string;
  dimension: string;
  count: number;
  surface_forms: string[];
  sample_post_ids: number[];
};

export type StudioSettings = {
  chat_enabled: boolean;
  chat_persona: string | null;
  voice_profile: Record<string, unknown> | null;
  channel_profile: Record<string, unknown> | null;
  bot_username: string | null;
  /** The channel's public @username, if it has one; needed to link to a sent post. */
  channel_username: string | null;
  /** Whether this member has pressed /start in the bot, which every notification needs. */
  notifications_linked: boolean;
  role: "owner" | "editor";
  paused: boolean;
  webhook_ready: boolean;
  locales: string[];
};

export type CostsOut = {
  days: number;
  total_usd: number;
  by_day: { day: string; usd: number; input_tokens: number; output_tokens: number }[];
  by_purpose: { purpose: string; usd: number; requests: number }[];
  by_model: { model: string; usd: number; requests: number }[];
  by_tenant: { id: number; domain: string; usd: number }[];
  cache_hit_rate: number | null;
  platform_daily_cap_usd: number;
};

export type StoryOut = {
  slug: string;
  title: Record<string, string>;
  summary: Record<string, string>;
  first_at: string | null;
  last_at: string | null;
  post_count: number;
  citations: number[];
};

export type StoryDetail = StoryOut & { items: PostOut[] };

export type EntitySummaryOut =
  | { available: false }
  | { available: true; summary: Record<string, string>; citations: number[]; generated_at: string; is_stale: boolean };

/** One post as the map draws it: a dot with a date, a size, and the things it points at. */
export type GraphPost = {
  id: number;
  date: string;
  title: string;
  views: number;
  /** The post this one replied to, when that post is also in the window. */
  reply: number | null;
  /** Posts of the same channel this one links to, when they are in the window. */
  links: number[];
  /** Indexes into `GraphOut.tags`. */
  tags: number[];
};

export type GraphTag = {
  slug: string;
  name: string;
  labels: Record<string, string>;
  dimension: string | null;
  /** Posts in the whole archive. */
  post_count: number;
  /** Posts in this window. */
  count: number;
};

export type GraphOut = {
  from: string;
  to: string;
  truncated: boolean;
  posts: GraphPost[];
  tags: GraphTag[];
  /** Posts per month over the whole archive, oldest first. */
  months: { month: string; count: number }[];
};
