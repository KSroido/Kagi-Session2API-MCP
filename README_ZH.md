# Kagi Session2API MCP Server

基于 Kagi Session Token 的 MCP（Model Context Protocol）服务器，无需官方付费 API 即可使用 Kagi 搜索和摘要功能。

[English](README.md) | **[中文文档](README_ZH.md)**

> **⚠️ 用户警告**：本项目通过 Kagi session token 访问搜索和摘要功能，绕过官方付费 API。这可能违反 [Kagi 服务条款](https://kagi.com/terms)，潜在后果包括账号暂停或永久封禁。**风险自负。** 作者不对 Kagi 采取的任何账号措施承担责任。
>
> **⚠️ 安全警告**：Kagi session token 等同于账号完整权限。请像对待密码一样保管，切勿泄露或提交至版本控制。

## 特性

- **Session 认证**：使用 Kagi session token 替代官方 API（$25/1000 次查询）
- **多 Token 池**：支持配置多个 token，轮询调度提高吞吐量
- **单 Token 限速**：令牌桶算法，5 req/s/token
- **输出兼容**：返回结果格式与官方 `kagimcp` 一致
- **两个工具**：`kagi_search_fetch`（网页搜索）和 `kagi_summarizer`（URL 摘要）
- **UA 伪装**：模拟 Firefox 浏览器进行 session 访问
- **过期 Token 自动禁用**：检测到 401/403 或登录重定向时自动跳过
- **搜索运算符**：支持 Kagi 运算符（`site:`、`lang:`、`filetype:` 等）

## 安装

```bash
pip install kagi-session2api-mcp
```

或使用 `uvx`：
```bash
uvx kagi-session2api-mcp
```

## 配置

### 方式一：环境变量（单 Token）

```json
{
  "mcpServers": {
    "kagi-session": {
      "command": "uvx",
      "args": ["kagi-session2api-mcp"],
      "env": {
        "KAGI_SESSION_TOKEN": "你的SESSION_TOKEN"
      }
    }
  }
}
```

### 方式二：环境变量（多 Token）

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

### 方式三：配置文件（推荐多 Token 场景）

创建 `~/.config/kagi-session2api-mcp/config.toml`：

```toml
[kagi]
session_tokens = [
    "你的TOKEN_1",
    "你的TOKEN_2",
]

summarizer_engine = "cecil"

[client]
timeout = 30
max_retries = 2
```

MCP 配置：
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

## 获取 Session Token

1. 登录 [kagi.com](https://kagi.com)
2. 进入 **Settings → Account → Session Link**
3. 从 session URL 中复制 token：`https://kagi.com/search?token={这里就是TOKEN}&q=test`
4. 将 token 填入配置

## 使用

### MCP 工具

#### `kagi_search_fetch`

使用 Kagi 搜索网页：

```
搜索 "Python async tutorial"
```

支持的搜索运算符：
- `site:github.com` — 限定域名
- `-site:reddit.com` — 排除域名
- `filetype:pdf` — 文件类型过滤
- `intitle:python` — 标题过滤
- `lang:zh` — 语言过滤
- `before:2024-01-01` / `after:2024-01-01` — 日期过滤
- `"exact phrase"` — 精确匹配

#### `kagi_summarizer`

对任意 URL 生成摘要：

```
摘要 https://example.com/article
```

参数：
- `summary_type`：`"summary"`（段落式）或 `"takeaway"`（要点式）
- `engine`：`"cecil"`（默认）、`"agnes"`、`"daphne"`、`"muriel"`
- `target_language`：语言代码（如 `"ZH"`、`"EN"`）

> ⚠️ 摘要功能为实验性——使用的是 Kagi 内部端点，可能随时变更。

### 传输模式

**Stdio**（默认，适用于 Claude Desktop）：
```bash
kagi-session2api-mcp
```

**HTTP**（远程访问）：
```bash
kagi-session2api-mcp --http --host 0.0.0.0 --port 8000
```

## 架构

```
MCP Client → FastMCP Server → TokenPool (轮询) → httpx.AsyncClient → kagi.com
                                ↓
                          TokenBucket (5 req/s/token)
                                ↓
                          过期 Token 自动禁用
```

## Token 池行为

| 配置 | 单 Token 限速 | 总吞吐量 |
|------|-------------|---------|
| 1 token | 5 req/s | 5 req/s |
| 2 tokens | 5 req/s/token | 10 req/s |
| N tokens | 5 req/s/token | 5×N req/s |

当 token 过期（通过 401/403 或登录重定向检测）时，自动禁用该 token，剩余 token 继续服务。

## 与官方 `kagimcp` 的区别

| 方面 | 官方 `kagimcp` | `kagi-session2api-mcp` |
|------|---------------|----------------------|
| 认证方式 | API key（$25/1000次） | Session token（免费） |
| 搜索端点 | `/api/v0/search` | `/html/search`（HTML 解析） |
| 摘要端点 | `/api/v0/summarize` | `/mother/summary_labs`（内部） |
| 限速 | 服务端 | 客户端（令牌桶） |
| `api_balance` | 返回余额 | 始终 `null` |
| 费用 | 付费 | 免费（使用已有 session） |

## 风险

- Kagi 可能变更 HTML 结构，导致解析器失效
- Session 访问可能违反 Kagi 服务条款
- 可能导致账号暂停或永久封禁
- 摘要端点为内部接口，可能无通知变更
- **风险自负。** 作者不对任何后果承担责任，包括但不限于 Kagi 对账号采取的措施。

## 许可证

MIT
