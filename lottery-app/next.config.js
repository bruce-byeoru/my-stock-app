/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
}

// Disable automatic package import optimization for problematic packages
// to avoid server bundle vendor-chunk issues (e.g. lucide-react).
// Clearing `optimizePackageImports` forces Next to skip modularizing
// listed packages into separate vendor-chunks on the server.
nextConfig.experimental = {
  optimizePackageImports: [],
}

module.exports = nextConfig
