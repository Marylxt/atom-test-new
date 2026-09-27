import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Atoms Demo · 多智能体 AI 应用生成器",
  description:
    "输入一句需求，产品经理 / 架构师 / 工程师三位 Agent 接力产出可运行的网页应用：SSE 实时进度、iframe 即时预览、Supabase 版本持久化、一键发布分享。",
};

export const viewport: Viewport = {
  themeColor: "#06080F",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
