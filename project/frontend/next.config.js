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
  webpack: (config, { isServer }) => {
    // Fix for Supabase vendor chunk issues
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      }
    }
    // Ensure Supabase is properly handled
    config.externals = config.externals || []
    if (isServer) {
      config.externals.push('@supabase/supabase-js')
    }
    return config
  },
}

module.exports = nextConfig

