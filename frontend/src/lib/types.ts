/** 与后端 schemas.py 一一对应的类型定义。 */

export type ProjectStatus = "draft" | "generating" | "ready" | "failed";
export type ChangeType = "create" | "modify" | "rollback";

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  current_version_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  version_count?: number;
  latest_version_no?: number | null;
  current_html?: string | null;
}

export interface Version {
  id: string;
  project_id: string;
  version_no: number;
  prompt: string;
  product_spec?: string | null;
  architecture?: string | null;
  html_code?: string | null;
  review?: string | null;
  change_type: ChangeType;
  parent_version_id?: string | null;
  model?: string | null;
  duration_ms?: number | null;
  created_at?: string | null;
}

export interface Publication {
  id: string;
  project_id: string;
  version_id: string;
  public_id: string;
  title: string | null;
  views: number;
  is_active: boolean;
  created_at: string | null;
  url?: string | null;
}

export interface PublicApp {
  public_id: string;
  title: string | null;
  html: string;
  version_no: number | null;
  published_at: string | null;
  views: number;
}

export interface AgentInfo {
  key: string;
  name: string;
  icon: string;
}

export interface StageInfo {
  stage: string;
  name: string;
  icon: string;
  duration_ms: number;
  chars: number;
}

export interface RuntimeConfig {
  app_name: string;
  version: string;
  llm_provider: string;
  llm_model: string;
  qa_stage_enabled: boolean;
  agent_mode: string;
  /** supabase | sqlite */
  storage_backend: string;
  supabase_ready: boolean;
  auth_disabled: boolean;
  public_base_url: string;
}

/** SSE 事件（后端 sse.py 里的 payload 结构）。 */
export interface PipelineEvent {
  type:
    | "open"
    | "start"
    | "pipeline_start"
    | "stage_start"
    | "token"
    | "stage_complete"
    | "complete"
    | "error";
  stage?: string;
  agent?: string;
  name?: string;
  message?: string;
  delta?: string;
  content?: string;
  duration_ms?: number;
  agents?: AgentInfo[];
  html?: string;
  version_id?: string;
  version_no?: number;
  product_spec?: string | null;
  architecture?: string | null;
  review?: string | null;
  model?: string;
  stages?: StageInfo[];
  prompt?: string;
  mode?: string;
  /** 生成成功但落库失败时的提示（产物仍可用，但刷新会丢） */
  warning?: string | null;
}

export interface ModifyResult {
  html: string;
  version_id: string;
  version_no: number;
  model?: string;
  duration_ms?: number;
}

export interface ReviewResult {
  review: string;
  version_id?: string | null;
  version_no?: number | null;
}
