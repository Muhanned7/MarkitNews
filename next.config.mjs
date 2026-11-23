/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['172.20.80.1'],
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Only the Docker/Cloud Run build sets this; local `npm run dev` / `npm start` are unchanged.
  ...(process.env.NEXT_OUTPUT_STANDALONE ? { output: 'standalone' } : {}),
};

export default nextConfig;
