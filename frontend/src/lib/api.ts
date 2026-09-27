import { getAccessToken } from "./supabase";
import type {
  PipelineEvent,
  Project,
  ProjectStatus,
  Publication,
  PublicApp,
  ReviewResult,
  RuntimeConfig,
  Version,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function buildHeaders(withJsonBody: boolean): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (withJsonBody) headers["Content-Type"] = "application/json";
  const token = await getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail) return JSON.stringify(detail);
  } catch {
    /* 忽略解析失败 */
  }
  return `${response.status} ${response.statusText}`;
}

/** 通用 JSON 请求。 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...(await buildHeaders(init.body !== undefined)), ...(init.headers ?? {}) },
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError(
      `无法连接后端（${API_BASE}），请确认服务已启动或 NEXT_PUBLIC_API_BASE_URL 配置正确`,
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ---------------------------------------------------------------
// 基础
// ---------------------------------------------------------------
export const getRuntimeConfig = () => apiFetch<RuntimeConfig>("/api/config");

// ---------------------------------------------------------------
// 项目
// ---------------------------------------------------------------
export const listProjects = () => apiFetch<Project[]>("/api/projects");

export const createProject = (payload: { name: string; description?: string }) =>
  apiFetch<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) });

export const getProject = (projectId: string) => apiFetch<Project>(`/api/projects/${projectId}`);

export const updateProject = (
  projectId: string,
  payload: { name?: string; description?: string; status?: ProjectStatus },
) =>
  apiFetch<Project>(`/api/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteProject = (projectId: string) =>
  apiFetch<void>(`/api/projects/${projectId}`, { method: "DELETE" });

export const listVersions = (projectId: string) =>
  apiFetch<Version[]>(`/api/projects/${projectId}/versions`);

export const getVersion = (projectId: string, versionId: string) =>
  apiFetch<Version>(`/api/projects/${projectId}/versions/${versionId}`);

export const rollbackVersion = (projectId: string, versionId: string) =>
  apiFetch<Version>(`/api/projects/${projectId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ project_id: projectId, version_id: versionId }),
  });

// ---------------------------------------------------------------
// 发布
// ---------------------------------------------------------------
export const publishProject = (payload: { project_id: string; version_id?: string; title?: string }) =>
  apiFetch<Publication>("/api/publish", { method: "POST", body: JSON.stringify(payload) });

export const listPublications = () => apiFetch<Publication[]>("/api/publications");

export const unpublish = (publicationId: string) =>
  apiFetch<void>(`/api/publications/${publicationId}`, { method: "DELETE" });

export const getPublicApp = (publicId: string) => apiFetch<PublicApp>(`/api/public/${publicId}`);

// ---------------------------------------------------------------
// 生成 / 修改 / 评审
// ---------------------------------------------------------------
export const modifyVersion = (payload: {
  project_id: string;
  modification: string;
  version_id?: string;
}) =>
  apiFetch<{ html: string; version_id: string; version_no: number }>("/api/modify", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const reviewVersion = (payload: { project_id: string; version_id?: string }) =>
  apiFetch<ReviewResult>("/api/review", { method: "POST", body: JSON.stringify(payload) });

/** 解析一帧 SSE 文本。 */
function parseFrame(frame: string): PipelineEvent | null {
  let eventName = "";
  const dataLines: string[] = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;

  try {
    const payload = JSON.parse(dataLines.join("\n")) as PipelineEvent;
    if (!payload.type && eventName) payload.type = eventName as PipelineEvent["type"];
    return payload;
  } catch {
    return null;
  }
}

/**
 * 用 fetch + ReadableStream 消费后端 SSE。
 *
 * 之所以不用原生 EventSource：EventSource 只支持 GET，而生成接口需要 POST 携带
 * 需求文本与鉴权头。
 */
export async function streamGenerate(
  path: "/api/generate" | "/api/modify/stream",
  body: Record<string, unknown>,
  onEvent: (event: PipelineEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: await buildHeaders(true),
      body: JSON.stringify(body),
      signal,
      cache: "no-store",
    });
  } catch (error) {
    if (signal?.aborted) return;
    throw new ApiError(`无法连接后端（${API_BASE}）`, 0);
  }

  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");

      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const event = parseFrame(frame);
        if (event) onEvent(event);
        separator = buffer.indexOf("\n\n");
      }
    }
    const tail = parseFrame(buffer);
    if (tail) onEvent(tail);
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
