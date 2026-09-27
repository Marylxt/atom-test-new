"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";

/**
 * 极简 Markdown 渲染：只处理 Agent 输出里实际会用到的标题 / 列表 / 分隔线。
 * 不引第三方依赖，避免为了一个详情面板把包体积撑大。
 */
export const MarkdownLite = memo(function MarkdownLite({
  text,
  className,
}: {
  text: string | null | undefined;
  className?: string;
}) {
  if (!text) {
    return <p className="text-xs text-slate-500">暂无内容</p>;
  }

  const lines = text.split("\n");

  return (
    <div className={cn("space-y-1.5 text-[13px] leading-relaxed text-slate-300", className)}>
      {lines.map((raw, index) => {
        const line = raw.trimEnd();
        if (!line.trim()) return <div key={index} className="h-1.5" />;

        if (/^#{1,2}\s/.test(line)) {
          return (
            <h4 key={index} className="pt-2 text-sm font-semibold text-slate-100">
              {line.replace(/^#{1,2}\s/, "")}
            </h4>
          );
        }
        if (/^#{3,}\s/.test(line)) {
          return (
            <h5 key={index} className="pt-1.5 text-[13px] font-semibold text-brand-300">
              {line.replace(/^#{3,}\s/, "")}
            </h5>
          );
        }
        if (/^\s*[-*]\s/.test(line)) {
          return (
            <div key={index} className="flex gap-2 pl-1">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-brand-400/80" />
              <span className="min-w-0 break-words">{line.replace(/^\s*[-*]\s/, "")}</span>
            </div>
          );
        }
        if (/^\s*\d+[.、)]\s/.test(line)) {
          const match = line.match(/^\s*(\d+)[.、)]\s(.*)$/);
          const order = match?.[1] ?? "";
          const rest = match?.[2] ?? "";
          return (
            <div key={index} className="flex gap-2 pl-1">
              <span className="shrink-0 font-mono text-[11px] text-brand-400">{order}.</span>
              <span className="min-w-0 break-words">{rest}</span>
            </div>
          );
        }
        if (/^\s*\|/.test(line)) {
          return (
            <pre key={index} className="overflow-x-auto font-mono text-[11.5px] text-slate-400">
              {line}
            </pre>
          );
        }
        if (/^-{3,}$/.test(line.trim())) {
          return <hr key={index} className="my-2 border-white/[0.08]" />;
        }

        // 把 **加粗** 渲染出来
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={index} className="break-words">
            {parts.map((part, partIndex) =>
              part.startsWith("**") && part.endsWith("**") ? (
                <strong key={partIndex} className="font-semibold text-slate-100">
                  {part.slice(2, -2)}
                </strong>
              ) : (
                <span key={partIndex}>{part}</span>
              ),
            )}
          </p>
        );
      })}
    </div>
  );
});
