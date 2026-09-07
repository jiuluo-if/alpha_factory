# DSH 工具使用守则与约束（DeepSeek Harness）

> 本文档基于本环境真实工具调用错误整理（2026-08-18 会话实证），是 Agent 在本平台工作的硬性纪律。
> 适用范围：本仓库内所有涉及 DSH 工具调用的任务。

---

## 0. 一句话总纲

- **唯一能直接调用的工具是 `run_code`**；其余所有工具（read/write/edit/glob/grep/pwsh/skill/subagent/workflow/…）都必须在 `run_code` 代码体内通过 `await tools.xxx(...)` 调用。
- `run_code` 的代码体是 **async 函数体**：支持顶层 `await` 和 `return`；**禁用 `require`、`import`、`export`**（环境既非 CommonJS 也非 ES Module，直接调用即报错）。
- 工具调用失败会抛出 `ToolCallError`（含 `toolName` 与 `message`），用 `try/catch` 捕获处理，不要假设成功。

---

## 1. 本次会话实证的错误清单（按类别）

### 1.1 直接调用工具（最高频错误）

| 错误原文 | 触发场景 | 原因 | 正确做法 |
|----------|----------|------|----------|
| `unknown tool "read": only run_code is callable directly` | 直接在顶层调用 `read` | 工具只能在 run_code 内调用 | `await tools.read({ file_path: ... })` |
| `unknown tool "write": only run_code is callable directly` | 直接在顶层调用 `write` | 同上 | `await tools.write({ file_path, content })` |
| `unknown tool "glob": only run_code is callable directly` | 直接在顶层调用 `glob` | 同上 | `await tools.glob({ pattern, path })` |
| `unknown tool "grep": only run_code is callable directly` | 直接在顶层调用 `grep` | 同上 | `await tools.grep({ pattern, path, include })` |
| `unknown tool "pwsh": only run_code is callable directly` | 直接在顶层调用 `pwsh` | 同上 | `await tools.pwsh({ command, description, ... })` |
| `unknown tool "skill": only run_code is callable directly` | 直接在顶层调用 `skill` | 同上 | `await tools.skill({ name })` |
| `unknown tool "edit": only run_code is callable directly` | 直接在顶层调用 `edit` | 同上 | `await tools.edit({ file_path, old_string, new_string })` |

**结论**：顶层只能写 `run_code` 一个调用。任何"直接调工具"的尝试都会被拒绝。

### 1.2 run_code 内使用模块系统

| 错误原文 | 触发场景 | 原因 | 正确做法 |
|----------|----------|------|----------|
| `ReferenceError: require is not defined` | 代码体里写 `const fs = require("fs")` | 运行环境不提供 CommonJS `require` | 不要用 require；需要读文件用 `tools.read`，执行命令用 `tools.pwsh` |
| `"import" and "export" cannot be used outside of module code` | 代码体里写 `import ... from "fs"` | 运行环境不是 ES Module | 不要用 import；同上 |

**结论**：run_code 代码体是"纯 async 函数体"，不是 Node 脚本。文件系统访问一律经工具完成，不经 `fs` 模块。

### 1.3 代码语法/字符串构造

| 错误原文 | 触发场景 | 原因 | 正确做法 |
|----------|----------|------|----------|
| `Expected ";", "}" or <eof>` | 在代码体内用反引号模板字符串拼接含 `\n` 或反引号的文档 | 模板字面量与文档内容里的反引号/换行转义冲突，或引号未闭合 | 用普通字符串数组 `lines.push(...)` + `lines.join("\n")` 构造长文本；避免文档内含反引号时用模板字符串 |

**结论**：构造含代码块（反引号）或长文本的内容时，用 `数组 push + join`，不用模板字面量。

### 1.4 文件不存在

| 错误原文 | 触发场景 | 原因 | 正确做法 |
|----------|----------|------|----------|
| `ToolCallError: cannot read "...": not found` | 读取不存在的文件（如 docs/DSH_TOOL_DISCIPLINE.md） | 路径错误或文件未创建 | 先用 `glob` 确认文件存在；读不到就 `write` 创建或 `glob` 找真实路径 |

### 1.5 大文件输出截断

| 现象 | 触发场景 | 处理 |
|------|----------|------|
| `(Omitted NNNNN bytes. Full formatted result stored at: ...)` | 一次 read 大文件（如 experience.json 3600+ 行） | 用 `offset`/`limit` 分页读取；或先用 `grep` 定位再读局部；溢出内容会存 spill 文件，可用 read 读 spill 路径 |

---

## 2. 工具调用总则

1. **入口唯一**：所有工具经 `run_code` 的 `await tools.xxx()` 调用，任何直接调用都是错误。
2. **参数按 schema**：每个工具的参数必须完全符合其定义（如 `read` 要 `file_path`，`pwsh` 要 `command`+`description`）。缺失/多余参数可能导致拒绝。
3. **返回值结构**：工具返回结构化对象而非裸文本——`read` 返回 `{path, offset, lines:[{number,text}], totalLines}`；`glob` 返回 `{root, paths}`；`grep` 返回 `{matches:[{path,lineNumber,line}]}`。需要文本时自行组装：`result.lines.map(l=>l.text).join("\n")`。
4. **失败即异常**：`ToolCallError` 带 `toolName`；捕获后输出 `e.toolName + ": " + e.message` 便于定位。
5. **并行与串行**：相互独立的只读调用可 `Promise.all` 并发；有依赖的必须 `await` 顺序执行。

---

## 3. 各工具快速用法

### 3.1 read（读文件）
- 参数：`file_path`（必填）；`offset`/`limit`（分页，大文件必用）。
- 例：`const r = await tools.read({ file_path: "F:\\codex\\newwqb\.wqb_state\\context.md" });`
- 取全文：`r.lines.map(l => l.text).join("\n")`；总行数：`r.totalLines`。

### 3.2 write（写文件，覆盖式）
- 参数：`file_path` + `content`（UTF-8 全量内容）。
- 例：`await tools.write({ file_path: "...", content: text });`

### 3.3 edit（定向编辑）
- 参数：`file_path` + `old_string` + `new_string`；`replace_all` 可选。
- 注意：默认 `old_string` 必须唯一匹配；多处匹配需加 `replace_all: true` 或写更长的上下文。

### 3.4 glob（按模式找文件）
- 参数：`pattern` + `path`（目录）。
- 注意：pattern 不含 `/` 时按 basename 全树搜索（如 `*.md` 会命中所有子目录）；含 `/` 才限深度。返回 `paths` 数组（含相对路径）。

### 3.5 grep（搜内容）
- 参数：`pattern`（ripgrep 正则）+ `path`；`include` 可过滤文件类型（如 `*.log`）。
- 返回 `matches`（path/lineNumber/line），最多 250 条，超出存 spill。

### 3.6 pwsh（执行 PowerShell）
- 参数：`command`（必填）+ `description`（必填，5-10 词）；`workdir` 指定工作目录；`timeoutMs` 限时。
- 每次调用是全新进程，状态不保留；跨调用传状态靠文件或重读。
- 长任务设 `run_in_background: true`，返回 jobId，用 `job_output` 取结果、`job_kill` 停止。
- 非零退出码记为 `[exit code: N]`；Windows 被杀进程显示 `[exit code: 1]`（视为中断而非失败）。
- 文件操作可能被沙箱拦截，报 `[sandbox: file access denied ...]`——按守则处理，不要换个方式硬闯。

### 3.7 skill（加载技能）
- 参数：`name`（技能名）。返回技能完整内容（含 resourceBase）。

### 3.8 subagent / subagent_fork（委托子代理）
- 参数：`description` + `prompt`；`run_in_background` 默认 true（不阻塞）。
- 后台运行完成会收到通知；前台运行（false）直接返回结果。

### 3.9 workflow / ralph / goal 工具
- 仅当用户明确要求多代理编排 / Ralph 循环 / 长目标时使用；普通单轮任务不要用。

---

## 4. run_code 代码体规范

```
async function main() {
  // 1. 调工具：await tools.xxx(args)
  const r = await tools.read({ file_path: "..." });

  // 2. 处理结果：组装文本 / 提取字段
  const text = r.lines.map(l => l.text).join("\n");

  // 3. 输出：console.log 或 return（只输出需要的部分）
  console.log(text.substring(0, 2000));
  return { totalLines: r.totalLines };
}
main();
```

**禁止**：
- `require(...)` / `import ...` / `export ...`；
- 直接在 run_code 外调用任何工具；
- 用模板字面量拼接含反引号/复杂转义的文档（改用数组 join）；
- 把超大输出（整份日志/整个大文件）打进对话——只回传结论，溢出走 spill。

---

## 5. 本环境要点（WQB 项目相关）

- 本项目文件路径：`F:\\codex\\newwqb`（Windows 反斜杠；JS 字符串里写 `F:\\codex\\newwqb` 或直接单反斜杠均可，工具层按原样解析）。
- 读文件用 `tools.read`（不要用 `cat`/`type`）；找文件用 `tools.glob`（不要用 shell find）；搜内容用 `tools.grep`（不要用 shell grep/rg）。
- 需要真实 BRAIN 模拟 / 网络时，经 `tools.pwsh` 运行 `python main.py ...`；模拟并发上限 3，耐心等待轮询。
- 日志文件（`.wqb_state/run_r*.log`）体量大，用 grep 提取 FAIL/verdicts 关键行，不整读。
- 记忆文件（experience.json）数千行，用 `offset/limit` 或 grep 定位，不整读。

---

## 6. 调试口诀

1. 报 `unknown tool` → 检查是否在 run_code 内用 `await tools.xxx()`。
2. 报 `require is not defined` / `import ... outside of module` → 删除模块语句，改用工具。
3. 报 `Expected ; } <eof>` → 检查字符串引号/模板字面量，改用数组 join。
4. 报 `not found` → 先 `glob` 确认真实路径。
5. 结果被截断（Omitted ...）→ 分页读取或 grep 定位。
6. 工具失败 → `try { ... } catch (e) { console.log(e.toolName, e.message) }` 定位。

---

## 7. 更新记录

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2026-08-18 | 依据本会话真实错误整理：直接调用工具 / require-import / 语法冲突 / 文件不存在 / 大文件截断 |
