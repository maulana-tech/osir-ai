import type { NextConfig } from "next";

// Django-owned paths. In development the Next dev server proxies them to
// Studio so the browser sees one origin (cookies, CSRF). In production Caddy
// routes these to Django before they reach Next; the rewrite is a harmless
// fallback there.
const STUDIO = (process.env.STUDIO_URL ?? "http://localhost:8000").replace(/\/$/, "");
const DJANGO_PATHS = [
  "api",
  "accounts",
  "admin",
  "static",
  "media",
  "social-accounts",
  "oauth",
  "webhooks",
  "portal",
  "health",
  ".well-known",
];

const nextConfig: NextConfig = {
  output: "standalone",
  // Django URLs end with a slash; without this Next 308s them to no-slash and
  // Django's APPEND_SLASH sends them back: an infinite redirect.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    // `:path*` drops a trailing slash, and Django's APPEND_SLASH would then
    // redirect forever, so match the slash-terminated form explicitly first.
    return DJANGO_PATHS.flatMap((p) => [
      { source: `/${p}/`, destination: `${STUDIO}/${p}/` },
      { source: `/${p}/:path*/`, destination: `${STUDIO}/${p}/:path*/` },
      { source: `/${p}/:path*`, destination: `${STUDIO}/${p}/:path*` },
    ]);
  },
};

export default nextConfig;
