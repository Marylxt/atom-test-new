"use client";

import { useEffect, useMemo, useRef } from "react";
import { AlertTriangle, Check, Loader2, Sparkles } from "lucide-react";
import type { AgentInfo, PipelineEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

type StageStatus = "pending" | "running" | "done";

interface StageView {
  key: string;
  name: string;
  icon: string;
  status: StageStatus;
  durationMs: number | null;
  output: string;
}

const DEFAULT_ROSTER: AgentInfo[] = [
  { key: "pm", name: "产品经理", icon: "🧑‍💼" },
  { key: "architect", name: "架构师", icon: "🏗️" },
  { key: "engineer", name: "工程师", icon: "👨‍💻" },
];

const MAX_PREVIEW_CHARS = 1400;

export function ProgressFeed({
  events,
  outputs,
  running,
  error,
  roster,
}: {
  events: PipelineEvent[];
  outputs: Record<string, string>;
  running: boolean;
  error?: string | null;
  roster?: AgentInfo[];
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const stages = useMemo<StageView[]>(() => {
    const fromEvents =
      events.find((event) => event.type === "pipeline_start")?.agents ??
      events.find((event) => event.type === "start")?.agents;
    const list = fromEvents?.length ? fromEvents : roster?.length ? roster : DEFAULT_ROSTER;

    return list.map((agent) => {
      const started = events.some(
        (event) => event.type === "stage_start" && event.stage === agent.key,
      );
      const finished = [...events]
        .reverse()
        .find((event) => event.type === "stage_complete" && event.stage === agent.key);

      let status: StageStatus = "pending";
      if (finished) status = "done";
      else if (started) status = "running";

      return {
        key: agent.key,
        name: agent.name,
        icon: agent.icon,
        status,
        durationMs: finished?.duration_ms ?? null,
        output: outputs[agent.key] ?? "",
      };
    });
  }, [events, outputs, roster]);

  const activeStage = stages.find((stage) => stage.status === "running");

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [activeStage?.output.length, running]);

  const finishedAll = !running && stages.every((stage) => stage.status === "done");

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
          <Sparkles className="h-3.5 w-3.5 text-brand-400" />
          多智能体接力
        </div>
        {running ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-brand-300">
            <Loader2 className="h-3 w-3 animate-spin" />
            生成中…
          </span>
        ) : finishedAll ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
            <Check className="h-3 w-3" />
            已完成
          </span>
        ) : null}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-0.5">
        {stages.map((stage, index) => (
          <div
            key={stage.key}
            className={cn(
              "rounded-xl border px-3 py-2.5 transition",
              stage.status === "running"
                ? "animate-pulse-ring border-brand-500/40 bg-brand-500/[0.07]"
                : stage.status === "done"
                  ? "border-emerald-500/25 bg-emerald-500/[0.05]"
                  : "border-white/[0.07] bg-white/[0.025]",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-base leading-none">{stage.icon}</span>
                <span
                  className={cn(
                    "text-xs font-medium",
                    stage.status === "pending" ? "text-slate-500" : "text-slate-200",
                  )}
                >
                  {index + 1}. {stage.name}
                </span>
              </div>
              <span className="shrink-0 text-[11px] text-slate-500">
                {stage.status === "running"
                  ? "进行中"
                  : stage.status === "done" && stage.durationMs
                    ? `${(stage.durationMs / 1000).toFixed(1)}s`
                    : "等待中"}
              </span>
            </div>

            {stage.output ? (
              <pre className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-ink-950/70 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-slate-400">
                {stage.output.length > MAX_PREVIEW_CHARS
                  ? `…${stage.output.slice(-MAX_PREVIEW_CHARS)}`
                  : stage.output}
                {stage.status === "running" ? <span className="typing-caret" /> : null}
              </pre>
            ) : null}
          </div>
        ))}

        {error ? (
          <div className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/[0.08] px-3 py-2.5 text-xs text-rose-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="leading-relaxed">{error}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
