export const ADMIN_HOST = process.env.ADMIN_HOST ?? "admin.localhost";
export const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";
export const LOCALES = ["uz", "ru", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "uz";
