"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { ExternalLink, Monitor, RefreshCw, Smartphone, Tablet } from "lucide-react";
import { Button } from "./ui/button";
import { cn } from "@/lib/utils";

type DeviceKey = "desktop" | "tablet" | "mobile";

const DEVICES: { key: DeviceKey; label: string; width: number | null; icon: typeof Monitor }[] = [
  { key: "desktop", label: "桌面", width: null, icon: Monitor },
  { key: "tablet", label: "平板", width: 834, icon: Tablet },
  { key: "mobile", label: "手机", width: 390, icon: Smartphone },
];

/**
 * 用 iframe 的 srcdoc 实时渲染 Agent 生成的 HTML。
 *
 * sandbox 说明：
 * - allow-scripts  生成的页面要跑 JS
 * - allow-same-origin 让生成代码能正常使用 localStorage（规格书要求数据持久化）
 * - allow-forms / allow-modals / allow-popups 保证表单与 alert 可用
 * 生产环境建议把产物放到独立域名的沙箱服务里再渲染，避免同源风险。
 */
export const AppPreview = memo(function AppPreview({
  html,
  title = "应用预览",
  onOpenExternal,
}: {
  html: string | null;
  title?: string;
  onOpenExternal?: () => void;
}) {
  const [device, setDevice] = useState<DeviceKey>("desktop");
  const [nonce, setNonce] = useState(0);

  // 每次内容变化都重置滚动位置（重建 iframe）
  useEffect(() => {
    setNonce((value) => value + 1);
  }, [html]);

  const width = useMemo(() => DEVICES.find((d) => d.key === device)?.width ?? null, [device]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          {title}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-white/[0.07] bg-white/[0.04] p-0.5">
            {DEVICES.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.key}
                  type="button"
                  title={item.label}
                  onClick={() => setDevice(item.key)}
                  className={cn(
                    "rounded-md p-1.5 transition",
                    device === item.key
                      ? "bg-white/10 text-white"
                      : "text-slate-500 hover:text-slate-300",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                </button>
              );
            })}
          </div>
          <Button size="icon" variant="ghost" title="刷新预览" onClick={() => setNonce((v) => v + 1)}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          {onOpenExternal ? (
            <Button size="icon" variant="ghost" title="新窗口打开" onClick={onOpenExternal}>
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-ink-950/60 p-3">
        {html ? (
          <div
            className="mx-auto h-full overflow-hidden rounded-xl border border-white/10 bg-white shadow-2xl transition-[width] duration-300"
            style={{ width: width ? `${width}px` : "100%", maxWidth: "100%" }}
          >
            <iframe
              key={nonce}
              srcDoc={html}
              className="h-full w-full border-0"
              sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
              title={title}
            />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-white/10 text-sm text-slate-500">
            还没有生成结果，先在左侧输入需求试试
          </div>
        )}
      </div>
    </div>
  );
});
