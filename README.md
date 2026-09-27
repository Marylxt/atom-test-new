# Atoms Demo · 多智能体 AI 应用生成器

> 输入一句自然语言需求，**🧑‍💼 产品经理 → 🏗️ 架构师 → 👨‍💻 工程师** 三位 Agent 接力，
> 直接产出一个可运行的网页应用：SSE 实时进度、iframe 即时预览、Supabase 版本持久化、一键发布公开链接。

技术栈：**FastAPI + Next.js 14 + Supabase + LangChain**，前端 Vercel 部署、后端 Railway 部署。

> 📄 想先看「为什么这么设计、做到哪了、下一步该做什么」，直接读
> **[docs/实现说明.md](docs/实现说明.md)**（实现思路与关键取舍 / 完成度自查 / 扩展优先级）。
> 本文档偏技术细节与操作步骤。

---

## 一、整体架构

```
                          浏览器
                             │
        ┌────────────────────▼────────────────────┐
        │            前端 (Next.js 14)             │
        │  登录页 │ 项目列表 │ 工作台 │ 预览 │ 代码  │
        └────────────────────┬────────────────────┘
                             │ REST API / SSE
        ┌────────────────────▼────────────────────┐
        │             后端 (FastAPI)               │
        │  认证模块 │ 项目模块 │ Agent 编排 │ 发布  │
        └───┬─────────────────┬───────────────┬───┘
            │                 │               │
      ┌─────▼─────┐    ┌──────▼──────┐  ┌─────▼─────┐
      │ Supabase  │    │  LLM API    │  │  沙箱环境  │
      │PostgreSQL │    │DeepSeek/    │  │ (iframe   │
      │ + Auth    │    │ Ollama      │  │  sandbox) │
      └───────────┘    └─────────────┘  └───────────┘
```

### 技术栈明细

| 层级 | 技术选型 | 理由 |
| --- | --- | --- |
| 前端框架 | Next.js 14（App Router） | 支持 SSR、部署简单 |
| UI | Tailwind CSS 3 + 手写 shadcn 风格组件 | 快速搭出美观界面，无额外依赖 |
| 后端框架 | FastAPI（Python） | 异步支持好，与 LangChain 生态无缝集成 |
| 数据库 | Supabase（PostgreSQL + Auth） | 认证 / 数据库 / 存储一体化 |
| LLM 调用 | DeepSeek API / Ollama | 性价比高，也支持本地部署 |
| Agent 框架 | LangChain（LCEL + `@tool` + `create_agent`） | 多工具调用、多步任务编排 |
| 实时进度 | SSE（`text/event-stream`） | 单向推送、实现简单、可穿透代理 |
| 代码渲染 | iframe `srcdoc` + sandbox | 与宿主页面完全隔离 |
| 部署 | Vercel（前端）+ Railway（后端） | 免费额度充足，一键部署 |

---

## 二、目录结构

```
atom-test-new/
├── supabase/
│   └── schema.sql              # 数据模型 + RLS 策略 + 触发器（在 Supabase SQL Editor 执行）
├── backend/                    # FastAPI + LangChain
│   ├── app/
│   │   ├── main.py             # 应用入口、CORS、/health、/api/config
│   │   ├── config.py           # pydantic-settings 配置
│   │   ├── db.py               # Supabase 客户端（service_role）+ 异步执行封装
│   │   ├── deps.py             # JWT 校验依赖（HS256 / JWKS 双通道）
│   │   ├── repository.py       # 数据访问门面：按 STORAGE_BACKEND 分发
│   │   ├── storage/
│   │   │   ├── supabase_store.py     # Supabase（PostgreSQL）实现
│   │   │   └── sqlite_store.py       # 本地 SQLite 实现（离线演示）
│   │   ├── schemas.py          # 请求 / 响应模型
│   │   ├── llm.py              # DeepSeek / Ollama 统一工厂
│   │   ├── sse.py              # SSE 编码工具
│   │   ├── agents/
│   │   │   ├── prompts.py             # 4 位 Agent 的 System Prompt + HTML 抽取
│   │   │   ├── agent_orchestrator.py  # ★ 多智能体接力引擎（核心）
│   │   │   └── tools.py               # LangChain @tool 工具层 + create_agent
│   │   └── routers/
│   │       ├── projects.py     # 项目 / 版本 / 回滚 / 过程日志
│   │       ├── generation.py   # 生成 / 修改 / 评审（含 SSE）
│   │       ├── publish.py      # 发布分享
│   │       └── public.py       # 免登录公开访问
│   ├── requirements.txt
│   ├── Dockerfile / Procfile / railway.json
│   └── run.py                  # 本地启动：python run.py
└── frontend/                   # Next.js 14
    └── src/
        ├── app/
        │   ├── page.tsx                    # 项目列表
        │   ├── login/page.tsx              # Supabase Auth 登录
        │   ├── workspace/[projectId]/page.tsx   # ★ 工作台
        │   └── app/[publicId]/page.tsx     # 公开访问页
        ├── components/                     # 预览 / 代码 / 进度 / 版本 / 发布弹窗
        └── lib/                            # API 客户端、SSE 解析、类型、工具
```

---

## 三、数据模型（Supabase）

执行 `supabase/schema.sql` 后得到 5 张表 + 1 个视图：

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `profiles` | 用户档案（= `auth.users.id`） | `id`、`email`、`display_name` |
| `projects` | 项目 | `user_id`、`name`、`status`、`current_version_id` |
| `versions` | **版本快照**（每次生成/修改/回滚一条） | `version_no`、`prompt`、`product_spec`、`architecture`、`html_code`、`change_type`、`parent_version_id` |
| `publications` | 发布记录 | `public_id`（短链）、`version_id`、`views`、`is_active` |
| `generation_events` | 生成过程日志 | `stage`（pm/architect/engineer/qa）、`message`、`level` |

设计要点：

1. **版本不可变**：回滚不是删数据，而是把历史版本的代码复制成一个**新版本**（`change_type=rollback`），
   `parent_version_id` 串成链，任何一次操作都可追溯。
2. **产物与过程分离**：`versions` 存最终代码，`generation_events` 存过程日志，方便复盘"哪个 Agent 拖慢了流水线"。
3. **RLS 全开**：后端用 `service_role_key` 绕过 RLS；同时给前端直连留了策略，即使有人拿到 anon key 也读不到别人的项目。
4. `project_overview` 视图把版本数 / 最新版本号聚合好，SQL 层直接可查。

---

## 四、核心功能实现

### 1. 用户认证（Supabase Auth）

前端用 `@supabase/supabase-js` 完成注册 / 登录，session（含 JWT）由 supabase-js 持久化到 localStorage；
每次请求把它塞进 `Authorization: Bearer <jwt>`。后端 `deps.py` 双通道校验：

- 非对称签名（ES256 / RS256）→ 走 JWKS；
- 对称签名（HS256）→ 用 `SUPABASE_JWT_SECRET` 校验。

```python
async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    token = authorization[7:].strip()          # Bearer xxx
    payload = _decode_token(token)
    return payload["sub"]                       # user_id
```

### 2. 多智能体生成引擎（核心）

`backend/app/agents/agent_orchestrator.py`：三位 Agent 接力，每一轮把上一轮的**完整产出**作为下一轮的输入。

```
用户需求 ──▶ 🧑‍💼 产品经理 ──▶ 产品规格 ──▶ 🏗️ 架构师 ──▶ 技术方案 ──▶ 👨‍💻 工程师 ──▶ 完整 HTML
                │                        │                        │
                └──────────── 每一步都通过回调推 SSE 进度 ────────┘
```

三种编排模式（`AGENT_MODE`）：

| 模式 | 说明 |
| --- | --- |
| `chain`（默认） | LCEL 串行接力，用 `llm.astream()` 逐 token 回调，前端能看到"打字机"效果 |
| `tool` | 走 `@tool` 工具层接力（`analyze_requirement` / `design_architecture` / `generate_code`），阶段粒度进度 |
| `agent` | 交给 `langchain.agents.create_agent`，由调度 Agent 自主决定工具调用顺序 |

**产物静态质量门**：工程师产出后立刻跑一次 `html_check.check_html()`（HTML 结构完整性 +
`node --check` 内联 JS 语法）。不合格就把**行号 + 出错源码 + 错误描述**回吐给「工程师（自修）」Agent
再改一轮；仍不合格则带一条 `warning` 正常交付并在前端顶部提示。
这道门是踩坑后加的：AI 写前端最容易犯的是括号/引号不匹配，而浏览器遇到 JS 语法错误会
**丢弃整个 `<script>`** —— 页面看起来完好，交互全死，人肉 Review 极难发现（详见第九节案例）。

工程上做了这些防御：

- **HTML 抽取**：模型爱把代码包在 ```` ```html ```` 里，甚至夹带解释。`extract_html()` 取最长的代码块并截取
  `<!DOCTYPE html>` 到 `</html>`；再用 `looks_like_html()` 粗校验，不合格直接报错重试。
- **Prompt 与模板分离**：提示词里含大量 `{ }`（CSS 代码示例），所以不用 `ChatPromptTemplate` 做变量替换，
  而是直接构造 `SystemMessage` / `HumanMessage`，避免模板解析炸掉。
- **token 合帧**：增量 token 攒够 32 字符才推一帧 SSE，避免一个 20KB 的 HTML 产生上千条事件。

### 3. 多轮修改与版本回滚

`POST /api/modify`（JSON）或 `/api/modify/stream`（SSE）：把**当前 HTML + 修改要求**交给"工程师 Agent"，
要求它只做增量修改、不许顺手重构；产出校验通过后落一条 `change_type=modify` 的新版本。

回滚 = 以历史版本为蓝本生成一个新版本，因此"回滚"本身也可被再次回滚，历史永不丢失。

### 4. 实时预览

```tsx
<iframe
  srcDoc={html}
  sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups"
  title="应用预览"
/>
```

- `allow-scripts`：生成的页面要跑 JS；
- `allow-same-origin`：让生成代码能正常使用 `localStorage` 做数据持久化；
- 支持 桌面 / 平板 / 手机 三种画布宽度切换，以及"在新窗口打开"（用 Blob URL，不泄露鉴权头）。

> ⚠️ 安全提示：`allow-scripts + allow-same-origin` 意味着产物与宿主同源，**仅适合 Demo**。
> 生产环境应把产物托管到独立域名（或 Docker 沙箱服务）后再用 iframe 引用。

### 5. SSE 流式推送生成进度

后端 `POST /api/generate` 返回 `text/event-stream`，事件类型：

| 事件 | 含义 |
| --- | --- |
| `start` / `pipeline_start` | 流水线启动，携带参与本轮的所有 Agent |
| `stage_start` | 某个 Agent 开始工作 |
| `token` | 该 Agent 的增量输出（打字机效果的数据源） |
| `stage_complete` | 该 Agent 完成，附耗时与产出（工程师的 HTML 通过 `complete` 下发，不重复回传） |
| `complete` | 全流程完成，附 `version_id` / `version_no` / `html` |
| `error` | 失败原因（同时把项目状态置为 `failed`） |

前端**没有用原生 `EventSource`**：它只支持 GET，而生成接口必须 POST（要带需求文本和鉴权头）。
所以用 `fetch` + `ReadableStream` 手写解析，见 `frontend/src/lib/api.ts` 的 `streamGenerate()`。
另外后端在响应头里加了 `X-Accel-Buffering: no`，避免反向代理把流攒成一坨再下发。

### 6. 发布分享

```python
@router.post("/publish")
async def publish(payload: PublishRequest, user_id: str = Depends(get_current_user)):
    public_id = secrets.token_urlsafe(9)[:12]
    publication = await repository.create_publication(project["id"], version["id"], title)
    return {**publication, "url": f"{settings.public_base_url}/app/{publication['public_id']}"}
```

公开页 `/app/{public_id}` 不需要登录，直接读 `publications` + `versions` 渲染；每次访问自增 `views`。
发布是"指向某个版本"的，所以旧链接永远指向当时那版代码，不会因为后续修改而变。

### 7. （可选）测试工程师 Agent

设 `ENABLE_QA_STAGE=true` 时，工程师产出后自动加一环 🧪 验收评审（缺陷清单 + 边界用例核对）；
也可以随时点顶部「代码评审」按钮对当前版本单独跑一次（`POST /api/review`）。

### 8. 存储后端双轨：Supabase（默认）/ 本地 SQLite

Demo 的核心之一是 Supabase 持久化，但"必须先注册 Supabase 才能跑"会让人连界面都看不到。
所以数据层做了个门面（`app/repository.py`），底下挂两个**同签名**的实现：

| `STORAGE_BACKEND` | 行为 |
| --- | --- |
| `auto`（默认） | 配了 Supabase 就用 Supabase，没配就自动落到本地 SQLite |
| `supabase` | 强制云端；配置不全时接口返回 503 并给出可执行的提示 |
| `sqlite` | 强制本地，零依赖离线演示 |

路由层完全不感知差异：`storage/supabase_store.py` 走 service_role + PostgREST，
`storage/sqlite_store.py` 走单文件 `data/atoms.db`（开 WAL、写操作加锁串行化，保证并发下版本号不撞车）。
两边的函数签名与返回结构一一对应，所以"接好 Supabase 就把 `STORAGE_BACKEND` 改回 `auto`"这一步不需要改任何业务代码。

### 9. 性能：换模型是最有效的一刀

同一条流水线，只换模型，实测差距在 10 倍以上（都是"产品经理 → 架构师 → 工程师"完整跑完）：

| 模型 | 吞吐 | 一次生成 | 说明 |
| --- | --- | --- | --- |
| 本机 Ollama `qwen2.5:7b` | 6.5 字符/秒 | **8~15 分钟** | 100% CPU 推理（`/api/ps` 的 `size_vram: 0`），独显不可用 |
| 云端 `deepseek-flash` | 388 字符/秒 | **55 秒** | 推荐，性价比最高 |
| 云端 `deepseek-v4-pro` | 17.6 字符/秒 | 3~8 分钟 | 重推理模型，回两个字都要 33 秒，不适合这种"写代码"任务 |

`deepseek-flash` 的一次完整实测（v1，产物 11555 字符 / 295 行，体检通过）：

```
  pm                  2.5s    527 字符   207.3 字符/秒     产品规格
  architect          14.2s   1071 字符    75.2 字符/秒     技术方案
  engineer           30.7s  11915 字符   388.3 字符/秒     完整 HTML
  ─────────────────────────────────────────────────────
  总计 55.0s
```

> ⚠️ **模型名必须先查再填**：`GET {DEEPSEEK_BASE_URL}/models` 返回的才是你账号下真实可用的。
> 2026-09 实测某账号下只有 `deepseek-flash` 与 `deepseek-v4-pro`，**沿用老教程里的 `deepseek-chat` 会直接失败**。

### 9.1 本地 CPU 推理的兜底调优

用本机 Ollama（无独显）实测约 **6.5 字符/秒**，不加约束时单次生成要 15 分钟以上，
瓶颈全在"话痨阶段"：实测产品经理 63s 写 494 字、架构师 161s 写 1698 字，
两轮铺垫比真正写代码还久。为此做了三层约束：

| 手段 | 位置 | 说明 |
| --- | --- | --- |
| 分阶段输出上限 | `AGENTS[key].max_tokens` | 产品经理 700 / 架构师 900 / 测试工程师 1500；工程师用全局 `LLM_MAX_TOKENS`（5000）。CPU 慢时这是最有效的一刀 |
| Prompt 篇幅硬约束 | `agents/prompts.py` | 产品规格 ≤ 300 字、技术方案 ≤ 400 字、产物 HTML ≤ 400 行；明确禁止加设置页 / 主题切换 / 动画特效 |
| 缩小上下文窗口 | `OLLAMA_NUM_CTX` | 默认 16384（qwen2.5:7b 原生 32768），KV cache 减半，CPU 推理更快 |

另外给产物加了一道**截断检测**：如果 HTML 只是被 `num_predict` 截断（有 `<html>` 没有 `</html>`），
会明确提示"撞到输出上限，请调大 `LLM_MAX_TOKENS`"，而不是含糊地说"不是完整 HTML"。

### 9.2 网络：跨国链路的连接成本（比换模型更容易被忽略）

数据库在境外时，瓶颈往往不在 SQL 而在**建连接**。实测（本地 → Supabase 悉尼）：

| 场景 | 延迟 |
| --- | --- |
| 每次新建连接（DNS + TLS 握手） | **2 ~ 17 秒** |
| 复用同一个连接池 | **0.5 秒** |
| DNS 首次解析 | 7 秒（之后被系统缓存，1ms） |

httpx 默认 `keepalive_expiry=5s`，请求间隔一超就断连 → 接口延迟会在 **0.5s 和 14s 之间随机跳**。
所以做了三件事：

1. 注入自定义 `httpx.Client` 延长保活（`SUPABASE_KEEPALIVE=300`）——
   supabase-py 的 `ClientOptions.httpx_client` 支持注入，postgrest 会直接拿它当会话；
2. 后台每 20 秒打一个轻量查询把连接焐住（`SUPABASE_KEEPALIVE_INTERVAL`）：
   链路中间设备空闲数十秒就会断连，光靠客户端保活不够；
3. 读操作重试 3 次，**写操作绝不重试** —— 超时不代表服务端没写成功，重试会写重复数据。
   （实测踩过：请求报超时，但数据其实已经落库了。）

配套还有一条**优雅降级**：生成成功但落库失败时，产物不会被丢掉 —— `_stream_pipeline` 照常下发
带 HTML 的 `complete` 事件，只在 `warning` 字段里报告保存失败，前端顶部显示一条黄色提示。
宁可数据没存上，也不能让用户等了 60 秒却什么都看不到。

> 想体面地演示（30–60 秒一次），把 `LLM_PROVIDER` 换成 `deepseek` 并填 `DEEPSEEK_API_KEY` 即可，
> 流水线与 Prompt 完全不用动。

---

## 五、快速开始

### 0. 前置条件

- Python 3.11+、Node.js 18+
- 一个 LLM：DeepSeek API Key，或本地 [Ollama](https://ollama.com)（`ollama pull qwen2.5:7b`）
- 一个 [Supabase](https://supabase.com) 项目（**可选**）
  没配也能跑：`STORAGE_BACKEND=auto` 会自动回落到本地 SQLite，
  生成 / 预览 / 版本 / 发布全部可用，只是数据落在本机 `backend/data/atoms.db`。
  想看当前用的是哪个后端，`GET /health` 会返回 `storage_backend`。

### 1. 建表（二选一）

**方式 A：一键脚本（推荐）** —— 用一个 Personal Access Token 自动建表 + 取回所有 Key + 写回配置：

```powershell
cd backend
python scripts/provision_supabase.py sbp_你的token     # Token 在 https://supabase.com/dashboard/account/tokens
```

脚本做五件事：校验项目归属 → 执行 `supabase/schema.sql` → 取回 anon / service_role / JWT Secret
→ 写回 `backend/.env` 与 `frontend/.env.local`（只改对应行）→ 用 service_role 真读一次库做最终校验。
输出里所有 Key 都脱敏。Token 用完建议立刻删除。

**方式 B：手工** —— 控制台 → **SQL Editor** → 粘贴 `supabase/schema.sql` 全文 → Run；
再把 URL / anon key / service_role key / JWT Secret 填进 `backend/.env`。

> ⚠️ `schema.sql` 结尾有一段显式 `GRANT`。走 Dashboard 的 SQL Editor 时 Supabase 会自动套用
> 默认权限，但**走 Management API 执行不会** —— 不显式授权会出现
> `42501 permission denied for table projects`（建表成功了，但读不到）。

### 2. 启动后端（端口 8000）

```powershell
cd C:\test\atom-test-new\backend
Copy-Item .env.example .env      # 填入 Supabase 与 LLM 配置
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

- 健康检查：<http://localhost:8000/health>（会返回 Supabase 是否连通）
- 接口文档：<http://localhost:8000/docs>

### 3. 启动前端（端口 3000）

```powershell
cd C:\test\atom-test-new\frontend
Copy-Item .env.local.example .env.local   # 填 API 地址与 Supabase 公钥
npm install
npm run dev
```

打开 <http://localhost:3000> → 注册 / 登录 → 新建项目 → 在工作台输入需求 → 看三位 Agent 接力。

> **不想配 Supabase？** 把前后端的 `AUTH_DISABLED` 都设为 `true`，可以免登录跑起来；
> 但数据仍然需要 Supabase（本 Demo 的核心之一就是持久化），数据库不可用时接口会返回 503 并给出提示。

### 4. 环境变量

`backend/.env`

```ini
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=xxxx
SUPABASE_SERVICE_KEY=xxxx          # service_role，仅后端使用
SUPABASE_JWT_SECRET=xxxx           # Project Settings → API → JWT Settings

LLM_PROVIDER=deepseek              # deepseek | ollama
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

ENABLE_QA_STAGE=false
AGENT_MODE=chain                   # chain | tool | agent
PUBLIC_BASE_URL=http://localhost:3000
AUTH_DISABLED=false
```

`frontend/.env.local`

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=xxxx
NEXT_PUBLIC_AUTH_DISABLED=false
```

---

## 六、部署方案

### 前端 → Vercel

```bash
npm i -g vercel
cd frontend
vercel --prod
```

或直接在 Vercel 导入 Git 仓库，**Root Directory 选 `frontend`**，环境变量填 `frontend/.env.local` 里那三项，
并额外加一个 `NEXT_PUBLIC_API_BASE_URL` 指向 Railway 的后端地址。

### 后端 → Railway

```bash
npm i -g @railway/cli
cd backend
railway login
railway init
railway up
```

Railway 会自动识别 `requirements.txt`，并按 `railway.json` / `Procfile` 启动
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`，健康检查打 `/health`。
把 `backend/.env` 里的变量全部配到 Railway 的 Variables 里即可（也可以用仓库根目录的 `Dockerfile` 方式部署到任意容器平台）。

### 部署后别忘了

| 位置 | 变量 | 值 |
| --- | --- | --- |
| Railway | `PUBLIC_BASE_URL` | Vercel 域名，用于拼公开分享链接 |
| Vercel | `NEXT_PUBLIC_API_BASE_URL` | Railway 后端域名 |
| Railway | `CORS_ORIGINS` | Vercel 域名（逗号分隔） |
| Supabase | Authentication → URL Configuration | Site URL / Redirect URLs 加上 Vercel 域名（魔法链接要用） |

---

## 七、API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查（含 Supabase 连通性） |
| GET | `/api/config` | 运行时配置（模型、编排模式、开关） |
| GET | `/api/me` | 当前登录用户 |
| GET / POST | `/api/projects` | 项目列表 / 新建 |
| GET / PATCH / DELETE | `/api/projects/{id}` | 详情 / 更新 / 删除 |
| GET | `/api/projects/{id}/versions` | 版本列表 |
| GET | `/api/projects/{id}/versions/{vid}` | 版本详情（含 HTML） |
| POST | `/api/projects/{id}/rollback` | 回滚（生成新版本） |
| GET | `/api/projects/{id}/events` | 生成过程日志 |
| POST | `/api/generate` | **多智能体接力生成（SSE）** |
| POST | `/api/modify` | 多轮修改（JSON） |
| POST | `/api/modify/stream` | 多轮修改（SSE） |
| POST | `/api/review` | 测试工程师视角代码评审 |
| POST | `/api/publish` | 发布，返回公开链接 |
| GET / DELETE | `/api/publications` `/api/publications/{id}` | 发布记录 / 下线 |
| GET | `/api/public/{public_id}` | 公开访问（免登录，JSON） |
| GET | `/api/public/{public_id}/raw` | 公开访问（免登录，原始 HTML，可 iframe 直引） |

---

## 八、设计取舍（面试可讲）

1. **为什么用 SSE 而不是 WebSocket？**
   生成进度是单向、一次性、秒级的推送，WebSocket 的双向能力用不上，还要额外处理心跳与重连。
   SSE 走标准 HTTP，天然穿透代理、断线由浏览器重连，Nginx 侧加一行 `X-Accel-Buffering: no` 就能保证不缓冲。
2. **为什么不把 HTML 直接渲染进页面（`dangerouslySetInnerHTML`）？**
   生成代码可能包含 `document.write`、`parent.*` 等越权操作。iframe + sandbox 是浏览器给的硬隔离边界，
   即使产物有恶意代码也只能在自己的小盒子里折腾。
3. **为什么"回滚"要生成新版本，而不是把指针指回旧版本？**
   指针回退会让历史分叉、难以审计。新版本 + `parent_version_id` 让每次操作都是一条只追加的记录，
   配合 `generation_events` 可以完整复盘"谁在什么时候改了哪一版、为什么"。
4. **为什么后端要接 service_role 而不是沿用前端 JWT？**
   前后端职责分离：前端只负责拿 JWT 证明"我是谁"，后端的 service_role 负责"我能做什么"。
   同时 `deps.py` 对 token 做双通道校验（JWKS / HS256），兼容 Supabase 的对称与非对称签名。
5. **这套系统怎么测？**（延续本仓库作者一贯的测试视角）
   - **Agent 产出契约测试**：`extract_html` / `looks_like_html` 对畸形输出的容错，是流水线的第一道质量关；
   - **SSE 协议测试**：断线、超时、模型报错时是否都能落到 `error` 事件而不是静默挂死；
   - **生成产物验收**：用 `ENABLE_QA_STAGE=true` 让测试 Agent 自查空输入、超长输入、空列表、状态不一致等高频缺陷
     （AI 生成的代码最容易踩的正是这些）。

---

## 九、AI 生成代码的真实缺陷案例（验收记录）

下面这些是**实际跑出来的缺陷**，不是假设。记录在此只想说明一件事：
AI 能快速产出"看起来能跑"的页面，而**"看起来正常"和"真的能用"之间，隔着一次验收**。

### 案例 1：一个多余的右括号，让整个应用退化成静态图

| 项 | 内容 |
| --- | --- |
| 产物 | 「番茄小钟」v1，389 行 / 15257 字符，`deepseek-flash` 生成 |
| 现象 | 修改「专注时长」输入框，下方倒计时纹丝不动（仍是 25:00） |
| 第一直觉 | 状态没同步（改了配置没重渲染）—— 但翻代码，`onSettingChange()` 里**明明写了**同步逻辑 |
| 真实根因 | `renderRing()` 第 104 行 `phaseBadge.className = '…' + (isFocus ? 'a' : 'b'));` **多了一个右括号** |
| 影响面 | 浏览器遇 JS 语法错误会**丢弃整个 `<script>`**：事件没绑、`init()` 没跑、localStorage 没写。元素和样式都还在，所以肉眼完全看不出问题 |
| 关键证据 | `focusInput.value` 是**空字符串**（说明 `renderSettings()` 从未执行过），而页面上的 25:00 是 HTML 里写死的 |
| 定位方式 | 把内联脚本抠出来跑 `node --check`，一条命令定位到行号 |
| 修复过程 | 把检查报告当缺陷单提交 `POST /api/modify`，工程师 Agent **19.8s** 修完，产物 15256 字符（只少一个括号，没顺手改别的） |
| 修复后验证 | 输入框初值 25 ✓、改专注 10 → 显示 10:00 ✓、改休息 3 → 副标题同步 ✓、localStorage 三个键 ✓ |

**由此引入的质量门**：`app/agents/html_check.py` 在工程师产出后跑一次静态检查
（结构完整性 + `node --check`），不合格就让 Agent 带着**行号 + 出错源码 + 错误描述**自修一轮；
仍不合格则带 `warning` 交付并在前端顶部提示。这类问题人工 Review 很难发现，工具一跑就现形 ——
这正是"验收"该做的事。（未安装 node 时自动跳过，不阻断主流程。）

## 十、常见问题

| 现象 | 排查 |
| --- | --- |
| 想先不接 Supabase 跑一遍 | 什么都不用配，`auto` 会自动用本地 SQLite；`/health` 的 `storage_backend` 会告诉你当前用的是哪个 |
| 建表了却报 `42501 permission denied` | `schema.sql` 的 `GRANT` 段没执行到，用 Management API 建表时必现（见「快速开始 → 建表」） |
| 接口延迟在 0.5s / 14s 之间跳 | 跨国链路的连接复用问题，见 9.2；确认 `SUPABASE_KEEPALIVE_INTERVAL` 没被设成 0 |
| 换后端后启动就 `AttributeError` | 两个存储实现的接口不一致，跑 `python scripts/check_backends.py` 定位 |
| 生成的页面"看着正常但点了没反应" | 大概率是 JS 语法错误导致整个 `<script>` 被丢弃；流水线的静态检查会先拦一道，也可手工 `node --check` 内联脚本 |
| 想跳过 JS 语法检查 | 环境里没有 node 时会自动跳过；装一个 node 就能启用这道质量门 |
| `/api/*` 返回 503 | 只在 `STORAGE_BACKEND=supabase`（或显式强制云端）且配置不全时出现，检查 `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` |
| 登录后接口仍 401 | `SUPABASE_JWT_SECRET` 与 Supabase 项目不一致；或 token 过期（重新登录） |
| 生成报"不是完整 HTML" | 换更强的模型（如 `deepseek-chat`），或把 `LLM_MAX_TOKENS` 调大 |
| 预览里 `localStorage` 不生效 | iframe 缺少 `allow-same-origin` |
| 前端报"无法连接后端" | `NEXT_PUBLIC_API_BASE_URL` 没配或后端未启动；部署后记得在 Railway 放行 CORS |
| 魔法链接跳回 localhost | Supabase → Authentication → URL Configuration 里补上线上域名 |
