import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // No page uses next/image with remote sources; leaving remotePatterns open would turn
  // /_next/image into an open image proxy.
  images: { unoptimized: true },
  async rewrites() {
    // Convenience for running Next directly (without Caddy) in development.
    if (process.env.NODE_ENV !== "development") return [];
    const api = process.env.API_INTERNAL_URL ?? "http://localhost:8001";
    // Media is served straight from MinIO's public bucket, the way Caddy does it in production.
    const s3 = process.env.S3_ENDPOINT ?? "http://localhost:9002";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/tg/:path*", destination: `${api}/tg/:path*` },
      { source: "/media/:path*", destination: `${s3}/media/:path*` },
      { source: "/uploads/:path*", destination: `${s3}/uploads/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
