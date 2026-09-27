"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  FolderPlus,
  LogOut,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { Button, Spinner } from "@/components/ui/button";
import { Input, Badge, EmptyState } from "@/components/ui/primitives";
import {
  createProject,
  deleteProject,
  getRuntimeConfig,
  listProjects,
} from "@/lib/api";
import { signOut } from "@/lib/supabase";
import { useSession } from "@/lib/use-session";
import type { Project, RuntimeConfig } from "@/lib/types";
import { STATUS_META, cn, errorMessage, formatRelative } from "@/lib/utils";

const SAMPLE_IDEAS = [
  "做一个待办清单，支持增删改查、优先级和本地保存",
  "做一个记账小工具，能记收支、看分类占比和月度总计",
  "做一个番茄钟，可自定义时长并记录每天完成的番茄数",
];

/** 从一句需求里抠出一个简短的项目名，避免用户被"项目名必填"卡住。 */
function ideaToName(idea: string): string {
  const core = idea.replace(/^做一[个张]/, "").split(/[，,。.；;：:、]/)[0].trim();
  return core.slice(0, 20);
}

export default function HomePage() {
  const router = useRouter();
  const { session, loading: sessionLoading, anonymous } = useSession();

  const [projects, setProjects] = useState<Project[]>([]);
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [showForm, setShowForm] = useState(false);

  // 未登录（且不是免登录模式）时跳转登录页
  useEffect(() => {
    if (!anonymous && !sessionLoading && !session) router.replace("/login");
  }, [anonymous, sessionLoading, session, router]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProjects(await listProjects());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading) return;
    if (!anonymous && !session) return;
    void getRuntimeConfig().then(setConfig).catch(() => undefined);
    void refresh();
  }, [refresh, session, sessionLoading, anonymous]);

  async function handleCreate() {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setName("");
      setDescription("");
      setShowForm(false);
      router.push(`/workspace/${project.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(project: Project) {
    if (!window.confirm(`确认删除「${project.name}」？该项目的所有版本与发布记录都会一并删除。`)) return;
    try {
      await deleteProject(project.id);
      setProjects((prev) => prev.filter((item) => item.id !== project.id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const stats = useMemo(() => {
    const ready = projects.filter((p) => p.status === "ready").length;
    const versions = projects.reduce((sum, p) => sum + (p.version_count ?? 0), 0);
    return { total: projects.length, ready, versions };
  }, [projects]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-12">
      {/* 顶部 */}
      <header className="mb-10 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-violet-500 shadow-lg">
            <Boxes className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Atoms Demo</h1>
            <p className="text-xs text-slate-500">多智能体接力 · 网页应用生成器</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {anonymous ? (
            <Badge className="bg-amber-500/15 text-amber-200 ring-amber-400/30">本地免登录模式</Badge>
          ) : (
            <span className="hidden text-xs text-slate-400 sm:inline">{session?.user.email}</span>
          )}
          {!anonymous ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await signOut();
                router.replace("/login");
              }}
            >
              <LogOut className="h-3.5 w-3.5" />
              退出
            </Button>
          ) : null}
        </div>
      </header>

      {/* Hero */}
      <section className="surface relative mb-8 overflow-hidden p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="relative">
          <Badge className="mb-3 bg-brand-500/15 text-brand-200 ring-brand-400/30">
            <Sparkles className="h-3 w-3" />
            {config
              ? `${config.llm_provider} · ${config.llm_model}${
                  config.storage_backend === "sqlite" ? " · 本地 SQLite" : ""
                }`
              : "LangChain 多智能体编排"}
          </Badge>
          <h2 className="max-w-2xl text-2xl font-semibold leading-snug text-slate-50 sm:text-3xl">
            一句话需求，三位 Agent 接力，
            <br className="hidden sm:block" />
            直接交付一个可运行的网页应用。
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400">
            🧑‍💼 产品经理拆需求 → 🏗️ 架构师出方案 → 👨‍💻 工程师写代码。
            全过程 SSE 实时可见，产物存进 Supabase，iframe 即时预览，一键发布成公开链接。
            {config?.qa_stage_enabled ? " 另外还接了 🧪 测试工程师做验收评审。" : ""}
          </p>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={() => setShowForm(true)}>
              <Plus className="h-4 w-4" />
              新建项目
            </Button>
            <Button size="lg" variant="outline" onClick={refresh} loading={loading}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新列表
            </Button>
          </div>

          <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
            <span>
              项目 <span className="font-semibold text-slate-300">{stats.total}</span>
            </span>
            <span>
              已生成 <span className="font-semibold text-slate-300">{stats.ready}</span>
            </span>
            <span>
              历史版本 <span className="font-semibold text-slate-300">{stats.versions}</span>
            </span>
            {config ? (
              <>
                <span>
                  编排模式 <span className="font-semibold text-slate-300">{config.agent_mode}</span>
                </span>
                <span>
                  存储 <span className="font-semibold text-slate-300">
                    {config.storage_backend === "sqlite" ? "本地 SQLite" : "Supabase"}
                  </span>
                </span>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {/* 新建表单 */}
      {showForm ? (
        <section className="surface mb-8 animate-fade-in p-5">
          <div className="mb-4 flex items-center gap-2">
            <FolderPlus className="h-4 w-4 text-brand-400" />
            <h3 className="text-sm font-semibold text-slate-100">新建项目</h3>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">项目名称</label>
              <Input
                autoFocus
                value={name}
                maxLength={120}
                placeholder="例如：极简待办清单"
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void handleCreate();
                }}
              />
            </div>
            <div>
              <label className="label">一句话描述（可选）</label>
              <Input
                value={description}
                maxLength={500}
                placeholder="例如：给自己用的轻量任务管理"
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
          </div>

          <div className="mt-4">
            <label className="label">灵感不够？点一个试试</label>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_IDEAS.map((idea) => (
                <button
                  key={idea}
                  type="button"
                  onClick={() => {
                    setDescription(idea);
                    // 项目名还是空的话顺手补一个，否则按钮会一直灰着
                    if (!name.trim()) setName(ideaToName(idea));
                  }}
                  className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] text-slate-400 transition hover:border-brand-400/40 hover:text-slate-200"
                >
                  {idea}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            {!name.trim() ? (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-300">
                <AlertTriangle className="h-3.5 w-3.5" />
                请先填写项目名称，按钮才可以点
              </span>
            ) : null}

            <div className="ml-auto flex gap-2">
              <Button variant="ghost" onClick={() => setShowForm(false)}>
                取消
              </Button>
              <Button
                onClick={handleCreate}
                loading={creating}
                disabled={!name.trim()}
                title={name.trim() ? undefined : "项目名称是必填项"}
              >
                <Zap className="h-4 w-4" />
                创建并进入工作台
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {config?.storage_backend === "sqlite" ? (
        <p className="mb-6 rounded-xl border border-sky-500/25 bg-sky-500/[0.07] px-4 py-3 text-xs leading-relaxed text-sky-200">
          当前用<strong>本地 SQLite</strong> 存储（还没接 Supabase），数据落在{" "}
          <code className="font-mono">backend/data/atoms.db</code>，
          生成 / 预览 / 版本 / 发布全部功能可用。接好 Supabase 后把后端{" "}
          <code className="font-mono">.env</code> 的 <code className="font-mono">STORAGE_BACKEND</code>{" "}
          设回 <code className="font-mono">auto</code> 就切回云端。
        </p>
      ) : null}

      {error ? (
        <p className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/[0.08] px-4 py-3 text-xs text-rose-200">
          {error}
        </p>
      ) : null}

      {/* 项目列表 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">我的项目</h3>
          {loading ? <Spinner className="h-3.5 w-3.5 text-slate-500" /> : null}
        </div>

        {!loading && !projects.length ? (
          <EmptyState
            icon={<Sparkles className="h-5 w-5" />}
            title="还没有项目"
            desc="新建一个项目，输入「做一个记账小工具」这样的需求，看看三位 Agent 怎么把它变成能跑的页面。"
            action={
              <Button size="sm" className="mt-2" onClick={() => setShowForm(true)}>
                <Plus className="h-3.5 w-3.5" />
                新建项目
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => {
              const meta = STATUS_META[project.status] ?? STATUS_META.draft;
              return (
                <div
                  key={project.id}
                  className="surface surface-hover group flex flex-col p-5 animate-fade-in"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <h4 className="min-w-0 break-words text-sm font-semibold text-slate-100">
                      {project.name}
                    </h4>
                    <Badge className={cn("shrink-0", meta.className)}>{meta.label}</Badge>
                  </div>

                  <p className="mb-4 line-clamp-2 min-h-[2.5rem] break-words text-xs leading-relaxed text-slate-400">
                    {project.description || "暂无描述"}
                  </p>

                  <div className="mb-4 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                    <span>
                      {project.latest_version_no ? `最新 v${project.latest_version_no}` : "无版本"}
                    </span>
                    <span>{project.version_count ?? 0} 个版本</span>
                    <span>{formatRelative(project.updated_at)}</span>
                  </div>

                  <div className="mt-auto flex items-center justify-between">
                    <Link
                      href={`/workspace/${project.id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-brand-300 transition hover:text-brand-200"
                    >
                      打开工作台
                      <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                    </Link>
                    <Button
                      size="icon"
                      variant="ghost"
                      title="删除项目"
                      onClick={() => handleDelete(project)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
