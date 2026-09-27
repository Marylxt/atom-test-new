"use client";

import { History, RotateCcw, Send } from "lucide-react";
import type { Version } from "@/lib/types";
import { Badge } from "./ui/primitives";
import { Button } from "./ui/button";
import { CHANGE_TYPE_META, cn, formatRelative } from "@/lib/utils";

/** 版本历史：查看 / 回滚 / 发布某一版。 */
export function VersionHistory({
  versions,
  activeVersionId,
  busy,
  onSelect,
  onRollback,
  onPublish,
}: {
  versions: Version[];
  activeVersionId: string | null;
  busy: boolean;
  onSelect: (version: Version) => void;
  onRollback: (version: Version) => void;
  onPublish: (version: Version) => void;
}) {
  if (!versions.length) {
    return (
      <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
        <History className="h-4 w-4 text-slate-600" />
        <p className="text-xs text-slate-500">还没有版本，生成成功后会自动记录</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {versions.map((version) => {
        const active = version.id === activeVersionId;
        const meta = CHANGE_TYPE_META[version.change_type] ?? CHANGE_TYPE_META.create;
        return (
          <li
            key={version.id}
            className={cn(
              "group rounded-xl border px-3 py-2.5 transition",
              active
                ? "border-brand-500/45 bg-brand-500/[0.08]"
                : "border-white/[0.07] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-xs font-semibold text-slate-200">
                  v{version.version_no}
                </span>
                <Badge className={meta.className}>{meta.label}</Badge>
                {active ? <Badge className="bg-brand-500/15 text-brand-300 ring-brand-400/30">当前</Badge> : null}
              </div>
              <span className="shrink-0 text-[11px] text-slate-500">
                {formatRelative(version.created_at)}
              </span>
            </div>

            <p className="mt-1.5 line-clamp-2 break-words text-[11px] leading-relaxed text-slate-400">
              {version.prompt || "—"}
            </p>

            <div className="mt-2 flex items-center gap-1 opacity-70 transition group-hover:opacity-100">
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => onSelect(version)}
                title="加载这一版的代码"
              >
                查看
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => onRollback(version)}
                title="以该版本为基础生成新版本"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                回滚
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => onPublish(version)}
                title="发布该版本"
              >
                <Send className="h-3.5 w-3.5" />
                发布
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

