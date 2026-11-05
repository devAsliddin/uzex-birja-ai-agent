/** @type {import('next').NextConfig} */
const { PHASE_PRODUCTION_BUILD } = require("next/constants");

module.exports = (phase) => {
  const config = {
    reactStrictMode: true,
    // Static export -> frontend/out/, served by FastAPI on the same origin as /api/v1.
    output: "export",
    trailingSlash: true,
    images: { unoptimized: true },
  };
  if (phase === PHASE_PRODUCTION_BUILD) {
    // Same-origin build: the browser calls /api/v1 relative to wherever the page is served
    // (127.0.0.1:8000 or a tunnel). Override with EXPORT_API_URL if ever needed.
    // `next dev` keeps NEXT_PUBLIC_API_URL from .env.local (absolute http://127.0.0.1:8000/api/v1).
    config.env = { NEXT_PUBLIC_API_URL: process.env.EXPORT_API_URL || "/api/v1" };
  }
  return config;
};
