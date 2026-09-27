"""请求 / 响应模型（Pydantic v2）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["draft", "generating", "ready", "failed"]
ChangeType = Literal["create", "modify", "rollback"]


# ---------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="项目名称")
    description: str | None = Field(default=None, max_length=500)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    status: ProjectStatus | None = None


class GenerateRequest(BaseModel):
    project_id: str
    prompt: str = Field(min_length=2, max_length=4000, description="自然语言需求")


class ModifyRequest(BaseModel):
    project_id: str
    modification: str = Field(min_length=2, max_length=4000, description="本轮修改要求")
    version_id: str | None = Field(default=None, description="基于哪个版本修改，缺省用当前版本")
    current_html: str | None = Field(default=None, description="直接传入 HTML（调试用）")


class RollbackRequest(BaseModel):
    project_id: str
    version_id: str


class ReviewRequest(BaseModel):
    project_id: str
    version_id: str | None = Field(default=None, description="要评审的版本，缺省用当前版本")
    current_html: str | None = Field(default=None, description="直接传入 HTML（调试用）")


class PublishRequest(BaseModel):
    project_id: str
    version_id: str | None = Field(default=None, description="要发布的版本，缺省用当前版本")
    title: str | None = Field(default=None, max_length=120)


# ---------------------------------------------------------------
# 响应体
# ---------------------------------------------------------------
class ProjectOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    name: str
    description: str | None = None
    status: ProjectStatus = "draft"
    current_version_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    version_count: int = 0
    latest_version_no: int | None = None
    current_html: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    version_no: int
    prompt: str
    product_spec: str | None = None
    architecture: str | None = None
    html_code: str | None = None
    review: str | None = None
    change_type: ChangeType = "create"
    parent_version_id: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    created_at: str | None = None


class PublicationOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    project_id: str
    version_id: str
    public_id: str
    title: str | None = None
    views: int = 0
    is_active: bool = True
    created_at: str | None = None
    url: str | None = None


class MeOut(BaseModel):
    user_id: str
    email: str | None = None
    auth_disabled: bool = False


class RuntimeConfigOut(BaseModel):
    """给前端读的运行时开关。"""

    app_name: str
    version: str
    llm_provider: str
    llm_model: str
    qa_stage_enabled: bool
    agent_mode: str
    storage_backend: str = "supabase"
    supabase_ready: bool
    auth_disabled: bool
    public_base_url: str


class PublicAppOut(BaseModel):
    public_id: str
    title: str | None = None
    html: str
    version_no: int | None = None
    published_at: str | None = None
    views: int = 0
