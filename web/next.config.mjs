/**
 * Demo/prod'da oldida nginx turadi: /api, /admin, /static -> Django; qolgani -> Next (infra/hf-space/nginx.conf).
 * Lokal `npm run dev` uchun /api rewrite (admin'ni to'g'ridan-to'g'ri :8000 da oching).
 */
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
  },
  output: "standalone",
  eslint: { ignoreDuringBuilds: true },
  poweredByHeader: false,
  async headers() {
    // HF Space ilovani huggingface.co ichida iframe'da ochadi.
    return [{ source: "/:path*", headers: [{ key: "Content-Security-Policy", value: "frame-ancestors 'self' https://huggingface.co" }] }];
  },
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
