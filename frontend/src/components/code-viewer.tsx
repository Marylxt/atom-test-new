"use client";

import { memo, useMemo, useState } from "react";
import { Check, Copy, Download } from "lucide-react";
import { Button } from "./ui/button";
import { copyText, downloadText, formatBytes } from "@/lib/utils";

/** 生成代码查看器：行号 + 复制 + 下载。 */
export const CodeViewer = memo(function CodeViewer({
  code,
  filename = "app.html",
}: {
  code: string | null;
  filename?: string;
}) {
  const [copied, setCopied] = useState(false);

  const lines = useMemo(() => (code ? code.split("\n") : []), [code]);
  const gutterWidth = useMemo(() => String(lines.length).length, [lines.length]);

  async function handleCopy() {
    if (!code) return;
    if (await copyText(code)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }

  if (!code) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        还没有可查看的代码
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="font-mono text-slate-300">{filename}</span>
          <span className="text-slate-600">·</span>
          <span>
            {lines.length} 行 / {formatBytes(code.length)}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={handleCopy}>
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "已复制" : "复制"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => downloadText(filename, code)}>
            <Download className="h-3.5 w-3.5" />
            下载
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, index) => (
              <tr key={index} className="align-top hover:bg-white/[0.03]">
                <td
                  className="select-none border-r border-white/[0.06] px-3 py-0.5 text-right font-mono text-[11px] leading-relaxed text-slate-600"
                  style={{ width: `${gutterWidth + 2.5}ch` }}
                >
                  {index + 1}
                </td>
                <td className="whitespace-pre-wrap break-all px-3 py-0.5 code-block">{line || " "}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});
