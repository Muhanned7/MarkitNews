/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['172.20.80.1'],
  eslint: {
    ignoreDuringBuilds: true,
  }
};

export default nextConfig;
