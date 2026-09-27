"""产物静态校验：HTML 结构 + 内联 JavaScript 语法。

为什么需要这道门：
AI 生成的单页应用最致命、也最常见的缺陷不是"逻辑不对"，而是**一个括号打错**。
浏览器遇到 JS 语法错误会直接丢弃整个 `<script>` 标签 —— 页面看起来完全正常
（元素都在、样式都对），但所有交互全失效：事件没绑上、初始化没跑、localStorage 没写。
人肉看代码很难发现（本地实测踩过一次），但跑一次 `node --check` 就能精确定位到行。

没有安装 node 时自动跳过，不影响主流程。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# 匹配成对的 script 标签，带属性
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL)
_MAX_REPORT = 400


def extract_inline_scripts(html: str) -> list[str]:
    """取出所有内联脚本（忽略 src= 引用的外部脚本）。"""
    blocks: list[str] = []
    for attrs, body in _SCRIPT_RE.findall(html):
        if "src=" in attrs.lower():
            continue
        if body.strip():
            blocks.append(body)
    return blocks


def _first_error_line(stderr: str) -> str:
    """从 node 的输出里提炼出「第几行 + 出错源码 + 错误描述」。

    node --check 的输出形如：
        /tmp/xxx/block1.js:104
            (isFocus ? 'a' : 'b'));
                                 ^
        SyntaxError: Unexpected token ')'
    把行号和源码行都带出来，工程师 Agent 才能精准定位。
    """
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "未知语法错误"

    location = lines[0]
    line_no = location.rsplit(":", 1)[-1] if ":" in location else "?"

    for index, line in enumerate(lines):
        if "SyntaxError" not in line:
            continue
        # 源码行在 SyntaxError 之前，中间隔着指向错误位置的 "^" 行
        source = ""
        for offset in range(2, 5):
            if index - offset < 1:
                break
            candidate = lines[index - offset]
            if not candidate.startswith("^"):
                source = candidate
                break
        if source:
            return f"第 {line_no} 行：{source}  ⟵  {line}"
        return f"第 {line_no} 行：{line}"

    return lines[0]


def check_javascript(html: str) -> tuple[bool, str]:
    """检查内联 JS 语法。返回 (是否通过, 说明)。"""
    scripts = extract_inline_scripts(html)
    if not scripts:
        return True, "没有内联脚本，跳过"

    node = shutil.which("node")
    if not node:
        return True, "未安装 node，跳过 JS 语法检查"

    with tempfile.TemporaryDirectory() as tmp:
        for index, code in enumerate(scripts, start=1):
            path = Path(tmp) / f"block{index}.js"
            path.write_text(code, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [node, "--check", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    encoding="utf-8",
                    errors="replace",
                )
            except subprocess.TimeoutExpired:
                return False, f"第 {index} 段脚本语法检查超时"
            except OSError as exc:
                return True, f"无法执行 node（{exc}），跳过检查"

            if proc.returncode != 0:
                detail = _first_error_line(proc.stderr)[:_MAX_REPORT]
                return False, f"第 {index} 段内联脚本存在语法错误：{detail}"

    return True, f"JS 语法通过（{len(scripts)} 段）"


def check_html(html: str) -> tuple[bool, str]:
    """完整校验：结构完整性 + JS 语法。返回 (是否通过, 说明)。"""
    lowered = html.lower()
    for tag, name in (("</html>", "html"), ("</body>", "body")):
        if tag not in lowered:
            return False, f"缺少 {tag}，文件不完整（可能被输出上限截断）"

    if "<script" in lowered and "javascript" not in lowered:
        pass  # 只为可读性留个分支说明，不额外校验

    return check_javascript(html)
