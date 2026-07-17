import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a standalone Node.js server bundle — required for the Docker runtime stage.
  // This minimises the production image by including only necessary files.
  output: "standalone",

  // Environment variables exposed to the browser (prefixed with NEXT_PUBLIC_).
  // Server-side variables (without prefix) are also available.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1",
  },
};

export default nextConfig;
