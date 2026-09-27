import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind 友好的 className 合并工具。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 2026-09-27 14:03 */
export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 相对时间：3 分钟前 */
export function formatRelative(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const diff = Date.now() - date.getTime();
  const minute = 60_000;
  if (diff < minute) return "刚刚";
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`;
  if (diff < 30 * 24 * 60 * minute) return `${Math.floor(diff / (24 * 60 * minute))} 天前`;
  return formatDateTime(value);
}

/** 人类可读的文件大小。 */
export function formatBytes(chars: number): string {
  if (chars < 1024) return `${chars} B`;
  if (chars < 1024 * 1024) return `${(chars / 1024).toFixed(1)} KB`;
  return `${(chars / 1024 / 1024).toFixed(2)} MB`;
}

/** 复制到剪贴板（兼容非 https 环境）。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

/** 下载一段文本为文件。 */
export function downloadText(filename: string, text: string, mime = "text/html;charset=utf-8") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** 从错误对象里抠出可展示的信息（后端 detail / fetch 报错都兼容）。 */
export function errorMessage(error: unknown): string {
  if (!error) return "未知错误";
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** 状态徽标文案与配色。 */
export const STATUS_META: Record<string, { label: string; className: string }> = {
  draft: { label: "待生成", className: "bg-slate-500/15 text-slate-300 ring-slate-400/25" },
  generating: { label: "生成中", className: "bg-amber-500/15 text-amber-300 ring-amber-400/30" },
  ready: { label: "已生成", className: "bg-emerald-500/15 text-emerald-300 ring-emerald-400/30" },
  failed: { label: "生成失败", className: "bg-rose-500/15 text-rose-300 ring-rose-400/30" },
};

export const CHANGE_TYPE_META: Record<string, { label: string; className: string }> = {
  create: { label: "首次生成", className: "bg-brand-500/15 text-brand-300 ring-brand-400/30" },
  modify: { label: "多轮修改", className: "bg-violet-500/15 text-violet-300 ring-violet-400/30" },
  rollback: { label: "版本回滚", className: "bg-amber-500/15 text-amber-300 ring-amber-400/30" },
};
