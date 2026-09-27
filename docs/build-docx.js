/**
 * 把 docs/实现说明.md 的内容生成 Word 版：docs/实现说明.docx
 *
 * 用法（Windows，docx 是全局安装的）：
 *   $env:NODE_PATH = "$env:APPDATA\npm\node_modules"
 *   node docs/build-docx.js
 *
 * 生成后可用 docx skill 的校验脚本检查：
 *   python <skill>/scripts/office/validate.py docs/实现说明.docx
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, TableOfContents, HeadingLevel,
  PageBreak,
} = require("docx");

// ---------- 版式常量（A4 + 1 英寸页边距）----------
const PAGE_W = 11906;
const PAGE_H = 16838;
const MARGIN = 1440;
const CONTENT_W = PAGE_W - MARGIN * 2; // 9026

const CN_FONT = "微软雅黑";
const MONO = "Consolas";
const ACCENT = "2F5FD0";
const MUTED = "6B7280";

const border = { style: BorderStyle.SINGLE, size: 1, color: "C8CDD8" };
const cellBorders = { top: border, bottom: border, left: border, right: border };

// ---------- 行内格式：**加粗** 与 `代码` ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      out.push(new TextRun({ text: text.slice(last, match.index), ...base }));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      out.push(new TextRun({ text: token.slice(2, -2), ...base, bold: true }));
    } else {
      out.push(new TextRun({ text: token.slice(1, -1), ...base, font: MONO, color: "A03A3A" }));
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out.length ? out : [new TextRun({ text: "", ...base })];
}

// ---------- 段落快捷方法 ----------
const p = (text, opts = {}) =>
  new Paragraph({
    spacing: { before: opts.before ?? 60, after: opts.after ?? 100, line: 320 },
    indent: opts.indent,
    alignment: opts.alignment,
    children: runs(text, opts.run || {}),
  });

// outlineLevel 必须显式写出：目录域与导航窗格依赖它（只靠样式 ID 不够稳）
const h1 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    outlineLevel: 0,
    children: [new TextRun(text)],
  });

const h2 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_2,
    outlineLevel: 1,
    children: [new TextRun(text)],
  });

const bullet = (text) =>
  new Paragraph({
    numbering: { reference: "dots", level: 0 },
    spacing: { before: 40, after: 40, line: 300 },
    children: runs(text),
  });

const numbered = (text) =>
  new Paragraph({
    numbering: { reference: "nums", level: 0 },
    spacing: { before: 60, after: 60, line: 320 },
    children: runs(text),
  });

/** 引用块：左侧竖线 + 缩进 */
const quote = (text) =>
  new Paragraph({
    spacing: { before: 120, after: 140, line: 320 },
    indent: { left: 320 },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 10 } },
    children: runs(text, { size: 20, color: "333333" }),
  });

/** 代码 / 结构图：等宽字体 + 灰底 */
const code = (lines) =>
  lines.map(
    (line, index) =>
      new Paragraph({
        spacing: { before: index === 0 ? 100 : 0, after: index === lines.length - 1 ? 140 : 0, line: 260 },
        indent: { left: 240 },
        shading: { fill: "F4F5F7", type: ShadingType.CLEAR },
        children: [new TextRun({ text: line || " ", font: MONO, size: 17, color: "3C4043" })],
      })
  );

/** 表格：表头浅蓝底，正文白底 */
function table(headers, rows, widths) {
  const sum = widths.reduce((a, b) => a + b, 0);
  if (sum !== CONTENT_W) {
    throw new Error(`列宽合计 ${sum} 必须等于正文宽度 ${CONTENT_W}`);
  }
  const buildCell = (text, width, isHeader) =>
    new TableCell({
      borders: cellBorders,
      width: { size: width, type: WidthType.DXA },
      margins: { top: 70, bottom: 70, left: 110, right: 110 },
      verticalAlign: VerticalAlign.CENTER,
      shading: { fill: isHeader ? "E6EDF9" : "FFFFFF", type: ShadingType.CLEAR },
      children: [
        new Paragraph({
          spacing: { before: 20, after: 20, line: 280 },
          children: runs(text, { size: 19, bold: isHeader }),
        }),
      ],
    });

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((text, i) => buildCell(text, widths[i], true)),
      }),
      ...rows.map(
        (row) =>
          new TableRow({
            children: row.map((text, i) => buildCell(text, widths[i], false)),
          })
      ),
    ],
  });
}

const gap = (after = 160) => new Paragraph({ spacing: { before: 0, after }, children: [] });

// ============================================================
// 正文
// ============================================================
const children = [];

// ---------- 封面标题 ----------
children.push(
  new Paragraph({
    spacing: { before: 0, after: 60 },
    children: [new TextRun({ text: "Atoms Demo · 实现说明", size: 40, bold: true, color: ACCENT })],
  }),
  new Paragraph({
    spacing: { before: 0, after: 40 },
    children: [
      new TextRun({
        text: "多智能体接力生成 · Supabase 持久化 · iframe 实时预览 · 一键发布",
        size: 21,
        color: MUTED,
      }),
    ],
  }),
  new Paragraph({
    spacing: { before: 0, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 6 } },
    children: [
      new TextRun({
        text: "本文回答三个问题：为什么这么设计 · 做到哪了 · 继续投入该做什么",
        size: 19,
        color: MUTED,
      }),
    ],
  }),
  quote(
    "一句话概括：用户输入一句需求，三位 AI Agent 接力产出**可直接运行的单页应用**，全程 SSE 实时可见、iframe 即时预览、Supabase 版本持久化、一键发布成公开链接。"
  ),
  p("技术栈：FastAPI + Next.js 14 + Supabase + LangChain。配套的技术细节与操作步骤见项目 README。", {
    run: { size: 19, color: MUTED },
    after: 200,
  })
);

// ---------- 目录 ----------
children.push(
  new Paragraph({
    spacing: { before: 0, after: 120 },
    children: [new TextRun({ text: "目录", size: 26, bold: true })],
  }),
  new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({
    spacing: { before: 100, after: 240 },
    children: [
      new TextRun({
        text: "（若目录显示为空白，在目录上右键选择「更新域」即可生成）",
        size: 17,
        color: MUTED,
        italics: true,
      }),
    ],
  }),
  new Paragraph({ children: [new PageBreak()] })
);

// ============================================================
// 一、实现思路与关键取舍
// ============================================================
children.push(h1("一、实现思路与关键取舍"));
children.push(
  p(
    "挑的都是真正做过判断的地方：**选了什么、放弃了什么、依据是什么**。取舍的分界线通常只有一个标准——这个 Demo 的核心价值在哪里。"
  )
);

children.push(h2("1. 为什么是「多智能体接力」，而不是一个 Agent 干到底"));
children.push(
  p(
    "单个 Agent 拿一句需求直接写代码，能出结果，但**过程不可控、失败不可归因**。拆成「产品经理 → 架构师 → 工程师」之后："
  ),
  bullet("每一步的输入输出都是**可预期的结构化文本**，能单独测、单独换模型、单独限流；"),
  bullet("出错时能立刻定位是哪一环（需求没拆清？方案不可落地？还是代码写错？）；"),
  bullet("演示时「三位接力」本身就是可讲的故事。"),
  p(
    "代价是**延迟叠加**：实测产品经理 2.5s + 架构师 14.2s + 工程师 30.7s = 全程 55s。但仍然选串行——这三步是严格依赖关系，并行化在业务上不成立。"
  ),
  quote(
    "预留了 `AGENT_MODE=tool / agent` 两种编排模式（走 LangChain 工具层、或交给 `create_agent` 自主编排），默认用 `chain`：只有它能逐 token 回吐进度，前端才有「打字机」体验。"
  )
);

children.push(h2("2. 三个 anti-AI 的工程防御（都是踩坑后加的）"));
children.push(
  p("AI 生成的内容有个特点：**看起来对，跑起来错**。所以不能只靠 Prompt，得靠机制。"),
  table(
    ["防御手段", "解决什么问题", "代价"],
    [
      ["`extract_html()` 稳健抽取", "模型爱把代码包在 ``` 里，还夹带解释文字", "取最长 HTML 代码块 + 截取 DOCTYPE→/html，兜住解析"],
      ["**产物静态质量门**", "一个括号打错 → 浏览器丢弃整个 `<script>` → 页面看着正常、交互全死", "多跑一次 `node --check`；未装 node 时自动跳过"],
      ["不合格自动自修一轮", "静态检查报错后，把行号 + 出错源码回吐给「工程师（自修）」Agent 再改", "多一次 LLM 调用（实测 19.8 秒）"],
    ],
    [2200, 3900, 2926]
  ),
  p(
    "静态门是**踩了真坑才加的**：生成的番茄钟多写了一个右括号，人肉 Review 没看出来，`node --check` 一行命令就定位到行号。详见 README 第九节的缺陷案例。"
  )
);

children.push(h2("3. 产物形态：单文件 HTML，而不是 React 工程"));
children.push(
  table(
    ["选项", "优点", "代价"],
    [
      ["**单文件 HTML（选它）**", "生成即交付、iframe 直接渲染、零构建、易分享", "产物规模受输出 token 上限约束，复杂应用做不了"],
      ["React / Vue 工程", "能力上限高", "要装依赖、要构建、要部署，Demo 闭环从 1 分钟变成 10 分钟"],
    ],
    [2200, 3600, 3226]
  ),
  p(
    "判断依据：这个 Demo 的核心价值是**「需求 → 可运行应用」的闭环速度**。单文件 HTML 能把闭环压到 1 分钟内，这是它不可替代的优势。"
  )
);

children.push(h2("4. 实时预览：iframe + sandbox，而不是直接注入 DOM"));
children.push(
  p(
    "生成代码可能包含 `document.write`、访问 `parent.*` 等越权操作。`iframe srcdoc + sandbox` 是浏览器提供的**硬隔离边界**，产物再野也只能在自己的盒子里折腾。"
  ),
  p(
    "必须开 `allow-same-origin`（产物要用 localStorage 做持久化），这也意味着**产物与宿主同源**——所以这是 Demo 级方案。生产环境应把产物放到独立域名或 Docker 沙箱里再渲染。"
  ),
  quote("这个取舍我明确写进 README 了，不当成「已经安全了」。")
);

children.push(h2("5. 进度推送：SSE，且必须手写解析"));
children.push(
  bullet("**为什么不用 WebSocket**：进度是单向、短时、秒级的推送，双向能力用不上，还要自己管心跳重连。SSE 走标准 HTTP，穿透代理、浏览器自动重连。"),
  bullet("**为什么不用原生 EventSource**：它只支持 GET，而生成接口必须 POST（要带需求文本 + 鉴权头）。所以用 `fetch` + `ReadableStream` 手写帧解析。"),
  bullet("**token 合帧**：增量 token 攒够 32 字符才推一帧。一个 20KB 产物原本会产生上千条事件，合帧后只有几十条——用一点实时性换掉大量无意义的网络往返。")
);

children.push(h2("6. 数据模型：版本只追加不可变，「回滚」是生成新版本"));
children.push(
  ...code([
    "projects ──1:N──> versions ──1:N──> publications",
    "                     │                  └─ public_id 短链，指向具体版本",
    "                     └─ parent_version_id 串成链",
  ]),
  bullet("**回滚不是把指针指回旧版本**，而是以历史版本为蓝本**生成一个新版本**（change_type=rollback）。好处：历史只追加、可审计，且「回滚」本身还能被再回滚。"),
  bullet("**发布指向具体版本**：老链接永远指向当时那版代码，不会因为后续修改而变。"),
  bullet("**产物与过程分离**：versions 存代码，generation_events 存过程日志，方便复盘「哪一环慢、哪一环挂」。")
);

children.push(h2("7. 存储双轨：Supabase 为主，本地 SQLite 兜底"));
children.push(
  p(
    "Demo 的核心之一是 Supabase 持久化，但「必须先注册 Supabase 才能跑」会让评审者连界面都看不到。所以数据层做了个门面（`repository.py`），底下挂两个**同签名实现**：`STORAGE_BACKEND=auto` 时自动判断，配了 Supabase 用云端，没配就落到本地 SQLite。"
  ),
  p(
    "代价是**要维护两套实现**。为此加了 `scripts/check_backends.py` 做**接口契约测试**——自动比对两边的方法是否齐全、是否都是协程、门面调用是否都有实现。"
  ),
  quote(
    "这个脚本是为了修一个真实 bug 才写的：`supabase_store` 漏了 `ping()`，切到 Supabase 后服务启动直接崩。双后端靠人肉对齐是不可靠的。"
  )
);

children.push(h2("8. 认证：后端用 service_role 绕过 RLS"));
children.push(
  p(
    "后端所有数据库操作走 `service_role`，简化了实现（不用把用户 JWT 一路透传到 SQL 层）。同时 RLS 策略**照写不误**，作为「前端万一要直连 Supabase」的安全网。"
  ),
  p(
    "登录态用 Supabase Auth 签发 JWT，后端双通道校验（HS256 用共享密钥 / ES256、RS256 走 JWKS），兼容 Supabase 新旧签名体系。"
  ),
  quote(
    "本地联调留了 `AUTH_DISABLED=true` 免登录模式——演示场景下非常好用，但**不能当成「认证已经跑通」**（见第二节）。"
  )
);

children.push(h2("9. 运维细节：能自动化的绝不让人肉做"));
children.push(
  table(
    ["脚本", "解决什么"],
    [
      ["`scripts/provision_supabase.py`", "一个 Personal Access Token 搞定：建表 → 取回三样 Key → 写回配置 → 真读库校验"],
      ["`scripts/check_backends.py`", "两个存储后端的接口契约测试"],
      ["`scripts/init_db.py`", "有数据库连接串时的手工建表路径"],
      ["`scripts/smoke_llm.py`", "模型通路自检 + 可选的完整流水线冒烟"],
    ],
    [3200, 5826]
  ),
  p(
    "`provision_supabase.py` 顺带解决了一个隐蔽问题：**走 Dashboard 的 SQL Editor 时 Supabase 会自动套用默认权限，走 Management API 就不会**——不显式 GRANT 就会报 42501 permission denied。所以 schema.sql 里补上了显式授权，让两种执行方式结果一致。"
  )
);

children.push(h2("10. 跨区域链路的隐性成本（最容易被忽略的一条）"));
children.push(
  p("数据库在境外时，瓶颈往往不在 SQL 而在**建连接**。实测（本地 → Supabase 悉尼）："),
  table(
    ["场景", "延迟"],
    [
      ["每次新建连接（DNS + TLS 握手）", "**2 ~ 17 秒**"],
      ["复用同一连接池", "**0.5 秒**"],
    ],
    [5200, 3826]
  ),
  p(
    "httpx 默认 `keepalive_expiry=5s`，请求间隔一超就断连，于是接口延迟在 0.5s / 14s 之间随机跳。三招解决：注入自定义 `httpx.Client` 延长保活、后台每 20 秒打一个轻量查询焐住连接、读操作重试 3 次。"
  ),
  quote(
    "**写操作绝不重试**——实测踩过：请求报超时，但数据其实已经落库了，盲目重试会写重复数据。配套还有一条优雅降级：生成成功但落库失败时，产物照常下发（带 warning 字段），前端顶部显示黄色提示。宁可数据没存上，也不能让用户等了 60 秒却什么都看不到。"
  )
);

// ============================================================
// 二、当前完成程度
// ============================================================
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(h1("二、当前完成程度"));
children.push(
  p("分三档陈述，**不藏**：已实测的、只写了没验证的、明确没做的。第二档尤其重要——评审时一被追问就露馅的，通常就是这部分。")
);

children.push(h2("2.1 已做，且经过实测验证"));
children.push(
  table(
    ["能力", "验证方式与实测结果"],
    [
      ["多智能体接力（chain 模式）", "真机跑通，55~67 秒出完整产物（deepseek-flash）"],
      ["SSE 全流程", "14 帧事件序列正确（open → start → pipeline_start → 3×stage_start/token/stage_complete → complete）"],
      ["iframe 实时预览", "番茄钟、习惯打卡表均在 iframe 中渲染并**可交互**（输入、点击、localStorage 均验证）"],
      ["Supabase 持久化", "建项目 → 生成 → 修改 → 回滚 → 发布 → 公开访问 → 删除，**全链路通过**"],
      ["本地 SQLite 回落", "29/29 项断言通过（含版本号倒序、回滚代码一致性、views 自增）"],
      ["版本不可变 + 回滚", "回滚后代码与源版本**逐字符一致**，parent_version_id 链路正确"],
      ["发布 + 公开访问", "短链免登录可读、views 自增、/raw 返回 text/html"],
      ["**产物静态质量门 + 自修**", "真实缺陷（多余右括号）被拦下并自动修复，修复后功能验证通过"],
      ["阶段限流 + 篇幅约束", "架构师输出从 1698 字压到约 1100 字；工程师产物稳定在 300~400 行"],
      ["截断检测", "撞输出上限时给出「调大 LLM_MAX_TOKENS」的可执行建议"],
      ["跨区域连接保活", "接口延迟从 0.5~14s 抖动收敛到稳定 1.3~1.6s"],
      ["一键接入脚本", "建表 + 取回三样 Key + 写回前后端配置 + 最终校验，全自动完成"],
      ["双后端接口契约测试", "check_backends.py 通过"],
      ["前端四个页面", "项目列表、登录页、工作台、公开访问页，均已渲染验证"],
    ],
    [2600, 6426]
  )
);

children.push(h2("2.2 写了但尚未验证（必须如实说明）"));
children.push(
  table(
    ["项", "状态"],
    [
      ["**真实登录链路**", "注册 / 登录 / JWT 校验 / RLS 生效——全程用 AUTH_DISABLED=true 跑的，**真实链路未验**"],
      ["AGENT_MODE=tool / agent", "只验证了 create_agent 能构造成功，**两种模式的完整流程未跑通**"],
      ["QA Agent（测试工程师）", "Prompt 与接口（POST /api/review）都写了，**未实际运行过**"],
      ["部署配置", "Dockerfile / Procfile / railway.json / Vercel 步骤都写了，**未真实部署上线**"],
      ["profiles 表与触发器", "建表脚本里有，但注册流程没跑过，**触发器未触发过**"],
      ["RLS 策略", "策略写了，但后端用 service_role 绕过，**策略本身没被行使过**"],
    ],
    [2800, 6226]
  )
);

children.push(h2("2.3 明确没做"));
children.push(
  table(
    ["缺口", "影响"],
    [
      ["**自动化测试套件 + CI**", "只有 4 个手工自检脚本，没有 pytest、没有 GitHub Actions，**无法防回归**"],
      ["Docker 沙箱执行产物", "目前只有 iframe 软隔离，产物与宿主同源"],
      ["版本 diff 视图", "能回滚，但不能直观对比两版差异"],
      ["移动端适配", "工作台按桌面布局设计，窄屏会挤压"],
      ["分页 / 规模优化", "项目列表会把该项目所有版本拉回来算 count（limit 200），数据量上来是隐患"],
      ["可观测性", "没有耗时、失败率、token 统计的看板，只有日志"],
      ["生成产物缩略图", "列表卡片无预览图"],
      ["多轮修改的成本优化", "每次修改都重发全文 HTML，token 开销随版本单调增长"],
      ["配额 / 限流", "无按用户限流，理论上可被刷爆 API 额度"],
    ],
    [2800, 6226]
  )
);

// ============================================================
// 三、扩展方向与优先级
// ============================================================
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(h1("三、如果继续投入，我会怎么扩展"));
children.push(
  quote(
    "排序依据是「**验证价值 ÷ 成本**」，不是「哪个听起来更酷」。对一个要拿去做演示、评审的项目，**可信度 > 功能量**。"
  )
);

children.push(h2("P0 —— 不做的话项目站不住"));
children.push(
  p("**1）自动化测试套件 + CI（最高优先级）**", { before: 140 }),
  p(
    "理由：现在所有验证都是我手工跑的一次性脚本，**改一行代码就可能悄悄回归**。而这是个「AI 生成代码」的项目，最该展示的恰恰是工程化的质量保障能力。",
    { indent: { left: 240 } }
  ),
  bullet("把 smoke_llm.py / check_backends.py 升级成 pytest 用例；"),
  bullet("**SSE 协议测试**：注入假 LLM，断言事件序列，并覆盖断线、模型报错能否落到 error 事件而非静默挂死；"),
  bullet("**静态门单测**：坏产物 / 好产物 / 截断产物的判定（代码已有，补断言即可）；"),
  bullet("**双后端参数化测试**：同一套 CRUD 断言跑两遍（SQLite / Supabase）；"),
  bullet("GitHub Actions：push 即跑 node --check + pytest + tsc --noEmit + next build。"),
  p("**2）把 QA Agent 变成默认质量门，形成闭环**", { before: 160 }),
  p(
    "理由：现在流水线是「生成 → 静态检查 → 交付」，缺了**语义层的验收**。静态检查只能挡住「跑不起来」，挡不住「逻辑错」。",
    { indent: { left: 240 } }
  ),
  p(
    "做法：ENABLE_QA_STAGE 设为默认，让测试工程师 Agent 输出**结构化缺陷清单**（级别 / 复现步骤 / 期望 vs 实际 / 修复建议），在工作台以面板展示，并支持「一键把缺陷单交给工程师修复」——把我这次手工做的流程（发现缺陷 → 提交 modify → 验证）固化成一键操作。",
    { indent: { left: 240 } }
  ),
  p("**3）产物沙箱加固**", { before: 160 }),
  p(
    "理由：现在产物与宿主同源（allow-same-origin），是我明确标注的 Demo 级妥协。做法：产物托管到独立域名或独立子域，去掉 allow-same-origin；要执行后端代码时再上 Docker 沙箱。做完这条，「安全」才不是一句空话。",
    { indent: { left: 240 } }
  )
);

children.push(h2("P1 —— 显著提升可信度"));
children.push(
  numbered("**真实登录链路跑通并验收**：关掉 AUTH_DISABLED，走完整注册 → 登录 → JWT → RLS，并**验收多用户隔离**——A 用户看不到 B 的项目（这是 RLS 策略第一次真正被行使）。"),
  numbered("**版本 diff 视图**：能回滚但看不到差异，对「多轮迭代」场景是缺失的。有了 diff，「改了什么、有没有改坏」一眼可见——几乎是测试视角的刚需。"),
  numbered("**成本与延迟优化**：DeepSeek 缓存命中输入与未命中价差很大，把 System Prompt 固定在前缀可显著命中缓存；modify 从「重发全文」改成「只发差异 + 输出 patch」；产品经理与架构师两轮可换更小模型（铺垫工作只需格式化文本，实测可省约 30% 时间）。")
);

children.push(h2("P2 —— 锦上添花"));
children.push(
  numbered("**生成产物缩略图**：生成完成后截图存 Storage，列表卡片有预览。"),
  numbered("**可观测性看板**：把各阶段耗时、token 数、失败率落库，做一个简单统计页——既是产品功能，也是「这个系统能被度量」的证据。"),
  numbered("**模板市场**：预置常见应用骨架（待办 / 记账 / 番茄钟），让 LLM 只填业务逻辑不重复造轮子，更快、更稳、更省 token。"),
  numbered("**真正部署上线**：Vercel + Railway 跑通，接真实域名，做一轮线上验收（含 CORS、SSE 在 CDN 后的表现、健康检查）。")
);

children.push(h2("如果只做一件事"));
children.push(
  quote("**把 P0 的 1 和 2 一起做掉**：一套能跑的自动化测试 + 一个默认开启的验收闭环。"),
  p(
    "因为这两个东西合起来，才真正回答了那句最有价值的话：AI 能快速产出「看起来能跑」的页面，而**「看起来正常」和「真的能用」之间，隔着一次验收**。"
  ),
  p(
    "这个项目的意义不在于「能生成代码」（这已经不稀奇了），而在于它把**验证**做成了流水线里的一道自动关卡——这才是测试工程在 AI 时代的落点。"
  )
);

// ============================================================
// 组装文档
// ============================================================
const doc = new Document({
  creator: "Atoms Demo",
  title: "Atoms Demo · 实现说明",
  description: "实现思路与关键取舍 / 完成度自查 / 扩展优先级",
  styles: {
    default: {
      document: { run: { font: CN_FONT, size: 21, color: "1F2328" } },
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 30, bold: true, font: CN_FONT, color: "1A1F2B" },
        paragraph: { spacing: { before: 320, after: 180 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 24, bold: true, font: CN_FONT, color: ACCENT },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "dots",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 480, hanging: 240 } } },
          },
        ],
      },
      {
        reference: "nums",
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: "%1.",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 480, hanging: 300 } } },
          },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "D8DCE4", space: 4 } },
              children: [
                new TextRun({ text: "Atoms Demo · 实现说明", size: 17, color: MUTED }),
              ],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({ text: "第 ", size: 17, color: MUTED }),
                new TextRun({ children: [PageNumber.CURRENT], size: 17, color: MUTED }),
                new TextRun({ text: " 页 / 共 ", size: 17, color: MUTED }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 17, color: MUTED }),
                new TextRun({ text: " 页", size: 17, color: MUTED }),
              ],
            }),
          ],
        }),
      },
      children,
    },
  ],
});

const output = path.join(__dirname, "实现说明.docx");
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(output, buffer);
  console.log("已生成:", output);
  console.log("大小:", (buffer.length / 1024).toFixed(1), "KB");
});
