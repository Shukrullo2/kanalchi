import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  images: { remotePatterns: [{ protocol: "https", hostname: "**" }, { protocol: "http", hostname: "**" }] },
  async rewrites() {
    // Convenience for running Next directly (without Caddy) in development.
    if (process.env.NODE_ENV !== "development") return [];
    const api = process.env.API_INTERNAL_URL ?? "http://localhost:8001";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/tg/:path*", destination: `${api}/tg/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
