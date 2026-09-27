"use client";

import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Link2 } from "lucide-react";
import { Button } from "./ui/button";
import { Dialog } from "./ui/tabs";
import { Input } from "./ui/primitives";
import { publishProject } from "@/lib/api";
import type { Publication } from "@/lib/types";
import { copyText, errorMessage } from "@/lib/utils";

/** 发布弹窗：生成 /app/{public_id} 公开链接。 */
export function PublishDialog({
  open,
  onClose,
  projectId,
  projectName,
  versionId,
  versionNo,
  onPublished,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  projectName: string;
  versionId: string | null;
  versionNo?: number | null;
  onPublished?: (publication: Publication) => void;
}) {
  const [title, setTitle] = useState(projectName);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publication, setPublication] = useState<Publication | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      setTitle(projectName);
      setError(null);
      setPublication(null);
      setCopied(false);
    }
  }, [open, projectName]);

  async function handlePublish() {
    setLoading(true);
    setError(null);
    try {
      const result = await publishProject({
        project_id: projectId,
        version_id: versionId ?? undefined,
        title: title.trim() || projectName,
      });
      setPublication(result);
      onPublished?.(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!publication?.url) return;
    if (await copyText(publication.url)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="发布应用"
      desc={
        versionId
          ? `把当前版本${versionNo ? ` v${versionNo}` : ""} 发布成公开链接，任何人都能访问。`
          : "项目还没有生成过版本，先生成一次再来发布。"
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {publication ? "关闭" : "取消"}
          </Button>
          {!publication ? (
            <Button onClick={handlePublish} loading={loading} disabled={!versionId}>
              <Link2 className="h-4 w-4" />
              生成公开链接
            </Button>
          ) : null}
        </>
      }
    >
      <div className="space-y-3">
        {!publication ? (
          <div>
            <label className="label">分享标题</label>
            <Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} />
          </div>
        ) : (
          <div className="space-y-2">
            <label className="label">公开访问地址</label>
            <div className="flex items-center gap-2">
              <Input value={publication.url ?? ""} readOnly className="font-mono text-xs" />
              <Button size="icon" variant="secondary" onClick={handleCopy} title="复制链接">
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </Button>
              <Button
                size="icon"
                variant="secondary"
                title="新窗口打开"
                onClick={() => publication.url && window.open(publication.url, "_blank")}
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-[11px] text-slate-500">
              短链 ID：<span className="font-mono text-slate-400">{publication.public_id}</span> ·
              页面已渲染 {publication.views} 次
            </p>
          </div>
        )}

        {error ? (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/[0.08] px-3 py-2 text-xs text-rose-200">
            {error}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
