/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    // Demo 工程没有单独维护 ESLint 配置，避免部署时因 lint 阻断构建
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
