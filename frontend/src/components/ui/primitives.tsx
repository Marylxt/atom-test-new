"use client";

import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------
// 卡片
// ---------------------------------------------------------------
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("surface p-5", className)}>{children}</div>;
}

export function CardTitle({
  title,
  desc,
  action,
  className,
}: {
  title: ReactNode;
  desc?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-3", className)}>
      <div>
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        {desc ? <p className="mt-1 text-xs leading-relaxed text-slate-400">{desc}</p> : null}
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------
// 徽标
// ---------------------------------------------------------------
export function Badge({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        "bg-white/[0.06] text-slate-300 ring-white/10",
        className,
      )}
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------
// 输入
// ---------------------------------------------------------------
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("field", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn("field resize-none leading-relaxed", className)} {...props} />;
}

export function EmptyState({
  icon,
  title,
  desc,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  desc?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/10 px-6 py-10 text-center",
        className,
      )}
    >
      {icon ? <div className="text-slate-500">{icon}</div> : null}
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {desc ? <p className="max-w-sm text-xs leading-relaxed text-slate-500">{desc}</p> : null}
      {action}
    </div>
  );
}
