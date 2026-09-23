export const ADMIN_HOST = process.env.ADMIN_HOST ?? "admin.localhost";
export const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";
export const LOCALES = ["uz", "ru", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "uz";
/** Channels without a domain of their own live at <slug>.PLATFORM_DOMAIN; the bare domain is the landing page. */
export const PLATFORM_DOMAIN = (process.env.PLATFORM_DOMAIN ?? "").toLowerCase();
/** Where the landing page's "contact" buttons go, e.g. https://t.me/<username>. */
export const CONTACT_URL = process.env.CONTACT_URL ?? "";
