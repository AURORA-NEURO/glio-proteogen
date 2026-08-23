import path from "node:path";

import type { NextConfig } from "next";

const backendUrl = process.env.GLIO_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  agentRules: false,
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
