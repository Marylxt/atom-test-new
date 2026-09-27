"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpenText,
  Boxes,
  Code2,
  FlaskConical,
  History,
  Loader2,
  Play,
  Send,
  Sparkles,
  Square,
  Wand2,
} from "lucide-react";
import { AppPreview } from "@/components/app-preview";
import { CodeViewer } from "@/components/code-viewer";
import { MarkdownLite } from "@/components/markdown-lite";
import { ProgressFeed } from "@/components/progress-feed";
import { PublishDialog } from "@/components/publish-dialog";
import { VersionHistory } from "@/components/version-history";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardTitle, Textarea } from "@/components/ui/primitives";
import { Tabs } from "@/components/ui/tabs";
import {
  getProject,
  getRuntimeConfig,
  getVersion,
  listVersions,
  reviewVersion,
  rollbackVersion,
  streamGenerate,
} from "@/lib/api";
import { useSession } from "@/lib/use-session";
import type { PipelineEvent, Project, RuntimeConfig, Version } from "@/lib/types";
import { STATUS_META, cn, errorMessage, formatRelative } from "@/lib/utils";

const EXAMPLE_PROMPTS = [
  "做一个待办清单：可以新增、勾选完成、按优先级排序、删除，数据存 localStorage",
  "做一个个人记账本：记录收支金额与分类，展示本月总收入、总支出、结余和分类占比",
  "做一个番茄钟：25 分钟专注 + 5 分钟休息可自定义，记录今天完成的番茄数量",
  "做一个习惯打卡表：一周七天的打卡格子，可以标记完成，展示连续打卡天数",
];

type TabKey = "preview" | "code" | "specs";

export default function WorkspacePage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const projectId = params.projectId;
  const { session, loading: sessionLoading, anonymous } = useSession();

  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [activeVersion, setActiveVersion] = useState<Version | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [specs, setSpecs] = useState<{
    productSpec: string | null;
    architecture: string | null;
    review: string | null;
  }>({ productSpec: null, architecture: null, review: null });

  const [prompt, setPrompt] = useState("");
  const [modification, setModification] = useState("");
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [outputs, setOutputs] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("preview");
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishTarget, setPublishTarget] = useState<Version | null>(null);
  const [notReady, setNotReady] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  // 未登录拦截
  useEffect(() => {
    if (!anonymous && !sessionLoading && !session) router.replace("/login");
  }, [anonymous, sessionLoading, session, router]);

  // 载入项目与版本
  const load = useCallback(async () => {
    try {
      const [detail, versionList] = await Promise.all([
        getProject(projectId),
        listVersions(projectId),
      ]);
      setProject(detail);
      setVersions(versionList);

      if (detail.current_version_id) {
        const current = await getVersion(projectId, detail.current_version_id);
        applyVersion(current);
      } else if (detail.current_html) {
        setHtml(detail.current_html);
      }
    } catch (err) {
      setError(errorMessage(err));
      setNotReady(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  function applyVersion(version: Version) {
    setActiveVersion(version);
    if (version.html_code) setHtml(version.html_code);
    setSpecs({
      productSpec: version.product_spec ?? null,
      architecture: version.architecture ?? null,
      review: version.review ?? null,
    });
  }

  useEffect(() => {
    if (sessionLoading) return;
    if (!anonymous && !session) return;
    void getRuntimeConfig().then(setConfig).catch(() => undefined);
    void load();
  }, [load, session, sessionLoading, anonymous]);

  const refreshVersions = useCallback(
    async (selectId?: string | null) => {
      const [versionList, detail] = await Promise.all([
        listVersions(projectId),
        getProject(projectId),
      ]);
      setVersions(versionList);
      setProject(detail);
      const targetId = selectId ?? detail.current_version_id;
      if (targetId) applyVersion(await getVersion(projectId, targetId));
    },
    [projectId],
  );

  // -------------------------------------------------------------
  // 生成
  // -------------------------------------------------------------
  async function handleGenerate() {
    const text = prompt.trim();
    if (text.length < 2) {
      setError("需求太短了，把想做的应用说清楚一点");
      return;
    }

    setRunning(true);
    setError(null);
    setWarning(null);
    setEvents([]);
    setOutputs({});
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamGenerate(
        "/api/generate",
        { project_id: projectId, prompt: text },
        (event) => {
          if (event.type === "token") {
            const stage = event.stage ?? "engineer";
            setOutputs((prev) => ({ ...prev, [stage]: (prev[stage] ?? "") + (event.delta ?? "") }));
            return;
          }

          setEvents((prev) => [...prev, event]);

          if (event.type === "stage_complete" && event.content && event.stage) {
            setOutputs((prev) => ({ ...prev, [event.stage as string]: event.content as string }));
          }

          if (event.type === "complete") {
            setHtml(event.html ?? null);
            setSpecs({
              productSpec: event.product_spec ?? null,
              architecture: event.architecture ?? null,
              review: event.review ?? null,
            });
            setWarning(event.warning ?? null);
            setTab("preview");
            void refreshVersions(event.version_id ?? null);
          }

          if (event.type === "error") setError(event.message ?? "生成失败");
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) setError(errorMessage(err));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    setRunning(false);
    setError("已停止生成");
  }

  // -------------------------------------------------------------
  // 多轮修改 / 回滚 / 评审
  // -------------------------------------------------------------
  async function handleModify() {
    const text = modification.trim();
    if (text.length < 2) {
      setError("修改要求太短了");
      return;
    }

    setRunning(true);
    setError(null);
    setWarning(null);
    setEvents([]);
    setOutputs({});
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamGenerate(
        "/api/modify/stream",
        {
          project_id: projectId,
          modification: text,
          version_id: activeVersion?.id ?? undefined,
        },
        (event) => {
          if (event.type === "token") {
            const stage = event.stage ?? "engineer_modify";
            setOutputs((prev) => ({ ...prev, [stage]: (prev[stage] ?? "") + (event.delta ?? "") }));
            return;
          }
          setEvents((prev) => [...prev, event]);
          if (event.type === "complete") {
            setHtml(event.html ?? null);
            setWarning(event.warning ?? null);
            setTab("preview");
            setModification("");
            void refreshVersions(event.version_id ?? null);
          }
          if (event.type === "error") setError(event.message ?? "修改失败");
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) setError(errorMessage(err));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  async function handleSelectVersion(version: Version) {
    setBusy(true);
    setError(null);
    try {
      applyVersion(await getVersion(projectId, version.id));
      setTab("preview");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRollback(version: Version) {
    if (!window.confirm(`确认回滚到 v${version.version_no}？会基于这一版生成一个新的版本。`)) return;
    setBusy(true);
    setError(null);
    try {
      const created = await rollbackVersion(projectId, version.id);
      await refreshVersions(created.id);
      setTab("preview");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleReview() {
    setBusy(true);
    setError(null);
    try {
      const result = await reviewVersion({
        project_id: projectId,
        version_id: activeVersion?.id,
      });
      setSpecs((prev) => ({ ...prev, review: result.review }));
      setTab("specs");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function openExternal() {
    if (!html) return;
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function openPublish(version?: Version) {
    setPublishTarget(version ?? activeVersion ?? versions[0] ?? null);
    setPublishOpen(true);
  }

  const statusMeta = STATUS_META[project?.status ?? "draft"] ?? STATUS_META.draft;

  if (notReady) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-sm text-slate-300">项目加载失败或不存在</p>
        <p className="mt-2 text-xs text-slate-500">{error}</p>
        <Button className="mt-5" variant="secondary" onClick={() => router.push("/")}>
          返回项目列表
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* 顶栏 */}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] bg-ink-900/60 px-3 py-2.5 backdrop-blur sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 text-slate-400 transition hover:text-white"
            title="返回项目列表"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-violet-500">
            <Boxes className="h-4 w-4 text-white" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-semibold text-slate-100">
                {project?.name ?? "加载中…"}
              </h1>
              <Badge className={cn("shrink-0", statusMeta.className)}>{statusMeta.label}</Badge>
            </div>
            <p className="truncate text-[11px] text-slate-500">
              {activeVersion
                ? `当前 v${activeVersion.version_no} · ${formatRelative(activeVersion.created_at)}`
                : "还没有生成版本"}
              {config ? ` · ${config.llm_provider}/${config.llm_model}` : ""}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {config?.qa_stage_enabled ? (
            <Button size="sm" variant="outline" disabled={busy || !html} onClick={handleReview}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
              代码评审
            </Button>
          ) : null}
          <Button size="sm" disabled={!html || running} onClick={() => openPublish()}>
            <Send className="h-3.5 w-3.5" />
            发布
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* 左侧：输入 / 进度 / 历史 */}
        <aside className="flex max-h-[62vh] shrink-0 flex-col gap-3 overflow-y-auto border-b border-white/[0.06] p-3 lg:max-h-none lg:w-[400px] lg:border-b-0 lg:border-r">
          {/* 需求输入 */}
          <Card className="shrink-0 p-4">
            <CardTitle
              title={
                <span className="inline-flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-brand-400" />
                  描述你的应用
                </span>
              }
              desc="三位 Agent 会依次拆解需求、设计方案、写出代码。"
            />
            <Textarea
              rows={4}
              value={prompt}
              maxLength={4000}
              placeholder="例如：做一个待办清单，可以勾选完成、按优先级排序，数据要保存下来"
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void handleGenerate();
              }}
            />

            <div className="mt-2 flex flex-wrap gap-1.5">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  type="button"
                  disabled={running}
                  onClick={() => setPrompt(example)}
                  className="max-w-full truncate rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[11px] text-slate-400 transition hover:border-brand-400/40 hover:text-slate-200 disabled:opacity-50"
                  title={example}
                >
                  {example.slice(0, 18)}…
                </button>
              ))}
            </div>

            <div className="mt-3 flex items-center gap-2">
              <Button className="flex-1" onClick={handleGenerate} loading={running} disabled={running}>
                <Play className="h-4 w-4" />
                开始接力生成
              </Button>
              {running ? (
                <Button variant="danger" onClick={handleStop}>
                  <Square className="h-3.5 w-3.5" />
                  停止
                </Button>
              ) : null}
            </div>
            <p className="mt-2 text-[11px] text-slate-500">Ctrl / ⌘ + Enter 快速提交</p>
          </Card>

          {/* 进度：固定高度，保证三个 Agent 都看得见，内部自己滚 */}
          <Card className="shrink-0 p-4">
            <div className="h-[250px]">
              <ProgressFeed
                events={events}
                outputs={outputs}
                running={running}
                error={error}
              />
            </div>
          </Card>

          {/* 多轮修改 */}
          <Card className="shrink-0 p-4">
            <CardTitle
              title={
                <span className="inline-flex items-center gap-1.5">
                  <Wand2 className="h-3.5 w-3.5 text-violet-300" />
                  继续修改当前版本
                </span>
              }
              desc="只在当前代码上做增量修改，不会重新跑产品与架构环节。"
            />
            <Textarea
              rows={2}
              value={modification}
              maxLength={4000}
              placeholder="例如：把列表项加上完成时间，并支持按时间倒序"
              onChange={(event) => setModification(event.target.value)}
            />
            <Button
              className="mt-2 w-full"
              variant="secondary"
              disabled={running || !html}
              onClick={handleModify}
            >
              <Wand2 className="h-3.5 w-3.5" />
              应用修改
            </Button>
          </Card>

          {/* 版本历史 */}
          <Card className="shrink-0 p-4">
            <CardTitle
              title={
                <span className="inline-flex items-center gap-1.5">
                  <History className="h-3.5 w-3.5 text-slate-400" />
                  版本历史
                  <span className="text-[11px] font-normal text-slate-500">
                    ({versions.length})
                  </span>
                </span>
              }
            />
            <div className="max-h-[320px] overflow-y-auto">
              <VersionHistory
                versions={versions}
                activeVersionId={activeVersion?.id ?? null}
                busy={busy || running}
                onSelect={handleSelectVersion}
                onRollback={handleRollback}
                onPublish={(version) => openPublish(version)}
              />
            </div>
          </Card>
        </aside>

        {/* 右侧：预览 / 代码 / 规格 */}
        <main className="flex min-h-0 flex-1 flex-col">
          {warning ? (
            <div className="flex shrink-0 items-start gap-2 border-b border-amber-500/25 bg-amber-500/[0.08] px-3 py-2 text-[11px] leading-relaxed text-amber-200">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 break-words">{warning}</span>
            </div>
          ) : null}

          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] px-3 py-2">
            <Tabs<TabKey>
              value={tab}
              onChange={setTab}
              items={[
                { value: "preview", label: "实时预览", icon: <Play className="h-3.5 w-3.5" /> },
                { value: "code", label: "代码", icon: <Code2 className="h-3.5 w-3.5" /> },
                { value: "specs", label: "Agent 产出", icon: <BookOpenText className="h-3.5 w-3.5" /> },
              ]}
            />
            {running ? (
              <span className="inline-flex items-center gap-1.5 text-[11px] text-brand-300">
                <Loader2 className="h-3 w-3 animate-spin" />
                正在生成，完成后自动切到预览
              </span>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === "preview" ? (
              <AppPreview html={html} title={project?.name ?? "应用预览"} onOpenExternal={openExternal} />
            ) : tab === "code" ? (
              <CodeViewer code={html} filename={`${project?.name ?? "app"}.html`} />
            ) : (
              <div className="h-full overflow-y-auto px-4 py-4 sm:px-6">
                <div className="mx-auto max-w-3xl space-y-5">
                  <section>
                    <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-100">
                      🧑‍💼 产品经理 · 需求拆解
                    </h3>
                    <div className="surface p-4">
                      <MarkdownLite text={specs.productSpec} />
                    </div>
                  </section>
                  <section>
                    <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-100">
                      🏗️ 架构师 · 技术方案
                    </h3>
                    <div className="surface p-4">
                      <MarkdownLite text={specs.architecture} />
                    </div>
                  </section>
                  {specs.review ? (
                    <section>
                      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-100">
                        🧪 测试工程师 · 验收评审
                      </h3>
                      <div className="surface p-4">
                        <MarkdownLite text={specs.review} />
                      </div>
                    </section>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>

      <PublishDialog
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        projectId={projectId}
        projectName={project?.name ?? "我的应用"}
        versionId={publishTarget?.id ?? null}
        versionNo={publishTarget?.version_no ?? null}
        onPublished={() => void refreshVersions()}
      />
    </div>
  );
}
