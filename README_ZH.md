<div align="center">

# Kagi Session2API MCP Server

**免费 Kagi 搜索 MCP 服务器 — 会话令牌，无需 API Key**

[![PyPI version](https://img.shields.io/pypi/v/kagi-session2api-mcp.svg)](https://pypi.org/project/kagi-session2api-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/kagi-session2api-mcp.svg)](https://pypi.org/project/kagi-session2api-mcp/)
[![GitHub stars](https://img.shields.io/github/stars/KSroido/Kagi-Session2API-MCP?style=social)](https://github.com/KSroido/Kagi-Session2API-MCP/stargazers)
[![GitHub license](https://img.shields.io/github/license/KSroido/Kagi-Session2API-MCP)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://python.org/)

[English](README.md) | **[中文文档](README_ZH.md)**

</div>

---

> 通过会话令牌访问 Kagi 搜索和摘要器 — 完全免费。支持 Claude Desktop、Cursor、Windsurf、Cline、Hermes 及任何兼容 MCP 的 AI 编程助手/Agent。

## ⭐ Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=KSroido/Kagi-Session2API-MCP&type=Date)](https://star-history.com/#KSroido/Kagi-Session2API-MCP&Date)

> **⚠️ 用户警告**：本项目使用 Kagi 会话令牌访问搜索和摘要功能，绕过官方付费 API。这可能违反 [Kagi 服务条款](https://kagi.com/terms)。潜在后果包括账号暂停或永久封禁。**风险自负。** 作者不对 Kagi 采取的任何账号措施承担责任。
>
> **⚠️ 安全警告**：你的 Kagi 会话令牌具有完整账号访问权限。请像密码一样对待。切勿分享或提交到版本控制。

## 🌟 特性

- **基于会话访问**：使用 Kagi 会话令牌替代官方 API（$25/1000次查询）— 完全免费
- **多令牌池**：配置多个令牌实现更高吞吐量，轮询调度
- **每令牌限流**：每令牌5请求/秒，令牌桶算法
- **API 兼容输出**：返回与官方 `kagimcp` 相同格式的结果
- **两个工具**：`kagi_search_fetch`（网页搜索）和 `kagi_summarizer`（URL摘要）
- **Firefox UA 伪装**：模拟真实 Firefox 浏览器
- **自动禁用过期令牌**：过期令牌自动检测并跳过
- **搜索运算符**：支持 Kagi 运算符（`site:`、`lang:`、`filetype:` 等）

## 兼容平台

支持任何兼容 MCP 的客户端：

- [Claude Desktop](https://claude.ai/desktop)
- [Cursor](https://cursor.sh)
- [Windsurf](https://codeium.com/windsurf)
- [Cline](https://cline.bot)
- [Hermes Agent](https://github.com/nousresearch/hermes)
- 任何支持 `stdio` 或 `HTTP` 传输的 MCP 客户端

## 快速安装（AI Agent 专用）

直接粘贴此提示词给你的 AI Agent：

```
Install the Kagi Session2API MCP server from https://pypi.org/project/kagi-session2api-mcp/.
Then add it to my MCP:
`uvx kagi-session2api-mcp`
set env KAGI_SESSION_TOKEN to my token (ask me if you don't have it).
If I have multiple tokens, use KAGI_SESSION_TOKENS (comma-separated) instead,
or create a config file at ~/.config/kagi-session2api-mcp/config.toml with:
[kagi]
session_tokens = ["TOKEN_1", "TOKEN_2"]
summarizer_engine = "cecil"
[client]
timeout = 30
max_retries = 2
and set env KAGI_SESSION_CONFIG to that path.
```

## 手动安装

```bash
pip install kagi-session2api-mcp
```

或使用 `uvx`：
```bash
uvx kagi-session2api-mcp
```

## 配置

### 方式1：环境变量（单令牌）

```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_TOKEN": "YOUR_SESSION_TOKEN_HERE"
      }
    }
  }
}
```

### 方式2：环境变量（多令牌）

```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_TOKENS": "TOKEN_1,TOKEN_2,TOKEN_3"
      }
    }
  }
}
```

### 方式3：配置文件（推荐多令牌使用）

创建 `~/.config/kagi-session2api-mcp/config.toml`：

```toml
[kagi]
session_tokens = [
    "YOUR_TOKEN_1_HERE",
    "YOUR_TOKEN_2_HERE",
]

summarizer_engine = "cecil"

[client]
timeout = 30
max_retries = 2
```

然后配置：
```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_CONFIG": "/path/to/config.toml"
      }
    }
  }
}
```

## 获取会话令牌

1. 登录 [kagi.com](https://kagi.com)
2. 进入 **Settings → Account → Session Link**
3. 从会话 URL 中复制令牌：`https://kagi.com/search?token={这部分}&q=test`
4. 在配置中使用此令牌

## 使用

### MCP 工具

#### `kagi_search_fetch`

使用 Kagi 搜索网页：

```
Search for "Python async tutorial"
```

支持 Kagi 搜索运算符：
- `site:github.com` - 限制域名
- `-site:reddit.com` - 排除域名
- `filetype:pdf` - 文件类型过滤
- `intitle:python` - 标题过滤
- `lang:zh` - 语言过滤
- `before:2024-01-01` / `after:2024-01-01` - 日期过滤
- `"exact phrase"` - 精确匹配

#### `kagi_summarizer`

摘要任意 URL：

```
Summarize https://example.com/article
```

选项：
- `summary_type`："summary"（段落）或 "takeaway"（要点列表）
- `engine`："cecil"（默认）、"agnes"、"daphne"、"muriel"
- `target_language`：语言代码（如 "ZH"）

> ⚠️ 摘要器为实验性功能 — 使用 Kagi 内部端点，可能随时变更。

### 传输模式

**Stdio**（默认，适用于 Claude Desktop）：
```bash
kagi-session2api-mcp
```

**HTTP**（适用于远程访问）：
```bash
kagi-session2api-mcp --http --host 0.0.0.0 --port 8000
```

## 架构

```
MCP客户端 → FastMCP服务器 → TokenPool（轮询）→ httpx.AsyncClient → kagi.com
                              ↓
                        TokenBucket（每令牌5请求/秒）
                              ↓
                        自动禁用过期令牌
```

## 令牌池行为

| 配置 | 限流 | 有效速率 |
|------|------|----------|
| 1 个令牌 | 5 请求/秒 | 5 请求/秒 |
| 2 个令牌 | 各5请求/秒 | 10 请求/秒 |
| N 个令牌 | 各5请求/秒 | 5×N 请求/秒 |

当令牌过期（通过401/403或重定向到登录页检测到）时，自动禁用。剩余令牌继续服务请求。

## 与官方 `kagimcp` 的区别

| 方面 | 官方 `kagimcp` | `kagi-session2api-mcp` |
|------|----------------|------------------------|
| 认证 | API key ($25/1000) | 会话令牌（免费） |
| 搜索端点 | `/api/v0/search` | `/html/search`（HTML解析） |
| 摘要器 | `/api/v0/summarize` | `/mother/summary_labs`（内部） |
| 限流 | 服务端 | 客户端（令牌桶） |
| `api_balance` | 返回余额 | 始终 `null` |
| 费用 | 付费 | 免费（使用现有会话） |

## 风险

- Kagi 可能更改 HTML 结构，导致解析器失效
- 基于会话的访问可能违反 Kagi 服务条款
- 可能导致账号暂停或永久封禁
- 摘要器端点为内部接口，可能随时变更
- **风险自负。** 作者不对任何后果承担责任，包括但不限于 Kagi 采取的账号措施。

## 许可证

MIT
