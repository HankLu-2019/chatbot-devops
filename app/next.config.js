/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow server-side use of the pg package (Node.js-only module)
  serverExternalPackages: ["pg", "pgvector"],
};

module.exports = nextConfig;
