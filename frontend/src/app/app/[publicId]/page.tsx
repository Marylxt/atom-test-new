import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight, Boxes } from "lucide-react";
import { API_BASE, getPublicApp } from "@/lib/api";
import type { PublicApp } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "AI 生成的应用 · Atoms Demo",
  description: "由 Atoms Demo 的多智能体流水线生成并发布的网页应用。",
};

/** 公开访问页：任何人都能用 public_id 打开已发布的应用。 */
export default async function PublicAppPage({ params }: { params: { publicId: string } }) {
  let app: PublicApp | null = null;
  let error: string | null = null;

  try {
    app = await getPublicApp(params.publicId);
  } catch (err) {
    error = err instanceof Error ? err.message : "加载失败";
  }

  if (!app) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="surface max-w-md p-8 text-center">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-white/5">
            <Boxes className="h-5 w-5 text-slate-400" />
          </div>
          <h1 className="text-base font-semibold text-slate-100">这个链接打不开了</h1>
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            {error ?? "发布记录不存在或已被作者下线。"}
          </p>
          <Link
            href="/"
            className="mt-5 inline-flex items-center gap-1 text-xs font-medium text-brand-300 transition hover:text-brand-200"
          >
            去 Atoms Demo 自己做一个
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] bg-ink-900/70 px-4 py-2.5 backdrop-blur">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-violet-500">
            <Boxes className="h-4 w-4 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-slate-100">
              {app.title ?? "AI 生成的应用"}
            </h1>
            <p className="truncate text-[11px] text-slate-500">
              v{app.version_no ?? "-"} · 发布于 {formatDateTime(app.published_at)} · 已被访问{" "}
              {app.views} 次
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <a
            href={`${API_BASE}/api/public/${app.public_id}/raw`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg px-3 py-1.5 text-xs text-slate-300 transition hover:bg-white/[0.07] hover:text-white"
          >
            打开原始页面
          </a>
          <Link
            href="/"
            className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-brand-400"
          >
            我也要做一个
          </Link>
        </div>
      </header>

      <iframe
        src={`${API_BASE}/api/public/${app.public_id}/raw`}
        className="min-h-0 w-full flex-1 border-0 bg-white"
        sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
        title={app.title ?? "AI 生成的应用"}
      />
    </div>
  );
}
