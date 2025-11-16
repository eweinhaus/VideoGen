/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Vercel uses SWC minification by default
  swcMinify: true,
  images: {
    // Allow Supabase Storage signed URLs
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**.supabase.co',
      },
      {
        protocol: 'https',
        hostname: 'storage.supabase.co',
      },
    ],
  },
}

module.exports = nextConfig

