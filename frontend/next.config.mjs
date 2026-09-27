/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 自托管（Docker / 云托管 / 轻量服务器）时开启独立产物：
  // 会产出 .next/standalone/server.js，只带真正用到的依赖，镜像体积小一个数量级。
  // Vercel 用自己的构建产物，不需要这个开关，所以用环境变量控制、不硬编码。
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" } : {}),
  eslint: {
    // Demo 工程没有单独维护 ESLint 配置，避免部署时因 lint 阻断构建
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
