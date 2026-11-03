import type { NextConfig } from "next";

// `next build` writes a static export to out/, which `arena serve` serves next to its API.
// `next dev` cannot export, so it proxies /api to a running `arena serve` instead.
const isDev = process.env.NODE_ENV === "development";
const arenaOrigin = process.env.ARENA_ORIGIN ?? "http://127.0.0.1:8765";

// FastAPI routes have no trailing slash, so the proxy must not add one.
const devProxy: NextConfig = {
  skipTrailingSlashRedirect: true,
  rewrites: async () => [{ source: "/api/:path*", destination: `${arenaOrigin}/api/:path*` }],
};

const nextConfig: NextConfig = {
  ...(isDev ? devProxy : { output: "export" }),
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
